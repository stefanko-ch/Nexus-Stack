"""Tests for nexus_deploy.pipeline.

End-to-end mocked pipeline runs. The 3 new modules + the orchestrator
are DI'd via monkeypatch + the public ``tofu_runner`` /
``docker_hub_login`` seams. Per-phase invariants are R-tagged.

Coverage targets:
- R-tofu-state-fail: missing tofu state aborts BEFORE any output read.
- R-secrets-empty: empty secrets JSON aborts.
- R-r2-creds-injected: when ``.r2-credentials`` exists, the
  AWS_* env vars are populated BEFORE tofu calls.
- R-r2-creds-missing: missing ``.r2-credentials`` is a legitimate
  skip; pipeline continues.
- R-domain-required: empty ``domain`` in tfvars aborts.
- R-collision-fallback: admin == user_email triggers
  ``gitea-admin@<domain>`` (smoke through the pipeline).
- R-orchestrator-hard-fail: hard failure → PipelineError.
- R-banner-renders: format_done_banner produces a stable shape.
- R-options-defaults: missing PipelineOptions fields default
  cleanly.
- R-rc-mapping: CLI handler returns 0 for clean OR partial runs
  (partial → stderr warning, never a non-zero exit) and 2 for hard
  failures. The rc=1-on-partial path was removed in PR #535 R0.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from nexus_deploy.orchestrator import OrchestratorResult, OrchestratorState, PhaseResult
from nexus_deploy.pipeline import (
    PipelineError,
    PipelineOptions,
    PipelineResult,
    SnapshotResult,
    format_done_banner,
    run_pipeline,
    run_snapshot,
    write_phase_log,
)
from nexus_deploy.s3_restore import S3SnapshotApplied, S3SnapshotSkipped
from nexus_deploy.tofu import TofuRunner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tofu_dir(tmp_path: Path) -> Path:
    """Create a tofu/stack/config.tfvars + .r2-credentials skeleton."""
    tofu_root = tmp_path / "tofu"
    stack = tofu_root / "stack"
    stack.mkdir(parents=True)
    (stack / "config.tfvars").write_text(
        'domain = "example.com"\n'
        'admin_email = "admin@example.com"\n'
        'user_email = "user@example.com"\n',
        encoding="utf-8",
    )
    (tofu_root / ".r2-credentials").write_text(
        'R2_ACCESS_KEY_ID="ABC"\nR2_SECRET_ACCESS_KEY="DEF"\n',
        encoding="utf-8",
    )
    return stack


@pytest.fixture
def project_root(tofu_dir: Path) -> Path:
    """tofu/stack's parent's parent — i.e., where tofu/ lives."""
    return tofu_dir.parent.parent


@pytest.fixture
def fake_secrets_payload() -> dict[str, str]:
    """Minimum SECRETS_JSON shape that NexusConfig.from_secrets_json
    accepts. NexusConfig is permissive — unknown keys are ignored."""
    return {
        "ADMIN_USERNAME": "admin",
        "GITEA_ADMIN_PASS": "g-admin-pw",
        "INFISICAL_PASS": "inf-admin-pw",
        "WOODPECKER_AGENT_SECRET": "wp-secret",
    }


@pytest.fixture
def fake_tofu_runner(fake_secrets_payload: dict[str, str]) -> MagicMock:
    """A TofuRunner stand-in. ``state_list_ok`` returns True; outputs
    are configurable via ``output_json_map`` /
    ``output_raw_map`` set via setattr after construction."""
    runner = MagicMock(spec=TofuRunner)
    runner.tofu_dir = Path("/fake")
    runner.state_list_ok.return_value = True
    # Default: hcloud_server.main NOT in state. The snapshot pipeline
    # uses state_contains() as a safety check before treating a
    # missing ssh_service_token as graceful no-op — tests that want
    # to simulate "server in state but token missing" override this.
    runner.state_contains.return_value = False
    json_map: dict[str, Any] = {
        "secrets": fake_secrets_payload,
        "image_versions": {"kestra": "v0.51"},
        "enabled_services": ["kestra", "jupyter"],
        "firewall_rules": {},
        "ssh_service_token": {"client_id": "cf-id", "client_secret": "cf-secret"},
        "service_urls": {"kestra": "https://kestra.example.com"},
    }
    raw_map: dict[str, str] = {
        "server_ip": "1.2.3.4",
        "persistent_volume_id": "1234",
    }
    runner.output_json.side_effect = lambda name, default=None: json_map.get(name, default)
    runner.output_raw.side_effect = lambda name, default="": raw_map.get(name, default)
    return runner


@pytest.fixture
def setup_mocks(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Install no-op mocks for every external boundary the pipeline
    crosses. Tests that need to assert specific behavior re-set the
    mock they care about."""
    from nexus_deploy.setup import SSHReadinessResult

    mocks: dict[str, Any] = {
        "configure_ssh": MagicMock(return_value=None),
        "wait_for_ssh": MagicMock(return_value=SSHReadinessResult(succeeded=True, attempts=1)),
        "ensure_jq": MagicMock(return_value=False),
        # rclone must be installed BEFORE restore_from_s3 — pipeline
        # calls ensure_rclone right after ensure_jq. Pre-Round-6
        # missing-rclone caused silent fresh-starts → data loss.
        "ensure_rclone": MagicMock(return_value=False),
        # RFC 0001 cutover: mount_persistent_volume replaced by
        # ensure_data_dirs (chown-only; the Hetzner volume is gone).
        "ensure_data_dirs": MagicMock(return_value=None),
        "setup_wetty_ssh_agent": MagicMock(return_value=None),
        "ssh_keygen_cleanup": MagicMock(),
        "SSHClient": MagicMock(),
    }
    monkeypatch.setattr("nexus_deploy.pipeline._setup.configure_ssh", mocks["configure_ssh"])
    monkeypatch.setattr("nexus_deploy.pipeline._setup.wait_for_ssh", mocks["wait_for_ssh"])
    monkeypatch.setattr("nexus_deploy.pipeline._setup.ensure_jq", mocks["ensure_jq"])
    monkeypatch.setattr(
        "nexus_deploy.pipeline._setup.ensure_rclone",
        mocks["ensure_rclone"],
    )
    monkeypatch.setattr(
        "nexus_deploy.pipeline._setup.ensure_data_dirs",
        mocks["ensure_data_dirs"],
    )
    monkeypatch.setattr(
        "nexus_deploy.pipeline._setup.setup_wetty_ssh_agent",
        mocks["setup_wetty_ssh_agent"],
    )
    monkeypatch.setattr("nexus_deploy.pipeline._ssh_keygen_cleanup", mocks["ssh_keygen_cleanup"])
    # SSHClient is used as a context manager in the pipeline; the mock
    # just returns itself for both __enter__ / __exit__.
    ssh_instance = MagicMock()
    mocks["SSHClient"].return_value.__enter__.return_value = ssh_instance
    mocks["SSHClient"].return_value.__exit__.return_value = False
    monkeypatch.setattr("nexus_deploy.pipeline.SSHClient", mocks["SSHClient"])
    mocks["ssh_instance"] = ssh_instance
    return mocks


@pytest.fixture
def mock_orchestrator(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Make Orchestrator() return a MagicMock whose
    run_pre_bootstrap + run_all return clean OrchestratorResults."""
    instance = MagicMock()
    instance.run_pre_bootstrap.return_value = OrchestratorResult(
        phases=(PhaseResult(name="pre", status="ok"),),
        state=OrchestratorState(),
    )
    instance.run_all.return_value = OrchestratorResult(
        phases=(PhaseResult(name="post", status="ok"),),
        state=OrchestratorState(),
    )
    cls_mock = MagicMock(return_value=instance)
    monkeypatch.setattr("nexus_deploy.pipeline.Orchestrator", cls_mock)
    return instance


# ---------------------------------------------------------------------------
# R-tofu-state-fail / R-secrets-empty
# ---------------------------------------------------------------------------


def test_pipeline_aborts_when_tofu_state_uninitialized(
    project_root: Path, fake_tofu_runner: MagicMock, setup_mocks: dict[str, Any]
) -> None:
    """R-tofu-state-fail: state_list_ok=False → PipelineError BEFORE
    any output_json call."""
    fake_tofu_runner.state_list_ok.return_value = False
    with pytest.raises(PipelineError, match=r"state .* not initialised"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )
    fake_tofu_runner.output_json.assert_not_called()


def test_pipeline_state_failure_surfaces_diagnose_reason(
    project_root: Path, fake_tofu_runner: MagicMock, setup_mocks: dict[str, Any]
) -> None:
    """PR #535 R2 #2: when state_list_ok=False AND diagnose_state
    returns a real reason string, the PipelineError carries the
    reason so operators can distinguish 'state missing' from
    'tofu binary missing' / 'backend timeout' / 'rc=N + stderr'."""
    fake_tofu_runner.state_list_ok.return_value = False
    fake_tofu_runner.diagnose_state.return_value = "tofu binary not found on PATH"
    with pytest.raises(PipelineError, match=r"tofu binary not found on PATH"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )
    fake_tofu_runner.output_json.assert_not_called()


def test_pipeline_aborts_on_empty_secrets(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
) -> None:
    """R-secrets-empty: secrets={} → PipelineError. Without secrets
    the orchestrator can't run."""
    fake_tofu_runner.output_json.side_effect = lambda name, default=None: (
        {} if name == "secrets" else default
    )
    with pytest.raises(PipelineError, match=r"secrets .* empty"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )


# ---------------------------------------------------------------------------
# R-r2-creds-injected / R-r2-creds-missing
# ---------------------------------------------------------------------------


def test_pipeline_injects_r2_creds_into_environ(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-r2-creds-injected: when .r2-credentials exists with both
    keys, AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY land in
    os.environ BEFORE state_list_ok runs."""
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)

    captured_env: dict[str, str | None] = {}

    def _state_list_ok_capture() -> bool:
        captured_env["AWS_ACCESS_KEY_ID"] = os.environ.get("AWS_ACCESS_KEY_ID")
        captured_env["AWS_SECRET_ACCESS_KEY"] = os.environ.get("AWS_SECRET_ACCESS_KEY")
        return True

    fake_tofu_runner.state_list_ok.side_effect = _state_list_ok_capture
    run_pipeline(
        project_root=project_root,
        options=PipelineOptions(),
        tofu_runner=fake_tofu_runner,
    )
    assert captured_env["AWS_ACCESS_KEY_ID"] == "ABC"
    assert captured_env["AWS_SECRET_ACCESS_KEY"] == "DEF"


def test_pipeline_skips_creds_when_file_missing(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-r2-creds-missing: no .r2-credentials → pipeline continues
    without injecting AWS_*. Operator's pre-existing env (from CI
    secrets) survives."""
    (project_root / "tofu" / ".r2-credentials").unlink()
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "preset-by-ci")
    run_pipeline(
        project_root=project_root,
        options=PipelineOptions(),
        tofu_runner=fake_tofu_runner,
    )
    # CI's pre-set value survives — we didn't overwrite it.
    assert os.environ["AWS_ACCESS_KEY_ID"] == "preset-by-ci"


# ---------------------------------------------------------------------------
# R-domain-required
# ---------------------------------------------------------------------------


def test_pipeline_aborts_on_empty_domain(
    project_root: Path, fake_tofu_runner: MagicMock, setup_mocks: dict[str, Any]
) -> None:
    """R-domain-required: tfvars with no domain → PipelineError."""
    (project_root / "tofu" / "stack" / "config.tfvars").write_text(
        'admin_email = "admin@example.com"\n', encoding="utf-8"
    )
    with pytest.raises(PipelineError, match="missing a non-empty 'domain'"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )


# ---------------------------------------------------------------------------
# R-orchestrator-hard-fail
# ---------------------------------------------------------------------------


def test_pipeline_aborts_when_pre_bootstrap_hard_fails(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
) -> None:
    """R-orchestrator-hard-fail (pre-bootstrap): any phase
    status='failed' raises PipelineError."""
    mock_orchestrator.run_pre_bootstrap.return_value = OrchestratorResult(
        phases=(PhaseResult(name="pre", status="failed", detail="boom"),),
        state=OrchestratorState(),
    )
    with pytest.raises(PipelineError, match="pre-bootstrap pipeline aborted"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )
    # run_all must NOT have been called — pre-bootstrap aborted.
    mock_orchestrator.run_all.assert_not_called()


def test_pipeline_aborts_when_run_all_hard_fails(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
) -> None:
    """R-orchestrator-hard-fail (run-all): post-bootstrap hard fail
    after pre-bootstrap succeeded → PipelineError."""
    mock_orchestrator.run_all.return_value = OrchestratorResult(
        phases=(PhaseResult(name="post", status="failed", detail="boom"),),
        state=OrchestratorState(),
    )
    with pytest.raises(PipelineError, match="post-bootstrap pipeline aborted"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )


# ---------------------------------------------------------------------------
# R-banner-renders
# ---------------------------------------------------------------------------


def test_format_done_banner_contains_service_urls() -> None:
    """R-banner-renders: service URLs are formatted as 'name: url'."""
    result = PipelineResult(
        pre_bootstrap=OrchestratorResult(phases=(), state=OrchestratorState()),
        run_all=OrchestratorResult(phases=(), state=OrchestratorState()),
        service_urls={
            "kestra": "https://kestra.example.com",
            "jupyter": "https://jupyter.example.com",
        },
    )
    banner = format_done_banner(result)
    assert "✅ Deployment Complete" in banner
    assert "kestra: https://kestra.example.com" in banner
    assert "jupyter: https://jupyter.example.com" in banner
    assert "ssh nexus" in banner
    assert "Credentials available in Infisical" in banner


def test_pipeline_aborts_on_unparseable_secrets(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ConfigError from NexusConfig.from_secrets_json is wrapped in
    PipelineError. NexusConfig is currently permissive (every field
    Optional[str]) so this branch is only reachable when a future
    field gains stricter validation; we monkeypatch to exercise it
    today and pin the error-wrapping contract."""
    from nexus_deploy.config import ConfigError

    def _raise(_raw: str) -> Any:
        raise ConfigError("SECRETS_JSON failed validation")

    monkeypatch.setattr("nexus_deploy.pipeline.NexusConfig.from_secrets_json", _raise)
    with pytest.raises(PipelineError, match=r"could not parse secrets JSON"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )


def test_pipeline_wraps_tfvars_error_as_pipeline_error(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
) -> None:
    """PR #535 R4 #3: TfvarsError → PipelineError so the CLI handler
    classifies it as a pre-flight failure (rc=2 with actionable
    message), not "unexpected error"."""
    # Delete config.tfvars after the fixture created it so parse()
    # raises TfvarsError("not found").
    (project_root / "tofu" / "stack" / "config.tfvars").unlink()
    with pytest.raises(PipelineError, match=r"could not load .* config\.tfvars"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )


def test_pipeline_wraps_r2_creds_tofu_error(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
) -> None:
    """PR #535 R4 #2: TofuError from load_r2_credentials (malformed
    file) → PipelineError. Without the wrap the CLI shows
    "unexpected error (TofuError)" which masks the actionable cause."""
    # Overwrite the fixture's well-formed creds with a malformed
    # body that triggers TofuError (file exists but no valid keys).
    (project_root / "tofu" / ".r2-credentials").write_text(
        "garbage line that is not KEY=value\n",
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match=r"could not load .*\.r2-credentials"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )


def test_pipeline_wraps_required_output_missing(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
) -> None:
    """PR #535 R4 #1: when a destructive-default output (e.g.
    enabled_services) is missing → TofuError → PipelineError. The
    previous safe-looking ``default=[]`` would silently drive
    stack-sync to remove all remote stacks."""
    from nexus_deploy.tofu import TofuError

    def _output_json(name: str, default: Any = None) -> Any:
        if name == "secrets":
            return {"ADMIN_USERNAME": "admin"}
        if name in ("enabled_services", "firewall_rules", "ssh_service_token"):
            raise TofuError(f"tofu output -json {name} failed")
        return default

    fake_tofu_runner.output_json.side_effect = _output_json
    with pytest.raises(PipelineError, match=r"required tofu output missing or invalid"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )


def test_pipeline_runs_restore_then_ensure_data_dirs_then_pg_restore(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RFC 0001 cutover ordering invariant — the spinup pipeline
    splits restore into two halves around compose-up:

    1. ``restore_from_s3(phase="filesystem")`` BEFORE compose-up
       (so containers come up reading the seeded bind-mounts)
    2. ``ensure_data_dirs`` AFTER FS restore (chown the rsync'd
       files to container UIDs) but still BEFORE compose-up
    3. ``orchestrator.run_pre_bootstrap()`` — last phase is
       ``_phase_compose_up`` so containers are running after
    4. ``restore_from_s3(phase="postgres")`` — pg_restore via
       docker exec, requires running containers
    5. ``orchestrator.run_all()`` — gitea-configure et al. now
       see the restored database

    A parent MagicMock receives every call so we can assert the
    sequence in one go; pure ``assert_called`` per-mock would miss
    out-of-order regressions like calling pg-restore BEFORE
    pre_bootstrap (which was the round-4 bug Copilot caught)."""
    parent = MagicMock()
    parent.attach_mock(setup_mocks["ensure_rclone"], "ensure_rclone")
    parent.attach_mock(setup_mocks["ensure_data_dirs"], "ensure_data_dirs")

    restore_calls: list[str] = []

    def fake_restore(
        _ssh: Any,
        *,
        env: Any = None,
        phase: str = "all",
    ) -> Any:
        restore_calls.append(phase)
        parent.restore_from_s3(phase=phase)
        from nexus_deploy.s3_restore import S3RestoreSkipped

        return S3RestoreSkipped(reason="fresh_start_empty_s3")

    monkeypatch.setattr("nexus_deploy.pipeline._s3_restore.restore_from_s3", fake_restore)
    parent.attach_mock(mock_orchestrator.run_pre_bootstrap, "run_pre_bootstrap")
    parent.attach_mock(mock_orchestrator.run_all, "run_all")

    run_pipeline(
        project_root=project_root,
        options=PipelineOptions(),
        tofu_runner=fake_tofu_runner,
    )

    # Exact phase ordering — captured into restore_calls so the
    # assertion is readable, separately from the cross-mock order
    # assertion on parent.mock_calls below.
    assert restore_calls == ["filesystem", "postgres"]

    # Cross-mock ordering — extract only the names we care about
    # (parent.mock_calls also captures nested attribute lookups on
    # the orchestrator MagicMock from inside run_pipeline, which
    # would otherwise pollute the sequence).
    relevant = [
        c[0]
        for c in parent.mock_calls
        if c[0]
        in {
            "ensure_rclone",
            "restore_from_s3",
            "ensure_data_dirs",
            "run_pre_bootstrap",
            "run_all",
        }
    ]
    assert relevant == [
        "ensure_rclone",  # MUST come before restore_from_s3
        "restore_from_s3",  # phase="filesystem"
        "ensure_data_dirs",
        "run_pre_bootstrap",  # compose-up happens here
        "restore_from_s3",  # phase="postgres"
        "run_all",
    ]


def test_pipeline_aborts_when_enabled_services_not_list(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
) -> None:
    """Defensive guard: tofu's enabled_services output must be a list.
    A dict / scalar would let downstream `"wetty" in enabled_services`
    silently pass when wetty is in fact a key, not an enabled service."""
    original = fake_tofu_runner.output_json.side_effect

    def _wrap(name: str, default: Any = None) -> Any:
        if name == "enabled_services":
            return {"wetty": True}
        return original(name, default)

    fake_tofu_runner.output_json.side_effect = _wrap
    with pytest.raises(PipelineError, match=r"enabled_services is dict, expected list"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )


def test_format_done_banner_handles_empty_service_urls() -> None:
    """When tofu didn't return any URLs, the banner notes that
    instead of being empty."""
    result = PipelineResult(
        pre_bootstrap=OrchestratorResult(phases=(), state=OrchestratorState()),
        run_all=OrchestratorResult(phases=(), state=OrchestratorState()),
    )
    banner = format_done_banner(result)
    assert "service URLs not available" in banner


# ---------------------------------------------------------------------------
# R-wetty-conditional + R-dockerhub-conditional
# ---------------------------------------------------------------------------


def test_pipeline_skips_wetty_when_not_enabled(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
) -> None:
    """When 'wetty' isn't in enabled_services, setup_wetty_ssh_agent
    is NOT called."""
    fake_tofu_runner.output_json.side_effect = lambda name, default=None: {
        "secrets": {"ADMIN_USERNAME": "admin"},
        "image_versions": {},
        "enabled_services": ["kestra"],  # no wetty
        "firewall_rules": {},
        "ssh_service_token": {"client_id": "x", "client_secret": "y"},
        "service_urls": {},
    }.get(name, default)
    run_pipeline(
        project_root=project_root,
        options=PipelineOptions(),
        tofu_runner=fake_tofu_runner,
    )
    setup_mocks["setup_wetty_ssh_agent"].assert_not_called()


def test_pipeline_runs_wetty_when_enabled(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
) -> None:
    fake_tofu_runner.output_json.side_effect = lambda name, default=None: {
        "secrets": {"ADMIN_USERNAME": "admin"},
        "image_versions": {},
        "enabled_services": ["wetty"],
        "firewall_rules": {},
        "ssh_service_token": {"client_id": "x", "client_secret": "y"},
        "service_urls": {},
    }.get(name, default)
    run_pipeline(
        project_root=project_root,
        options=PipelineOptions(),
        tofu_runner=fake_tofu_runner,
    )
    setup_mocks["setup_wetty_ssh_agent"].assert_called_once()


def test_pipeline_skips_dockerhub_login_without_creds(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
) -> None:
    """No DOCKERHUB_USER/TOKEN → docker_hub_login is not invoked."""
    spy = MagicMock()
    run_pipeline(
        project_root=project_root,
        options=PipelineOptions(),  # no creds
        tofu_runner=fake_tofu_runner,
        docker_hub_login=spy,
    )
    spy.assert_not_called()


def test_pipeline_runs_dockerhub_login_when_creds_set(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
) -> None:
    spy = MagicMock()
    run_pipeline(
        project_root=project_root,
        options=PipelineOptions(dockerhub_user="alice", dockerhub_token="ghp_x"),
        tofu_runner=fake_tofu_runner,
        docker_hub_login=spy,
    )
    spy.assert_called_once_with("nexus", "alice", "ghp_x")


# ---------------------------------------------------------------------------
# R-options-defaults
# ---------------------------------------------------------------------------


def test_pipeline_options_defaults() -> None:
    options = PipelineOptions()
    assert options.ssh_private_key_content is None
    assert options.gh_mirror_token is None
    assert options.gh_mirror_repos is None
    assert options.dockerhub_user is None
    assert options.dockerhub_token is None
    assert options.infisical_env == "dev"


def test_pipeline_options_frozen() -> None:
    from dataclasses import FrozenInstanceError

    options = PipelineOptions()
    with pytest.raises(FrozenInstanceError):
        options.infisical_env = "prod"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# R-rc-mapping (CLI handler)
# ---------------------------------------------------------------------------


def test_cli_run_pipeline_unknown_arg_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    from nexus_deploy.__main__ import _run_pipeline

    rc = _run_pipeline(["--bogus"])
    assert rc == 2
    assert "unknown args" in capsys.readouterr().err


def test_cli_run_pipeline_returns_2_on_pipeline_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """PipelineError → rc=2 with the error message in stderr."""
    from nexus_deploy.__main__ import _run_pipeline

    def _raise(*_a: Any, **_kw: Any) -> Any:
        raise PipelineError("synthetic boom")

    monkeypatch.setattr("nexus_deploy.__main__._pipeline.run_pipeline", _raise)
    rc = _run_pipeline([])
    assert rc == 2
    assert "synthetic boom" in capsys.readouterr().err


def test_cli_run_pipeline_returns_2_on_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _run_pipeline

    def _raise(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("synthetic")

    monkeypatch.setattr("nexus_deploy.__main__._pipeline.run_pipeline", _raise)
    rc = _run_pipeline([])
    assert rc == 2
    assert "unexpected error (RuntimeError)" in capsys.readouterr().err


def test_cli_run_pipeline_returns_0_on_clean_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _run_pipeline

    fake = PipelineResult(
        pre_bootstrap=OrchestratorResult(
            phases=(PhaseResult(name="pre", status="ok"),),
            state=OrchestratorState(),
        ),
        run_all=OrchestratorResult(
            phases=(PhaseResult(name="post", status="ok"),),
            state=OrchestratorState(),
        ),
    )
    monkeypatch.setattr("nexus_deploy.__main__._pipeline.run_pipeline", lambda **_: fake)
    rc = _run_pipeline([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Deployment Complete" in out


def test_cli_run_pipeline_returns_0_on_partial_with_stderr_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R-rc-mapping: partial phases must NOT fail the workflow step.

    Standalone subcommands (``run-all`` / ``run-pre-bootstrap``)
    return rc=1 on partial so a wrapper script can branch on it,
    but ``run-pipeline`` is the top-level CLI invoked directly by
    spin-up.yml's bash with ``set -e`` — a non-zero exit fails the
    step. Partial is a 'warn and continue' semantic: rc=0 + stderr
    warning, NOT rc=1."""
    from nexus_deploy.__main__ import _run_pipeline

    fake = PipelineResult(
        pre_bootstrap=OrchestratorResult(
            phases=(PhaseResult(name="pre", status="partial"),),
            state=OrchestratorState(),
        ),
        run_all=OrchestratorResult(
            phases=(PhaseResult(name="post", status="ok"),),
            state=OrchestratorState(),
        ),
    )
    monkeypatch.setattr("nexus_deploy.__main__._pipeline.run_pipeline", lambda **_: fake)
    rc = _run_pipeline([])
    assert rc == 0  # NOT 1 — see docstring above.
    err = capsys.readouterr().err
    assert "status='partial'" in err
    assert "deploy succeeded with warnings" in err


# ---------------------------------------------------------------------------
# Frozen-dataclass invariants
# ---------------------------------------------------------------------------


def test_pipeline_result_default_service_urls_empty() -> None:
    result = PipelineResult(
        pre_bootstrap=OrchestratorResult(phases=(), state=OrchestratorState()),
        run_all=OrchestratorResult(phases=(), state=OrchestratorState()),
    )
    assert result.service_urls == {}


def test_pipeline_result_frozen() -> None:
    from dataclasses import FrozenInstanceError

    result = PipelineResult(
        pre_bootstrap=OrchestratorResult(phases=(), state=OrchestratorState()),
        run_all=OrchestratorResult(phases=(), state=OrchestratorState()),
    )
    with pytest.raises(FrozenInstanceError):
        result.service_urls = {"foo": "bar"}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Pure-function helpers
# ---------------------------------------------------------------------------


def test_b64_encode_ssh_key_empty_returns_empty() -> None:
    """Empty / None content must NOT round-trip to ``Cg==`` —
    BootstrapEnv treats any non-empty value as a populated key."""
    from nexus_deploy.pipeline import _b64_encode_ssh_key

    assert _b64_encode_ssh_key(None) == ""
    assert _b64_encode_ssh_key("") == ""


def test_b64_encode_ssh_key_matches_legacy_bash_semantic() -> None:
    """``echo "$KEY" | base64`` appends a trailing newline before the
    pipe — so the legacy-equivalent encoding is base64(content + '\\n').
    """
    import base64

    from nexus_deploy.pipeline import _b64_encode_ssh_key

    encoded = _b64_encode_ssh_key("ssh-ed25519 AAAA...")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == "ssh-ed25519 AAAA...\n"


def test_ssh_keygen_cleanup_skips_empty_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty-string targets must NOT spawn a subprocess (would be a
    ssh-keygen syntax error and waste a fork)."""
    import subprocess

    from nexus_deploy.pipeline import _ssh_keygen_cleanup

    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        return subprocess.CompletedProcess(args=argv, returncode=0)

    monkeypatch.setattr("nexus_deploy.pipeline.subprocess.run", _fake_run)
    _ssh_keygen_cleanup("ssh.example.com", "", "1.2.3.4")
    assert len(calls) == 2
    assert ["ssh-keygen", "-R", "ssh.example.com"] in calls
    assert ["ssh-keygen", "-R", "1.2.3.4"] in calls


def test_ssh_keygen_cleanup_swallows_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #535 R2 #1: TimeoutExpired must NOT propagate (best-effort)."""
    import subprocess

    from nexus_deploy.pipeline import _ssh_keygen_cleanup

    def _hang(*_a: Any, **_kw: Any) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(["ssh-keygen"], 10.0)

    monkeypatch.setattr("nexus_deploy.pipeline.subprocess.run", _hang)
    # Must not raise.
    _ssh_keygen_cleanup("ssh.example.com")


# ---------------------------------------------------------------------------
# SUBDOMAIN_SEPARATOR — Issue #540 (SSH host + BootstrapEnv threading)
# ---------------------------------------------------------------------------


def test_pipeline_passes_subdomain_separator_to_bootstrap_env(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When config.tfvars sets ``subdomain_separator = \"-\"``, the
    pipeline must thread that into the BootstrapEnv that the
    Orchestrator sees. Without this, the ``woodpecker-oauth`` phase
    + every service_env render would silently fall back to the dot
    form (default field value)."""
    # Add the separator line to the fixture's config.tfvars.
    tfvars_path = project_root / "tofu" / "stack" / "config.tfvars"
    tfvars_path.write_text(
        tfvars_path.read_text(encoding="utf-8") + 'subdomain_separator = "-"\n',
        encoding="utf-8",
    )
    captured_env: dict[str, Any] = {}

    def _capture_orchestrator(**kwargs: Any) -> MagicMock:
        captured_env["bootstrap_env"] = kwargs.get("bootstrap_env")
        return mock_orchestrator

    monkeypatch.setattr("nexus_deploy.pipeline.Orchestrator", _capture_orchestrator)
    run_pipeline(
        project_root=project_root,
        options=PipelineOptions(),
        tofu_runner=fake_tofu_runner,
    )
    bs_env = captured_env["bootstrap_env"]
    assert bs_env is not None
    assert bs_env.subdomain_separator == "-"


def test_pipeline_uses_separator_for_ssh_host_dns(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
) -> None:
    """SSH host known_hosts cleanup runs against the
    separator-aware DNS name. Default separator='.' yields
    ``ssh.example.com`` (verified by the existing fixture's
    domain field); flat-tenant separator='-' yields
    ``ssh-user1.example.com`` matching the Cloudflare Tunnel
    DNS record Tofu provisions for that tenant."""
    tfvars_path = project_root / "tofu" / "stack" / "config.tfvars"
    tfvars_path.write_text(
        'domain = "user1.example.com"\n'
        'admin_email = "user1@example.com"\n'
        'user_email = "user1@example.com"\n'
        'subdomain_separator = "-"\n',
        encoding="utf-8",
    )
    run_pipeline(
        project_root=project_root,
        options=PipelineOptions(),
        tofu_runner=fake_tofu_runner,
    )
    # ssh_keygen_cleanup mock was called with the flat-form host name.
    cleanup_mock = setup_mocks["ssh_keygen_cleanup"]
    cleanup_mock.assert_called_once()
    # Exact tuple equality (rather than membership) — pinned shape +
    # also dodges CodeQL's py/incomplete-url-substring-sanitization
    # rule which heuristically flags ``"<bare-domain>" in container``
    # patterns even when the container is a fixture-controlled tuple.
    assert cleanup_mock.call_args.args == ("ssh-user1.example.com", "1.2.3.4")
    assert cleanup_mock.call_args.args[0] != "ssh.user1.example.com"


# ---------------------------------------------------------------------------
# run_snapshot — teardown-side preflight + SSH wiring (PR-4)
# ---------------------------------------------------------------------------


def test_run_snapshot_aborts_when_tofu_state_uninitialized(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teardown counterpart to
    :func:`test_pipeline_aborts_when_tofu_state_uninitialized`. No
    state → nothing to snapshot → PipelineError → CLI rc=2 → teardown
    workflow aborts BEFORE tofu destroy. We never want to run
    destroy against a stack whose state file has gone walkabout
    (could mean the previous teardown raced or the R2 backend is
    flaky).

    Feature flag MUST be set ``"true"`` here — the
    feature-flag-off short-circuit at the top of ``run_snapshot``
    would otherwise return ``Skipped(feature_flag_off)`` before
    ever reading tofu state, masking the missing-state failure.
    """
    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    fake_tofu_runner.state_list_ok.return_value = False
    fake_tofu_runner.diagnose_state.return_value = None
    with pytest.raises(PipelineError, match="not initialised"):
        run_snapshot(
            project_root=project_root,
            stack_slug="nexus-test",
            template_version="v1.0.0",
            tofu_runner=fake_tofu_runner,
        )


def test_run_snapshot_skips_when_state_file_missing(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #564: partially-deployed forks (setup-control-plane
    succeeded, spin-up aborted before any ``tofu apply``) have a
    state-list failure with the specific stderr "No state file was
    found!". This is materially different from a real state-list
    failure (binary missing, R2 auth/timeout) — there is genuinely
    nothing on the server to snapshot, so teardown should proceed.

    The narrow ``"No state file was found"`` substring match is
    what distinguishes this skip from a hard PipelineError. Once
    this branch fires we must NOT reach output_json (no outputs
    to read) and we must NOT touch SSH (no server to snapshot
    from)."""
    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    fake_tofu_runner.state_list_ok.return_value = False
    fake_tofu_runner.diagnose_state.return_value = (
        "state list failed (rc=1): No state file was found!"
    )
    result = run_snapshot(
        project_root=project_root,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        tofu_runner=fake_tofu_runner,
    )
    assert isinstance(result.outcome, S3SnapshotSkipped)
    assert result.outcome.reason == "no_state_to_snapshot"
    # Skip path must short-circuit before reading outputs or
    # touching SSH — otherwise we'd ironically fail the very
    # teardown we're trying to unblock.
    fake_tofu_runner.output_json.assert_not_called()
    setup_mocks["configure_ssh"].assert_not_called()
    setup_mocks["wait_for_ssh"].assert_not_called()
    setup_mocks["SSHClient"].assert_not_called()


def test_run_snapshot_skips_when_ssh_service_token_missing(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #564 follow-up (mid-2026-05 partial-state case): SOME
    state is present in tofu/stack — so ``state_list_ok()`` returns
    True — but the ``ssh_service_token`` output isn't in it because
    the Hetzner server + Cloudflare Access Service Token resource
    never got applied (setup ran, Spin Up never did). Observed on a
    deads7 fork whose scheduled daily 21:00-UTC teardown went red
    for five days straight, generating noise without snapshotting
    anything.

    Right behaviour: graceful Skipped with reason
    ``no_snapshot_source``, the same way the "no state file at all"
    case in :func:`test_run_snapshot_skips_when_state_file_missing`
    is treated — there is nothing on the server to back up either
    way. The subsequent ``tofu destroy`` still runs to reap any
    partial state.

    Tests that the short-circuit fires BEFORE any SSH side-effect
    (configure_ssh / wait_for_ssh / SSHClient) — same invariant as
    the file-missing test, but at one branch deeper into the
    pipeline."""
    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    # State list works (the partial state is real) but the specific
    # output we need is absent. Mirror the fixture's default signature
    # so other outputs (server_ip, etc.) still resolve via raw_map.
    fake_tofu_runner.output_json.side_effect = lambda name, default=None: (
        None if name == "ssh_service_token" else {"any": "other"}
    )
    result = run_snapshot(
        project_root=project_root,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        tofu_runner=fake_tofu_runner,
    )
    assert isinstance(result.outcome, S3SnapshotSkipped)
    assert result.outcome.reason == "no_snapshot_source"
    # SSH path must not have been entered — short-circuit invariant.
    setup_mocks["configure_ssh"].assert_not_called()
    setup_mocks["wait_for_ssh"].assert_not_called()
    setup_mocks["SSHClient"].assert_not_called()


def test_run_snapshot_aborts_on_other_state_failures(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #564 counterpart: every state-list failure that does
    NOT contain ``"No state file was found"`` must still raise
    PipelineError → CLI rc=2 → teardown aborts. The carve-out is
    *narrow*: a missing tofu binary, an R2 backend timeout, an
    auth failure — these are all unsafe to ignore because we
    can't know whether state actually exists or just isn't
    reachable, and a tofu destroy against unverifiable state
    could lose data."""
    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    fake_tofu_runner.state_list_ok.return_value = False
    fake_tofu_runner.diagnose_state.return_value = "tofu binary not found on PATH"
    with pytest.raises(PipelineError, match=r"tofu binary not found on PATH"):
        run_snapshot(
            project_root=project_root,
            stack_slug="nexus-test",
            template_version="v1.0.0",
            tofu_runner=fake_tofu_runner,
        )


def test_run_snapshot_skips_when_output_not_declared_in_state(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same logical no-op as the null-value case above, but exercised
    via tofu's real error path: when an output isn't declared in state,
    `tofu output -json X` exits 1 with stderr "The output variable
    requested could not be found in the state file." TofuRunner wraps
    that as TofuError; pipeline.py must distinguish this specific
    case (graceful skip) from other TofuError causes (re-raise as
    PipelineError) instead of collapsing both into None via default."""
    import subprocess

    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    from nexus_deploy import tofu as _tofu

    def raise_tofu_error(name: str, default: Any = ...) -> Any:
        if name == "ssh_service_token":
            err = subprocess.CalledProcessError(
                returncode=1,
                cmd=["tofu", "output", "-json", "ssh_service_token"],
                output="",
                stderr="The output variable requested could not be found in the state file.",
            )
            raise _tofu.TofuError("tofu output failed") from err
        return {"any": "other"}

    fake_tofu_runner.output_json.side_effect = raise_tofu_error
    result = run_snapshot(
        project_root=project_root,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        tofu_runner=fake_tofu_runner,
    )
    assert isinstance(result.outcome, S3SnapshotSkipped)
    assert result.outcome.reason == "no_snapshot_source"
    setup_mocks["configure_ssh"].assert_not_called()


def test_run_snapshot_skips_on_capitalized_no_outputs_found_marker(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenTofu emits ``"No outputs found"`` with a capital N
    (opentofu/internal/command/views/output.go:297). A case-sensitive
    ``"no outputs found" in stderr`` check would miss this and force
    the hard-failure branch, defeating the no_snapshot_source skip on
    a state file with no outputs declared at all. Regression guard
    for the case-folding fix — pipeline.py now lowercases stderr
    before marker matching, so the real Capital-N string still
    triggers the graceful skip."""
    import subprocess

    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    from nexus_deploy import tofu as _tofu

    def raise_tofu_error(name: str, default: Any = ...) -> Any:
        if name == "ssh_service_token":
            err = subprocess.CalledProcessError(
                returncode=1,
                cmd=["tofu", "output", "-json", "ssh_service_token"],
                output="",
                # Verbatim OpenTofu wording — capital N, Warning prefix.
                stderr="Warning: No outputs found\n\nThe state file either has no outputs defined...",
            )
            raise _tofu.TofuError("tofu output failed") from err
        return {"any": "other"}

    fake_tofu_runner.output_json.side_effect = raise_tofu_error
    result = run_snapshot(
        project_root=project_root,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        tofu_runner=fake_tofu_runner,
    )
    assert isinstance(result.outcome, S3SnapshotSkipped)
    assert result.outcome.reason == "no_snapshot_source"
    setup_mocks["configure_ssh"].assert_not_called()


def test_run_snapshot_aborts_when_server_in_state_but_token_missing(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SAFETY-CRITICAL: if ssh_service_token is missing BUT
    hcloud_server.main is in state, the server may have data on it
    that the pipeline can't reach via SSH. A silent graceful-skip
    here would let `tofu destroy` nuke the server with data — must
    raise PipelineError instead so the operator investigates."""
    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    # Token output missing (null in state)
    fake_tofu_runner.output_json.side_effect = lambda name, default=None: (
        None if name == "ssh_service_token" else {"any": "other"}
    )
    # But hcloud_server.main IS in state
    fake_tofu_runner.state_contains.return_value = True

    with pytest.raises(PipelineError, match="Dangerous partial state"):
        run_snapshot(
            project_root=project_root,
            stack_slug="nexus-test",
            template_version="v1.0.0",
            tofu_runner=fake_tofu_runner,
        )
    setup_mocks["configure_ssh"].assert_not_called()


def test_run_snapshot_aborts_on_other_tofu_output_failures(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The carve-out for `output_json("ssh_service_token")` failures
    is narrow: only "output not declared" stderr triggers the graceful
    no_snapshot_source skip. Every other TofuError cause (binary
    missing, transient R2 backend timeout / 5xx, JSON parse failure,
    auth failure) must re-raise as PipelineError so the operator sees
    a hard abort instead of a silently-skipped snapshot followed by
    a destroy that loses data.

    SECURITY: tofu stderr can contain provider/backend credential
    material (Cloudflare API tokens shown in plan diffs, Hetzner
    auth tokens, R2 SignatureDoesNotMatch leaking partial keys).
    The PipelineError surfaced here must NOT contain that stderr —
    same convention as TofuRunner's own error wrapping (see
    ``test_output_raw_error_message_does_not_leak_subprocess_stderr``).
    This test asserts the abort happens but pins the
    no-stderr-in-message invariant rather than locking in the
    sensitive content."""
    import subprocess

    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    from nexus_deploy import tofu as _tofu

    leaky_stderr = (
        "Error: Failed to query available provider packages — "
        "AccessKeyId=AKIA-do-not-leak-this-token-eyJhb..."
    )

    def raise_transient(name: str, default: Any = ...) -> Any:
        if name == "ssh_service_token":
            err = subprocess.CalledProcessError(
                returncode=1,
                cmd=["tofu", "output", "-json", "ssh_service_token"],
                output="",
                stderr=leaky_stderr,
            )
            raise _tofu.TofuError("tofu output failed") from err
        return {"any": "other"}

    fake_tofu_runner.output_json.side_effect = raise_transient
    # Abort behaviour: PipelineError raised, SSH side-effects skipped.
    with pytest.raises(PipelineError) as exc_info:
        run_snapshot(
            project_root=project_root,
            stack_slug="nexus-test",
            template_version="v1.0.0",
            tofu_runner=fake_tofu_runner,
        )
    setup_mocks["configure_ssh"].assert_not_called()
    # SECURITY: the user-facing exception message must NOT contain
    # the credential-looking content from tofu stderr.
    assert "AKIA-do-not-leak-this-token" not in str(exc_info.value)
    assert "eyJhb" not in str(exc_info.value)
    # But the message should still be operator-actionable.
    assert "ssh_service_token" in str(exc_info.value)


def test_run_snapshot_aborts_on_empty_domain(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty domain in config.tfvars makes ssh_host_dns unbuildable;
    must be a hard PipelineError so the teardown caller maps to rc=2
    instead of proceeding to a no-op snapshot + destroy. Feature
    flag set to ``"true"`` so we bypass the top-of-function
    short-circuit and reach the tfvars parse."""
    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    tfvars_path = project_root / "tofu" / "stack" / "config.tfvars"
    tfvars_path.write_text(
        'domain = ""\nadmin_email = "a@example.com"\nuser_email = "u@example.com"\n',
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="domain"):
        run_snapshot(
            project_root=project_root,
            stack_slug="nexus-test",
            template_version="v1.0.0",
            tofu_runner=fake_tofu_runner,
        )


def test_run_snapshot_short_circuits_before_tofu_when_flag_off(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feature-flag short-circuit (PR-4 fix-pr-comments round 2):
    when the flag is off, run_snapshot MUST return Skipped BEFORE
    any tofu/SSH side-effect. Direct callers (programmatic use,
    library import) bypass the CLI's own early gate, so this
    invariant has to live inside run_snapshot itself. Concretely:
    state_list_ok would normally raise if it returned False, but
    here we set it to False AND expect a clean Skipped return —
    proving tofu state was never touched."""
    monkeypatch.delenv("NEXUS_S3_PERSISTENCE", raising=False)
    fake_tofu_runner.state_list_ok.return_value = False
    result = run_snapshot(
        project_root=project_root,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        tofu_runner=fake_tofu_runner,
    )
    assert isinstance(result.outcome, S3SnapshotSkipped)
    assert result.outcome.reason == "feature_flag_off"
    # The short-circuit's whole point: state_list_ok was never read.
    fake_tofu_runner.state_list_ok.assert_not_called()


def test_run_snapshot_returns_skipped_when_flag_off(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With NEXUS_S3_PERSISTENCE unset (or != "true"), snapshot_to_s3
    returns Skipped/feature_flag_off and run_snapshot surfaces that
    upward without raising. CLI maps to rc=0 — the stack hasn't
    opted in to S3 persistence; the workflow proceeds to tofu
    destroy on the legacy volume-mount path."""
    monkeypatch.delenv("NEXUS_S3_PERSISTENCE", raising=False)
    result = run_snapshot(
        project_root=project_root,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        tofu_runner=fake_tofu_runner,
    )
    assert isinstance(result, SnapshotResult)
    assert isinstance(result.outcome, S3SnapshotSkipped)
    assert result.outcome.reason == "feature_flag_off"


def test_run_snapshot_returns_applied_when_full_env_set(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full feature-flag + env + ssh setup → snapshot_to_s3 ships
    the rendered script → returns Applied. ssh_instance.run_script
    is the boundary: assert it was called exactly once with a
    string starting with the bash shebang."""
    monkeypatch.setenv("NEXUS_S3_PERSISTENCE", "true")
    monkeypatch.setenv("PERSISTENCE_S3_ENDPOINT", "https://abc.r2.cloudflarestorage.com")
    monkeypatch.setenv("PERSISTENCE_S3_REGION", "auto")
    monkeypatch.setenv("PERSISTENCE_S3_BUCKET", "nexus-test")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "AKIA1234")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret-xyz")

    import subprocess

    setup_mocks["ssh_instance"].run_script.return_value = subprocess.CompletedProcess(
        args=["ssh"],
        returncode=0,
        stdout="✓ snapshot complete\n",
        stderr="",
    )

    result = run_snapshot(
        project_root=project_root,
        stack_slug="nexus-test",
        template_version="v1.0.0",
        tofu_runner=fake_tofu_runner,
    )
    assert isinstance(result.outcome, S3SnapshotApplied)
    # Run-script was called once with a bash script (starts with shebang).
    ssh_instance = setup_mocks["ssh_instance"]
    ssh_instance.run_script.assert_called_once()
    rendered_script = ssh_instance.run_script.call_args.args[0]
    assert rendered_script.startswith("#!/usr/bin/env bash")


# ---------------------------------------------------------------------------
# write_phase_log — the abort paths must print what they point at
# ---------------------------------------------------------------------------


def _result(*phases: PhaseResult) -> OrchestratorResult:
    return OrchestratorResult(phases=phases, state=OrchestratorState())


def test_write_phase_log_renders_a_marker_per_status() -> None:
    import io

    buf = io.StringIO()
    write_phase_log(
        (
            (
                "run-all",
                _result(
                    PhaseResult(name="a", status="ok"),
                    PhaseResult(name="b", status="partial", detail="half"),
                    PhaseResult(name="c", status="failed", detail="boom"),
                    PhaseResult(name="d", status="skipped"),
                ),
            ),
        ),
        stream=buf,
    )
    out = buf.getvalue()
    assert "[run-all]" in out
    assert "✓ a: ok" in out
    assert "⚠ b: partial — half" in out
    assert "✗ c: failed — boom" in out
    assert "— d: skipped" in out


def test_write_phase_log_renders_every_section_in_order() -> None:
    import io

    buf = io.StringIO()
    write_phase_log(
        (
            ("pre-bootstrap", _result(PhaseResult(name="early", status="ok"))),
            ("run-all", _result(PhaseResult(name="late", status="failed"))),
        ),
        stream=buf,
    )
    out = buf.getvalue()
    assert out.index("[pre-bootstrap]") < out.index("[run-all]")
    assert out.index("early") < out.index("late")


# ---------------------------------------------------------------------------
# GitHub Actions annotations for degraded phases (#682)
# ---------------------------------------------------------------------------


def _phase_log(
    *phases: PhaseResult,
    label: str = "run-all",
    env: dict[str, str] | None = None,
    monkeypatch: Any = None,
) -> str:
    import io

    if monkeypatch is not None:
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        for key, value in (env or {}).items():
            monkeypatch.setenv(key, value)
    buf = io.StringIO()
    write_phase_log(((label, _result(*phases)),), stream=buf)
    return buf.getvalue()


def test_partial_phase_gets_a_warning_annotation_under_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A degraded phase must be visible without opening the step log.

    ``partial`` deliberately keeps rc=0 (PR #535), so run, job and step
    all stay green. The annotation is what carries the signal into the
    run summary instead.
    """
    out = _phase_log(
        PhaseResult(name="services-configure", status="partial", detail="failed=1 (portainer)"),
        env={"GITHUB_ACTIONS": "true"},
        monkeypatch=monkeypatch,
    )
    assert "::warning title=run-all%3A services-configure::failed=1 (portainer)" in out


def test_failed_phase_gets_an_error_annotation(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _phase_log(
        PhaseResult(name="stack-sync", status="failed", detail="rc=255"),
        env={"GITHUB_ACTIONS": "true"},
        monkeypatch=monkeypatch,
    )
    assert "::error title=run-all%3A stack-sync::rc=255" in out


def test_clean_run_emits_no_annotations(monkeypatch: pytest.MonkeyPatch) -> None:
    """An all-green run must not add noise to the summary."""
    out = _phase_log(
        PhaseResult(name="a", status="ok", detail="fine"),
        PhaseResult(name="b", status="skipped", detail="not enabled"),
        env={"GITHUB_ACTIONS": "true"},
        monkeypatch=monkeypatch,
    )
    assert "::warning" not in out
    assert "::error" not in out


def test_no_annotations_outside_github_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local runs and tests get the human log only."""
    out = _phase_log(
        PhaseResult(name="services-configure", status="partial", detail="failed=1 (portainer)"),
        monkeypatch=monkeypatch,
    )
    assert "⚠ services-configure: partial" in out
    assert "::warning" not in out


def test_annotation_escapes_workflow_command_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`%`, CR and LF are structure to GitHub's parser.

    An unescaped newline in a detail would split the annotation and
    drop everything after it.
    """
    out = _phase_log(
        PhaseResult(name="p", status="partial", detail="100% done\nsecond line"),
        env={"GITHUB_ACTIONS": "true"},
        monkeypatch=monkeypatch,
    )
    assert "::warning title=run-all%3A p::100%25 done%0Asecond line" in out


def test_annotation_falls_back_to_status_when_detail_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An annotation with an empty body says nothing at all."""
    out = _phase_log(
        PhaseResult(name="p", status="partial"),
        env={"GITHUB_ACTIONS": "true"},
        monkeypatch=monkeypatch,
    )
    assert "::warning title=run-all%3A p::partial" in out


def test_annotation_title_escapes_property_delimiters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The property section delimits on `:` and `,`, the message does not.

    GitHub's parser uses two escape sets (`escapeProperty` vs
    `escapeData` in actions/toolkit). A comma in a title would start a
    second property; a colon can close the property section early. The
    same characters in the message body are literal and must stay
    readable.
    """
    out = _phase_log(
        PhaseResult(name="a,b", status="partial", detail="x, y: z"),
        label="run:all",
        env={"GITHUB_ACTIONS": "true"},
        monkeypatch=monkeypatch,
    )
    assert "::warning title=run%3Aall%3A a%2Cb::x, y: z" in out


def test_post_bootstrap_abort_prints_the_phase_log_before_raising(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression guard for a debugging cycle lost to a missing log.

    The abort message says "see per-phase log above". The CLI handler
    that prints phases sits after its try block, so on PipelineError it
    never ran and operators got the sentence with nothing above it.
    """
    mock_orchestrator.run_pre_bootstrap.return_value = _result(
        PhaseResult(name="pre", status="ok"),
    )
    mock_orchestrator.run_all.return_value = _result(
        PhaseResult(name="infisical-bootstrap", status="failed", detail="token missing"),
    )

    with pytest.raises(PipelineError, match="post-bootstrap"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )

    err = capsys.readouterr().err
    assert "✗ infisical-bootstrap: failed — token missing" in err
    # Both halves, so a "partial" earlier on is visible as context.
    assert "[pre-bootstrap]" in err
    assert "[run-all]" in err


def test_pre_bootstrap_abort_prints_the_phase_log_before_raising(
    project_root: Path,
    fake_tofu_runner: MagicMock,
    setup_mocks: dict[str, Any],
    mock_orchestrator: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock_orchestrator.run_pre_bootstrap.return_value = _result(
        PhaseResult(name="compose-up", status="failed", detail="stack down"),
    )

    with pytest.raises(PipelineError, match="pre-bootstrap"):
        run_pipeline(
            project_root=project_root,
            options=PipelineOptions(),
            tofu_runner=fake_tofu_runner,
        )

    err = capsys.readouterr().err
    assert "✗ compose-up: failed — stack down" in err
