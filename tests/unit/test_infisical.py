"""Tests for nexus_deploy.infisical.

Covers:
- skip-empty rule (#504 contract: preserve operator UI edits)
- folder list + per-folder key list are emitted in a stable source-order
- payload JSON shape (folder + secrets-batch upsert)
- adversarial token quoting in the remote bash loop
- end-to-end bootstrap with mocked ssh/rsync runners
- snapshot of compute_folders output for a fully-populated config
- CLI integration: `infisical bootstrap` reads stdin + env vars
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion

from nexus_deploy.config import NexusConfig
from nexus_deploy.infisical import (
    BootstrapEnv,
    BootstrapResult,
    FolderSpec,
    InfisicalClient,
    _filter_empty,
    compute_folders,
    parse_provision_result,
    provision_admin,
    render_provision_admin_script,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ---------------------------------------------------------------------------
# _filter_empty — skip-empty rule
# ---------------------------------------------------------------------------


def test_filter_empty_drops_none() -> None:
    assert _filter_empty({"K": None, "L": "v"}) == {"L": "v"}


def test_filter_empty_drops_empty_string() -> None:
    assert _filter_empty({"K": "", "L": "v"}) == {"L": "v"}


def test_filter_empty_keeps_whitespace() -> None:
    """A single space is a valid value (some configs use ' ' as a sentinel)."""
    assert _filter_empty({"K": " ", "L": "v"}) == {"K": " ", "L": "v"}


def test_filter_empty_preserves_input_order() -> None:
    items = {"C": "1", "A": "2", "B": "3"}
    assert list(_filter_empty(items)) == ["C", "A", "B"]


# ---------------------------------------------------------------------------
# FolderSpec — payload shapes
# ---------------------------------------------------------------------------


def test_folder_payload_shape() -> None:
    spec = FolderSpec("kestra", {"K": "v"})
    assert spec.folder_payload("proj-1", "dev") == {
        "projectId": "proj-1",
        "environment": "dev",
        "name": "kestra",
        "path": "/",
    }


def test_secrets_payload_shape() -> None:
    spec = FolderSpec("kestra", {"K1": "v1", "K2": "v2"})
    assert spec.secrets_payload("proj-1", "dev") == {
        "projectId": "proj-1",
        "environment": "dev",
        "secretPath": "/kestra",
        "mode": "upsert",
        "secrets": [
            {"secretKey": "K1", "secretValue": "v1"},
            {"secretKey": "K2", "secretValue": "v2"},
        ],
    }


def test_secrets_payload_preserves_secret_order() -> None:
    """Source-order matches the canonical layout's jq filter (sequential `secretKey: $kN`)."""
    spec = FolderSpec("dify", {"DIFY_USERNAME": "u", "DIFY_PASSWORD": "p", "DIFY_DB_PASSWORD": "d"})
    payload = spec.secrets_payload("p", "e")
    secrets = payload["secrets"]
    assert isinstance(secrets, list)
    keys = [s["secretKey"] for s in secrets]
    assert keys == ["DIFY_USERNAME", "DIFY_PASSWORD", "DIFY_DB_PASSWORD"]


# ---------------------------------------------------------------------------
# compute_folders — schema + ordering + conditional gates
# ---------------------------------------------------------------------------


def _make_config(**overrides: str) -> NexusConfig:
    return NexusConfig.from_secrets_json(json.dumps(overrides))


def test_compute_folders_minimal_emits_unconditional_only() -> None:
    """Empty config + minimal env → no R2/Hetzner-S3/External-S3/SSH folders."""
    folders = compute_folders(NexusConfig.from_secrets_json("{}"), BootstrapEnv())
    names = [f.name for f in folders]
    # Conditional folders absent
    assert "r2-datalake" not in names
    assert "hetzner-s3" not in names
    assert "external-s3" not in names
    assert "ssh" not in names
    # Unconditional core present
    for required in ("config", "infisical", "kestra", "gitea", "forgejo", "woodpecker"):
        assert required in names


def test_compute_folders_r2_gate() -> None:
    """All four r2_* fields must be present for the r2-datalake folder."""
    config = _make_config(
        r2_data_endpoint="ep",
        r2_data_access_key="ak",
        r2_data_secret_key="sk",
        # missing r2_data_bucket
    )
    folders = compute_folders(config, BootstrapEnv())
    assert "r2-datalake" not in [f.name for f in folders]

    config = _make_config(
        r2_data_endpoint="ep",
        r2_data_access_key="ak",
        r2_data_secret_key="sk",
        r2_data_bucket="bk",
    )
    folders = compute_folders(config, BootstrapEnv())
    r2 = next(f for f in folders if f.name == "r2-datalake")
    assert r2.secrets == {
        "R2_ENDPOINT": "ep",
        "R2_ACCESS_KEY": "ak",
        "R2_SECRET_KEY": "sk",
        "R2_BUCKET": "bk",
    }


def test_compute_folders_hetzner_default_bucket_chain() -> None:
    """HETZNER_S3_BUCKET prefers _general, falls back to _lakefs."""
    base = {
        "hetzner_s3_server": "s3.example",
        "hetzner_s3_access_key": "ak",
        "hetzner_s3_secret_key": "sk",
    }
    folders = compute_folders(_make_config(**base, hetzner_s3_bucket_general="g"), BootstrapEnv())
    h = next(f for f in folders if f.name == "hetzner-s3")
    assert h.secrets["HETZNER_S3_BUCKET"] == "g"

    folders = compute_folders(
        _make_config(**base, hetzner_s3_bucket_lakefs="l"),
        BootstrapEnv(),
    )
    h = next(f for f in folders if f.name == "hetzner-s3")
    assert h.secrets["HETZNER_S3_BUCKET"] == "l"

    folders = compute_folders(
        _make_config(**base, hetzner_s3_bucket_general="g", hetzner_s3_bucket_lakefs="l"),
        BootstrapEnv(),
    )
    h = next(f for f in folders if f.name == "hetzner-s3")
    assert h.secrets["HETZNER_S3_BUCKET"] == "g"


def test_compute_folders_skip_empty_drops_optional_keys() -> None:
    """A folder builder skips per-key None/empty values (preserves UI edits)."""
    folders = compute_folders(NexusConfig.from_secrets_json("{}"), BootstrapEnv(domain="x.test"))
    config_folder = next(f for f in folders if f.name == "config")
    assert config_folder.secrets == {"DOMAIN": "x.test", "ADMIN_USERNAME": "admin"}
    # ADMIN_EMAIL absent → not in payload


def test_compute_folders_woodpecker_oauth_optional() -> None:
    folders = compute_folders(
        _make_config(woodpecker_agent_secret="s"),
        BootstrapEnv(),
    )
    w = next(f for f in folders if f.name == "woodpecker")
    assert w.secrets == {"WOODPECKER_AGENT_SECRET": "s"}

    folders = compute_folders(
        _make_config(woodpecker_agent_secret="s"),
        BootstrapEnv(woodpecker_forgejo_client="cid", woodpecker_forgejo_secret="csec"),
    )
    w = next(f for f in folders if f.name == "woodpecker")
    assert w.secrets == {
        "WOODPECKER_AGENT_SECRET": "s",
        "WOODPECKER_FORGEJO_CLIENT": "cid",
        "WOODPECKER_FORGEJO_SECRET": "csec",
    }


def test_compute_folders_ssh_optional() -> None:
    folders = compute_folders(NexusConfig.from_secrets_json("{}"), BootstrapEnv())
    assert "ssh" not in [f.name for f in folders]

    folders = compute_folders(
        NexusConfig.from_secrets_json("{}"),
        BootstrapEnv(ssh_private_key_base64="b64-key"),
    )
    ssh = next(f for f in folders if f.name == "ssh")
    assert ssh.secrets == {"SSH_PRIVATE_KEY_BASE64": "b64-key"}


def test_compute_folders_public_repo_url_falls_back_to_default_repo_name() -> None:
    """`${REPO_NAME:-nexus-${DOMAIN//./-}-workspace}` mirror.

    The URL lives in the forgejo folder: Forgejo hosts the workspace
    repo now, and it points at git-proxy because that is the only
    endpoint a git client can reach without an Access browser login.
    """
    config = _make_config(admin_username="bob")
    folders = compute_folders(config, BootstrapEnv(domain="ex.example.com"))
    forgejo = next(f for f in folders if f.name == "forgejo")
    assert (
        forgejo.secrets["FORGEJO_REPO_URL_PUBLIC"]
        == "https://git.ex.example.com/bob/nexus-ex-example-com-workspace.git"
    )


def test_compute_folders_full_snapshot(snapshot: SnapshotAssertion) -> None:
    """Lock the entire folder list + ordering + per-folder keys.

    Uses the ``secrets_full.json`` fixture (88 fields populated) so any
    accidental reordering or skipped key surfaces as a snapshot diff.
    """
    raw = (FIXTURES / "secrets_full.json").read_text()
    config = NexusConfig.from_secrets_json(raw)
    env = BootstrapEnv(
        domain="snapshot.test",
        admin_email="admin@snapshot.test",
        forgejo_user_email="user@snapshot.test",
        forgejo_user_username="snapshot-user",
        forgejo_repo_owner="snapshot-org",
        repo_name="snapshot-repo",
        om_principal_domain="snapshot.test",
        woodpecker_forgejo_client="cid",
        woodpecker_forgejo_secret="csec",
        ssh_private_key_base64="snapshot-ssh-base64",
    )
    folders = compute_folders(config, env)
    assert {f.name: f.secrets for f in folders} == snapshot


# ---------------------------------------------------------------------------
# InfisicalClient — payload encoding + remote-loop bash
# ---------------------------------------------------------------------------


def test_encode_payloads_round_trip() -> None:
    client = InfisicalClient("p", "dev", "tok")
    folders = [FolderSpec("kestra", {"K": "v"})]
    encoded = client.encode_payloads(folders)
    f_payload = json.loads(encoded["f-kestra.json"])
    s_payload = json.loads(encoded["s-kestra.json"])
    assert f_payload == folders[0].folder_payload("p", "dev")
    assert s_payload == folders[0].secrets_payload("p", "dev")


def test_encode_payloads_compact() -> None:
    """No whitespace between JSON tokens — matches `json.dumps(..., separators=(',',':'))`."""
    client = InfisicalClient("p", "dev", "tok")
    encoded = client.encode_payloads([FolderSpec("k", {"X": "1"})])
    assert " " not in encoded["s-k.json"]


def test_remote_loop_quotes_token_safely(tmp_path: Path) -> None:
    """Adversarial token can't break out of the bash structure.

    Eval-extracts only the ``TOKEN=`` assignment from the generated
    loop and verifies the resolved bash variable equals the original
    payload — confirming that the quoting in :meth:`_build_remote_loop`
    survives an attempt to use ``';rm -rf /;echo '`` to escape and
    inject commands. Side-channel canary in tmp_path catches any
    accidental execution of the injection payload.
    """
    canary_dir = tmp_path / "canary"
    canary_dir.mkdir()
    canary = canary_dir / "INJECTED"
    nasty = f"tok';touch {shlex.quote(str(canary))};echo '"
    client = InfisicalClient("p", "dev", nasty)
    loop = client._build_remote_loop()
    # Extract just the TOKEN= line. Eval-running the full loop would
    # reach the curl + rm -rf in the loop body; isolating the assignment
    # is enough to prove the quoting holds. We also force the
    # token-fallback file to a path that doesn't exist so the OR-fallback
    # branch fires and we exercise the shlex.quote'd token literal.
    token_line = next(line for line in loop.splitlines() if line.startswith("TOKEN=$(cat"))
    completed = subprocess.run(
        [
            "bash",
            "-c",
            f'{token_line.replace("/opt/docker-server/.infisical-token", "/nonexistent")}\nprintf "%s" "$TOKEN"',
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    assert completed.stdout == nasty
    assert not canary.exists(), "shlex.quote breach: injection payload executed"


# ---------------------------------------------------------------------------
# bootstrap() — end-to-end with mocked ssh/rsync
# ---------------------------------------------------------------------------


def _ok_ssh(stdout: str = "5:0") -> Any:
    def runner(_cmd: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=stdout, stderr="")

    return runner


def _ok_rsync() -> Any:
    def runner(_local: Path, _remote: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["rsync"], returncode=0, stdout="", stderr="")

    return runner


def test_bootstrap_writes_payloads_with_restrictive_perms(tmp_path: Path) -> None:
    """Payload files contain secret values — must be 0600 / dir 0700.

    Default umask on shared CI runners (0o022) would yield 0644 files,
    which is group/world-readable. We explicitly chmod to override.
    """
    push_dir = tmp_path / "push"
    client = InfisicalClient("p", "dev", "tok", push_dir=push_dir)

    captured_modes: dict[str, int] = {}

    def inspect_rsync(local: Path, _remote: str) -> subprocess.CompletedProcess[str]:
        # Inspect modes inside the rsync callback — payloads are
        # cleaned up by the finally block, so this is the only point
        # where they're observable.
        captured_modes["dir"] = local.stat().st_mode & 0o777
        for f in sorted(local.glob("[fs]-*.json")):
            captured_modes[f.name] = f.stat().st_mode & 0o777
        return subprocess.CompletedProcess(args=["rsync"], returncode=0, stdout="", stderr="")

    client.bootstrap(
        [FolderSpec("kestra", {"K": "v"})],
        ssh_runner=_ok_ssh(),
        rsync_runner=inspect_rsync,
    )
    assert captured_modes["dir"] == 0o700
    assert captured_modes["f-kestra.json"] == 0o600
    assert captured_modes["s-kestra.json"] == 0o600


def test_bootstrap_removes_local_payloads_on_success(tmp_path: Path) -> None:
    """After a successful bootstrap, the local f-/s-*.json files are gone.

    The bootstrap is responsible for removing its own ``$PUSH_DIR``
    payloads — they contain secret values and leaving them on the
    runner is a secrets-at-rest leak.
    """
    push_dir = tmp_path / "push"
    client = InfisicalClient("p", "dev", "tok", push_dir=push_dir)
    folders = [FolderSpec("kestra", {"K": "v"})]
    client.bootstrap(folders, ssh_runner=_ok_ssh(), rsync_runner=_ok_rsync())
    assert list(push_dir.glob("[fs]-*.json")) == []


def test_bootstrap_cleans_up_when_write_fails_mid_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure during payload-writing must NOT leave half-written secrets behind.

    The previous implementation only wrapped rsync+ssh in try/finally;
    a disk-full / permission error during the write loop would leave
    already-created f-/s-*.json files in push_dir with secret values.
    Now the whole materialise+push path is inside the try/finally.
    """
    push_dir = tmp_path / "push"
    client = InfisicalClient("p", "dev", "tok", push_dir=push_dir)

    # Force os.open to fail on the SECOND payload — by which point the
    # first one has already been written and contains secret values.
    real_os_open = os.open
    call_count = {"n": 0}

    def flaky_open(*args: Any, **kwargs: Any) -> int:
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise PermissionError("simulated mid-loop disk failure")
        return real_os_open(*args, **kwargs)

    monkeypatch.setattr("nexus_deploy.infisical.os.open", flaky_open)
    folders = [FolderSpec("first", {"K": "v1"}), FolderSpec("second", {"K": "v2"})]
    with pytest.raises(PermissionError):
        client.bootstrap(folders, ssh_runner=_ok_ssh(), rsync_runner=_ok_rsync())
    # finally clause must have removed the first-folder file
    assert list(push_dir.glob("[fs]-*.json")) == []


def test_bootstrap_removes_local_payloads_on_failure(tmp_path: Path) -> None:
    """Cleanup runs in `finally` — even when ssh raises, payloads are gone."""
    push_dir = tmp_path / "push"
    client = InfisicalClient("p", "dev", "tok", push_dir=push_dir)

    def failing_ssh(_cmd: str) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, ["ssh"])

    folders = [FolderSpec("kestra", {"K": "v"})]
    with pytest.raises(subprocess.CalledProcessError):
        client.bootstrap(folders, ssh_runner=failing_ssh, rsync_runner=_ok_rsync())
    assert list(push_dir.glob("[fs]-*.json")) == []


def test_bootstrap_cleanup_preserves_unrelated_files(tmp_path: Path) -> None:
    """Only f-*.json + s-*.json get removed; unrelated files stay."""
    push_dir = tmp_path / "push"
    push_dir.mkdir()
    (push_dir / "operator-notes.txt").write_text("keep me")
    client = InfisicalClient("p", "dev", "tok", push_dir=push_dir)
    client.bootstrap(
        [FolderSpec("kestra", {"K": "v"})],
        ssh_runner=_ok_ssh(),
        rsync_runner=_ok_rsync(),
    )
    assert (push_dir / "operator-notes.txt").exists()


def test_remote_loop_counts_curl_transport_failure_as_fail() -> None:
    """Legacy bash miscounted curl transport failures (rc != 0) as OK.

    The current loop checks ``CURL_RC`` after each PATCH and treats any
    non-zero exit as FAIL — fixing a long-standing legacy bug while
    keeping the OK:FAIL output format unchanged.
    """
    client = InfisicalClient("p", "dev", "tok")
    loop = client._build_remote_loop()
    # The relevant guard
    assert "CURL_RC=$?" in loop
    assert '[ "$CURL_RC" -ne 0 ]' in loop
    # And the original error-substring check is still part of the OR
    assert "grep -q '\"error\"'" in loop


def test_remote_loop_uses_printf_not_echo_for_token() -> None:
    """`echo` would mangle tokens starting with `-n`/`-e`/`-E`. printf doesn't."""
    client = InfisicalClient("p", "dev", "tok-value")
    loop = client._build_remote_loop()
    # Token comes via printf, never via echo
    assert "printf '%s' " in loop
    # Specifically, the fallback line uses printf
    fallback_line = next(line for line in loop.splitlines() if "TOKEN=$(cat" in line)
    assert "echo " not in fallback_line


def test_bootstrap_writes_payloads_before_rsync(tmp_path: Path) -> None:
    """bootstrap() materialises both f-NAME.json and s-NAME.json per folder.

    Files are deleted in the finally block (secrets-at-rest cleanup),
    so this test inspects the push_dir state INSIDE the mocked rsync
    callback — the moment rsync would see them on a real run.
    """
    push_dir = tmp_path / "push"
    client = InfisicalClient("p", "dev", "tok", push_dir=push_dir)
    folders = [FolderSpec("kestra", {"K": "v"}), FolderSpec("postgres", {"P": "1"})]

    seen: dict[str, list[str]] = {"files": []}

    def inspect_rsync(local: Path, _remote: str) -> subprocess.CompletedProcess[str]:
        seen["files"] = sorted(p.name for p in local.glob("*.json"))
        return subprocess.CompletedProcess(args=["rsync"], returncode=0, stdout="", stderr="")

    client.bootstrap(folders, ssh_runner=_ok_ssh(), rsync_runner=inspect_rsync)
    assert seen["files"] == [
        "f-kestra.json",
        "f-postgres.json",
        "s-kestra.json",
        "s-postgres.json",
    ]


def test_bootstrap_clears_stale_payloads(tmp_path: Path) -> None:
    """Pre-existing f-/s- files from a prior run are removed before write."""
    push_dir = tmp_path / "push"
    push_dir.mkdir()
    (push_dir / "f-stale.json").write_text("stale")
    (push_dir / "s-stale.json").write_text("stale")
    (push_dir / "unrelated.txt").write_text("keep me")
    client = InfisicalClient("p", "dev", "tok", push_dir=push_dir)
    client.bootstrap(
        [FolderSpec("new", {"K": "v"})],
        ssh_runner=_ok_ssh(),
        rsync_runner=_ok_rsync(),
    )
    assert not (push_dir / "f-stale.json").exists()
    assert not (push_dir / "s-stale.json").exists()
    # Non-payload files are NOT touched
    assert (push_dir / "unrelated.txt").exists()


def test_bootstrap_parses_ok_fail_counts(tmp_path: Path) -> None:
    client = InfisicalClient("p", "dev", "tok", push_dir=tmp_path / "p")
    result = client.bootstrap(
        [FolderSpec("k", {"X": "v"})],
        ssh_runner=_ok_ssh("3:1"),
        rsync_runner=_ok_rsync(),
    )
    assert result == BootstrapResult(folders_built=1, pushed=3, failed=1)


def test_bootstrap_takes_last_line_of_stdout(tmp_path: Path) -> None:
    """The remote bash may emit a baseline-capture ``WARN`` message
    before the trailing ``OK:FAIL`` line; the parser must take the
    last line, not the first."""
    client = InfisicalClient("p", "dev", "tok", push_dir=tmp_path / "p")
    result = client.bootstrap(
        [FolderSpec("k", {"X": "v"})],
        ssh_runner=_ok_ssh("WARN: capture failed\n7:2"),
        rsync_runner=_ok_rsync(),
    )
    assert result.pushed == 7
    assert result.failed == 2


def test_bootstrap_unparseable_output_yields_failure(tmp_path: Path) -> None:
    client = InfisicalClient("p", "dev", "tok", push_dir=tmp_path / "p")
    folders = [FolderSpec("k", {"X": "v"}), FolderSpec("p", {"Y": "v"})]
    result = client.bootstrap(
        folders, ssh_runner=_ok_ssh("garbage output"), rsync_runner=_ok_rsync()
    )
    assert result == BootstrapResult(folders_built=2, pushed=0, failed=2)


def test_bootstrap_invokes_rsync_with_push_dir(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_rsync(local: Path, remote: str) -> subprocess.CompletedProcess[str]:
        captured["local"] = local
        captured["remote"] = remote
        return subprocess.CompletedProcess(args=["rsync"], returncode=0, stdout="", stderr="")

    push_dir = tmp_path / "push"
    client = InfisicalClient("p", "dev", "tok", push_dir=push_dir)
    client.bootstrap([FolderSpec("k", {"X": "v"})], ssh_runner=_ok_ssh(), rsync_runner=fake_rsync)
    assert captured["local"] == push_dir
    assert captured["remote"] == "nexus:/tmp/infisical-push/"


def test_bootstrap_runs_ssh_loop_with_token(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_ssh(cmd: str) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="0:0", stderr="")

    client = InfisicalClient("p", "dev", "real-token", push_dir=tmp_path / "p")
    client.bootstrap([FolderSpec("k", {"X": "v"})], ssh_runner=fake_ssh, rsync_runner=_ok_rsync())
    cmd = captured["cmd"]
    assert "real-token" in cmd
    assert "/api/v2/folders" in cmd
    assert "/api/v4/secrets/batch" in cmd
    assert 'mode: "upsert"' not in cmd  # the JSON is sent via @file, not inlined
    # Token-fallback file logic preserved
    assert "/opt/docker-server/.infisical-token" in cmd


# ---------------------------------------------------------------------------
# CLI: `nexus-deploy infisical bootstrap`
# ---------------------------------------------------------------------------


def test_cli_infisical_bootstrap_requires_project_id_and_token(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing required env → rc=2 (hard fail; the orchestrator aborts the deploy)."""
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "infisical", "bootstrap"])
    monkeypatch.setattr(sys, "stdin", _StubStdin("{}"))
    # Strip both required vars
    monkeypatch.delenv("PROJECT_ID", raising=False)
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "PROJECT_ID and INFISICAL_TOKEN" in captured.err


def test_cli_infisical_bootstrap_unexpected_arg_returns_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "infisical", "bootstrap", "--bogus"])
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "unexpected arg" in captured.err


def test_cli_infisical_bootstrap_invalid_json_exits_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid SECRETS_JSON on stdin → rc=2 (hard fail)."""
    from nexus_deploy.__main__ import main

    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "infisical", "bootstrap"])
    monkeypatch.setattr(sys, "stdin", _StubStdin("not-json"))
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.setenv("INFISICAL_TOKEN", "t")
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "not valid JSON" in captured.err


def test_cli_infisical_bootstrap_happy_path(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """End-to-end CLI exercise with mocked SSH/rsync — rc=0 on full success."""
    from nexus_deploy.__main__ import main

    push_dir = tmp_path / "push"

    def fake_ssh(_script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="3:0", stderr="")

    def fake_rsync(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["rsync"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy._remote.ssh_run_script", fake_ssh)
    monkeypatch.setattr("nexus_deploy._remote.rsync_to_remote", fake_rsync)
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "infisical", "bootstrap"])
    monkeypatch.setattr(sys, "stdin", _StubStdin('{"admin_username": "u"}'))
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.setenv("INFISICAL_TOKEN", "t")
    monkeypatch.setenv("DOMAIN", "ex.test")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@ex.test")
    monkeypatch.setenv("PUSH_DIR", str(push_dir))
    rc = main()
    captured = capsys.readouterr()
    assert rc == 0
    assert "pushed=3" in captured.out
    assert "failed=0" in captured.out


def test_cli_infisical_bootstrap_partial_failure_returns_1(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """API-reported partial failure (folder errors) → rc=1; the orchestrator
    surfaces this as a partial PhaseResult and continues the deploy."""
    from nexus_deploy.__main__ import main

    def fake_ssh(_script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="2:1", stderr="")

    def fake_rsync(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["rsync"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nexus_deploy._remote.ssh_run_script", fake_ssh)
    monkeypatch.setattr("nexus_deploy._remote.rsync_to_remote", fake_rsync)
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "infisical", "bootstrap"])
    monkeypatch.setattr(sys, "stdin", _StubStdin("{}"))
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.setenv("INFISICAL_TOKEN", "t")
    monkeypatch.setenv("PUSH_DIR", str(tmp_path / "push"))
    rc = main()
    _ = capsys.readouterr()
    assert rc == 1


def test_cli_infisical_bootstrap_unexpected_exception_returns_2(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A non-transport exception (e.g. KeyError from a bug in compute_folders)
    must surface as rc=2, NOT rc=1.

    Python's default unhandled-exception exit code is 1, which would
    collide with the "partial push" semantic the orchestrator uses
    for soft-fail Infisical results and cause the deploy to continue
    past a broken bootstrap. The broad ``except Exception`` in the
    CLI re-routes that to rc=2.

    Also asserts: the exception's ``str(exc)`` / ``repr(exc)`` contents
    must NOT surface in stderr — those can carry attribute values from
    pydantic ValidationError that include secret-bearing fields.
    """
    from nexus_deploy.__main__ import main

    secret_payload = "very-secret-value-must-not-appear-in-output"

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise KeyError(secret_payload)

    monkeypatch.setattr("nexus_deploy.__main__.compute_folders", boom)
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "infisical", "bootstrap"])
    monkeypatch.setattr(sys, "stdin", _StubStdin("{}"))
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.setenv("INFISICAL_TOKEN", "t")
    monkeypatch.setenv("PUSH_DIR", str(tmp_path / "push"))
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "unexpected error (KeyError)" in captured.err
    # Defence-in-depth: the exception's args must not leak — only the
    # class name surfaces in the formatted message.
    assert secret_payload not in captured.err
    assert secret_payload not in captured.out


def test_cli_infisical_bootstrap_transport_failure_returns_2(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """rsync/ssh transport failure (CalledProcessError, etc.) → rc=2; the caller aborts.

    We must NOT pass through the underlying CalledProcessError because
    its ``cmd`` attribute carries the full argv — and even though we
    moved the token to stdin, defence-in-depth: never let
    bootstrap-internal exceptions surface to the workflow log.
    """
    from nexus_deploy.__main__ import main

    def fake_rsync(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(255, ["rsync", "secret-token-leak-attempt"])

    monkeypatch.setattr("nexus_deploy._remote.rsync_to_remote", fake_rsync)
    monkeypatch.setattr(sys, "argv", ["nexus-deploy", "infisical", "bootstrap"])
    monkeypatch.setattr(sys, "stdin", _StubStdin("{}"))
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.setenv("INFISICAL_TOKEN", "t")
    monkeypatch.setenv("PUSH_DIR", str(tmp_path / "push"))
    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "transport failure" in captured.err
    # Argv contents must not surface — the exc.cmd would carry it
    assert "secret-token-leak-attempt" not in captured.err
    assert "secret-token-leak-attempt" not in captured.out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubStdin:
    """Tiny stand-in for ``sys.stdin`` that returns a fixed string."""

    def __init__(self, content: str) -> None:
        self._content = content

    def read(self) -> str:
        return self._content


# ---------------------------------------------------------------------------
# provision_admin
# ---------------------------------------------------------------------------


def test_render_provision_admin_script_basic_shape() -> None:
    """Rendered bash includes the readiness probe + the bootstrap path."""
    script = render_provision_admin_script(
        admin_email="ops@example.com",
        admin_password="s3cret-Pw",
    )
    assert "set -euo pipefail" in script
    # Two-stage readiness probe
    assert "docker inspect --format='{{.State.Status}}' infisical" in script
    assert "/api/v1/admin/config" in script
    # Init-state branch
    assert '"initialized":true' in script
    # Bootstrap + project-create endpoints
    assert "/api/v1/admin/bootstrap" in script
    assert "/api/v2/workspace" in script
    # Cred persistence paths
    assert "/opt/docker-server/.infisical-token" in script
    assert "/opt/docker-server/.infisical-project-id" in script


def test_render_provision_admin_script_secrets_via_env_not_argv() -> None:
    """R-secret: admin_email + admin_password embed via shlex-quoted
    bash vars then route to jq via env vars (NEXUS_E / NEXUS_PW),
    NOT via --arg argv. Bearer token uses mode-600 curl --config
    tmpfile (not -H argv)."""
    script = render_provision_admin_script(
        admin_email="ops@example.com",
        admin_password="s3cret-Pw",
    )
    # No --arg pass-through to jq
    assert "--arg email" not in script
    assert "--arg password" not in script
    # Bearer token via curl --config tmpfile
    assert "TOKEN_CFG=$(mktemp)" in script
    assert 'chmod 600 "$TOKEN_CFG"' in script
    assert "trap 'rm -f \"$TOKEN_CFG\"' EXIT" in script


def test_render_provision_admin_script_emits_result_line() -> None:
    """Every exit path emits exactly one 'RESULT status=...' line."""
    script = render_provision_admin_script(
        admin_email="a@b",
        admin_password="x",
    )
    assert "RESULT status=not-ready" in script
    assert "RESULT status=loaded-existing" in script
    assert "RESULT status=loaded-existing-missing-creds" in script
    assert "RESULT status=already-bootstrapped-no-saved-creds" in script
    assert "RESULT status=bootstrap-failed" in script
    assert "RESULT status=project-create-failed" in script
    assert "RESULT status=freshly-bootstrapped" in script


def test_parse_provision_result_freshly_bootstrapped() -> None:
    import base64

    raw_token = "test-token-value"
    token_b64 = base64.b64encode(raw_token.encode()).decode()
    line = f"RESULT status=freshly-bootstrapped token={token_b64} project_id=ws-abc-123"
    result = parse_provision_result(line)
    assert result is not None
    assert result.status == "freshly-bootstrapped"
    assert result.token == raw_token
    assert result.project_id == "ws-abc-123"
    assert result.has_credentials is True


def test_parse_provision_result_loaded_existing() -> None:
    import base64

    token_b64 = base64.b64encode(b"existing-token").decode()
    line = f"RESULT status=loaded-existing token={token_b64} project_id=ws-existing"
    result = parse_provision_result(line)
    assert result is not None
    assert result.status == "loaded-existing"
    assert result.has_credentials is True


def test_parse_provision_result_not_ready_no_creds() -> None:
    """The not-ready / bootstrap-failed / etc. branches emit just the
    status, no token + project_id. has_credentials must be False."""
    for status_line in (
        "RESULT status=not-ready",
        "RESULT status=loaded-existing-missing-creds",
        "RESULT status=already-bootstrapped-no-saved-creds",
        "RESULT status=bootstrap-failed",
        "RESULT status=project-create-failed",
    ):
        result = parse_provision_result(status_line)
        assert result is not None, f"failed to parse: {status_line!r}"
        assert result.token is None
        assert result.project_id is None
        assert result.has_credentials is False


def test_parse_provision_result_no_match_returns_none() -> None:
    """Garbage stdout → None; CLI maps that to a not-ready ProvisionResult."""
    assert parse_provision_result("") is None
    assert parse_provision_result("garbage") is None
    assert parse_provision_result("RESULT something_else") is None


def test_parse_provision_result_invalid_utf8_drops_token() -> None:
    """If the base64-decoded bytes are not valid UTF-8 (which a real
    Infisical token never would be — they're all ASCII / hex chars),
    the parser drops the token but keeps the status. Defence-in-depth
    against a malicious / truncated RESULT line."""
    # 'ZZZ=' decodes to a single non-ASCII byte that's not valid UTF-8
    line = "RESULT status=freshly-bootstrapped token=ZZZ= project_id=ws-abc"
    result = parse_provision_result(line)
    assert result is not None
    assert result.status == "freshly-bootstrapped"
    assert result.token is None  # invalid utf-8 → dropped
    assert result.project_id == "ws-abc"


def test_provision_admin_returns_not_ready_when_email_or_password_missing() -> None:
    """Don't even try the SSH script if we don't have credentials."""
    runner_calls: list[str] = []

    def runner(script: str) -> subprocess.CompletedProcess[str]:
        runner_calls.append(script)
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    result = provision_admin(
        admin_email="",
        admin_password="x",
        script_runner=runner,
    )
    assert result.status == "not-ready"
    assert result.has_credentials is False
    assert runner_calls == []


def test_provision_admin_freshly_bootstrapped_path() -> None:
    """Mock the SSH runner to return a freshly-bootstrapped RESULT."""
    import base64

    token = "fresh-token"
    token_b64 = base64.b64encode(token.encode()).decode()

    def runner(_script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout=f"RESULT status=freshly-bootstrapped token={token_b64} project_id=ws-new",
            stderr="",
        )

    result = provision_admin(
        admin_email="ops@example.com",
        admin_password="pw",
        script_runner=runner,
    )
    assert result.status == "freshly-bootstrapped"
    assert result.token == token
    assert result.project_id == "ws-new"


def test_provision_admin_loaded_existing_path() -> None:
    import base64

    token_b64 = base64.b64encode(b"saved-token").decode()

    def runner(_script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout=f"RESULT status=loaded-existing token={token_b64} project_id=ws-saved",
            stderr="",
        )

    result = provision_admin(
        admin_email="ops@example.com",
        admin_password="pw",
        script_runner=runner,
    )
    assert result.status == "loaded-existing"
    assert result.token == "saved-token"
    assert result.project_id == "ws-saved"


def test_provision_admin_unparseable_stdout_returns_not_ready() -> None:
    """Garbage stdout (e.g. SSH succeeded but the script crashed before
    emitting RESULT) → ProvisionResult.not-ready instead of None."""

    def runner(_script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="oops", stderr="")

    result = provision_admin(
        admin_email="ops@example.com",
        admin_password="pw",
        script_runner=runner,
    )
    assert result.status == "not-ready"
    assert result.token is None


def test_cli_infisical_provision_admin_returns_1_when_creds_dropped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R-creds-required-for-rc-0 (#530 R2 #4): a `loaded-existing` /
    `freshly-bootstrapped` status with token=None (e.g. invalid-UTF8
    base64 decode dropped the token) MUST be reported as rc=1, not
    rc=0. Otherwise the caller prints '✓ Infisical provisioned' while
    eval'ing empty INFISICAL_TOKEN= / PROJECT_ID= lines that
    downstream consumers treat as legitimate."""
    import nexus_deploy.__main__ as main_mod
    from nexus_deploy.infisical import ProvisionResult

    class _FakeSSH:
        def __init__(self, _alias: str) -> None:
            del _alias

        def __enter__(self) -> _FakeSSH:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def run_script(self, _s: str, *, check: bool = False) -> subprocess.CompletedProcess[str]:
            del check
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    # Bypass the real provision_admin: simulate the dropped-token case
    def _fake_provision(
        *,
        admin_email: str,
        admin_password: str,
        **_kwargs: object,
    ) -> ProvisionResult:
        del admin_email, admin_password
        return ProvisionResult(
            status="loaded-existing",
            token=None,  # dropped (invalid utf-8 etc.)
            project_id=None,
        )

    monkeypatch.setenv("ADMIN_EMAIL", "ops@example.com")
    monkeypatch.setenv("INFISICAL_PASS", "pw")
    monkeypatch.setattr(main_mod, "SSHClient", _FakeSSH)
    monkeypatch.setattr(main_mod, "provision_admin", _fake_provision)

    rc = main_mod._infisical_provision_admin([])
    assert rc == 1, "loaded-existing without credentials must be soft-fail"
    captured = capsys.readouterr()
    # The handler still writes the eval lines (the caller's eval needs to
    # CLEAR stale values from prior runs), but the rc=1 signals the
    # soft-fail so the caller skips the "✓ Infisical provisioned" branch.
    # Critically the values must be EMPTY-quoted, not stale or garbage.
    assert "INFISICAL_TOKEN=''" in captured.out
    assert "PROJECT_ID=''" in captured.out


def test_cli_infisical_provision_admin_returns_0_with_full_creds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Happy path: token + project_id both populated → rc=0 + eval
    lines on stdout."""
    import nexus_deploy.__main__ as main_mod
    from nexus_deploy.infisical import ProvisionResult

    class _FakeSSH:
        def __init__(self, _alias: str) -> None:
            del _alias

        def __enter__(self) -> _FakeSSH:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def run_script(self, _s: str, *, check: bool = False) -> subprocess.CompletedProcess[str]:
            del check
            return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    def _fake_provision(
        *,
        admin_email: str,
        admin_password: str,
        **_kwargs: object,
    ) -> ProvisionResult:
        del admin_email, admin_password
        return ProvisionResult(
            status="freshly-bootstrapped",
            token="real-token",
            project_id="ws-real",
        )

    monkeypatch.setenv("ADMIN_EMAIL", "ops@example.com")
    monkeypatch.setenv("INFISICAL_PASS", "pw")
    monkeypatch.setattr(main_mod, "SSHClient", _FakeSSH)
    monkeypatch.setattr(main_mod, "provision_admin", _fake_provision)

    rc = main_mod._infisical_provision_admin([])
    assert rc == 0
    out = capsys.readouterr().out
    # shlex.quote leaves [a-zA-Z0-9_@%+=:,./-] unquoted, wraps others.
    assert "INFISICAL_TOKEN=" in out
    assert "real-token" in out
    assert "PROJECT_ID=" in out
    assert "ws-real" in out


# ---------------------------------------------------------------------------
# Forgejo folder
# ---------------------------------------------------------------------------


def test_forgejo_folder_carries_every_generated_credential() -> None:
    """A dropped or misspelled key here is invisible at deploy time —
    provisioning simply never sees the value — so assert the whole set
    rather than a sample."""
    config = NexusConfig(
        admin_username="nexus-admin",
        forgejo_admin_password="fj-admin",
        forgejo_user_password="fj-user",
        forgejo_db_password="fj-db",
        forgejo_runner_secret="a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
    )
    folders = compute_folders(config, BootstrapEnv(domain="example.com"))
    forgejo = next(f for f in folders if f.name == "forgejo")

    assert forgejo.secrets == {
        "FORGEJO_ADMIN_USERNAME": "nexus-admin",
        "FORGEJO_ADMIN_PASSWORD": "fj-admin",
        "FORGEJO_USER_PASSWORD": "fj-user",
        "FORGEJO_REPO_URL_PUBLIC": "https://git.example.com/nexus-admin/nexus-example-com-workspace.git",
        "FORGEJO_DB_PASSWORD": "fj-db",
    }


def test_forgejo_runner_secret_is_never_published_to_infisical() -> None:
    """Everything in Infisical is copied into Kestra's environment by
    `secret_sync`, so publishing the runner's registration credential
    would hand it to every flow author. Nothing reads it from here —
    the pipeline takes it from the tofu output — so it stays out."""
    config = NexusConfig(
        admin_username="nexus-admin",
        forgejo_runner_secret="a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
    )
    folders = compute_folders(config, BootstrapEnv(domain="example.com"))

    for folder in folders:
        assert "FORGEJO_RUNNER_SECRET" not in folder.secrets, folder.name
        assert "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678" not in folder.secrets.values()


def test_forgejo_folder_drops_unset_credentials() -> None:
    """Skip-empty preserves operator edits made in the Infisical UI
    (issue #504) — an unset value must not overwrite one."""
    config = NexusConfig(admin_username="nexus-admin", forgejo_db_password="fj-db")
    folders = compute_folders(config, BootstrapEnv(domain="example.com"))
    forgejo = next(f for f in folders if f.name == "forgejo")

    assert "FORGEJO_ADMIN_PASSWORD" not in forgejo.secrets
    assert forgejo.secrets["FORGEJO_DB_PASSWORD"] == "fj-db"


def test_forgejo_folder_publishes_the_public_workspace_repo_url() -> None:
    """Forgejo hosts the workspace repo, so the URL belongs here.

    This assertion used to be the opposite: while Gitea still held
    the internal role, publishing a Forgejo URL would have been a
    claim the platform could not keep.
    """
    config = NexusConfig(admin_username="nexus-admin", forgejo_db_password="fj-db")
    folders = compute_folders(config, BootstrapEnv(domain="example.com"))
    forgejo = next(f for f in folders if f.name == "forgejo")

    assert forgejo.secrets["FORGEJO_REPO_URL_PUBLIC"].endswith("-workspace.git")
    gitea = next(f for f in folders if f.name == "gitea")
    assert "GITEA_REPO_URL" not in gitea.secrets


def test_the_two_clone_urls_never_share_a_name() -> None:
    """Infisical must not publish the bare ``FORGEJO_REPO_URL``.

    ``secret_sync`` writes every Infisical key unprefixed into a stack's
    ``.infisical.env``, and compose reads that AFTER ``.env`` — so a key
    sharing the workspace block's name silently replaces the internal
    clone URL inside the container, whose ``.netrc`` authenticates
    ``machine forgejo``. That was #694; the names must stay distinct.
    """
    config = _make_config(admin_username="bob")
    folders = compute_folders(config, BootstrapEnv(domain="example.com"))
    for folder in folders:
        assert "FORGEJO_REPO_URL" not in folder.secrets, (
            f"folder {folder.name!r} publishes the bare name — it would "
            "override the internal URL in every workspace stack"
        )
