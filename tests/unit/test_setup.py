"""Tests for nexus_deploy.setup.

8 R-tagged invariants on the rendered ssh-config + volume-mount
script, retry-loop semantics with injected sleep + probe runner,
exec'd-bash regression tests for the volume-mount fallback chain,
and CLI rc=0/1/2 contract for all four setup subcommands.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from nexus_deploy.setup import (
    SetupError,
    SSHConfigSpec,
    SSHReadinessResult,
    configure_ssh,
    ensure_data_dirs,
    ensure_jq,
    ensure_rclone,
    render_ssh_config_block,
    strip_existing_block,
    wait_for_service_token,
    wait_for_ssh,
)


def _bash_can_be_invoked() -> bool:
    return shutil.which("bash") is not None


# ---------------------------------------------------------------------------
# render_ssh_config_block — locks the rendered ssh-config shape
# ---------------------------------------------------------------------------


def test_render_with_service_token_emits_env_proxycommand() -> None:
    """Token credentials reach the rendered block via the
    `env VAR=val cmd` ProxyCommand form (Round-2 PR #524 fix). The
    legacy `bash -c 'VAR=val cmd'` form is gone — single quotes in
    a token value would have broken the surrounding bash quoting."""
    spec = SSHConfigSpec(
        ssh_host="ssh.example.com",
        cf_client_id="client-abc",
        cf_client_secret="secret-xyz",
    )
    block = render_ssh_config_block(spec)
    assert "Host nexus" in block
    assert "HostName ssh.example.com" in block
    assert "ProxyCommand env" in block
    assert "TUNNEL_SERVICE_TOKEN_ID=client-abc" in block
    assert "TUNNEL_SERVICE_TOKEN_SECRET=secret-xyz" in block
    assert "cloudflared access ssh --hostname %h" in block
    # bash -c form must be GONE (would re-introduce the quote-injection bug).
    assert "bash -c" not in block


def test_render_with_token_containing_single_quote_is_safe() -> None:
    """Round-2 PR #524: a token with a single quote MUST round-trip
    safely through the rendered ProxyCommand. shlex.quote handles
    embedded quotes with the `'"'"'` escape pattern."""
    spec = SSHConfigSpec(
        ssh_host="ssh.example.com",
        cf_client_id="abc'def",  # injection-shaped id
        cf_client_secret="x'y",
    )
    block = render_ssh_config_block(spec)
    # The hostile values must NOT appear as bare bash text — they
    # must be wrapped in shell-safe quoting. shlex.quote of `abc'def`
    # produces `'abc'"'"'def'`.
    proxy_line = next(line for line in block.splitlines() if "ProxyCommand" in line)
    assert "'abc'" in proxy_line  # the safe-quote opener+segment
    assert """abc'def cloudflared""" not in proxy_line  # raw injection absent
    assert "TUNNEL_SERVICE_TOKEN_ID=abc'def " not in proxy_line


def test_render_without_service_token_emits_browser_login_proxycommand() -> None:
    """No-token form is the legacy browser-login path — kept for
    parity but configure_ssh raises before we'd ever write it."""
    spec = SSHConfigSpec(ssh_host="ssh.example.com")
    block = render_ssh_config_block(spec)
    assert "TUNNEL_SERVICE_TOKEN_ID" not in block
    assert "ProxyCommand cloudflared access ssh --hostname %h" in block


def test_render_block_uses_supplied_host_alias_and_identity_file() -> None:
    spec = SSHConfigSpec(
        ssh_host="ssh.example.com",
        cf_client_id="a",
        cf_client_secret="b",
        host_alias="custom-alias",
        identity_file="~/.ssh/custom_key",
    )
    block = render_ssh_config_block(spec)
    assert "Host custom-alias" in block
    assert "IdentityFile ~/.ssh/custom_key" in block


# ---------------------------------------------------------------------------
# strip_existing_block — awk-equivalent dedup
# ---------------------------------------------------------------------------


def test_strip_existing_block_removes_target_block() -> None:
    """R2 — dedup of an existing `Host nexus` block. Block ends at
    the next `Host ` line, which is preserved."""
    config = textwrap.dedent("""\
        Host other
          HostName foo
          User bar

        Host nexus
          HostName old.example.com
          User root
          IdentityFile /tmp/old

        Host another
          HostName baz
        """)
    result = strip_existing_block(config, "nexus")
    assert "old.example.com" not in result
    assert "Host other" in result
    assert "Host another" in result
    assert "HostName baz" in result


def test_strip_existing_block_idempotent_when_target_missing() -> None:
    """No-op for configs without a `Host nexus` block (matches awk)."""
    config = "Host other\n  HostName foo\n"
    assert strip_existing_block(config, "nexus") == config.rstrip()


def test_strip_existing_block_handles_target_at_end_of_file() -> None:
    """Block at EOF: skip continues until end-of-input (no following
    `Host ` boundary)."""
    config = textwrap.dedent("""\
        Host other
          HostName foo

        Host nexus
          HostName x
          User root
        """)
    result = strip_existing_block(config, "nexus")
    assert "Host nexus" not in result
    assert "Host other" in result


def test_strip_existing_block_collapses_double_blank_lines() -> None:
    """Avoid leaving two consecutive blank lines after dedup —
    snapshot-friendly invariant."""
    config = "Host nexus\n  HostName x\n\n\nHost other\n  HostName y\n"
    result = strip_existing_block(config, "nexus")
    assert "\n\n\n" not in result


# ---------------------------------------------------------------------------
# configure_ssh — atomic write + Service Token requirement
# ---------------------------------------------------------------------------


def test_configure_ssh_raises_when_service_token_missing(tmp_path: Path) -> None:
    """R6 — browser-login fallback is never written. Caller gets a
    clear SetupError instead of a silent rendered block."""
    spec = SSHConfigSpec(ssh_host="ssh.example.com")
    with pytest.raises(SetupError, match="Service Token"):
        configure_ssh(spec, ssh_config_path=tmp_path / "config")


def test_configure_ssh_writes_mode_600_atomic(tmp_path: Path) -> None:
    """R3 — file lands at mode 0o600 (no umask race window) and is
    written via atomic same-dir replace."""
    spec = SSHConfigSpec(
        ssh_host="ssh.example.com",
        cf_client_id="a",
        cf_client_secret="b",
    )
    target = tmp_path / "config"
    configure_ssh(spec, ssh_config_path=target)
    assert target.exists()
    # Mode check — strip the file-type bits, keep permission bits.
    mode = target.stat().st_mode & 0o777
    assert mode == 0o600
    # Content sanity
    content = target.read_text()
    assert "Host nexus" in content
    assert "TUNNEL_SERVICE_TOKEN_ID=a" in content


def test_configure_ssh_dedups_existing_block(tmp_path: Path) -> None:
    """Two consecutive configure_ssh calls with different secrets
    leave only ONE Host-nexus block — the second one wins. Pinned
    so a re-deploy doesn't accumulate stale ProxyCommand lines."""
    target = tmp_path / "config"
    spec1 = SSHConfigSpec(ssh_host="old.example.com", cf_client_id="a", cf_client_secret="b")
    spec2 = SSHConfigSpec(ssh_host="new.example.com", cf_client_id="a", cf_client_secret="b")
    configure_ssh(spec1, ssh_config_path=target)
    configure_ssh(spec2, ssh_config_path=target)
    content = target.read_text()
    assert content.count("Host nexus") == 1
    # Match against the full HostName-prefixed line, not bare hostname
    # substrings — strengthens the test (verifies context, not just
    # presence) AND avoids CodeQL's `py/incomplete-url-substring-
    # sanitization` false positive that flags `"x.example.com" in
    # content` as a URL-validation anti-pattern. Same intent, more
    # precise.
    assert "HostName old.example.com" not in content
    assert "HostName new.example.com" in content


def test_configure_ssh_preserves_other_host_blocks(tmp_path: Path) -> None:
    target = tmp_path / "config"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("Host github.com\n  IdentityFile ~/.ssh/id_gh\n  User git\n\n")
    spec = SSHConfigSpec(ssh_host="ssh.example.com", cf_client_id="a", cf_client_secret="b")
    configure_ssh(spec, ssh_config_path=target)
    content = target.read_text()
    assert "Host github.com" in content
    assert "IdentityFile ~/.ssh/id_gh" in content
    assert "Host nexus" in content


def test_configure_ssh_resolves_home_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round-4 PR #524: Path.home() must resolve when configure_ssh
    is CALLED, not when the module is imported. Otherwise a process
    that imports nexus_deploy.setup before HOME is set (or that
    redirects HOME mid-process for testing) gets the wrong default
    ssh-config path."""
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    spec = SSHConfigSpec(ssh_host="ssh.example.com", cf_client_id="a", cf_client_secret="b")
    # No ssh_config_path arg — defaults to Path.home() / .ssh / config
    configure_ssh(spec)
    expected = fake_home / ".ssh" / "config"
    assert expected.exists(), "default path should track HOME at call time"
    assert "Host nexus" in expected.read_text()


def test_configure_ssh_creates_parent_dir(tmp_path: Path) -> None:
    """`~/.ssh` doesn't exist yet on a fresh runner. mkdir parents
    creates it before the write."""
    target = tmp_path / "subdir" / "config"
    spec = SSHConfigSpec(ssh_host="ssh.example.com", cf_client_id="a", cf_client_secret="b")
    configure_ssh(spec, ssh_config_path=target)
    assert target.exists()
    assert target.parent.is_dir()


# ---------------------------------------------------------------------------
# wait_for_service_token + wait_for_ssh — retry-loop semantics with
# injected sleep + probe runner. R4 + R5 invariants.
# ---------------------------------------------------------------------------


def _ok_proc() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="ok\n", stderr="")


def _fail_proc(stderr: str = "Connection refused") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["ssh"], returncode=255, stdout="", stderr=stderr)


def test_wait_for_service_token_succeeds_on_first_attempt() -> None:
    """Happy path: probe returns rc=0 immediately, no further sleeps."""
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    def probe(_alias: str, _timeout: float) -> subprocess.CompletedProcess[str]:
        return _ok_proc()

    result = wait_for_service_token(probe_runner=probe, sleep=fake_sleep)
    assert result.succeeded
    assert result.attempts == 1
    # Only the initial 10s wait happens, no retry sleeps
    assert sleeps == [10.0]


def test_wait_for_service_token_linear_backoff_after_failures() -> None:
    """R4 — sleep schedule is initial 10s + 5/10/15/20/25s = 75s
    total when all 6 attempts fail. Pinned so a regression to
    constant or exponential backoff fails this test."""
    sleeps: list[float] = []
    attempts: list[int] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    def probe(_alias: str, _timeout: float) -> subprocess.CompletedProcess[str]:
        attempts.append(1)
        return _fail_proc()

    result = wait_for_service_token(probe_runner=probe, sleep=fake_sleep)
    assert not result.succeeded
    assert result.attempts == 6
    assert len(attempts) == 6
    # initial + after attempts 1,2,3,4,5 (no sleep after final attempt)
    assert sleeps == [10.0, 5.0, 10.0, 15.0, 20.0, 25.0]


def test_wait_for_service_token_succeeds_on_third_attempt() -> None:
    """Realistic case: token propagates between attempts 2 and 3."""
    sleeps: list[float] = []
    call_count = {"n": 0}

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    def probe(_alias: str, _timeout: float) -> subprocess.CompletedProcess[str]:
        call_count["n"] += 1
        return _ok_proc() if call_count["n"] >= 3 else _fail_proc()

    result = wait_for_service_token(probe_runner=probe, sleep=fake_sleep)
    assert result.succeeded
    assert result.attempts == 3
    # initial 10s + 5s after attempt 1 + 10s after attempt 2
    assert sleeps == [10.0, 5.0, 10.0]


def test_wait_for_service_token_captures_last_error_on_max_retries() -> None:
    """Diagnostic: stderr from the last failed probe lands in
    `last_error`, truncated tail-preserving."""
    long_err = "rsync: file: " + "x" * 5000 + "\nFinal line: connection lost\n"

    def probe(_alias: str, _timeout: float) -> subprocess.CompletedProcess[str]:
        return _fail_proc(stderr=long_err)

    result = wait_for_service_token(probe_runner=probe, sleep=lambda _: None)
    assert not result.succeeded
    assert len(result.last_error) <= 2000
    # Tail preserved
    assert "Final line: connection lost" in result.last_error


def test_wait_for_ssh_exponential_timeout_ramp() -> None:
    """R5 — timeout schedule: 5s for attempts 1-3, 10s for 4-7, 15s
    for 8+. Pinned via the timeout_s passed to the probe.

    Round-2 PR #524 fix: previous version expected only 2 fast
    attempts which was off-by-one against the caller's legacy schedule
    (the legacy bash bumped TIMEOUT *after* the failed attempt's
    counter increment, so RETRY=1, 2, AND 3 all stayed at 5s before
    jumping). The new expected list mirrors the legacy bash exactly.
    """
    timeouts: list[float] = []

    def probe(_alias: str, timeout_s: float) -> subprocess.CompletedProcess[str]:
        timeouts.append(timeout_s)
        return _fail_proc()

    wait_for_ssh(probe_runner=probe, sleep=lambda _: None)
    # 15 attempts: 1,2,3 → 5s; 4,5,6,7 → 10s; 8..15 → 15s
    expected = [
        5.0,
        5.0,
        5.0,
        10.0,
        10.0,
        10.0,
        10.0,
        15.0,
        15.0,
        15.0,
        15.0,
        15.0,
        15.0,
        15.0,
        15.0,
    ]
    assert timeouts == expected


def test_wait_for_ssh_succeeds_on_first_attempt() -> None:
    sleeps: list[float] = []

    def probe(_alias: str, _timeout: float) -> subprocess.CompletedProcess[str]:
        return _ok_proc()

    result = wait_for_ssh(probe_runner=probe, sleep=sleeps.append)
    assert result.succeeded
    assert result.attempts == 1
    assert sleeps == []  # no sleeps when first attempt succeeds


def test_wait_for_ssh_max_retries_returns_failure() -> None:
    def probe(_alias: str, _timeout: float) -> subprocess.CompletedProcess[str]:
        return _fail_proc(stderr="Connection refused")

    result = wait_for_ssh(probe_runner=probe, sleep=lambda _: None, max_retries=15)
    assert not result.succeeded
    assert result.attempts == 15
    assert "Connection refused" in result.last_error


# ---------------------------------------------------------------------------
# ensure_jq — idempotent install
# ---------------------------------------------------------------------------


def test_ensure_jq_returns_false_when_already_present() -> None:
    """check command returns rc=0 → no install runs."""
    ssh = MagicMock()
    ssh.run.return_value = subprocess.CompletedProcess(
        args=["ssh"], returncode=0, stdout="/usr/bin/jq\n", stderr=""
    )
    result = ensure_jq(ssh)
    assert result is False
    # Only the check ran, not the install
    ssh.run.assert_called_once()


def test_ensure_jq_installs_when_missing() -> None:
    """check command rc=1 → install runs, returns True."""
    ssh = MagicMock()
    ssh.run.side_effect = [
        subprocess.CompletedProcess(args=["ssh"], returncode=1, stdout="", stderr=""),
        subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr=""),
    ]
    result = ensure_jq(ssh)
    assert result is True
    assert ssh.run.call_count == 2


def test_ensure_rclone_returns_false_when_already_present() -> None:
    """If rclone is already installed (rc=0 from `command -v rclone`),
    skip the apt-get install."""
    ssh = MagicMock()
    ssh.run.return_value = subprocess.CompletedProcess(
        args=["ssh"], returncode=0, stdout="/usr/bin/rclone\n", stderr=""
    )
    result = ensure_rclone(ssh)
    assert result is False
    ssh.run.assert_called_once()


def test_ensure_rclone_installs_when_missing() -> None:
    """Pre-Round-6, a missing rclone caused the restore script to
    silently fresh-start (data loss on next teardown). The current
    Round-6 probe turns it into a loud rc=2, but the real fix is to
    install rclone BEFORE the probe runs. This test pins that the
    install actually happens when the binary is missing."""
    ssh = MagicMock()
    ssh.run.side_effect = [
        # `command -v rclone` → rc=1 (missing)
        subprocess.CompletedProcess(args=["ssh"], returncode=1, stdout="", stderr=""),
        # apt-get install → rc=0
        subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr=""),
    ]
    result = ensure_rclone(ssh)
    assert result is True
    assert ssh.run.call_count == 2
    # The install command must reference rclone explicitly so a
    # future refactor doesn't silently swap the package name.
    install_call = ssh.run.call_args_list[1]
    assert "rclone" in install_call.args[0]


# ---------------------------------------------------------------------------
# ensure_data_dirs — RFC 0001 cutover replacement for the chown half
# of the removed mount_persistent_volume helper.
# ---------------------------------------------------------------------------


def test_ensure_data_dirs_runs_one_script() -> None:
    """Sanity — happy path is a single SSHClient.run_script call
    that doesn't raise."""
    ssh = MagicMock()
    ssh.run_script.return_value = subprocess.CompletedProcess(
        args=["ssh"], returncode=0, stdout="", stderr=""
    )
    ensure_data_dirs(ssh)
    ssh.run_script.assert_called_once()


def test_ensure_data_dirs_script_chowns_gitea_uids() -> None:
    """The rendered script must chown the three Gitea bind-mount
    sources to their container-expected UIDs (1000:1000 for the
    git data, 70:70 for the bundled postgres). Asserts against
    the literal substrings — these UIDs are part of the
    stack-compose contract; a future change must update both."""
    ssh = MagicMock()
    ssh.run_script.return_value = subprocess.CompletedProcess(
        args=["ssh"], returncode=0, stdout="", stderr=""
    )
    ensure_data_dirs(ssh)
    rendered = ssh.run_script.call_args.args[0]
    assert "MOUNT_POINT=/mnt/nexus-data" in rendered
    assert "chown -R 1000:1000" in rendered
    assert '"$MOUNT_POINT/gitea/repos"' in rendered
    assert '"$MOUNT_POINT/gitea/lfs"' in rendered
    assert "chown -R 70:70" in rendered
    assert '"$MOUNT_POINT/gitea/db"' in rendered


def test_ensure_data_dirs_script_covers_dify_bind_mounts() -> None:
    """Round-4 PR review fix: ensure_data_dirs must also cover
    Dify's bind-mount sources. dify-db is postgres:15-alpine
    (uid 70), dify-redis is redis:6-alpine (uid 999). The other
    three Dify mounts (storage, weaviate, plugins) run as root
    inside the container — mkdir only, no chown — but they MUST
    be mkdir'd here so Docker doesn't auto-create them under the
    wrong parent perms when the bind path is missing."""
    ssh = MagicMock()
    ssh.run_script.return_value = subprocess.CompletedProcess(
        args=["ssh"], returncode=0, stdout="", stderr=""
    )
    ensure_data_dirs(ssh)
    rendered = ssh.run_script.call_args.args[0]
    # All 5 Dify bind paths get mkdir'd.
    assert '"$MOUNT_POINT/dify/db"' in rendered
    assert '"$MOUNT_POINT/dify/redis"' in rendered
    assert '"$MOUNT_POINT/dify/storage"' in rendered
    assert '"$MOUNT_POINT/dify/weaviate"' in rendered
    assert '"$MOUNT_POINT/dify/plugins"' in rendered
    # Only db (postgres) + redis get chowned to non-root UIDs.
    # The chown -R lines (the test below pins their exact UIDs).
    assert 'chown -R 70:70 "$MOUNT_POINT/dify/db"' in rendered
    assert 'chown -R 999:999 "$MOUNT_POINT/dify/redis"' in rendered


def test_ensure_data_dirs_forwards_script_stdout_to_stderr(capsys) -> None:  # type: ignore[no-untyped-def]
    """The remote script's success echo (``ensured data-dir
    ownership under /mnt/nexus-data``) must reach local stderr so
    operators see it in the workflow log. Without this, the message
    is silently dropped — same mistake docstring-vs-behavior drift
    that Copilot flagged in PR #555 round 7."""
    ssh = MagicMock()
    ssh.run_script.return_value = subprocess.CompletedProcess(
        args=["ssh"],
        returncode=0,
        stdout="ensured data-dir ownership under /mnt/nexus-data\n",
        stderr="",
    )
    ensure_data_dirs(ssh)
    captured = capsys.readouterr()
    assert "ensured data-dir ownership under /mnt/nexus-data" in captured.err


def test_ensure_data_dirs_propagates_called_process_error() -> None:
    """A failed chown is a HARD failure — a stack that comes up
    with mis-owned data dirs misbehaves silently, which is much
    harder to debug than a fail-loud abort here."""
    ssh = MagicMock()
    ssh.run_script.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["ssh"], output="chown: invalid user: 'gitea'\n"
    )
    with pytest.raises(subprocess.CalledProcessError):
        ensure_data_dirs(ssh)


@pytest.mark.skipif(not _bash_can_be_invoked(), reason="bash not on PATH")
def test_ensure_data_dirs_script_parses_under_bash() -> None:
    """`bash -n` static parse — same regression net as the old
    volume-mount script: catches syntax errors in the rendered
    template that pure substring tests would miss."""
    from nexus_deploy.setup import _ENSURE_DATA_DIRS_SCRIPT

    proc = subprocess.run(
        ["bash", "-n", "-c", _ENSURE_DATA_DIRS_SCRIPT],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# CLI rc=0/1/2 contract — direct call into _setup_* handlers
# ---------------------------------------------------------------------------


def test_cli_setup_no_subcommand_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    from nexus_deploy.__main__ import _setup

    rc = _setup([])
    assert rc == 2
    assert "subcommand required" in capsys.readouterr().err


def test_cli_setup_unknown_subcommand_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    from nexus_deploy.__main__ import _setup

    rc = _setup(["bogus"])
    assert rc == 2
    assert "unknown subcommand" in capsys.readouterr().err


def test_cli_setup_ssh_config_missing_ssh_host_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _setup_ssh_config

    monkeypatch.delenv("SSH_HOST", raising=False)
    rc = _setup_ssh_config([])
    assert rc == 2
    assert "SSH_HOST" in capsys.readouterr().err


def test_cli_setup_ssh_config_missing_token_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Service Token absent → SetupError → rc=2 (NOT a silent
    browser-login fallback)."""
    from nexus_deploy.__main__ import _setup_ssh_config

    monkeypatch.setenv("SSH_HOST", "ssh.example.com")
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    rc = _setup_ssh_config([])
    assert rc == 2
    assert "Service Token" in capsys.readouterr().err


def test_cli_setup_ssh_config_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Full happy path — env vars set, file written, rc=0."""
    from nexus_deploy.__main__ import _setup_ssh_config

    monkeypatch.setattr(
        "nexus_deploy.__main__.configure_ssh",
        lambda spec: None,  # No-op, we just verify the env-var parse + rc
    )
    monkeypatch.setenv("SSH_HOST", "ssh.example.com")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "client-abc")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "secret-xyz")
    rc = _setup_ssh_config([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Service Token" in out


def test_cli_setup_wait_ssh_token_fail_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _setup_wait_ssh

    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "a")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "b")
    monkeypatch.setattr(
        "nexus_deploy.__main__.wait_for_service_token",
        lambda **_kwargs: SSHReadinessResult(succeeded=False, attempts=6, last_error="Auth failed"),
    )
    rc = _setup_wait_ssh([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Service Token authentication failed" in err
    assert "Auth failed" in err


def test_cli_setup_wait_ssh_skips_token_when_absent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No token → only the readiness loop runs, no token-test phase."""
    from nexus_deploy.__main__ import _setup_wait_ssh

    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    token_called = {"n": 0}

    def fake_token(**_kwargs: Any) -> SSHReadinessResult:
        token_called["n"] += 1
        return SSHReadinessResult(succeeded=True, attempts=1)

    monkeypatch.setattr("nexus_deploy.__main__.wait_for_service_token", fake_token)
    monkeypatch.setattr(
        "nexus_deploy.__main__.wait_for_ssh",
        lambda **_kwargs: SSHReadinessResult(succeeded=True, attempts=1),
    )
    rc = _setup_wait_ssh([])
    assert rc == 0
    assert token_called["n"] == 0


def test_cli_setup_wait_ssh_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_deploy.__main__ import _setup_wait_ssh

    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "a")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "b")
    monkeypatch.setattr(
        "nexus_deploy.__main__.wait_for_service_token",
        lambda **_kwargs: SSHReadinessResult(succeeded=True, attempts=2),
    )
    monkeypatch.setattr(
        "nexus_deploy.__main__.wait_for_ssh",
        lambda **_kwargs: SSHReadinessResult(succeeded=True, attempts=3),
    )
    rc = _setup_wait_ssh([])
    assert rc == 0


def test_cli_setup_ensure_jq_remote_command_failure_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Round-5 PR #524: CalledProcessError now classified as
    'remote command failed' (not 'transport failure' — apt repo
    errors / dpkg lock / missing sudo are not network issues),
    AND exc.output's tail is forwarded to stderr so operators
    have actionable diagnostics. exc.cmd still NOT echoed."""
    from nexus_deploy.__main__ import _setup_ensure_jq

    class _FakeSSHContext:
        def __enter__(self) -> Any:
            return MagicMock()

        def __exit__(self, *_a: Any) -> None:
            return None

    fake_output = "E: Could not get lock /var/lib/dpkg/lock-frontend\n"

    def boom(_ssh: Any) -> bool:
        exc = subprocess.CalledProcessError(100, ["ssh", "secret-bearing-arg"])
        exc.output = fake_output
        raise exc

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", lambda _alias: _FakeSSHContext())
    monkeypatch.setattr("nexus_deploy.__main__.ensure_jq", boom)
    rc = _setup_ensure_jq([])
    assert rc == 2
    captured = capsys.readouterr()
    assert "remote command failed" in captured.err
    assert "rc=100" in captured.err
    # The actionable diagnostic must reach stderr
    assert "Could not get lock" in captured.err
    # exc.cmd must NOT leak
    assert "secret-bearing-arg" not in captured.err
    assert "secret-bearing-arg" not in captured.out


def test_cli_setup_ensure_jq_transport_failure_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """True transport failure (TimeoutExpired/OSError) keeps the
    'transport failure' label — distinct from remote-command-failed
    after Round-5 PR #524 split."""
    from nexus_deploy.__main__ import _setup_ensure_jq

    class _FakeSSHContext:
        def __enter__(self) -> Any:
            return MagicMock()

        def __exit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", lambda _alias: _FakeSSHContext())
    monkeypatch.setattr(
        "nexus_deploy.__main__.ensure_jq",
        lambda _ssh: (_ for _ in ()).throw(OSError("connection refused")),
    )
    rc = _setup_ensure_jq([])
    assert rc == 2
    captured = capsys.readouterr()
    assert "transport failure" in captured.err
    assert "OSError" in captured.err


# test_cli_setup_mount_volume_* — REMOVED in RFC 0001 cutover. The
# `nexus-deploy setup mount-volume` CLI subcommand is gone; the
# data-dir half lives in ensure_data_dirs (tested above) and runs
# from inside pipeline.run_pipeline rather than a standalone CLI
# entry point.


# ---------------------------------------------------------------------------
# Subprocess-level CLI smoke (one happy path through the real entry point)
# ---------------------------------------------------------------------------


def test_cli_subprocess_setup_unknown_returns_2() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "nexus_deploy", "setup"],
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    assert proc.returncode == 2
    assert "subcommand required" in proc.stderr


# ---------------------------------------------------------------------------
# Wetty SSH-Agent setup
# ---------------------------------------------------------------------------


def test_render_wetty_agent_script_basic_shape() -> None:
    from nexus_deploy.setup import render_wetty_agent_script

    script = render_wetty_agent_script()
    assert "set -uo pipefail" in script
    # All 5 idempotent steps present
    assert "ssh-keygen -t ed25519" in script
    assert "authorized_keys" in script
    assert "ssh-agent -a" in script
    assert "ssh-add" in script
    assert "SSH_AUTH_SOCK=" in script
    # The happy-path RESULT_WETTY line is present. Multiple
    # RESULT_WETTY lines exist in the script (each fail-fast path
    # emits its own, all-zero, then exit 0) — we just check the
    # all-success shape lands in there.
    assert "RESULT_WETTY keypair_generated=$KEYPAIR_GEN" in script


def test_render_wetty_agent_script_uses_quoted_paths() -> None:
    """Non-default paths are shlex-quoted into the rendered script."""
    from nexus_deploy.setup import render_wetty_agent_script

    script = render_wetty_agent_script(
        key_path="/tmp/with space/id_test",  # noqa: S108 — synthetic test path
        agent_socket="/tmp/sock with space.sock",  # noqa: S108
        wetty_env_file="/tmp/wetty.env",  # noqa: S108
    )
    assert "'/tmp/with space/id_test'" in script
    assert "'/tmp/sock with space.sock'" in script


def test_render_wetty_agent_script_fail_fast_on_keygen_failure() -> None:
    """R-fail-fast: ssh-keygen non-zero OR missing output files emits
    an all-zero RESULT_WETTY + exit 0. Without this, downstream steps
    would silently fail and we'd produce a misleading
    'keypair_generated=1' while Wetty can't actually SSH."""
    from nexus_deploy.setup import render_wetty_agent_script

    script = render_wetty_agent_script()
    # The fail-fast RESULT line emits all-zero flags + bails
    assert (
        "RESULT_WETTY keypair_generated=0 pubkey_added=0 agent_started=0 "
        "key_added_to_agent=0 auth_sock_written=0"
    ) in script
    # Both check paths present: ssh-keygen exit-status check + post-keygen
    # output-files-exist check
    assert "if ! ssh-keygen -t ed25519" in script
    assert '[ ! -f "$KEY_PATH" ] || [ ! -f "$KEY_PATH.pub" ]' in script


def test_render_wetty_agent_script_dead_socket_cleanup() -> None:
    """R-stale-socket: a socket file that exists but isn't responsive
    must be removed before forking a fresh agent (otherwise ssh-agent
    fails with 'address already in use')."""
    from nexus_deploy.setup import render_wetty_agent_script

    script = render_wetty_agent_script()
    assert 'if [ -S "$SOCKET" ]' in script
    # Probe + cleanup-on-dead-socket
    assert "ssh-add -l >/dev/null 2>&1 && AGENT_OK=1" in script
    assert 'rm -f "$SOCKET"' in script


def test_render_wetty_agent_script_authorized_keys_full_line_match() -> None:
    """R-pubkey-dedup (#530 R5 #2): -F (fixed string) AND -x (whole
    line) together. -F alone is a substring match — a longer line in
    authorized_keys containing $PUBKEY as substring would false-
    positive (skip the append) AND vice-versa. The actual invariant
    the comment claims is whole-line equality, which only -Fx
    delivers."""
    from nexus_deploy.setup import render_wetty_agent_script

    script = render_wetty_agent_script()
    assert 'grep -qFx "$PUBKEY" /root/.ssh/authorized_keys' in script
    # Must NOT be the substring-only -F form
    assert 'grep -qF "$PUBKEY" /root/.ssh/authorized_keys' not in script


def test_render_wetty_agent_script_strips_existing_auth_sock_line() -> None:
    """R-idempotent-env: re-runs strip any prior SSH_AUTH_SOCK= line
    before re-appending. Without this, every spin-up would leave
    multiple SSH_AUTH_SOCK= lines in wetty/.env (last-wins for
    docker-compose, but still messy)."""
    from nexus_deploy.setup import render_wetty_agent_script

    script = render_wetty_agent_script()
    assert "sed -i '/^SSH_AUTH_SOCK=/d' \"$ENV_FILE\"" in script


def test_parse_wetty_agent_result_all_changed() -> None:
    from nexus_deploy.setup import parse_wetty_agent_result

    line = (
        "RESULT_WETTY keypair_generated=1 pubkey_added=1 "
        "agent_started=1 key_added_to_agent=1 auth_sock_written=1"
    )
    result = parse_wetty_agent_result(line)
    assert result is not None
    assert result.keypair_generated is True
    assert result.pubkey_added is True
    assert result.agent_started is True
    assert result.key_added_to_agent is True
    assert result.auth_sock_written is True


def test_parse_wetty_agent_result_all_noop() -> None:
    """Idempotent re-run: every step finds nothing to do, only the
    final auth_sock write is unconditional (always 1)."""
    from nexus_deploy.setup import parse_wetty_agent_result

    line = (
        "RESULT_WETTY keypair_generated=0 pubkey_added=0 "
        "agent_started=0 key_added_to_agent=0 auth_sock_written=1"
    )
    result = parse_wetty_agent_result(line)
    assert result is not None
    assert result.keypair_generated is False
    assert result.pubkey_added is False
    assert result.agent_started is False
    assert result.key_added_to_agent is False
    assert result.auth_sock_written is True


def test_parse_wetty_agent_result_no_match_returns_none() -> None:
    from nexus_deploy.setup import parse_wetty_agent_result

    assert parse_wetty_agent_result("") is None
    assert parse_wetty_agent_result("garbage") is None
    # Wrong prefix
    assert parse_wetty_agent_result("RESULT keypair_generated=1") is None


def test_setup_wetty_ssh_agent_parses_result_via_mocked_ssh() -> None:
    """End-to-end happy-path: mocked SSHClient returns canned stdout
    with a RESULT_WETTY line; setup_wetty_ssh_agent parses it back."""
    import subprocess

    from nexus_deploy.setup import setup_wetty_ssh_agent

    class _FakeSSH:
        def run_script(
            self, _script: str, *, check: bool = False
        ) -> subprocess.CompletedProcess[str]:
            del check
            return subprocess.CompletedProcess(
                args=["ssh"],
                returncode=0,
                stdout=(
                    "RESULT_WETTY keypair_generated=1 pubkey_added=0 "
                    "agent_started=1 key_added_to_agent=1 auth_sock_written=1\n"
                ),
                stderr="",
            )

    result = setup_wetty_ssh_agent(_FakeSSH())  # type: ignore[arg-type]
    assert result is not None
    assert result.keypair_generated is True
    assert result.pubkey_added is False
    assert result.agent_started is True
    assert result.key_added_to_agent is True
    assert result.auth_sock_written is True


def test_setup_wetty_ssh_agent_returns_none_on_unparseable_stdout() -> None:
    """If the script produces no RESULT_WETTY line, the wrapper returns
    None — caller maps to rc=1 (soft failure)."""
    import subprocess

    from nexus_deploy.setup import setup_wetty_ssh_agent

    class _FakeSSH:
        def run_script(
            self, _script: str, *, check: bool = False
        ) -> subprocess.CompletedProcess[str]:
            del check
            return subprocess.CompletedProcess(
                args=["ssh"],
                returncode=0,
                stdout="some other output, no RESULT_WETTY here\n",
                stderr="",
            )

    result = setup_wetty_ssh_agent(_FakeSSH())  # type: ignore[arg-type]
    assert result is None


def test_setup_wetty_ssh_agent_propagates_transport_failure() -> None:
    """R-transport-failure-as-rc-2 (#530 R4 #1): SSH transport
    failure (rc=255, connection drop) must propagate as
    CalledProcessError so the CLI maps it to rc=2 ('transport
    failure'), not silently to None → rc=1 ('soft fail'). The
    rendered script always ends with exit 0, so a non-zero rc from
    run_script can only mean the transport broke."""
    import subprocess

    from nexus_deploy.setup import setup_wetty_ssh_agent

    class _BrokenSSH:
        def run_script(
            self, _script: str, *, check: bool = False
        ) -> subprocess.CompletedProcess[str]:
            # check=True is what the wrapper now passes; mimic the
            # behaviour of subprocess.run(check=True) on rc != 0.
            assert check is True, "wrapper must pass check=True"
            raise subprocess.CalledProcessError(
                returncode=255,
                cmd=["ssh", "nexus", "bash"],
                output="kex_exchange_identification: Connection closed",
            )

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        setup_wetty_ssh_agent(_BrokenSSH())  # type: ignore[arg-type]
    assert exc_info.value.returncode == 255


def test_render_wetty_agent_script_regenerates_on_half_present_keypair() -> None:
    """R-half-keypair (#530 R3 #4): the keygen-skip gate must check
    BOTH $KEY_PATH and $KEY_PATH.pub. If only one exists (manual
    cleanup, partial write, fs corruption), regenerate — otherwise
    a stale private key + missing .pub would yield empty PUBKEY +
    silently broken authorized_keys append."""
    from nexus_deploy.setup import render_wetty_agent_script

    script = render_wetty_agent_script()
    # Gate is OR-of-missing, not just $KEY_PATH-missing
    assert 'if [ ! -f "$KEY_PATH" ] || [ ! -f "$KEY_PATH.pub" ]; then' in script
    # Half-present case must rm -f BOTH before calling ssh-keygen
    # (ssh-keygen refuses to overwrite an existing $KEY_PATH).
    assert 'if [ -f "$KEY_PATH" ] || [ -f "$KEY_PATH.pub" ]; then' in script
    assert 'rm -f "$KEY_PATH" "$KEY_PATH.pub"' in script


def test_render_wetty_agent_script_validates_agent_responsiveness() -> None:
    """R-agent-validate (#530 R2 #1): after `ssh-agent -a SOCKET -s`
    we must validate that the spawned agent is actually responsive
    (socket present + `ssh-add -l` not rc=2). Without this validation
    a silent ssh-agent failure would still set AGENT_STARTED=1 and we'd
    falsely report success on a broken socket."""
    from nexus_deploy.setup import render_wetty_agent_script

    script = render_wetty_agent_script()
    # Must wrap the ssh-agent eval in a conditional (not `|| true`)
    assert 'if eval "$(ssh-agent -a "$SOCKET" -s)"' in script
    # Must check both the socket file AND ssh-add response
    assert 'if [ -S "$SOCKET" ] && SSH_AUTH_SOCK="$SOCKET" ssh-add -l' in script
    # rc=1 (no keys loaded) is still OK; only rc>=2 (can't connect) bails
    assert 'if [ "$ADD_RC" = "1" ]' in script


def test_render_wetty_agent_script_fail_fast_on_env_append_failure() -> None:
    """R-env-write-guarded (#530 R2 #2): the .env append must be
    conditionally guarded; on failure emit RESULT_WETTY with
    auth_sock_written=0 + bail. Legacy unconditional `>> $ENV_FILE`
    + `AUTH_SOCK_WROTE=1` lied about the write succeeding when the
    file/dir was unwritable."""
    from nexus_deploy.setup import render_wetty_agent_script

    script = render_wetty_agent_script()
    # printf must be wrapped in `if ... 2>/dev/null; then` not unconditional
    assert 'if printf \'SSH_AUTH_SOCK=%s\\n\' "$SSH_AUTH_SOCK" >> "$ENV_FILE"' in script
    # The else-branch emits a parseable RESULT_WETTY with auth_sock_written=0
    assert "auth_sock_written=0" in script


def test_render_wetty_agent_script_ssh_add_failure_leaves_key_added_zero() -> None:
    """R-ssh-add-non-fatal (#530 R2 #2 part b): ssh-add failure should
    NOT bail (key file + agent socket still exist; operator can retry)
    but MUST leave KEY_ADDED=0 so the operator sees the discrepancy
    in RESULT_WETTY rather than a misleading 1."""
    from nexus_deploy.setup import render_wetty_agent_script

    script = render_wetty_agent_script()
    # ssh-add wrapped in `if ... ; then KEY_ADDED=1` (no unconditional set)
    assert 'if ssh-add "$KEY_PATH" >/dev/null 2>&1; then' in script
    # Legacy unconditional pattern must be gone
    assert 'ssh-add "$KEY_PATH" >/dev/null 2>&1 || true' not in script


def test_render_wetty_agent_script_step_numbering_aligns_with_docstring() -> None:
    """R-step-numbering (#530 R2 #3): inline step comments use 2-6
    (not 1-5) so they align with the docstring's '1. mkdir + chmod 700'
    precondition + 'steps 2-6 produce a 0/1 in RESULT_WETTY' framing."""
    from nexus_deploy.setup import render_wetty_agent_script

    script = render_wetty_agent_script()
    assert "# Step 2: ssh-keygen" in script
    assert "# Step 3: append pubkey" in script
    assert "# Step 4: ssh-agent" in script
    assert "# Step 5: ssh-add" in script
    assert "# Step 6: write SSH_AUTH_SOCK=" in script
    # Old numbering is gone
    assert "# Step 1: ssh-keygen" not in script


def test_cli_setup_wetty_ssh_agent_returns_1_when_auth_sock_not_written(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R-soft-fail-on-missing-env-write (#530 R2 #6): when the
    fail-fast paths in render_wetty_agent_script emit a parseable
    RESULT_WETTY with auth_sock_written=0, the CLI handler must
    surface rc=1 (not rc=0). Without this, the caller would log a
    misleading 'all 5 steps ok' for a Wetty container that won't
    actually see the agent socket."""
    import subprocess as _sp

    from nexus_deploy.__main__ import _setup_wetty_ssh_agent

    class _FakeSSH:
        def __init__(self, _alias: str) -> None:
            del _alias

        def __enter__(self) -> _FakeSSH:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def run_script(self, _script: str, *, check: bool = False) -> _sp.CompletedProcess[str]:
            del check
            return _sp.CompletedProcess(
                args=["ssh"],
                returncode=0,
                stdout=(
                    "RESULT_WETTY keypair_generated=1 pubkey_added=1 "
                    "agent_started=0 key_added_to_agent=0 auth_sock_written=0\n"
                ),
                stderr="",
            )

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _FakeSSH)
    rc = _setup_wetty_ssh_agent([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "soft-fail" in err
    assert "SSH_AUTH_SOCK not written" in err


def test_cli_setup_wetty_ssh_agent_happy_path_returns_0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: auth_sock_written=1 → rc=0 even when other flags
    are mixed (idempotent re-run)."""
    import subprocess as _sp

    from nexus_deploy.__main__ import _setup_wetty_ssh_agent

    class _FakeSSH:
        def __init__(self, _alias: str) -> None:
            del _alias

        def __enter__(self) -> _FakeSSH:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def run_script(self, _script: str, *, check: bool = False) -> _sp.CompletedProcess[str]:
            del check
            return _sp.CompletedProcess(
                args=["ssh"],
                returncode=0,
                stdout=(
                    "RESULT_WETTY keypair_generated=0 pubkey_added=0 "
                    "agent_started=0 key_added_to_agent=0 auth_sock_written=1\n"
                ),
                stderr="",
            )

    monkeypatch.setattr("nexus_deploy.__main__.SSHClient", _FakeSSH)
    rc = _setup_wetty_ssh_agent([])
    assert rc == 0


def test_ensure_data_dirs_covers_the_forgejo_bind_mounts() -> None:
    """Forgejo's paths need the same treatment as Gitea's, plus one
    that Gitea does not have.

    The runner drops to uid 1001 — the upstream image's own uid — and
    `create-runner-file` cannot write `.runner` into a root-owned
    directory. Without that chown the runner restart-loops on first
    boot, so a regression removing it must not pass silently.
    """
    from unittest.mock import MagicMock

    from nexus_deploy.setup import ensure_data_dirs

    ssh = MagicMock()
    ssh.run_script.return_value = MagicMock(returncode=0, stdout="")
    ensure_data_dirs(ssh)
    rendered = ssh.run_script.call_args.args[0]

    for path in ("repos", "lfs", "db"):
        assert f'"$MOUNT_POINT/forgejo/{path}"' in rendered, path
    # The runner is a separate, opt-in stack and gets its own tree.
    assert '"$MOUNT_POINT/forgejo-runner"' in rendered

    # uid 1000 for the forge, 70 for its postgres, 1001 for the runner.
    forgejo_block = rendered.split("Forgejo bind-mount sources")[1]
    assert 'chown -R 1000:1000 "$MOUNT_POINT/forgejo/repos"' in forgejo_block
    # LFS too: restored objects land owned by the SSH user, and Forgejo
    # cannot write them back without this.
    assert '"$MOUNT_POINT/forgejo/lfs"' in forgejo_block.split("chown -R 70:70")[0]
    assert 'chown -R 70:70 "$MOUNT_POINT/forgejo/db"' in forgejo_block
    assert 'chown -R 1001:1001 "$MOUNT_POINT/forgejo-runner"' in rendered
