"""Subprocess primitives for talking to the nexus server.

Plain ``subprocess.run`` wrappers around ``ssh nexus <cmd>`` and
``rsync … nexus:…``. Coexists with :class:`nexus_deploy.ssh.SSHClient`,
which is ALSO subprocess-based (it spawns ``ssh`` per call; see
``ssh.py`` — no paramiko, no persistent connection, no SFTP). The
two modules differ in ergonomics and intent, not transport:
``_remote`` is a thin fire-and-forget pair of free functions used
by the early-phase setup helpers; ``SSHClient`` carries the
orchestrator-side conveniences (``run`` and ``run_script`` with
stdin, ``rsync_to`` for directory pushes, ``port_forward`` for
tunnelled local-to-remote port mappings) that the later phases
need.

Every consumer here uses the system ``ssh`` config alias ``nexus``,
which the spin-up workflow's "Setup SSH config" step writes. That
alias is the ground truth for connection params; the wrappers
themselves don't know about hostnames, ports, or service tokens.

Tests mock ``subprocess.run`` directly — see ``tests/unit/test_remote.py``.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

# No subprocess timeout by default. A slow Hetzner control-plane
# spin-up (creds rotation, first cold start, big rsync diff) can
# legitimately take several minutes; a Python-side cap would convert
# "slow" into a hard failure with TimeoutExpired even though the
# underlying op would have completed. Callers that DO want a cap
# pass `timeout=<seconds>` explicitly.
_DEFAULT_TIMEOUT_S: float | None = None


def ssh_run(
    cmd: str,
    *,
    host: str = "nexus",
    check: bool = True,
    timeout: float | None = _DEFAULT_TIMEOUT_S,
    merge_stderr: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a single command on the nexus server via the local ssh-config alias.

    Equivalent to::

        ssh nexus "<cmd>"        # merge_stderr=True (default)
        ssh nexus "<cmd>" 2>&1   # bash equivalent of the default

    With ``merge_stderr=True`` (default) stderr is folded into stdout
    in the returned ``CompletedProcess`` (the ``ssh nexus "..." 2>&1``
    equivalent). With ``merge_stderr=False``
    stdout and stderr are captured into separate fields on the
    CompletedProcess. Either way the streams are captured (we don't
    let them flow to the local terminal — long stderr tails on a
    failing curl loop would clutter the deploy log; callers that want
    that should print ``result.stderr`` themselves).

    Note: arguments after ``host`` are passed via argv and visible in
    ``ps``. For commands containing secret values, prefer
    :func:`ssh_run_script` which feeds the script over stdin.
    """
    # Don't use `capture_output=True` here: it sets stdout=PIPE+stderr=PIPE
    # internally, and combining it with an explicit `stderr=...` raises
    # ValueError("stderr and capture_output may not both be used"). We
    # need explicit stderr control (STDOUT-merging in the default case)
    # so we set both pipes ourselves.
    return subprocess.run(
        ["ssh", host, cmd],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def ssh_run_script(
    script: str,
    *,
    host: str = "nexus",
    check: bool = True,
    timeout: float | None = _DEFAULT_TIMEOUT_S,
    merge_stderr: bool = True,
    detached: bool = False,
    poll_interval_s: float = 5.0,
    max_unreachable_s: float = 600.0,
    _sleep: Callable[[float], None] = time.sleep,
) -> subprocess.CompletedProcess[str]:
    """Run a bash script on the nexus server via stdin, NOT argv.

    Equivalent to::

        ssh nexus bash -s <<<"<script>"

    Why a separate function from :func:`ssh_run`: when a script
    contains secret values (Infisical tokens, etc.), passing it via
    argv exposes the secret to ``ps``, CI argv-logging, and
    ``CalledProcessError.cmd`` / ``TimeoutExpired.cmd`` exception
    messages. Feeding the script over stdin keeps it out of the
    process command line entirely; only ``["ssh", "nexus", "bash",
    "-s"]`` is visible.

    ``detached=True`` is for scripts that run long enough to outlive an
    SSH session: see :func:`_run_script_detached`. The return value and
    the ``check`` contract are the same either way.
    """
    if detached:
        return _run_script_detached(
            script,
            host=host,
            check=check,
            timeout=timeout,
            merge_stderr=merge_stderr,
            poll_interval_s=poll_interval_s,
            max_unreachable_s=max_unreachable_s,
            sleep=_sleep,
        )
    return subprocess.run(
        ["ssh", host, "bash", "-s"],
        input=script,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Detached scripts
# ---------------------------------------------------------------------------

# ssh's own exit status for "the connection failed", as opposed to the remote
# command's status.
_SSH_TRANSPORT_FAILURE = 255

# Job directories live on tmpfs: a script can carry secret values, and this
# way it never reaches a disk. A reboot clears them, which the poll reports
# as a job that vanished.
_DETACHED_ROOT = "/run/nexus-deploy"

# One poll, fetch or launch is a short command. A cap keeps a hung ssh from
# hanging the pipeline; hitting it counts as "unreachable", like a 255.
_DETACHED_CALL_TIMEOUT_S = 120.0

# What a job that vanished is reported with. Not 255: the transport worked,
# it is the job that is missing.
_DETACHED_VANISHED_STATUS = 1


def _run_script_detached(
    script: str,
    *,
    host: str,
    check: bool,
    timeout: float | None,
    merge_stderr: bool,
    poll_interval_s: float,
    max_unreachable_s: float,
    sleep: Callable[[float], None],
) -> subprocess.CompletedProcess[str]:
    """Run ``script`` on the server so that it survives a dropped SSH session.

    ``ssh host bash -s`` ties the script to the session that started it.
    That session dropped in the field while the server kept working: during
    an image build in compose-up (#972), during the teardown's snapshot
    (#941) and, 75 seconds into a spin-up, during the R2 restore. The
    pipeline saw rc=255 and aborted; the phases after it never ran.

    Here the script is uploaded, started under ``setsid nohup`` with its
    output and exit status going to files in a job directory, and the
    status is polled over short SSH calls. A call that fails with 255 is one
    lost poll, not a failed script. Only a server that stays unreachable for
    ``max_unreachable_s`` in a row ends in a transport error.

    The script still travels on stdin, never in argv. It is checked against
    a SHA-256 before anything starts, because a session that drops during
    the upload ends the remote ``cat`` with a short file and status 0, and a
    truncated script must not run. The job unlinks the script as soon as
    bash has it open.

    ``argv`` in the returned ``CompletedProcess`` and in a raised
    ``CalledProcessError`` is the same ``["ssh", host, "bash", "-s"]`` the
    attached path reports, so nothing a caller logs changes.
    """
    job_dir = f"{_DETACHED_ROOT}/{secrets.token_hex(8)}"
    quoted_dir = shlex.quote(job_dir)
    digest = hashlib.sha256(script.encode()).hexdigest()
    reported_argv = ["ssh", host, "bash", "-s"]
    unreachable_s = 0.0
    elapsed_s = 0.0

    def call(command: str, *, stdin: str | None = None) -> subprocess.CompletedProcess[str] | None:
        """One short SSH call. ``None`` means the server could not be reached."""
        nonlocal unreachable_s, elapsed_s
        try:
            result = subprocess.run(
                ["ssh", host, command],
                input=stdin,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=_DETACHED_CALL_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            result = None
        if result is not None and result.returncode != _SSH_TRANSPORT_FAILURE:
            unreachable_s = 0.0
            return result
        last_output = result.stdout if result is not None else "ssh call timed out"
        if unreachable_s >= max_unreachable_s:
            raise subprocess.CalledProcessError(
                _SSH_TRANSPORT_FAILURE,
                reported_argv,
                output=(
                    f"the server was unreachable for {int(unreachable_s)}s while a detached "
                    f"script ran in {job_dir}; it may still be running there.\n{last_output}"
                ),
            )
        sleep(poll_interval_s)
        unreachable_s += poll_interval_s
        elapsed_s += poll_interval_s
        return None

    def call_until_reached(
        command: str, *, stdin: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        while True:
            result = call(command, stdin=stdin)
            if result is not None:
                return result

    # POSIX sh on purpose: `ssh host "<cmd>"` runs in the account's login
    # shell, which need not be bash (#886). The script itself runs in bash.
    stderr_target = "2>&1" if merge_stderr else f'2> "{job_dir}/err"'
    job = (
        f'd="$1"; mkdir "$d/lock" 2>/dev/null || {{ rm -f "$d/script"; exit 0; }}; '
        f'echo $$ > "$d/pid"; '
        f'( rm -f "$d/script"; exec bash -s ) < "$d/script" > "$d/out" {stderr_target}; '
        f'echo $? > "$d/rc.tmp"; mv "$d/rc.tmp" "$d/rc"'
    )
    launch = (
        ": nexus-detached launch; set -eu; umask 077; "
        f"d={quoted_dir}; "
        f'mkdir -p "$d"; '
        # Already started by an earlier attempt whose session dropped: take
        # the upload off stdin and start nothing a second time.
        f'if [ -e "$d/lock" ]; then cat > /dev/null; exit 0; fi; '
        f'cat > "$d/script"; '
        f'if ! echo "{digest}  $d/script" | sha256sum -c - > /dev/null 2>&1; then '
        f'rm -f "$d/script"; echo "script: upload incomplete, nothing started" >&2; exit 1; fi; '
        f'setsid nohup sh -c {shlex.quote(job)} nexus-detached "$d" '
        f"< /dev/null > /dev/null 2>&1 & "
        # Return only once the job has recorded its pid. Without this the
        # first poll can arrive before the job has written anything, and a
        # job that is merely starting would be reported as gone.
        f'i=0; while [ ! -e "$d/pid" ] && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i + 1)); done'
    )
    poll = (
        ": nexus-detached poll; "
        f"d={quoted_dir}; "
        f'if [ -e "$d/rc" ]; then echo "DONE $(cat "$d/rc")"; '
        f'elif [ -e "$d/pid" ] && kill -0 "$(cat "$d/pid")" 2>/dev/null; then echo RUNNING; '
        # Lock taken, pid not written yet: the job is between its first two commands.
        f'elif [ -e "$d/lock" ] && [ ! -e "$d/pid" ]; then echo RUNNING; '
        # The job can finish between the two checks above.
        f'elif [ -e "$d/rc" ]; then echo "DONE $(cat "$d/rc")"; '
        f"else echo GONE; fi"
    )

    launched = call_until_reached(launch, stdin=script)
    if launched.returncode != 0:
        raise subprocess.CalledProcessError(
            launched.returncode, reported_argv, output=launched.stdout
        )

    def fetch(stream: str) -> str:
        fetched = call_until_reached(f": nexus-detached fetch; cat {quoted_dir}/{stream}")
        return fetched.stdout if fetched.returncode == 0 else ""

    def cleanup() -> None:
        # Best effort and one attempt: the directory holds output only by now,
        # and tmpfs forgets it at the next boot.
        call(f": nexus-detached cleanup; rm -rf {quoted_dir}")

    status: int | None = None
    vanished = False
    while status is None and not vanished:
        if timeout is not None and elapsed_s >= timeout:
            raise subprocess.TimeoutExpired(reported_argv, timeout)
        polled = call(poll)
        if polled is None:
            continue
        answer = polled.stdout.strip().splitlines()[-1] if polled.stdout.strip() else ""
        if answer.startswith("DONE "):
            status = int(answer.removeprefix("DONE ").strip() or _DETACHED_VANISHED_STATUS)
        elif answer == "GONE":
            vanished = True
        else:
            sleep(poll_interval_s)
            elapsed_s += poll_interval_s

    stdout = fetch("out")
    stderr = None if merge_stderr else fetch("err")
    cleanup()

    if vanished:
        raise subprocess.CalledProcessError(
            _DETACHED_VANISHED_STATUS,
            reported_argv,
            output=(
                f"{stdout}the detached script in {job_dir} ended without leaving an exit "
                "status: the server rebooted, or the job was killed. Its work may be incomplete.\n"
            ),
            stderr=stderr,
        )
    if status is None:  # unreachable: the loop ends on a status or on `vanished`
        raise RuntimeError("detached script ended without a status and without being reported gone")
    if check and status != 0:
        raise subprocess.CalledProcessError(status, reported_argv, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(reported_argv, status, stdout=stdout, stderr=stderr)


def push_directory(
    local: Path,
    remote: str,
    *,
    delete: bool = False,
    timeout: float | None = _DEFAULT_TIMEOUT_S,
) -> subprocess.CompletedProcess[str]:
    """Push a local directory's CONTENTS to a path on the nexus server.

    ``remote`` is ``<host>:<path>`` (e.g. ``"nexus:/tmp/infisical-push/"``);
    the alias resolves through the same ssh config as :func:`ssh_run`.

    ``delete=True`` clears destination paths that do not exist locally —
    used when the local dir is the canonical source-of-truth for that
    remote location.

    **Two transports, chosen at call time.** `rsync` when it is on PATH,
    which is every GitHub runner, and `tar` over `ssh` when it is not.
    A Forgejo runner's job image (`node:22-bookworm`) has ssh, scp, tar
    and gzip but no rsync, and Python raises ``FileNotFoundError`` for a
    missing executable — which surfaced as `stack-sync: transport
    (FileNotFoundError)` on the first Conductor spin-up that reached this
    phase (#897).

    Installing rsync there was the other option and was measured: it
    needs the rsync and libpopt packages extracted per architecture, and
    Debian removes old point releases from its pool — a URL pinned today
    404s within weeks, which is how that route was ruled out. tar and ssh
    are in the image and in every runner image this project targets.

    Both transports raise :class:`subprocess.CalledProcessError` with
    ``stderr`` populated, because callers print that excerpt.
    """
    if shutil.which("rsync") is not None:
        return _rsync_push(local, remote, delete=delete, timeout=timeout)
    return _tar_push(local, remote, delete=delete, timeout=timeout)


# Kept as the historical name: four call sites and their tests use it,
# and `stack_sync` names its result type after it. The transport is
# chosen inside `push_directory`, so this no longer promises rsync.
rsync_to_remote = push_directory


def _rsync_push(
    local: Path,
    remote: str,
    *,
    delete: bool,
    timeout: float | None,
) -> subprocess.CompletedProcess[str]:
    """The original path. The trailing slash on ``local`` is
    auto-appended so rsync uploads the directory's CONTENTS rather than
    the directory itself."""
    src = f"{local}/" if not str(local).endswith("/") else str(local)
    args = ["rsync", "-aq"]
    if delete:
        args.append("--delete")
    args += [src, remote]
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _tar_push(
    local: Path,
    remote: str,
    *,
    delete: bool,
    timeout: float | None,
) -> subprocess.CompletedProcess[str]:
    """`tar` locally, `tar -x` on the far side, one ssh in between.

    Written as an archive file rather than a `tar | ssh` pipeline on
    purpose. A pipeline hides the writer's exit status behind the
    reader's, which is the shape that produced #883; here each half is
    a separate call whose status is checked on its own.

    The archive inherits ``mkstemp``'s 0600, which matters because one
    caller pushes an Infisical payload of secret values. It is removed
    in a ``finally``, including when ssh fails.

    ``--no-same-owner`` on extraction: the numeric uid of whatever
    account the CI job runs as means nothing on the server, and every
    destination here is root-owned service configuration. Modes are
    preserved, which is what the 0600 payload needs.
    """
    host, separator, path = remote.partition(":")
    if not separator or not path:
        raise ValueError(f"remote must be '<host>:<path>', got {remote!r}")

    quoted = shlex.quote(path)
    steps = [f"mkdir -p -- {quoted}"]
    if delete:
        # rsync --delete leaves the directory itself in place and clears
        # what is under it, including dotfiles. `find -delete` is the
        # same contract without a glob that would miss them.
        steps.append(f"find {quoted} -mindepth 1 -delete")
    steps.append(f"tar -C {quoted} -xpf - --no-same-owner")
    # POSIX `set -eu`, not `set -euo pipefail`: `ssh host "<cmd>"` runs the
    # command in the remote account's login shell, which is not guaranteed to
    # be bash — dash answers `-o pipefail` with "Illegal option", the same
    # way a container job did in #886. There is no pipeline here to protect,
    # so the bash-only option bought nothing.
    script = "set -eu; " + "; ".join(steps)

    handle, archive_name = tempfile.mkstemp(prefix="nexus-push-", suffix=".tar")
    os.close(handle)  # tar writes the path; the descriptor is only how mkstemp reserves it
    archive = Path(archive_name)
    try:
        subprocess.run(
            ["tar", "-C", str(local), "-cf", archive_name, "."],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        with archive.open("rb") as payload:
            return subprocess.run(
                ["ssh", host, script],
                check=True,
                stdin=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
    finally:
        archive.unlink(missing_ok=True)
