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
import shlex
import shutil
import subprocess
import tempfile
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
    """
    return subprocess.run(
        ["ssh", host, "bash", "-s"],
        input=script,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


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
    script = "set -euo pipefail; " + "; ".join(steps)

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
