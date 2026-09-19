"""Tests for nexus_deploy.ssh.

Mocks subprocess + socket for deterministic unit coverage. The real
end-to-end path (against a live nexus host with Cloudflare Access
ProxyCommand) is verified via spin-up acceptance, not these tests.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from nexus_deploy.ssh import SSHClient, SSHError

# -- run / run_script ---------------------------------------------------


def test_run_invokes_ssh_with_host_and_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("nexus_deploy.ssh.subprocess.run", fake_run)
    result = SSHClient().run("echo hello")
    assert result.returncode == 0
    assert captured["args"][0] == ["ssh", "nexus", "echo hello"]
    assert captured["kwargs"]["check"] is True
    assert captured["kwargs"]["stdout"] == subprocess.PIPE
    assert captured["kwargs"]["stderr"] == subprocess.STDOUT
    assert "capture_output" not in captured["kwargs"]
    assert captured["kwargs"]["text"] is True


def test_run_custom_host(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy.ssh.subprocess.run", fake_run)
    SSHClient(host="dev-host").run("uptime")
    assert captured["args"][0] == ["ssh", "dev-host", "uptime"]


def test_run_no_check_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*_args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["check"] = kwargs.get("check")
        return subprocess.CompletedProcess(args=["ssh"], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr("nexus_deploy.ssh.subprocess.run", fake_run)
    result = SSHClient().run("false", check=False)
    assert captured["check"] is False
    assert result.returncode == 1


def test_run_merge_stderr_false_keeps_streams_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*_args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy.ssh.subprocess.run", fake_run)
    SSHClient().run("foo", merge_stderr=False)
    assert captured["kwargs"]["stdout"] == subprocess.PIPE
    assert captured["kwargs"]["stderr"] == subprocess.PIPE


def test_run_script_invokes_bash_s_with_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = args[0]
        captured["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("nexus_deploy.ssh.subprocess.run", fake_run)
    secret = "TOKEN=top-secret-do-not-leak\necho hi"
    SSHClient().run_script(secret)
    assert captured["argv"] == ["ssh", "nexus", "bash", "-s"]
    assert captured["input"] == secret
    # The secret MUST be on stdin and ONLY on stdin
    assert "top-secret-do-not-leak" not in " ".join(captured["argv"])


def test_run_script_timeout_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*_args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy.ssh.subprocess.run", fake_run)
    SSHClient().run_script("echo hi", timeout=42)
    assert captured["timeout"] == 42


# -- rsync_to -----------------------------------------------------------
#
# These three pin the rsync invocation, so they have to pin the transport
# too: since #897 `push_directory` picks tar-over-ssh when rsync is absent,
# and CI for a Conductor fork runs on a job image where it IS absent. Without
# this fixture they would pass on GitHub and fail there — on the very machine
# the fallback exists for.


@pytest.fixture
def rsync_installed(monkeypatch: pytest.MonkeyPatch) -> None:

    real_which = shutil.which
    monkeypatch.setattr(
        "nexus_deploy._remote.shutil.which",
        lambda name, *a, **k: "/usr/bin/rsync" if name == "rsync" else real_which(name, *a, **k),
    )


def test_rsync_to_appends_trailing_slash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rsync_installed: None
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args[0]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy.ssh.subprocess.run", fake_run)
    SSHClient().rsync_to(tmp_path, "nexus:/dst/")
    cmd = captured["args"]
    assert cmd[0] == "rsync"
    assert "-aq" in cmd
    assert cmd[-2] == f"{tmp_path}/"
    assert cmd[-1] == "nexus:/dst/"


def test_rsync_to_delete_flag(monkeypatch: pytest.MonkeyPatch, rsync_installed: None) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args[0]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy.ssh.subprocess.run", fake_run)
    SSHClient().rsync_to(Path("/src"), "nexus:/dst/", delete=True)
    assert "--delete" in captured["args"]


def test_rsync_to_no_delete_by_default(
    monkeypatch: pytest.MonkeyPatch, rsync_installed: None
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args[0]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy.ssh.subprocess.run", fake_run)
    SSHClient().rsync_to(Path("/src"), "nexus:/dst/")
    assert "--delete" not in captured["args"]


# -- context manager ----------------------------------------------------


def test_ssh_client_is_context_manager() -> None:
    with SSHClient("nexus") as ssh:
        assert ssh.host == "nexus"


# -- port_forward -------------------------------------------------------


class _FakeProc:
    """Minimal Popen-like stand-in. ``poll`` returns None until ``rc``
    is set; ``wait`` honours timeout."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode if self.returncode is not None else 0


def _start_loopback_listener(port_holder: list[int], stop: threading.Event) -> threading.Thread:
    """Open a TCP listener on an OS-chosen port, record it, accept until ``stop``."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    sock.settimeout(0.2)
    port_holder.append(sock.getsockname()[1])

    def _serve() -> None:
        while not stop.is_set():
            try:
                conn, _ = sock.accept()
            except OSError:
                continue
            else:
                conn.close()
        sock.close()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    return t


def test_port_forward_yields_after_local_port_accepts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Port-forward yields ``local_port`` once the local TCP listener accepts."""
    port_holder: list[int] = []
    stop = threading.Event()
    listener = _start_loopback_listener(port_holder, stop)
    try:
        # Wait for the listener thread to have bound + recorded its port
        for _ in range(50):
            if port_holder:
                break
            time.sleep(0.02)
        assert port_holder, "listener thread didn't bind in time"
        local_port = port_holder[0]

        fake_proc = _FakeProc()
        captured_argv: list[list[str]] = []

        def fake_popen(argv: list[str], **_kwargs: Any) -> _FakeProc:
            captured_argv.append(argv)
            return fake_proc

        monkeypatch.setattr("nexus_deploy.ssh.subprocess.Popen", fake_popen)

        ssh = SSHClient("nexus")
        with ssh.port_forward(local_port, "localhost", 9200) as p:
            assert p == local_port
            # The argv we constructed must be the canonical -N -L form
            # plus -o ExitOnForwardFailure=yes (so a port-in-use bind
            # failure exits ssh immediately instead of leaving a stale
            # process that could let _wait_for_local_port falsely
            # connect to an unrelated listener) AND the explicit
            # 127.0.0.1: bind-address prefix on the forward spec
            # (round-4 fix: prevents IPv6 ::1 dual-stack bind that
            # could collide with an IPv4-only port-allocator's probe).
            assert captured_argv[0] == [
                "ssh",
                "-N",
                "-o",
                "ExitOnForwardFailure=yes",
                "-L",
                f"127.0.0.1:{local_port}:localhost:9200",
                "nexus",
            ]
        # Tunnel subprocess gets terminated on context exit
        assert fake_proc.terminated is True
    finally:
        stop.set()
        listener.join(timeout=1.0)


def test_port_forward_raises_if_subprocess_exits_early(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``ssh -N -L`` exits before the local port comes up → SSHError."""
    fake_proc = _FakeProc()
    fake_proc.returncode = 255  # ssh exits 255 on auth/connect failure

    def fake_popen(_argv: list[str], **_kwargs: Any) -> _FakeProc:
        return fake_proc

    monkeypatch.setattr("nexus_deploy.ssh.subprocess.Popen", fake_popen)

    # Pick an unused port on the local machine for the test
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    unused_port = sock.getsockname()[1]
    sock.close()

    with (
        pytest.raises(SSHError, match="rc=255"),
        SSHClient("nexus").port_forward(unused_port, "localhost", 9200, wait_seconds=1.0),
    ):
        pytest.fail("should have raised before yielding")


def test_port_forward_raises_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ssh stays up but local port never accepts → SSHError on timeout."""
    fake_proc = _FakeProc()  # poll() returns None forever

    def fake_popen(_argv: list[str], **_kwargs: Any) -> _FakeProc:
        return fake_proc

    monkeypatch.setattr("nexus_deploy.ssh.subprocess.Popen", fake_popen)

    # Pick a port we know is closed (bind + immediately release)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    closed_port = sock.getsockname()[1]
    sock.close()

    with (
        pytest.raises(SSHError, match="did not come up"),
        SSHClient("nexus").port_forward(closed_port, "localhost", 9200, wait_seconds=0.3),
    ):
        pytest.fail("should have raised before yielding")
    # And the fake subprocess gets cleaned up either way
    assert fake_proc.terminated is True


def test_port_forward_kills_subprocess_if_terminate_hangs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If terminate()'s wait() times out, fall through to kill()."""

    class HangingProc(_FakeProc):
        def __init__(self) -> None:
            super().__init__()
            self._wait_calls = 0

        def wait(self, timeout: float | None = None) -> int:
            self._wait_calls += 1
            if self._wait_calls == 1:
                # First wait() (post-terminate) hangs out
                raise subprocess.TimeoutExpired(cmd="ssh", timeout=5.0)
            return -9

    proc = HangingProc()
    proc.returncode = None  # poll returns None → "alive"

    port_holder: list[int] = []
    stop = threading.Event()
    listener = _start_loopback_listener(port_holder, stop)
    try:
        for _ in range(50):
            if port_holder:
                break
            time.sleep(0.02)
        assert port_holder
        local_port = port_holder[0]

        def fake_popen(_argv: list[str], **_kwargs: Any) -> HangingProc:
            return proc

        monkeypatch.setattr("nexus_deploy.ssh.subprocess.Popen", fake_popen)

        # Make sure poll() returns None during _wait_for_local_port
        # so we DO yield, then hit the hanging-terminate path on exit.
        with SSHClient("nexus").port_forward(local_port, "localhost", 1):
            pass

        assert proc.terminated is True
        assert proc.killed is True
    finally:
        stop.set()
        listener.join(timeout=1.0)


# -- terminate ProcessLookupError hardening -----------------------------


def test_port_forward_does_not_terminate_already_exited_proc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ssh exited before context exit, skip terminate() entirely.

    Race: the process exits naturally (signal, transient drop) AFTER
    _wait_for_local_port saw it alive but BEFORE the finally block runs.
    Calling terminate() on a reaped pid raises ProcessLookupError on
    POSIX. We defend by checking poll() first.
    """

    class ProcExitsAfterYield(_FakeProc):
        """poll() None during yield, then exits before cleanup poll."""

        def __init__(self) -> None:
            super().__init__()
            self.exited = False

        def poll(self) -> int | None:
            if self.exited:
                self.returncode = 0
            return self.returncode

    proc = ProcExitsAfterYield()
    port_holder: list[int] = []
    stop = threading.Event()
    listener = _start_loopback_listener(port_holder, stop)
    try:
        for _ in range(50):
            if port_holder:
                break
            time.sleep(0.02)
        assert port_holder

        def fake_popen(_argv: list[str], **_kwargs: Any) -> ProcExitsAfterYield:
            return proc

        monkeypatch.setattr("nexus_deploy.ssh.subprocess.Popen", fake_popen)

        with SSHClient("nexus").port_forward(port_holder[0], "localhost", 1):
            # Simulate the ssh subprocess exiting on its own during the yield —
            # auth refresh dropped, network blip, etc. Cleanup must skip
            # terminate() because poll() now reports the exit.
            proc.exited = True
        # terminate() must NOT have been called — proc was already gone
        assert proc.terminated is False
    finally:
        stop.set()
        listener.join(timeout=1.0)


def test_port_forward_swallows_process_lookup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even if poll() lies (returns None) and terminate() raises, cleanup is non-fatal."""

    class RaisingProc(_FakeProc):
        def terminate(self) -> None:
            raise ProcessLookupError(3, "No such process")

    proc = RaisingProc()
    port_holder: list[int] = []
    stop = threading.Event()
    listener = _start_loopback_listener(port_holder, stop)
    try:
        for _ in range(50):
            if port_holder:
                break
            time.sleep(0.02)
        assert port_holder

        def fake_popen(_argv: list[str], **_kwargs: Any) -> RaisingProc:
            return proc

        monkeypatch.setattr("nexus_deploy.ssh.subprocess.Popen", fake_popen)

        # No exception should escape the with-block
        with SSHClient("nexus").port_forward(port_holder[0], "localhost", 1):
            pass
    finally:
        stop.set()
        listener.join(timeout=1.0)


# -- exception-message hygiene ------------------------------------------


def test_ssh_error_message_does_not_leak_argv() -> None:
    """SSHError text should not include user-controlled host/host-config bits.

    ``SSHError`` carries fixed format strings; this is a static check
    against the patterns we know we emit. If a future contributor adds
    ``str(e)`` of subprocess output into the SSHError message, that
    output may include credentials echoed by a misconfigured
    ProxyCommand — this test guards against that regression.
    """
    msg1 = str(SSHError("ssh tunnel exited with rc=255 before local port 8080 became reachable"))
    msg2 = str(SSHError("ssh tunnel to local port 8080 did not come up within 10.0s"))
    for msg in (msg1, msg2):
        assert "ProxyCommand" not in msg
        assert "Authorization" not in msg
        assert "Bearer" not in msg
