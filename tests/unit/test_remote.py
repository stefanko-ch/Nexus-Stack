"""Tests for nexus_deploy._remote."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from nexus_deploy import _remote


def test_ssh_run_invokes_ssh_with_host_and_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ssh_run('cmd')`` calls ``ssh nexus 'cmd'`` via subprocess."""
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", fake_run)
    result = _remote.ssh_run("echo hello")
    assert result.returncode == 0
    assert captured["args"][0] == ["ssh", "nexus", "echo hello"]
    assert captured["kwargs"]["check"] is True
    # stdout=PIPE + stderr=STDOUT (NOT capture_output=True; that combo
    # raises ValueError when stderr is also explicit — see the docstring
    # in _remote.ssh_run).
    assert captured["kwargs"]["stdout"] == subprocess.PIPE
    assert captured["kwargs"]["stderr"] == subprocess.STDOUT
    assert "capture_output" not in captured["kwargs"]
    assert captured["kwargs"]["text"] is True


def test_ssh_run_custom_host(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", fake_run)
    _remote.ssh_run("uptime", host="dev-host")
    assert captured["args"][0] == ["ssh", "dev-host", "uptime"]


def test_ssh_run_no_check_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``check=False`` is forwarded so non-zero exits don't raise."""
    captured: dict[str, Any] = {}

    def fake_run(*_args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["check"] = kwargs.get("check")
        return subprocess.CompletedProcess(args=["ssh"], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", fake_run)
    result = _remote.ssh_run("false", check=False)
    assert captured["check"] is False
    assert result.returncode == 1


@pytest.fixture
def rsync_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the transport for the tests below.

    Since #897 `push_directory` picks tar-over-ssh when rsync is absent, and
    CI for a Conductor fork runs on a job image where it IS absent. Without
    this, these tests would pass on GitHub and fail there — on the very
    machine the fallback exists for.
    """
    real_which = shutil.which
    monkeypatch.setattr(
        "nexus_deploy._remote.shutil.which",
        lambda name, *a, **k: "/usr/bin/rsync" if name == "rsync" else real_which(name, *a, **k),
    )


def test_rsync_to_remote_appends_trailing_slash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rsync_installed: None
) -> None:
    """``Path('/foo')`` is normalised to ``/foo/`` so rsync copies the
    directory contents (not the directory itself, which would land at
    ``<dest>/foo/...``)."""
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args[0]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", fake_run)
    _remote.rsync_to_remote(tmp_path, "nexus:/dst/")
    cmd = captured["args"]
    assert cmd[0] == "rsync"
    assert "-aq" in cmd
    # Source has trailing slash → rsync uploads dir contents, not the dir itself
    assert cmd[-2] == f"{tmp_path}/"
    assert cmd[-1] == "nexus:/dst/"


def test_rsync_to_remote_preserves_existing_trailing_slash(
    monkeypatch: pytest.MonkeyPatch,
    rsync_installed: None,
) -> None:
    """Passing a string path that already ends in ``/`` is left alone."""
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args[0]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", fake_run)
    _remote.rsync_to_remote(Path("/some/path/"), "nexus:/dst/")
    # Path('/some/path/') normalises to '/some/path' in str(); we
    # always re-append /, so the result is the same.
    assert captured["args"][-2].endswith("/")


def test_rsync_to_remote_delete_flag(
    monkeypatch: pytest.MonkeyPatch, rsync_installed: None
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args[0]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", fake_run)
    _remote.rsync_to_remote(Path("/src"), "nexus:/dst/", delete=True)
    assert "--delete" in captured["args"]


def test_ssh_run_merge_stderr_false_keeps_streams_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``merge_stderr=False`` → stderr=PIPE (not STDOUT), stdout still captured."""
    captured: dict[str, Any] = {}

    def fake_run(*_args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", fake_run)
    _remote.ssh_run("foo", merge_stderr=False)
    assert captured["kwargs"]["stdout"] == subprocess.PIPE
    assert captured["kwargs"]["stderr"] == subprocess.PIPE  # NOT STDOUT


def test_ssh_run_script_invokes_bash_s_with_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ssh_run_script`` runs ``ssh nexus bash -s`` with the script on stdin (NOT argv)."""
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = args[0]
        captured["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", fake_run)
    secret_payload = "TOKEN=top-secret-do-not-leak\necho hi"
    _remote.ssh_run_script(secret_payload)
    # The script is on stdin, NOT argv — argv contains only the bash invocation
    assert captured["argv"] == ["ssh", "nexus", "bash", "-s"]
    assert captured["input"] == secret_payload
    # And of course the secret must be on stdin and ONLY on stdin
    assert "top-secret-do-not-leak" not in " ".join(captured["argv"])


def test_ssh_run_actually_invokes_subprocess(tmp_path: Path) -> None:
    """End-to-end against a fake `ssh` on PATH — catches subprocess.run misuse.

    The mocked tests above prove the call shape (args + kwargs), but
    they can't catch combinations of subprocess.run kwargs that raise
    ValueError before any subprocess is spawned (e.g., the historical
    ``capture_output=True`` + ``stderr=...`` clash). This test puts a
    minimal stand-in `ssh` script on PATH and exercises ``ssh_run``
    against it.
    """
    fake_ssh = tmp_path / "ssh"
    fake_ssh.write_text("#!/usr/bin/env bash\necho stdout-line\necho err-line >&2\n")
    fake_ssh.chmod(0o755)
    import os

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{tmp_path}:{old_path}"
    try:
        result = _remote.ssh_run("does-not-matter")
    finally:
        os.environ["PATH"] = old_path
    assert result.returncode == 0
    # merge_stderr=True (default) merges stderr into stdout
    assert "stdout-line" in result.stdout
    assert "err-line" in result.stdout


def test_rsync_to_remote_no_delete_by_default(
    monkeypatch: pytest.MonkeyPatch, rsync_installed: None
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args[0]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy._remote.subprocess.run", fake_run)
    _remote.rsync_to_remote(Path("/src"), "nexus:/dst/")
    assert "--delete" not in captured["args"]
