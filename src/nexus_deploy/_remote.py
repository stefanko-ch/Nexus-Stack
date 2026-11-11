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

import os
import secrets
import shlex
import shutil
import subprocess
import sys
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
    transport_retries: int = 0,
    _sleep: Callable[[float], None] = time.sleep,
    _clock: Callable[[], float] = time.monotonic,
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

    ``transport_retries`` reruns the script when ssh itself fails (exit
    255), up to that many extra times. Only for a script that is safe to
    run twice: a dropped session gives no way to tell whether the script
    ran, ran halfway or never started. Ignored with ``detached=True``,
    which already survives a drop. See :func:`_retry_transport`.
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
            clock=_clock,
        )
    return _retry_transport(
        lambda: subprocess.run(
            ["ssh", host, "bash", "-s"],
            input=script,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            text=True,
            timeout=timeout,
        ),
        retries=transport_retries,
        transport_codes=_SSH_TRANSPORT_CODES,
        label="ssh",
        sleep=_sleep,
    )


# ---------------------------------------------------------------------------
# Retrying a dropped connection
# ---------------------------------------------------------------------------

# ssh's own status for "the connection failed", as opposed to the remote
# command's status.
_SSH_TRANSPORT_CODES = frozenset({255})

# rsync's statuses for a broken transport (rsync(1), EXIT VALUES): 10 socket
# I/O, 12 protocol data stream (what a connection dropped mid-transfer
# usually gives), 30 timeout, 35 daemon connect timeout, and 255, the
# remote shell's own failure passed through. Everything else (permission
# denied, missing source, disk full) is not transport and is not retried.
_RSYNC_TRANSPORT_CODES = frozenset({10, 12, 30, 35, 255})

# The pause between attempts. Long enough for a dropped Cloudflare Access
# session to be replaced, short against a spin-up.
_TRANSPORT_RETRY_DELAY_S = 15.0

# How many extra attempts an idempotent push gets.
_PUSH_TRANSPORT_RETRIES = 2


def _retry_transport(
    call: Callable[[], subprocess.CompletedProcess[str]],
    *,
    retries: int,
    transport_codes: frozenset[int],
    label: str,
    sleep: Callable[[float], None] = time.sleep,
) -> subprocess.CompletedProcess[str]:
    """Run ``call`` again when it fails with a transport status.

    The SSH session to the server sometimes drops mid-command with
    `Connection closed by UNKNOWN port 65535`, exit 255 (#972, #941). The
    long steps survive it by running detached; this covers the short ones.
    On 2026-11-11 a spin-up failed in stack-sync that way, after its
    restore had finished, and a rerun of the same workflow passed.

    Only a ``CalledProcessError`` whose status is in ``transport_codes``
    is retried; any other failure, and the last transport failure, is
    raised unchanged. A non-zero status the call returns without raising
    (``check=False``) is the caller's to judge and is returned as is.
    Callers must only pass operations that are safe to repeat.
    """
    attempt = 0
    while True:
        try:
            return call()
        except subprocess.CalledProcessError as exc:
            if exc.returncode not in transport_codes or attempt >= retries:
                raise
            attempt += 1
            sys.stderr.write(
                f"  ⚠ {label}: connection failed (exit {exc.returncode}); "
                f"retry {attempt} of {retries} in {_TRANSPORT_RETRY_DELAY_S:.0f}s\n"
            )
            sleep(_TRANSPORT_RETRY_DELAY_S)


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

# How long a job may hold the lock without having written its pid before the
# poll stops calling that "starting". The gap is two shell commands.
_DETACHED_STARTUP_GRACE_S = 60

# How much of a script's output is kept. The job directory is on tmpfs.
_DETACHED_OUTPUT_CAP_BYTES = 16 * 1024 * 1024

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
    clock: Callable[[], float],
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

    The script still travels on stdin, never in argv. Its size is checked
    before anything starts, because a session that drops during the upload
    ends the remote ``cat`` with a short file and status 0, and a truncated
    script must not run. A byte count is enough: SSH protects the bytes it
    delivers, so the only way an upload goes wrong is by ending early. It is
    also deliberately not a digest of the script, which can carry secret
    values and would put a hash of them on a command line. Every launch attempt uploads to a file of
    its own, so a retry cannot rewrite the file an earlier attempt is about
    to run; a lock directory lets exactly one of them start. The job unlinks
    its script as soon as bash has it open.

    Times are wall-clock, so a call that hangs until its own cap counts in
    full against ``max_unreachable_s`` and ``timeout``.

    ``argv`` in the returned ``CompletedProcess`` and in a raised
    ``CalledProcessError`` is the same ``["ssh", host, "bash", "-s"]`` the
    attached path reports, so nothing a caller logs changes.
    """
    job_dir = f"{_DETACHED_ROOT}/{secrets.token_hex(8)}"
    quoted_dir = shlex.quote(job_dir)
    expected_bytes = len(script.encode())
    reported_argv = ["ssh", host, "bash", "-s"]
    started_at = clock()
    unreachable_since: float | None = None

    def remaining() -> float | None:
        """Seconds left of ``timeout``, or None when there is no cap."""
        return None if timeout is None else timeout - (clock() - started_at)

    def call(command: str, *, stdin: str | None = None) -> subprocess.CompletedProcess[str] | None:
        """One short SSH call. ``None`` means the server could not be reached."""
        nonlocal unreachable_since
        left = remaining()
        if left is not None and left <= 0:
            raise subprocess.TimeoutExpired(reported_argv, timeout or 0.0)
        cap = _DETACHED_CALL_TIMEOUT_S if left is None else min(_DETACHED_CALL_TIMEOUT_S, left)
        call_started = clock()
        try:
            result = subprocess.run(
                ["ssh", host, command],
                input=stdin,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=cap,
            )
        except subprocess.TimeoutExpired:
            result = None
        if result is not None and result.returncode != _SSH_TRANSPORT_FAILURE:
            unreachable_since = None
            return result
        now = clock()
        if unreachable_since is None:
            # From when the failing call began: a call that hung for two
            # minutes before failing was two minutes of an unreachable server.
            unreachable_since = call_started
        if now - unreachable_since >= max_unreachable_s:
            last_output = result.stdout if result is not None else "ssh call timed out"
            raise subprocess.CalledProcessError(
                _SSH_TRANSPORT_FAILURE,
                reported_argv,
                output=(
                    f"the server was unreachable for {int(now - unreachable_since)}s while a "
                    f"detached script ran in {job_dir}; it may still be running there.\n"
                    f"{last_output}"
                ),
            )
        sleep(poll_interval_s)
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
    # $1 the job directory, $2 this attempt's own copy of the script. The
    # lock is what makes "started twice" impossible: mkdir is atomic, and an
    # attempt that loses removes only its own copy.
    #
    # The output goes through `tail -c`, which keeps the last
    # _DETACHED_OUTPUT_CAP_BYTES of it. The job directory is on tmpfs, and an
    # image build can print far more than that is worth: a full /run would
    # also stop the status from being written. The end is the part to keep,
    # since callers read their result lines from it.
    #
    # The status is written inside the pipeline and renamed to `rc` after it,
    # so `rc` appears only once `out` is complete.
    run_and_record = '{ ( rm -f "$f"; exec bash -s ) < "$f"; echo $? > "$d/rc.tmp"; }'
    keep_tail = f"tail -c {_DETACHED_OUTPUT_CAP_BYTES}"
    if merge_stderr:
        captured = f'{run_and_record} 2>&1 | {keep_tail} > "$d/out"'
    else:
        # Separate streams, each through its own `tail`. Inside, stderr takes
        # the pipe and stdout leaves through fd 3 to the outer pipe.
        captured = (
            f'{{ {run_and_record} 2>&1 >&3 | {keep_tail} > "$d/err"; }} '
            f'3>&1 | {keep_tail} > "$d/out"'
        )
    job = (
        'd="$1"; f="$2"; '
        'mkdir "$d/lock" 2>/dev/null || { rm -f "$f"; exit 0; }; '
        'echo $$ > "$d/pid"; '
        f"{captured}; "
        'mv "$d/rc.tmp" "$d/rc"'
    )
    launch = (
        ": nexus-detached launch; set -eu; umask 077; "
        f"d={quoted_dir}; "
        'mkdir -p "$d"; '
        # Already started by an earlier attempt whose answer was lost: take
        # the upload off stdin and start nothing a second time.
        'if [ -e "$d/lock" ]; then cat > /dev/null; exit 0; fi; '
        'f="$d/script.$$"; cat > "$f"; '
        f'if [ "$(wc -c < "$f")" -ne {expected_bytes} ]; then '
        'rm -f "$f"; echo "script: upload incomplete, nothing started" >&2; exit 1; fi; '
        f'setsid nohup sh -c {shlex.quote(job)} nexus-detached "$d" "$f" '
        "< /dev/null > /dev/null 2>&1 & "
        # Return only once the job has taken the lock. Without this the
        # first poll can arrive before the job has written anything, and a
        # job that is merely starting would be reported as gone.
        'i=0; while [ ! -e "$d/lock" ] && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i + 1)); done'
    )
    poll = (
        ": nexus-detached poll; "
        f"d={quoted_dir}; "
        'if [ -e "$d/rc" ]; then echo "DONE $(cat "$d/rc")"; '
        'elif [ -e "$d/pid" ] && kill -0 "$(cat "$d/pid")" 2>/dev/null; then echo RUNNING; '
        # Lock taken, pid not written yet: the job is between its first two
        # commands. That lasts milliseconds; a lock that old without a pid
        # belongs to a job that died there, and must not read as running.
        'elif [ -e "$d/lock" ] && [ ! -e "$d/pid" ] && '
        f'[ $(( $(date +%s) - $(stat -c %Y "$d/lock") )) -lt {_DETACHED_STARTUP_GRACE_S} ]; '
        "then echo RUNNING; "
        # The job can finish between the checks above.
        'elif [ -e "$d/rc" ]; then echo "DONE $(cat "$d/rc")"; '
        "else echo GONE; fi"
    )

    launched = call_until_reached(launch, stdin=script)
    if launched.returncode != 0:
        raise subprocess.CalledProcessError(
            launched.returncode, reported_argv, output=launched.stdout
        )

    def fetch(stream: str) -> str:
        fetched = call_until_reached(f": nexus-detached fetch; cat {quoted_dir}/{stream}")
        if fetched.returncode != 0:
            # The status is known but the output is not. Callers parse the
            # output for their result, so an empty string here would read as
            # "ran, reported nothing". The directory is left for inspection.
            raise subprocess.CalledProcessError(
                fetched.returncode,
                reported_argv,
                output=(
                    f"the detached script in {job_dir} finished, but its {stream!r} "
                    f"could not be read:\n{fetched.stdout}"
                ),
            )
        return fetched.stdout

    def cleanup() -> None:
        # Best effort and one attempt: the directory holds output only by now,
        # and tmpfs forgets it at the next boot.
        call(f": nexus-detached cleanup; rm -rf {quoted_dir}")

    status: int | None = None
    vanished = False
    while status is None and not vanished:
        polled = call(poll)
        if polled is None:
            continue
        answer = polled.stdout.strip().splitlines()[-1] if polled.stdout.strip() else ""
        if (
            answer.startswith("DONE ")
            and answer.removeprefix("DONE ").strip().lstrip("-").isdigit()
        ):
            status = int(answer.removeprefix("DONE ").strip())
        elif answer == "GONE":
            vanished = True
        elif answer == "RUNNING" and polled.returncode == 0:
            sleep(poll_interval_s)
        else:
            # The server answered, and not with one of the three things the
            # poll can say. Polling on would loop on the same answer forever.
            raise subprocess.CalledProcessError(
                polled.returncode or _DETACHED_VANISHED_STATUS,
                reported_argv,
                output=(
                    f"could not read the state of the detached script in {job_dir}; "
                    f"it may still be running there. The poll answered:\n{polled.stdout}"
                ),
            )

    if vanished:
        # Whatever output exists is worth showing, but its absence must not
        # hide the real finding.
        try:
            partial = fetch("out")
        except subprocess.CalledProcessError:
            partial = ""
        cleanup()
        raise subprocess.CalledProcessError(
            _DETACHED_VANISHED_STATUS,
            reported_argv,
            output=(
                f"{partial}the detached script in {job_dir} ended without leaving an exit "
                "status: the server rebooted, or the job was killed. Its work may be incomplete.\n"
            ),
        )

    stdout = fetch("out")
    stderr = None if merge_stderr else fetch("err")
    cleanup()

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

    A push is retried when the connection drops (:func:`_retry_transport`):
    it copies a local directory to a fixed path, so a second run lands on
    the same result whether the first got halfway or not at all.
    """
    if shutil.which("rsync") is not None:
        return _retry_transport(
            lambda: _rsync_push(local, remote, delete=delete, timeout=timeout),
            retries=_PUSH_TRANSPORT_RETRIES,
            transport_codes=_RSYNC_TRANSPORT_CODES,
            label="rsync",
        )
    return _retry_transport(
        lambda: _tar_push(local, remote, delete=delete, timeout=timeout),
        retries=_PUSH_TRANSPORT_RETRIES,
        transport_codes=_SSH_TRANSPORT_CODES,
        label="tar over ssh",
    )


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
