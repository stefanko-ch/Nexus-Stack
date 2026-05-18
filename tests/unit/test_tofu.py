"""Tests for nexus_deploy.tofu."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from nexus_deploy.tofu import (
    R2Credentials,
    TofuError,
    TofuRunner,
    load_r2_credentials,
)

# -- output_raw ---------------------------------------------------------


def test_output_raw_invokes_tofu_with_correct_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = args[0]
        captured["cwd"] = kwargs.get("cwd")
        captured["check"] = kwargs.get("check")
        captured["capture_output"] = kwargs.get("capture_output")
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="1.2.3.4", stderr="")

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    runner = TofuRunner(Path("/some/tofu/dir"))
    result = runner.output_raw("server_ip")

    assert result == "1.2.3.4"
    assert captured["argv"] == ["tofu", "output", "-raw", "server_ip"]
    assert captured["cwd"] == Path("/some/tofu/dir")
    assert captured["check"] is True
    assert captured["capture_output"] is True


def test_output_raw_default_tofu_dir_is_stack() -> None:
    """No-arg constructor uses tofu/stack — matches the canonical layout's $TOFU_DIR."""
    runner = TofuRunner()
    assert runner.tofu_dir == Path("tofu/stack")


def test_output_raw_strips_trailing_newlines_to_match_dollar_paren(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``tofu output -raw`` adds a trailing ``\\n``; the caller's ``$(...)``
    command-substitution strips it. The Python wrapper must do the same
    or downstream f-strings get a stray ``\\n`` in the middle of URLs etc.
    POSIX ``$(...)`` strips ALL trailing newlines, not just one — match
    that with ``rstrip('\\n')``.
    """

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="1.2.3.4\n\n",  # tofu adds one + extra possible
            stderr="",
        )

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    result = TofuRunner().output_raw("server_ip")
    assert result == "1.2.3.4"


def test_output_raw_preserves_internal_newlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Newlines INSIDE the value (e.g. multi-line PEM) must NOT be stripped —
    only trailing ones. Defends against an over-eager rstrip()."""

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="line1\nline2\nline3\n",  # 2 internal + 1 trailing
            stderr="",
        )

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    result = TofuRunner().output_raw("multiline_value")
    assert result == "line1\nline2\nline3"


def test_output_raw_returns_default_on_called_process_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0], stderr="no output X")

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    result = TofuRunner().output_raw("missing_output", default="0")
    assert result == "0"


def test_output_raw_returns_default_on_tofu_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "tofu")

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    result = TofuRunner().output_raw("anything", default="")
    assert result == ""


def test_output_raw_raises_when_no_default_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without default → TofuError. Distinguishes silent-fallback vs strict."""

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0])

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    with pytest.raises(TofuError, match="output -raw server_ip"):
        TofuRunner(Path("/some/dir")).output_raw("server_ip")


def test_output_raw_error_message_does_not_leak_subprocess_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TofuError text contains only name + tofu_dir, never the stderr output.

    `tofu` errors can include sensitive provider state (Cloudflare API
    tokens shown in plan diff failures, Hetzner cloud credentials in
    auth-error messages). The exception we raise on top must NOT
    re-emit subprocess.stderr, so we explicitly pin the format.
    """

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        # Simulate stderr containing a credential-looking token
        raise subprocess.CalledProcessError(
            returncode=1, cmd=args[0], stderr="provider token=eyJhb-secret-do-not-leak"
        )

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    with pytest.raises(TofuError) as excinfo:
        TofuRunner(Path("/dir")).output_raw("server_ip")
    assert "secret-do-not-leak" not in str(excinfo.value)


# -- output_json --------------------------------------------------------


def test_output_json_invokes_tofu_with_correct_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = args[0]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout='{"a": 1}', stderr="")

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    runner = TofuRunner(Path("/dir"))
    result = runner.output_json("secrets")

    assert result == {"a": 1}
    assert captured["argv"] == ["tofu", "output", "-json", "secrets"]


def test_output_json_parses_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tofu list outputs (e.g. enabled_services) parse to Python lists."""

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout='["jupyter", "marimo"]', stderr=""
        )

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    result = TofuRunner().output_json("enabled_services")
    assert result == ["jupyter", "marimo"]


def test_output_json_returns_default_on_called_process_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0])

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    result = TofuRunner().output_json("missing_output", default={})
    assert result == {}


def test_output_json_returns_default_on_tofu_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "tofu")

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    result = TofuRunner().output_json("anything", default=None)
    assert result is None


def test_output_json_returns_default_on_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tofu succeeded but stdout isn't JSON → default kicks in if provided."""

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout="not json at all", stderr=""
        )

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    result = TofuRunner().output_json("anything", default={"fallback": True})
    assert result == {"fallback": True}


def test_output_json_raises_on_invalid_json_without_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="not json", stderr="")

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    with pytest.raises(TofuError, match="returned non-JSON"):
        TofuRunner().output_json("enabled_services")


def test_output_json_raises_when_no_default_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0])

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    with pytest.raises(TofuError, match="output -json enabled_services"):
        TofuRunner(Path("/dir")).output_json("enabled_services")


def test_output_json_default_none_is_treated_as_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller passing default=None should NOT trigger raise — None is a valid default."""

    def fake_run(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0])

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    result = TofuRunner().output_json("anything", default=None)
    # Distinguishes the _MISSING sentinel from None
    assert result is None


def test_output_json_default_empty_string_is_treated_as_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty-string default is a valid silent-fallback (matches the canonical layout)."""

    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "tofu")

    monkeypatch.setattr("nexus_deploy.tofu.subprocess.run", fake_run)
    result = TofuRunner().output_raw("anything", default="")
    assert result == ""


# -- end-to-end against a real tofu-stand-in ----------------------------


def test_output_json_actually_invokes_subprocess(tmp_path: Path) -> None:
    """End-to-end against a fake `tofu` on PATH — catches subprocess.run misuse.

    Mirrors test_remote.test_ssh_run_actually_invokes_subprocess: mocked
    tests prove call-shape but don't catch combinations that raise
    ValueError before subprocess is spawned.
    """
    fake_tofu = tmp_path / "tofu"
    payload = json.dumps({"server_ip": "1.2.3.4"})
    fake_tofu.write_text(f"#!/usr/bin/env bash\nprintf %s {payload!r}\n")
    fake_tofu.chmod(0o755)

    import os

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{tmp_path}:{old_path}"
    try:
        result = TofuRunner(tmp_path).output_json("server_ip")
    finally:
        os.environ["PATH"] = old_path
    assert result == {"server_ip": "1.2.3.4"}


# ---------------------------------------------------------------------------
# state_list_ok + R2 credentials parser
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["tofu"],
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


# ---- TofuRunner.state_list_ok ----


def test_state_list_ok_false_when_dir_missing(tmp_path: Path) -> None:
    """Pre-flight: missing tofu_dir → not ok (don't even try to run)."""
    runner = TofuRunner(tmp_path / "does-not-exist")
    assert runner.state_list_ok() is False


def test_state_list_ok_true_when_state_initialized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        lambda *_a, **_kw: _completed(stdout="some.resource\n"),
    )
    assert TofuRunner(tmp_path).state_list_ok() is True


def test_state_list_ok_false_when_state_uninitialized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        lambda *_a, **_kw: _completed(stdout="", returncode=1),
    )
    assert TofuRunner(tmp_path).state_list_ok() is False


def test_state_list_ok_false_on_missing_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        MagicMock(side_effect=FileNotFoundError("tofu")),
    )
    assert TofuRunner(tmp_path).state_list_ok() is False


def test_state_list_ok_false_on_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        MagicMock(side_effect=subprocess.TimeoutExpired(["tofu"], 60.0)),
    )
    assert TofuRunner(tmp_path).state_list_ok() is False


# ---- TofuRunner.state_contains (PR #600 partial-state safety check) ----


def test_state_contains_true_when_address_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Address matches a line in `tofu state list` output → True."""
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        lambda *_a, **_kw: _completed(
            stdout="hcloud_server.main\ncloudflare_tunnel.main\ncloudflare_record.foo\n",
        ),
    )
    assert TofuRunner(tmp_path).state_contains("hcloud_server.main") is True


def test_state_contains_false_when_address_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Address NOT in state list → False."""
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        lambda *_a, **_kw: _completed(stdout="cloudflare_zero_trust_tunnel_cloudflared.main\n"),
    )
    runner = TofuRunner(tmp_path)
    assert runner.state_contains("hcloud_server.main") is False


def test_state_contains_does_not_substring_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Substring matches must not count: querying for ``hcloud`` must
    NOT match the line ``hcloud_server.main``, even when that line is
    present in state. This is the regression guard against a future
    impl that uses ``in stdout`` instead of exact-line matching —
    that bug would silently swallow real "server in state" cases under
    a query like 'hcloud' and re-introduce the data-loss vulnerability
    state_contains was added to prevent."""
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        lambda *_a, **_kw: _completed(
            stdout="hcloud_server.main\ncloudflare_record.ssh\n",
        ),
    )
    runner = TofuRunner(tmp_path)
    # Bare 'hcloud' is a substring of 'hcloud_server.main' but NOT a
    # full-line match — must return False.
    assert runner.state_contains("hcloud") is False
    # Sanity: the actual exact line still matches.
    assert runner.state_contains("hcloud_server.main") is True
    # Partial-line prefix that's a real Tofu address fragment also
    # must NOT match (the line in state is "cloudflare_record.ssh",
    # not "cloudflare_record").
    assert runner.state_contains("cloudflare_record") is False


def test_state_contains_raises_tofuerror_on_command_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The safe default for an unreachable backend is NOT silently
    returning False (would hide a resource about to be destroyed) —
    raise TofuError so the caller can decide."""
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        MagicMock(
            side_effect=subprocess.CalledProcessError(
                1, ["tofu", "state", "list"], output="", stderr="backend timeout"
            )
        ),
    )
    with pytest.raises(TofuError, match="cannot determine"):
        TofuRunner(tmp_path).state_contains("hcloud_server.main")


def test_state_contains_raises_tofuerror_on_missing_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        MagicMock(side_effect=FileNotFoundError("tofu")),
    )
    with pytest.raises(TofuError, match="cannot determine"):
        TofuRunner(tmp_path).state_contains("hcloud_server.main")


def test_state_contains_raises_tofuerror_on_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        MagicMock(side_effect=subprocess.TimeoutExpired(["tofu"], 60.0)),
    )
    with pytest.raises(TofuError, match="timed out"):
        TofuRunner(tmp_path).state_contains("hcloud_server.main")


# ---- TofuRunner.diagnose_state (PR #535 R2 #2) ----


def test_diagnose_state_returns_none_when_initialized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        lambda *_a, **_kw: _completed(stdout="some.resource\n"),
    )
    assert TofuRunner(tmp_path).diagnose_state() is None


def test_diagnose_state_directory_missing(tmp_path: Path) -> None:
    runner = TofuRunner(tmp_path / "nope")
    reason = runner.diagnose_state()
    assert reason is not None
    assert "directory not found" in reason


def test_diagnose_state_binary_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        MagicMock(side_effect=FileNotFoundError("tofu")),
    )
    reason = TofuRunner(tmp_path).diagnose_state()
    assert reason == "tofu binary not found on PATH"


def test_diagnose_state_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        MagicMock(side_effect=subprocess.TimeoutExpired(["tofu"], 60.0)),
    )
    reason = TofuRunner(tmp_path).diagnose_state()
    assert reason is not None
    assert "timed out" in reason


def test_diagnose_state_includes_stderr_tail_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Auth/backend failures (rc!=0) → reason carries stderr tail."""
    completed = subprocess.CompletedProcess(
        args=["tofu"],
        returncode=1,
        stdout="",
        stderr="Error: Backend configuration changed: AWS credentials invalid\n",
    )
    monkeypatch.setattr(
        "nexus_deploy.tofu.subprocess.run",
        lambda *_a, **_kw: completed,
    )
    reason = TofuRunner(tmp_path).diagnose_state()
    assert reason is not None
    assert "rc=1" in reason
    assert "AWS credentials invalid" in reason


# ---- load_r2_credentials ----


def test_load_r2_credentials_returns_none_when_file_missing(tmp_path: Path) -> None:
    """Legitimate skip — local-dev / CI without R2 backend."""
    assert load_r2_credentials(tmp_path / "does-not-exist") is None


def test_load_r2_credentials_parses_quoted_values(tmp_path: Path) -> None:
    creds_file = tmp_path / ".r2-credentials"
    creds_file.write_text(
        'R2_ACCESS_KEY_ID="abc123"\nR2_SECRET_ACCESS_KEY="def456"\n',
        encoding="utf-8",
    )
    assert load_r2_credentials(creds_file) == R2Credentials(
        access_key_id="abc123",
        secret_access_key="def456",
    )


def test_load_r2_credentials_parses_unquoted_values(tmp_path: Path) -> None:
    """Tolerant: hand-edited file without quotes still works."""
    creds_file = tmp_path / ".r2-credentials"
    creds_file.write_text(
        "R2_ACCESS_KEY_ID=abc\nR2_SECRET_ACCESS_KEY=def\n",
        encoding="utf-8",
    )
    assert load_r2_credentials(creds_file) == R2Credentials(
        access_key_id="abc",
        secret_access_key="def",
    )


def test_load_r2_credentials_tolerates_whitespace_around_equals(tmp_path: Path) -> None:
    creds_file = tmp_path / ".r2-credentials"
    creds_file.write_text(
        'R2_ACCESS_KEY_ID = "abc"\nR2_SECRET_ACCESS_KEY  =  "def"\n',
        encoding="utf-8",
    )
    parsed = load_r2_credentials(creds_file)
    assert parsed is not None
    assert parsed.access_key_id == "abc"
    assert parsed.secret_access_key == "def"


def test_load_r2_credentials_raises_when_one_key_missing(tmp_path: Path) -> None:
    """File present but malformed → raise. Silent skip would mask
    the operator error and surface as 'tofu state inaccessible' 30
    seconds later."""
    creds_file = tmp_path / ".r2-credentials"
    creds_file.write_text('R2_ACCESS_KEY_ID="abc"\n', encoding="utf-8")
    with pytest.raises(TofuError, match="missing R2_"):
        load_r2_credentials(creds_file)


def test_load_r2_credentials_raises_when_both_keys_missing(tmp_path: Path) -> None:
    creds_file = tmp_path / ".r2-credentials"
    creds_file.write_text("# just a comment\n", encoding="utf-8")
    with pytest.raises(TofuError, match="missing R2_"):
        load_r2_credentials(creds_file)


def test_load_r2_credentials_raises_on_unreadable_file(tmp_path: Path) -> None:
    creds_file = tmp_path / ".r2-credentials"
    creds_file.write_text("R2_ACCESS_KEY_ID=a\nR2_SECRET_ACCESS_KEY=b\n", encoding="utf-8")
    with (
        patch.object(Path, "read_text", side_effect=PermissionError("denied")),
        pytest.raises(TofuError, match="could not read"),
    ):
        load_r2_credentials(creds_file)


def test_load_r2_credentials_ignores_extra_keys(tmp_path: Path) -> None:
    """Forward-compat: a future contributor adding R2_ENDPOINT or
    similar shouldn't break the parser."""
    creds_file = tmp_path / ".r2-credentials"
    creds_file.write_text(
        'R2_ACCESS_KEY_ID="a"\nR2_SECRET_ACCESS_KEY="b"\nR2_ENDPOINT="https://r2.example"\n',
        encoding="utf-8",
    )
    assert load_r2_credentials(creds_file) == R2Credentials(
        access_key_id="a",
        secret_access_key="b",
    )


def test_r2_credentials_frozen() -> None:
    from dataclasses import FrozenInstanceError

    creds = R2Credentials(access_key_id="a", secret_access_key="b")
    with pytest.raises(FrozenInstanceError):
        creds.access_key_id = "other"  # type: ignore[misc]
