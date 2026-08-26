"""SSH client wrapper for nexus_deploy.

Class-based wrapper around the system ``ssh`` binary that adds
**port-forwarding** on top of the ``ssh nexus <cmd>`` and
``rsync … nexus:…`` patterns. The port-forward capability lets REST
client modules (Filestash, Forgejo, Kestra) talk to services on the
nexus server via local ``http://localhost:<port>`` calls instead of
rendering a server-side bash curl loop — Python ``requests`` calls
run locally, exceptions surface as exceptions, no token ever crosses
into a rendered bash script.

Implementation choice — subprocess + system ``ssh``, not paramiko:

The user's ``~/.ssh/config`` for the ``nexus`` alias uses
``ProxyCommand cloudflared access ssh --hostname …`` to tunnel through
Cloudflare Access. paramiko's SSHConfig parsing recognises
``ProxyCommand`` but spawning + driving it through paramiko's
``ProxyCommand`` channel is fragile in practice — Cloudflare's
``cloudflared access ssh`` does its own multiplex protocol and we'd be
re-implementing edge cases that the system ``ssh`` binary already
handles. Subprocess + system ``ssh`` reuses the exact path that's been
battle-tested across PRs #506-#515 and adds zero new auth-failure
modes. Port-forwarding via ``ssh -N -L`` works through ProxyCommand
transparently for free.

If we ever need persistent connection-multiplexing, paramiko, or
SFTP-API niceties, the API surface here is small enough to swap the
backend without changing call sites.
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType


class SSHError(Exception):
    """Raised for SSH-side errors not modelled by ``CalledProcessError``.

    Used for port-forward setup failures (tunnel never came up) and
    other infra-layer issues. Subprocess-level command failures still
    surface as ``CalledProcessError`` from the standard library.
    """


class SSHClient:
    """SSH client for the nexus server.

    Used as a context manager so any port-forwards opened during the
    block are torn down deterministically on exit::

        with SSHClient("nexus") as ssh:
            ssh.run("uptime")
            with ssh.port_forward(8222, "localhost", 8222):
                requests.get("http://localhost:8222/healthz")

    All methods accept the same ``timeout`` semantics as
    ``_remote.py``: ``None`` (default) means no Python-side cap. A
    slow first-cold-start on Hetzner can legitimately take several
    minutes; a default cap would convert "slow" into spurious
    ``TimeoutExpired`` errors.
    """

    def __init__(self, host: str = "nexus") -> None:
        self.host = host

    def __enter__(self) -> SSHClient:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        # No persistent state to clean up at the connection level —
        # individual port_forward() context managers handle their own
        # subprocess lifecycle.
        return None

    def run(
        self,
        cmd: str,
        *,
        check: bool = True,
        timeout: float | None = None,
        merge_stderr: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a single command on the nexus server.

        Equivalent to ``ssh <host> "<cmd>"``. ``cmd`` is passed via
        argv — for commands containing secrets prefer
        :meth:`run_script`, which feeds the script over stdin so it
        never lands in ``ps`` / ``CalledProcessError.cmd``.

        With ``merge_stderr=True`` (default), stderr is folded into
        stdout (the ``ssh nexus "..." 2>&1`` equivalent).
        """
        return subprocess.run(
            ["ssh", self.host, cmd],
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            text=True,
            timeout=timeout,
        )

    def run_script(
        self,
        script: str,
        *,
        check: bool = True,
        timeout: float | None = None,
        merge_stderr: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a bash script on the nexus server, fed over stdin.

        Equivalent to ``ssh <host> bash -s <<<"<script>"``. The script
        body is written to the remote shell's stdin so it never enters
        local ``ps`` output, CI argv-logging, or
        ``CalledProcessError.cmd`` / ``TimeoutExpired.cmd`` — only
        ``["ssh", "<host>", "bash", "-s"]`` is ever visible.

        Use this whenever the script may contain secret values
        (Infisical tokens, generated passwords, base64-encoded payloads).
        """
        return subprocess.run(
            ["ssh", self.host, "bash", "-s"],
            input=script,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            text=True,
            timeout=timeout,
        )

    def rsync_to(
        self,
        local: Path,
        remote: str,
        *,
        delete: bool = False,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Push a local directory to the nexus server via rsync.

        ``remote`` follows rsync syntax (e.g. ``"<host>:/tmp/push/"``);
        the alias resolves through the same ssh config as :meth:`run`.
        The trailing slash on ``local`` is auto-appended so rsync
        uploads the directory's CONTENTS rather than the directory
        itself.

        ``delete=True`` clears destination paths that don't exist
        locally — used when the local dir is the canonical
        source-of-truth for that remote location.
        """
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

    @contextmanager
    def port_forward(
        self,
        local_port: int,
        remote_host: str,
        remote_port: int,
        *,
        wait_seconds: float = 10.0,
    ) -> Iterator[int]:
        """Open an SSH ``-L`` tunnel for the duration of the with-block.

        Spawns ``ssh -N -L <local_port>:<remote_host>:<remote_port> <host>``
        as a subprocess, polls ``localhost:<local_port>`` until it
        accepts TCP, then yields ``local_port`` to the caller. On
        exit the subprocess is terminated and reaped.

        ``remote_host`` is resolved on the **remote** side (i.e.
        ``localhost`` here means localhost on the nexus server, not
        the local machine). This is the standard ``ssh -L`` semantics.

        Raises :class:`SSHError` if the tunnel doesn't come up within
        ``wait_seconds`` — typical causes are a wrong host alias, a
        broken Cloudflare-Access ProxyCommand, or the remote service
        not listening on the expected port. ``SSHError`` carries no
        process output: stderr might include credentials echoed by a
        misconfigured ProxyCommand and we never want to leak that into
        an exception message.
        """
        # Explicit IPv4 bind: without ``127.0.0.1:`` prefix, ``ssh -L``
        # binds both the IPv4 and IPv6 loopback on dual-stack hosts.
        # Callers (e.g. :func:`nexus_deploy.__main__._allocate_free_port`)
        # typically probe IPv4 only when picking a "free" local port —
        # a port that's free on 127.0.0.1 may still be occupied on ::1
        # by another tunnel, and the resulting ssh-bind failure would
        # surface as an ExitOnForwardFailure abort. Pinning the bind
        # to IPv4 matches the allocator's probe surface and eliminates
        # that whole class of intermittent collisions.
        forward_spec = f"127.0.0.1:{local_port}:{remote_host}:{remote_port}"
        # ExitOnForwardFailure=yes: if the local bind fails (port already
        # in use), ssh exits non-zero immediately instead of staying up
        # without a working forward. Without it, _wait_for_local_port
        # could TCP-connect to whichever unrelated process happens to
        # already own the port and falsely report the tunnel as ready.
        proc = subprocess.Popen(
            [
                "ssh",
                "-N",
                "-o",
                "ExitOnForwardFailure=yes",
                "-L",
                forward_spec,
                self.host,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            self._wait_for_local_port(local_port, wait_seconds, proc)
            yield local_port
        finally:
            # If ssh exited on its own (transient network drop, signal,
            # auth-renew failure mid-session) we may race terminate()
            # against a pid that no longer exists. On POSIX that surfaces
            # as ProcessLookupError; on Windows OSError. Either way we
            # still want to reap to avoid a zombie. poll() is the
            # cheap probe; the broad except is the belt to the suspenders.
            if proc.poll() is None:
                with contextlib.suppress(ProcessLookupError, OSError):
                    proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError, OSError):
                    proc.kill()
                proc.wait(timeout=5.0)

    @staticmethod
    def _wait_for_local_port(
        port: int,
        timeout_s: float,
        proc: subprocess.Popen[bytes],
    ) -> None:
        """Poll ``localhost:<port>`` until it accepts TCP or timeout.

        Bails out early if the ssh subprocess has already exited —
        that means tunnel setup failed (auth problem, missing
        ProxyCommand binary, etc.) and there's no point waiting for
        the timeout.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise SSHError(
                    f"ssh tunnel exited with rc={proc.returncode} "
                    f"before local port {port} became reachable",
                )
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.1)
        raise SSHError(
            f"ssh tunnel to local port {port} did not come up within {timeout_s}s",
        )
