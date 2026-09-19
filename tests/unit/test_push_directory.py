"""`_remote.push_directory` copies a directory with rsync, or with tar over ssh
where rsync is absent (#897).

The tar path is exercised **for real**: a fake `ssh` on PATH runs the remote
command locally, so the test asserts which files arrived and with which modes,
not which arguments were assembled. That is the half worth testing — the
argument list was never the thing that broke.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from nexus_deploy import _remote

# `ssh <host> <command>` where the command runs here instead of over the wire.
# It ignores the host, and passes stdin through, which is what carries the
# archive.
_FAKE_SSH = """#!/usr/bin/env bash
shift            # drop the host
exec bash -c "$*"
"""

_FAILING_SSH = """#!/usr/bin/env bash
echo "kex_exchange_identification: connection closed by remote host" >&2
exit 255
"""


def _fake_ssh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str = _FAKE_SSH) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "ssh").write_text(body)
    (bin_dir / "ssh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


def _no_rsync(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the fallback the only option, whatever the test machine has."""
    real_which = shutil.which
    monkeypatch.setattr(
        "nexus_deploy._remote.shutil.which",
        lambda name, *a, **k: None if name == "rsync" else real_which(name, *a, **k),
    )


def _tree(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------------------
# Which transport
# ---------------------------------------------------------------------------


def test_rsync_is_used_when_it_is_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The GitHub path must not change: rsync present means rsync used."""
    calls: list[list[str]] = []
    monkeypatch.setattr("nexus_deploy._remote.shutil.which", lambda name, *a, **k: "/usr/bin/rsync")
    monkeypatch.setattr(
        "nexus_deploy._remote.subprocess.run",
        lambda args, **kwargs: (
            calls.append(list(args))  # type: ignore[func-returns-value]
            or subprocess.CompletedProcess(args, 0, "", "")
        ),
    )

    _remote.push_directory(tmp_path, "nexus:/dst/", delete=True)

    assert calls == [["rsync", "-aq", "--delete", f"{tmp_path}/", "nexus:/dst/"]]


def test_the_fallback_needs_no_rsync_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of #897: the whole push must work on an image without it."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch)
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "docker-compose.yml").write_text("services: {}\n")

    _remote.push_directory(src, f"nexus:{dst}")

    assert _tree(dst) == {"docker-compose.yml": "services: {}\n"}


# ---------------------------------------------------------------------------
# What actually arrives
# ---------------------------------------------------------------------------


def test_the_directory_contents_arrive_not_the_directory_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """rsync's trailing-slash semantics, which four call sites rely on."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch)
    src, dst = tmp_path / "stacks-kestra", tmp_path / "dst"
    (src / "nested").mkdir(parents=True)
    (src / "a.txt").write_text("a")
    (src / "nested" / "b.txt").write_text("b")

    _remote.push_directory(src, f"nexus:{dst}")

    assert _tree(dst) == {"a.txt": "a", "nested/b.txt": "b"}
    assert not (dst / "stacks-kestra").exists()


def test_dotfiles_come_along(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every stack push carries a rendered `.env`. A glob-based copy would
    silently leave it behind, and the stack would come up unconfigured."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch)
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / ".env").write_text("KESTRA_DB_PASSWORD=x\n")

    _remote.push_directory(src, f"nexus:{dst}")

    assert _tree(dst) == {".env": "KESTRA_DB_PASSWORD=x\n"}


def test_restrictive_modes_survive_the_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Infisical push writes 0600 files of secret values and relies on
    the transport keeping them that way."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch)
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    secret = src / "payload.json"
    secret.write_text('{"k": "v"}')
    secret.chmod(0o600)

    _remote.push_directory(src, f"nexus:{dst}")

    assert stat.S_IMODE((dst / "payload.json").stat().st_mode) == 0o600


def test_the_destination_is_created_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """rsync creates the last path component; a bare `tar -x` would not."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch)
    src, dst = tmp_path / "src", tmp_path / "deep" / "not" / "there"
    src.mkdir()
    (src / "f").write_text("x")

    _remote.push_directory(src, f"nexus:{dst}")

    assert _tree(dst) == {"f": "x"}


# ---------------------------------------------------------------------------
# delete=True
# ---------------------------------------------------------------------------


def test_delete_clears_what_is_no_longer_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three callers push a directory they treat as the source of truth."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch)
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "keep").write_text("new")
    dst.mkdir()
    (dst / "stale").write_text("old")
    (dst / ".hidden-stale").write_text("old")

    _remote.push_directory(src, f"nexus:{dst}", delete=True)

    assert _tree(dst) == {"keep": "new"}


def test_without_delete_the_remote_keeps_what_is_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stack-sync and the woodpecker push deliberately do not delete: the
    server-side dir also holds files the deploy generated there."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch)
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "docker-compose.yml").write_text("new")
    dst.mkdir()
    (dst / "docker-compose.firewall.yml").write_text("generated on the server")

    _remote.push_directory(src, f"nexus:{dst}")

    assert _tree(dst) == {
        "docker-compose.yml": "new",
        "docker-compose.firewall.yml": "generated on the server",
    }


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------


def test_a_failing_ssh_raises_with_its_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stack_sync prints `exc.stderr` as the per-service diagnostic, so the
    fallback has to fail the same shape as rsync did."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch, body=_FAILING_SSH)
    src = tmp_path / "src"
    src.mkdir()
    (src / "f").write_text("x")

    with pytest.raises(subprocess.CalledProcessError) as caught:
        _remote.push_directory(src, "nexus:/dst")

    assert caught.value.returncode == 255
    assert "kex_exchange_identification" in caught.value.stderr


def test_a_remote_without_a_path_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`nexus` alone would make `tar -C ''` run in the remote home dir."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch)
    src = tmp_path / "src"
    src.mkdir()

    with pytest.raises(ValueError, match="<host>:<path>"):
        _remote.push_directory(src, "nexus")


def test_no_archive_is_left_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """It holds a copy of whatever was pushed — for one caller, secrets."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch, body=_FAILING_SSH)
    src = tmp_path / "src"
    src.mkdir()
    (src / "f").write_text("x")
    # `tempfile.tempdir`, not the TMPDIR env var: tempfile resolves the
    # directory once and caches it, so setting the variable here would have
    # no effect — and the assertion below would then inspect a directory
    # nothing ever wrote to and pass for the wrong reason. It did, until a
    # mutation that removed the cleanup failed to fail.
    spool = tmp_path / "tmp"
    spool.mkdir()
    monkeypatch.setattr("nexus_deploy._remote.tempfile.tempdir", str(spool))

    with pytest.raises(subprocess.CalledProcessError):
        _remote.push_directory(src, "nexus:/dst")

    assert list(spool.iterdir()) == [], "the archive outlived a failed push"


# `ssh <host> <command>` that only records what it was asked to run.
_RECORDING_SSH = """#!/usr/bin/env bash
shift
printf '%s' "$*" > "$REMOTE_SCRIPT_LOG"
"""


def test_the_remote_script_runs_in_a_posix_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ssh host "<cmd>"` runs the command in the remote account's login
    shell, which is not guaranteed to be bash. dash answers `-o pipefail`
    with "Illegal option" — the same failure a container job hit in #886 —
    and there is no pipeline in this script for pipefail to protect."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch, body=_RECORDING_SSH)
    log = tmp_path / "remote-script.txt"
    monkeypatch.setenv("REMOTE_SCRIPT_LOG", str(log))
    src = tmp_path / "src"
    src.mkdir()
    (src / "f").write_text("x")

    _remote.push_directory(src, "nexus:/dst", delete=True)

    script = log.read_text()
    assert script.startswith("set -eu;")
    assert "pipefail" not in script
    # Still POSIX with a pipe would be a different question — there is none.
    assert "|" not in script


def test_the_remote_path_is_quoted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The path reaches a remote shell as part of a command string."""
    _no_rsync(monkeypatch)
    _fake_ssh(tmp_path, monkeypatch, body=_RECORDING_SSH)
    log = tmp_path / "remote-script.txt"
    monkeypatch.setenv("REMOTE_SCRIPT_LOG", str(log))
    src = tmp_path / "src"
    src.mkdir()

    _remote.push_directory(src, "nexus:/opt/docker server/stacks")

    assert "'/opt/docker server/stacks'" in log.read_text()


# ---------------------------------------------------------------------------
# The diagnostic that sent the reader to the network
# ---------------------------------------------------------------------------


def test_a_missing_executable_is_named_as_such() -> None:
    """#897 read as `transport (FileNotFoundError)` for an hour. A missing
    program is not a network problem and needs a different fix."""
    from nexus_deploy.orchestrator import _transport_detail

    try:
        subprocess.run(["definitely-not-installed-xyz"], check=True)
    except FileNotFoundError as exc:
        detail = _transport_detail(exc)

    assert "definitely-not-installed-xyz" in detail
    assert "transport" not in detail
    assert "job image" in detail
