"""Tests for nexus_deploy.orchestrator.

Heavy mocking of underlying module functions — orchestrator is wiring,
not new logic. Focus on:

- State-handoff between phases (gitea_token → seed/kestra/woodpecker/mirror)
- Phase ordering (gitea before seed, gitea before kestra, etc.)
- Skip-conditions (kestra skipped when 'kestra' not enabled, etc.)
- Failed phase aborts orchestrator (later phases not invoked)
- Partial phase keeps orchestrator running
- ExitStack tunnel cleanup
- CLI rc=0/1/2 contract
"""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path
from typing import Any, Literal, cast
from unittest.mock import MagicMock, patch

import pytest

from nexus_deploy.config import NexusConfig
from nexus_deploy.gitea import (
    CreateRepoResult,
    CreateUserResult,
    ForkResult,
    GiteaResult,
    MirrorResult,
    MirrorSetupResult,
    OAuthAppResult,
)
from nexus_deploy.infisical import BootstrapEnv
from nexus_deploy.orchestrator import (
    Orchestrator,
    OrchestratorResult,
    OrchestratorState,
    PhaseResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_config() -> NexusConfig:
    """Minimal config for orchestrator instantiation; phase methods
    are mocked so most fields don't matter."""
    return NexusConfig(
        admin_username="admin",
        gitea_admin_password="gitea-admin",
        kestra_admin_password="kestra-pw",
    )


@pytest.fixture
def minimal_env() -> BootstrapEnv:
    return BootstrapEnv(
        domain="example.com",
        admin_email="admin@example.com",
    )


@pytest.fixture
def orchestrator(minimal_config: NexusConfig, minimal_env: BootstrapEnv) -> Orchestrator:
    """An orchestrator with a typical enabled list. Phase methods
    will be mocked per-test."""
    return Orchestrator(
        config=minimal_config,
        bootstrap_env=minimal_env,
        enabled_services=["gitea", "kestra", "jupyter", "marimo", "woodpecker"],
        repo_name="nexus-example-com-gitea",
        gitea_repo_owner="admin",
        project_id="proj-id",
        infisical_token="infi-token",
    )


# Generic mock for a phase that returns a successful PhaseResult.
def _ok_phase(name: str) -> Any:
    return PhaseResult(name=name, status="ok")


# ---------------------------------------------------------------------------
# Result aggregation
# ---------------------------------------------------------------------------


def test_orchestrator_result_is_success_when_all_ok() -> None:
    result = OrchestratorResult(
        phases=(
            PhaseResult("a", "ok"),
            PhaseResult("b", "ok"),
            PhaseResult("c", "skipped"),
        ),
        state=OrchestratorState(),
    )
    assert result.is_success
    assert not result.has_partial
    assert not result.has_hard_failure


def test_orchestrator_result_partial() -> None:
    result = OrchestratorResult(
        phases=(PhaseResult("a", "ok"), PhaseResult("b", "partial")),
        state=OrchestratorState(),
    )
    assert not result.is_success
    assert result.has_partial
    assert not result.has_hard_failure


def test_orchestrator_result_hard_failure() -> None:
    result = OrchestratorResult(
        phases=(PhaseResult("a", "failed"),),
        state=OrchestratorState(),
    )
    assert not result.is_success
    assert result.has_hard_failure


# ---------------------------------------------------------------------------
# State-handoff: gitea_token flows from gitea-configure to downstream phases
# ---------------------------------------------------------------------------


def _mk_gitea_result(token: str = "abc-token") -> GiteaResult:
    """Helper: build a GiteaResult with the given token."""
    return GiteaResult(
        db_pw_synced=True,
        admin=CreateUserResult(name="admin", status="created"),
        user=None,
        token=token,
        token_error="",
        repo=CreateRepoResult(name="repo", status="created"),
        collaborator_added=False,
        restart_services=("kestra", "jupyter"),
    )


def test_state_handoff_gitea_token_reaches_seed(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-state: gitea-configure populates state.gitea_token; seed reads it."""
    captured_tokens: list[str | None] = []

    def fake_gitea_configure(*args: Any, **kwargs: Any) -> GiteaResult:
        return _mk_gitea_result(token="abc-token")

    def fake_seed(**kwargs: Any) -> Any:
        captured_tokens.append(kwargs.get("token"))
        result = MagicMock()
        result.created = 5
        result.skipped = 0
        result.failed = 0
        return result

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._gitea.run_configure_gitea", fake_gitea_configure
    )
    monkeypatch.setattr("nexus_deploy.orchestrator._seeder.run_seed_for_repo", fake_seed)
    # Mock other phases to avoid running them. The post-bootstrap
    # phase set is stubbed in full so the test stays focused on the
    # phase-handoff under test.
    monkeypatch.setattr("nexus_deploy.orchestrator.SSHClient", MagicMock())
    for phase_name in (
        "_phase_infisical_bootstrap",
        "_phase_services_configure",
        "_phase_compose_restart",
        "_phase_kestra_secret_sync",
        "_phase_kestra_register",
        "_phase_woodpecker_oauth",
        "_phase_woodpecker_apply",
        "_phase_mirror_setup",
        "_phase_mirror_seed_rerun",
        "_phase_mirror_finalize",
        "_phase_secret_sync_jupyter",
        "_phase_secret_sync_marimo",
        "_phase_secret_sync_code_server",
    ):
        monkeypatch.setattr(orchestrator, phase_name, lambda _ssh, n=phase_name: _ok_phase(n))
    # Make examples/workspace-seeds/ "exist" so seed phase doesn't skip
    monkeypatch.setattr("nexus_deploy.orchestrator.Path.is_dir", lambda self: True)

    result = orchestrator.run_all()
    assert orchestrator.state.gitea_token == "abc-token"
    assert captured_tokens == ["abc-token"]
    assert result.state.gitea_token == "abc-token"


def test_state_handoff_restart_services_populated_from_gitea(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-stdout: state.restart_services populated by gitea-configure;
    will be emitted to stdout by the CLI."""
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._gitea.run_configure_gitea",
        lambda *a, **kw: _mk_gitea_result(),
    )
    monkeypatch.setattr("nexus_deploy.orchestrator.SSHClient", MagicMock())
    for phase_name in (
        "_phase_infisical_bootstrap",
        "_phase_services_configure",
        "_phase_compose_restart",
        "_phase_kestra_secret_sync",
        "_phase_seed",
        "_phase_kestra_register",
        "_phase_woodpecker_oauth",
        "_phase_woodpecker_apply",
        "_phase_mirror_setup",
        "_phase_mirror_seed_rerun",
        "_phase_mirror_finalize",
        "_phase_secret_sync_jupyter",
        "_phase_secret_sync_marimo",
        "_phase_secret_sync_code_server",
    ):
        monkeypatch.setattr(orchestrator, phase_name, lambda _ssh, n=phase_name: _ok_phase(n))

    result = orchestrator.run_all()
    assert result.state.restart_services == ("kestra", "jupyter")


def test_state_handoff_woodpecker_creds_populated(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-stdout: woodpecker-oauth populates state.woodpecker_*."""
    orchestrator.state.gitea_token = "pre-set-token"  # skip the gitea phase

    def fake_woodpecker(*args: Any, **kwargs: Any) -> tuple[OAuthAppResult, str | None, bool]:
        return (
            OAuthAppResult(client_id="wp-id", client_secret="wp-secret", name="Woodpecker CI"),
            None,
            False,
        )

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._gitea.run_woodpecker_oauth_setup", fake_woodpecker
    )
    monkeypatch.setattr("nexus_deploy.orchestrator.SSHClient", MagicMock())
    for phase_name in (
        "_phase_infisical_bootstrap",
        "_phase_services_configure",
        "_phase_gitea_configure",
        "_phase_compose_restart",
        "_phase_kestra_secret_sync",
        "_phase_seed",
        "_phase_kestra_register",
        "_phase_woodpecker_apply",
        "_phase_mirror_setup",
        "_phase_mirror_seed_rerun",
        "_phase_mirror_finalize",
        "_phase_secret_sync_jupyter",
        "_phase_secret_sync_marimo",
        "_phase_secret_sync_code_server",
    ):
        monkeypatch.setattr(orchestrator, phase_name, lambda _ssh, n=phase_name: _ok_phase(n))

    result = orchestrator.run_all()
    assert result.state.woodpecker_client_id == "wp-id"
    assert result.state.woodpecker_client_secret == "wp-secret"


def test_state_handoff_fork_populated_from_mirror(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-state: mirror-setup populates state.fork_name + fork_owner
    when a fork is provisioned."""
    orchestrator.gh_mirror_repos = ["https://github.com/owner/repo"]
    orchestrator.gh_mirror_token = "gh-tok"
    orchestrator.gitea_user_username = "user"
    orchestrator.state.gitea_token = "pre-set-token"

    def fake_mirror(*args: Any, **kwargs: Any) -> MirrorSetupResult:
        return MirrorSetupResult(
            admin_uid=1,
            admin_uid_error="",
            mirrors=(MirrorResult(name="repo", status="created"),),
            fork=ForkResult(owner="user", name="user-fork", status="created"),
            collaborator_added_count=1,
            fork_synced=True,
        )

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_mirror_setup", fake_mirror)
    monkeypatch.setattr("nexus_deploy.orchestrator.SSHClient", MagicMock())
    for phase_name in (
        "_phase_infisical_bootstrap",
        "_phase_services_configure",
        "_phase_gitea_configure",
        "_phase_compose_restart",
        "_phase_kestra_secret_sync",
        "_phase_seed",
        "_phase_kestra_register",
        "_phase_woodpecker_oauth",
        "_phase_woodpecker_apply",
        "_phase_mirror_seed_rerun",
        "_phase_mirror_finalize",
        "_phase_secret_sync_jupyter",
        "_phase_secret_sync_marimo",
        "_phase_secret_sync_code_server",
    ):
        monkeypatch.setattr(orchestrator, phase_name, lambda _ssh, n=phase_name: _ok_phase(n))

    result = orchestrator.run_all()
    assert result.state.fork_name == "user-fork"
    assert result.state.fork_owner == "user"


# ---------------------------------------------------------------------------
# Phase skipping conditions
# ---------------------------------------------------------------------------


def test_phase_kestra_skipped_when_kestra_not_enabled(
    minimal_config: NexusConfig, minimal_env: BootstrapEnv
) -> None:
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=minimal_env,
        enabled_services=["gitea"],  # kestra NOT enabled
        repo_name="r",
        gitea_repo_owner="o",
    )
    ssh = MagicMock()
    result = orch._phase_kestra_register(ssh)
    assert result.status == "skipped"
    assert "kestra not enabled" in result.detail


def test_phase_mirror_skipped_when_no_mirrors_configured(
    minimal_config: NexusConfig, minimal_env: BootstrapEnv
) -> None:
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=minimal_env,
        enabled_services=["gitea"],
        repo_name="r",
        gitea_repo_owner="o",
        # gh_mirror_repos defaults to []
    )
    ssh = MagicMock()
    result = orch._phase_mirror_setup(ssh)
    assert result.status == "skipped"
    assert "no mirrors" in result.detail


def test_phase_seed_skipped_when_no_gitea_token(
    minimal_config: NexusConfig, minimal_env: BootstrapEnv
) -> None:
    """Seed depends on gitea_token; if a prior phase didn't produce
    one, seed skips gracefully."""
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=minimal_env,
        enabled_services=["gitea"],
        repo_name="r",
        gitea_repo_owner="o",
    )
    # state.gitea_token is None by default
    ssh = MagicMock()
    result = orch._phase_seed(ssh)
    assert result.status == "skipped"
    assert "no gitea_token" in result.detail


def test_phase_woodpecker_skipped_when_woodpecker_not_enabled(
    minimal_config: NexusConfig, minimal_env: BootstrapEnv
) -> None:
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=minimal_env,
        enabled_services=["gitea"],  # NOT woodpecker
        repo_name="r",
        gitea_repo_owner="o",
    )
    ssh = MagicMock()
    result = orch._phase_woodpecker_oauth(ssh)
    assert result.status == "skipped"


def test_phase_woodpecker_skipped_when_no_gitea_token(
    minimal_config: NexusConfig, minimal_env: BootstrapEnv
) -> None:
    """If gitea-configure didn't produce a token (e.g. partial fail),
    woodpecker-oauth skips."""
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=minimal_env,
        enabled_services=["woodpecker"],
        repo_name="r",
        gitea_repo_owner="o",
    )
    # state.gitea_token is None
    ssh = MagicMock()
    result = orch._phase_woodpecker_oauth(ssh)
    assert result.status == "skipped"


# ---------------------------------------------------------------------------
# Phase failure aborts orchestrator
# ---------------------------------------------------------------------------


def test_failed_phase_aborts_downstream_phases(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-abort: a phase with status='failed' stops the run; later
    phases are NOT invoked."""
    invoked: list[str] = []

    def make_phase(name: str, status: Literal["ok", "partial", "failed", "skipped"] = "ok") -> Any:
        def phase(_ssh: Any) -> PhaseResult:
            invoked.append(name)
            return PhaseResult(name=name, status=status)

        return phase

    monkeypatch.setattr("nexus_deploy.orchestrator.SSHClient", MagicMock())
    monkeypatch.setattr(orchestrator, "_phase_infisical_bootstrap", make_phase("infisical"))
    # services-configure FAILS
    monkeypatch.setattr(orchestrator, "_phase_services_configure", make_phase("services", "failed"))
    # Downstream phases — should NOT be invoked
    monkeypatch.setattr(orchestrator, "_phase_gitea_configure", make_phase("gitea"))
    monkeypatch.setattr(orchestrator, "_phase_seed", make_phase("seed"))
    monkeypatch.setattr(orchestrator, "_phase_kestra_register", make_phase("kestra"))
    monkeypatch.setattr(orchestrator, "_phase_woodpecker_oauth", make_phase("woodpecker"))
    monkeypatch.setattr(orchestrator, "_phase_mirror_setup", make_phase("mirror"))
    monkeypatch.setattr(orchestrator, "_phase_secret_sync_jupyter", make_phase("ss-j"))
    monkeypatch.setattr(orchestrator, "_phase_secret_sync_marimo", make_phase("ss-m"))
    monkeypatch.setattr(orchestrator, "_phase_secret_sync_code_server", make_phase("ss-cs"))

    result = orchestrator.run_all()
    assert invoked == ["infisical", "services"]
    assert result.has_hard_failure
    assert len(result.phases) == 2
    assert result.phases[1].status == "failed"


def test_partial_phase_continues_to_downstream(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-continue: status='partial' is yellow-warn but not abort.
    Downstream phases still run."""
    invoked: list[str] = []

    def make_phase(name: str, status: Literal["ok", "partial", "failed", "skipped"] = "ok") -> Any:
        def phase(_ssh: Any) -> PhaseResult:
            invoked.append(name)
            return PhaseResult(name=name, status=status)

        return phase

    monkeypatch.setattr("nexus_deploy.orchestrator.SSHClient", MagicMock())
    monkeypatch.setattr(orchestrator, "_phase_infisical_bootstrap", make_phase("infisical"))
    monkeypatch.setattr(
        orchestrator, "_phase_services_configure", make_phase("services", "partial")
    )
    monkeypatch.setattr(orchestrator, "_phase_forgejo_configure", make_phase("forgejo-cfg"))
    monkeypatch.setattr(
        orchestrator, "_phase_forgejo_runner_register", make_phase("forgejo-runner")
    )
    monkeypatch.setattr(orchestrator, "_phase_gitea_configure", make_phase("gitea"))
    monkeypatch.setattr(orchestrator, "_phase_compose_restart", make_phase("compose-restart"))
    monkeypatch.setattr(orchestrator, "_phase_kestra_secret_sync", make_phase("kestra-ss"))
    monkeypatch.setattr(orchestrator, "_phase_seed", make_phase("seed"))
    monkeypatch.setattr(orchestrator, "_phase_kestra_register", make_phase("kestra-reg"))
    monkeypatch.setattr(orchestrator, "_phase_woodpecker_oauth", make_phase("woodpecker"))
    monkeypatch.setattr(orchestrator, "_phase_woodpecker_apply", make_phase("wp-apply"))
    monkeypatch.setattr(orchestrator, "_phase_mirror_setup", make_phase("mirror"))
    monkeypatch.setattr(orchestrator, "_phase_mirror_seed_rerun", make_phase("mirror-seed"))
    monkeypatch.setattr(orchestrator, "_phase_mirror_finalize", make_phase("mirror-fin"))
    monkeypatch.setattr(orchestrator, "_phase_secret_sync_jupyter", make_phase("ss-j"))
    monkeypatch.setattr(orchestrator, "_phase_secret_sync_marimo", make_phase("ss-m"))
    monkeypatch.setattr(orchestrator, "_phase_secret_sync_code_server", make_phase("ss-cs"))

    result = orchestrator.run_all()
    # All 17 phases ran despite the partial in services-configure.
    assert len(invoked) == 17
    assert result.has_partial
    assert not result.has_hard_failure


# ---------------------------------------------------------------------------
# Phase ordering
# ---------------------------------------------------------------------------


def test_phases_run_in_deterministic_order(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-order: phases run in the documented order. Updated for Phase
    4b2 (#505) — 14 phases instead of 9. New phases interleave per the
    state-handoff dependency graph (compose-restart after gitea;
    kestra-secret-sync before kestra-register; woodpecker-apply after
    woodpecker-oauth; mirror-seed-rerun + mirror-finalize after
    mirror-setup)."""
    invoked: list[str] = []

    def make_phase(name: str) -> Any:
        def phase(_ssh: Any) -> PhaseResult:
            invoked.append(name)
            return PhaseResult(name=name, status="ok")

        return phase

    monkeypatch.setattr("nexus_deploy.orchestrator.SSHClient", MagicMock())
    monkeypatch.setattr(orchestrator, "_phase_infisical_bootstrap", make_phase("1-infisical"))
    monkeypatch.setattr(orchestrator, "_phase_services_configure", make_phase("2-services"))
    monkeypatch.setattr(orchestrator, "_phase_gitea_configure", make_phase("3-gitea"))
    monkeypatch.setattr(orchestrator, "_phase_compose_restart", make_phase("4-compose-restart"))
    monkeypatch.setattr(orchestrator, "_phase_kestra_secret_sync", make_phase("5-kestra-ss"))
    monkeypatch.setattr(orchestrator, "_phase_kestra_register", make_phase("6-kestra-reg"))
    monkeypatch.setattr(orchestrator, "_phase_seed", make_phase("7-seed"))
    monkeypatch.setattr(orchestrator, "_phase_woodpecker_oauth", make_phase("8-wp-oauth"))
    monkeypatch.setattr(orchestrator, "_phase_woodpecker_apply", make_phase("9-wp-apply"))
    monkeypatch.setattr(orchestrator, "_phase_mirror_setup", make_phase("10-mirror"))
    monkeypatch.setattr(orchestrator, "_phase_mirror_seed_rerun", make_phase("11-mirror-seed"))
    monkeypatch.setattr(orchestrator, "_phase_mirror_finalize", make_phase("12-mirror-fin"))
    monkeypatch.setattr(orchestrator, "_phase_secret_sync_jupyter", make_phase("13-ss-jupyter"))
    monkeypatch.setattr(orchestrator, "_phase_secret_sync_marimo", make_phase("14-ss-marimo"))
    monkeypatch.setattr(
        orchestrator,
        "_phase_secret_sync_code_server",
        make_phase("15-ss-code-server"),
    )

    orchestrator.run_all()
    assert invoked == [
        "1-infisical",
        "2-services",
        "3-gitea",
        "4-compose-restart",
        "5-kestra-ss",
        "6-kestra-reg",
        "7-seed",
        "8-wp-oauth",
        "9-wp-apply",
        "10-mirror",
        "11-mirror-seed",
        "12-mirror-fin",
        "13-ss-jupyter",
        "14-ss-marimo",
        "15-ss-code-server",
    ]


# ---------------------------------------------------------------------------
# CLI rc=0/1/2 contract
# ---------------------------------------------------------------------------


def test_cli_run_all_unknown_arg_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    from nexus_deploy.__main__ import _run_all

    rc = _run_all(["--bogus"])
    assert rc == 2
    assert "unknown args" in capsys.readouterr().err


def test_cli_run_all_missing_env_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _run_all

    for var in (
        "ADMIN_EMAIL",
        "REPO_NAME",
        "GITEA_REPO_OWNER",
        "ENABLED_SERVICES",
        "DOMAIN",
        "PROJECT_ID",
        "INFISICAL_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    rc = _run_all([])
    assert rc == 2
    assert "missing required env" in capsys.readouterr().err


def test_cli_run_all_rc0_on_all_ok(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _run_all

    for var, val in (
        ("ADMIN_EMAIL", "a@b"),
        ("REPO_NAME", "r"),
        ("GITEA_REPO_OWNER", "o"),
        ("ENABLED_SERVICES", "gitea,kestra"),
        ("DOMAIN", "example.com"),
        ("PROJECT_ID", "p"),
        ("INFISICAL_TOKEN", "t"),
    ):
        monkeypatch.setenv(var, val)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")

    fake_result = OrchestratorResult(
        phases=(PhaseResult("p1", "ok"), PhaseResult("p2", "skipped")),
        state=OrchestratorState(restart_services=("kestra",)),
    )
    with patch.object(Orchestrator, "run_all", return_value=fake_result):
        rc = _run_all([])
    assert rc == 0
    out = capsys.readouterr().out
    # shlex.quote of "kestra" (no special chars) yields bare "kestra"
    assert "RESTART_SERVICES=kestra" in out


def test_cli_run_all_rc1_on_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_deploy.__main__ import _run_all

    for var, val in (
        ("ADMIN_EMAIL", "a@b"),
        ("REPO_NAME", "r"),
        ("GITEA_REPO_OWNER", "o"),
        ("ENABLED_SERVICES", "gitea"),
        ("DOMAIN", "example.com"),
        ("PROJECT_ID", "p"),
        ("INFISICAL_TOKEN", "t"),
    ):
        monkeypatch.setenv(var, val)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")

    fake_result = OrchestratorResult(
        phases=(PhaseResult("p1", "partial", "warn"),),
        state=OrchestratorState(),
    )
    with patch.object(Orchestrator, "run_all", return_value=fake_result):
        rc = _run_all([])
    assert rc == 1


def test_cli_run_all_rc2_on_hard_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_deploy.__main__ import _run_all

    for var, val in (
        ("ADMIN_EMAIL", "a@b"),
        ("REPO_NAME", "r"),
        ("GITEA_REPO_OWNER", "o"),
        ("ENABLED_SERVICES", "gitea"),
        ("DOMAIN", "example.com"),
        ("PROJECT_ID", "p"),
        ("INFISICAL_TOKEN", "t"),
    ):
        monkeypatch.setenv(var, val)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")

    fake_result = OrchestratorResult(
        phases=(PhaseResult("p1", "failed", "boom"),),
        state=OrchestratorState(),
    )
    with patch.object(Orchestrator, "run_all", return_value=fake_result):
        rc = _run_all([])
    assert rc == 2


def test_cli_run_all_emits_woodpecker_creds_when_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R-stdout: woodpecker_* values are emitted as eval-able lines
    when populated by orchestrator state."""
    from nexus_deploy.__main__ import _run_all

    for var, val in (
        ("ADMIN_EMAIL", "a@b"),
        ("REPO_NAME", "r"),
        ("GITEA_REPO_OWNER", "o"),
        ("ENABLED_SERVICES", "gitea,woodpecker"),
        ("DOMAIN", "example.com"),
        ("PROJECT_ID", "p"),
        ("INFISICAL_TOKEN", "t"),
    ):
        monkeypatch.setenv(var, val)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")

    fake_result = OrchestratorResult(
        phases=(PhaseResult("p1", "ok"),),
        state=OrchestratorState(
            restart_services=(),
            woodpecker_client_id="wp-client",
            woodpecker_client_secret="wp-secret",
        ),
    )
    with patch.object(Orchestrator, "run_all", return_value=fake_result):
        _run_all([])
    out = capsys.readouterr().out
    assert (
        "WOODPECKER_GITEA_CLIENT='wp-client'" in out or "WOODPECKER_GITEA_CLIENT=wp-client" in out
    )
    assert (
        "WOODPECKER_GITEA_SECRET='wp-secret'" in out or "WOODPECKER_GITEA_SECRET=wp-secret" in out
    )


def test_cli_run_all_no_gitea_token_in_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R-state-confinement: gitea_token must NOT leak to stdout —
    it's consumed entirely inside the orchestrator. Same for
    fork_name / fork_owner."""
    from nexus_deploy.__main__ import _run_all

    for var, val in (
        ("ADMIN_EMAIL", "a@b"),
        ("REPO_NAME", "r"),
        ("GITEA_REPO_OWNER", "o"),
        ("ENABLED_SERVICES", "gitea"),
        ("DOMAIN", "example.com"),
        ("PROJECT_ID", "p"),
        ("INFISICAL_TOKEN", "t"),
    ):
        monkeypatch.setenv(var, val)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")

    fake_result = OrchestratorResult(
        phases=(PhaseResult("p1", "ok"),),
        state=OrchestratorState(
            gitea_token="SECRET-TOKEN-ABCDEF",
            fork_name="some-fork",
            fork_owner="some-owner",
        ),
    )
    with patch.object(Orchestrator, "run_all", return_value=fake_result):
        _run_all([])
    captured = capsys.readouterr()
    assert "SECRET-TOKEN-ABCDEF" not in captured.out
    assert "SECRET-TOKEN-ABCDEF" not in captured.err
    assert "GITEA_TOKEN" not in captured.out
    assert "FORK_NAME" not in captured.out
    assert "FORK_OWNER" not in captured.out


def test_phase_infisical_skipped_without_creds(
    minimal_config: NexusConfig, minimal_env: BootstrapEnv
) -> None:
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=minimal_env,
        enabled_services=[],
        repo_name="r",
        gitea_repo_owner="o",
        # project_id + infisical_token left as None
    )
    result = orch._phase_infisical_bootstrap(MagicMock())
    assert result.status == "skipped"


def test_phase_gitea_configure_skipped_when_gitea_disabled(
    minimal_env: BootstrapEnv,
) -> None:
    config = NexusConfig()
    orch = Orchestrator(
        config=config,
        bootstrap_env=minimal_env,
        enabled_services=[],
        repo_name="r",
        gitea_repo_owner="o",
    )
    result = orch._phase_gitea_configure(MagicMock())
    assert result.status == "skipped"


def test_phase_gitea_configure_partial_without_admin_password(
    minimal_env: BootstrapEnv,
) -> None:
    config = NexusConfig()  # no gitea_admin_password
    orch = Orchestrator(
        config=config,
        bootstrap_env=minimal_env,
        enabled_services=["gitea"],
        repo_name="r",
        gitea_repo_owner="o",
    )
    result = orch._phase_gitea_configure(MagicMock())
    assert result.status == "partial"
    assert "GITEA_ADMIN_PASS" in result.detail


def test_phase_kestra_partial_without_admin_pass(minimal_env: BootstrapEnv) -> None:
    config = NexusConfig()  # no kestra_admin_password
    orch = Orchestrator(
        config=config,
        bootstrap_env=minimal_env,
        enabled_services=["kestra"],
        repo_name="r",
        gitea_repo_owner="o",
    )
    result = orch._phase_kestra_register(MagicMock())
    assert result.status == "partial"


def test_phase_secret_sync_jupyter_skipped_when_disabled(minimal_env: BootstrapEnv) -> None:
    config = NexusConfig()
    orch = Orchestrator(
        config=config,
        bootstrap_env=minimal_env,
        enabled_services=[],
        repo_name="r",
        gitea_repo_owner="o",
    )
    result = orch._phase_secret_sync_jupyter(MagicMock())
    assert result.status == "skipped"


def test_phase_secret_sync_marimo_skipped_when_disabled(minimal_env: BootstrapEnv) -> None:
    config = NexusConfig()
    orch = Orchestrator(
        config=config,
        bootstrap_env=minimal_env,
        enabled_services=[],
        repo_name="r",
        gitea_repo_owner="o",
    )
    result = orch._phase_secret_sync_marimo(MagicMock())
    assert result.status == "skipped"


def test_phase_secret_sync_code_server_skipped_when_disabled(minimal_env: BootstrapEnv) -> None:
    config = NexusConfig()
    orch = Orchestrator(
        config=config,
        bootstrap_env=minimal_env,
        enabled_services=[],
        repo_name="r",
        gitea_repo_owner="o",
    )
    result = orch._phase_secret_sync_code_server(MagicMock())
    assert result.status == "skipped"


def test_phase_secret_sync_partial_without_creds(minimal_env: BootstrapEnv) -> None:
    config = NexusConfig()
    orch = Orchestrator(
        config=config,
        bootstrap_env=minimal_env,
        enabled_services=["jupyter"],
        repo_name="r",
        gitea_repo_owner="o",
        # project_id + infisical_token left as None
    )
    result = orch._phase_secret_sync_jupyter(MagicMock())
    assert result.status == "partial"


def test_cli_run_all_unexpected_exception_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _run_all

    for var, val in (
        ("ADMIN_EMAIL", "a@b"),
        ("REPO_NAME", "r"),
        ("GITEA_REPO_OWNER", "o"),
        ("ENABLED_SERVICES", "gitea"),
        ("DOMAIN", "example.com"),
        ("PROJECT_ID", "p"),
        ("INFISICAL_TOKEN", "t"),
    ):
        monkeypatch.setenv(var, val)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")

    def boom(self: Any) -> Any:
        raise RuntimeError("secret-bearing-message-NEVER-PRINT")

    with patch.object(Orchestrator, "run_all", boom):
        rc = _run_all([])
    assert rc == 2
    captured = capsys.readouterr()
    assert "RuntimeError" in captured.err
    assert "secret-bearing-message-NEVER-PRINT" not in captured.err
    assert "secret-bearing-message-NEVER-PRINT" not in captured.out


# ---------------------------------------------------------------------------
# Per-phase happy-path bodies (mock underlying module functions to drive
# the try-block + result-mapping logic to ok/partial/failed PhaseResults).
# ---------------------------------------------------------------------------


class _FakeTunnel:
    """Stand-in for SSHClient.port_forward()'s context manager.
    Yields the port int that __enter__ returns."""

    def __init__(self, port: int = 5500) -> None:
        self._port = port

    def __enter__(self) -> int:
        return self._port

    def __exit__(self, *_a: Any) -> None:
        return None


def _ssh_with_tunnel() -> Any:
    ssh = MagicMock()
    ssh.port_forward = MagicMock(return_value=_FakeTunnel())
    return ssh


def test_phase_infisical_bootstrap_ok(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.infisical import BootstrapResult

    fake_client = MagicMock()
    fake_client.bootstrap.return_value = BootstrapResult(folders_built=3, pushed=12, failed=0)
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._infisical.InfisicalClient", lambda **_kw: fake_client
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._infisical.compute_folders", lambda *_a, **_kw: ()
    )
    result = orchestrator._phase_infisical_bootstrap(MagicMock())
    assert result.status == "ok"
    assert "built=3" in result.detail
    assert "pushed=12" in result.detail


def test_phase_infisical_bootstrap_partial_when_failed_gt_zero(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.infisical import BootstrapResult

    fake_client = MagicMock()
    fake_client.bootstrap.return_value = BootstrapResult(folders_built=2, pushed=5, failed=1)
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._infisical.InfisicalClient", lambda **_kw: fake_client
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._infisical.compute_folders", lambda *_a, **_kw: ()
    )
    result = orchestrator._phase_infisical_bootstrap(MagicMock())
    assert result.status == "partial"
    assert "failed=1" in result.detail


def test_phase_infisical_bootstrap_failed_on_transport(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    def boom(**_kw: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr("nexus_deploy.orchestrator._infisical.InfisicalClient", boom)
    result = orchestrator._phase_infisical_bootstrap(MagicMock())
    assert result.status == "failed"
    assert "TimeoutExpired" in result.detail


def test_phase_infisical_bootstrap_skipped_when_creds_missing(
    minimal_config: NexusConfig, minimal_env: BootstrapEnv
) -> None:
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=minimal_env,
        enabled_services=[],
        repo_name="r",
        gitea_repo_owner="o",
        # project_id / infisical_token default to None
    )
    result = orch._phase_infisical_bootstrap(MagicMock())
    assert result.status == "skipped"


def test_phase_services_configure_ok(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.services import HookResult, SetupResult

    fake = SetupResult(
        hooks=(
            HookResult(name="x", status="configured"),
            HookResult(name="y", status="already-configured"),
        )
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._services.run_admin_setups", lambda *_a, **_kw: fake
    )
    result = orchestrator._phase_services_configure(MagicMock())
    assert result.status == "ok"
    assert "configured=1" in result.detail


def test_phase_services_configure_partial_when_failed(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.services import HookResult, SetupResult

    fake = SetupResult(
        hooks=(
            HookResult(name="x", status="configured"),
            HookResult(name="y", status="failed"),
        )
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._services.run_admin_setups", lambda *_a, **_kw: fake
    )
    result = orchestrator._phase_services_configure(MagicMock())
    assert result.status == "partial"
    assert "failed=1" in result.detail


def test_phase_services_configure_names_the_failing_hooks(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The detail must say *which* hook failed.

    A bare ``failed=1`` over six enabled services is not a diagnosis;
    recovering the name previously meant correlating three workflow
    runs.
    """
    from nexus_deploy.services import HookResult, SetupResult

    fake = SetupResult(
        hooks=(
            HookResult(name="portainer", status="failed"),
            HookResult(name="metabase", status="skipped-not-ready"),
            HookResult(name="lakefs", status="failed"),
        )
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._services.run_admin_setups", lambda *_a, **_kw: fake
    )
    result = orchestrator._phase_services_configure(MagicMock())
    assert result.status == "partial"
    assert "failed=2 (portainer, lakefs)" in result.detail
    assert "skipped-not-ready=1 (metabase)" in result.detail


def test_phase_services_configure_omits_empty_name_lists(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An all-green line must not gain a stray ``()``."""
    from nexus_deploy.services import HookResult, SetupResult

    fake = SetupResult(hooks=(HookResult(name="x", status="configured"),))
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._services.run_admin_setups", lambda *_a, **_kw: fake
    )
    result = orchestrator._phase_services_configure(MagicMock())
    assert result.status == "ok"
    assert "()" not in result.detail
    assert result.detail == "configured=1 already-configured=0 skipped-not-ready=0"


def test_phase_gitea_configure_ok_populates_state(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _mk_gitea_result(token="abc-token")
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._gitea.run_configure_gitea", lambda *_a, **_kw: fake
    )
    result = orchestrator._phase_gitea_configure(_ssh_with_tunnel())
    assert result.status == "ok"
    assert orchestrator.state.gitea_token == "abc-token"
    assert orchestrator.state.restart_services == ("kestra", "jupyter")


def test_phase_gitea_configure_partial_when_subresult_unsuccessful(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = GiteaResult(
        db_pw_synced=True,
        admin=CreateUserResult(name="admin", status="failed"),  # is_success=False
        user=None,
        token="abc",
        token_error="",
        repo=CreateRepoResult(name="repo", status="created"),
        collaborator_added=False,
        restart_services=(),
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._gitea.run_configure_gitea", lambda *_a, **_kw: fake
    )
    result = orchestrator._phase_gitea_configure(_ssh_with_tunnel())
    assert result.status == "partial"


def test_phase_gitea_configure_partial_when_admin_password_missing(
    minimal_env: BootstrapEnv,
) -> None:
    cfg = NexusConfig(admin_username="admin")  # no gitea_admin_password
    orch = Orchestrator(
        config=cfg,
        bootstrap_env=minimal_env,
        enabled_services=["gitea"],
        repo_name="r",
        gitea_repo_owner="o",
    )
    result = orch._phase_gitea_configure(MagicMock())
    assert result.status == "partial"
    assert "GITEA_ADMIN_PASS" in result.detail


def test_phase_gitea_configure_failed_on_transport(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_kw: Any) -> Any:
        raise OSError("connection refused")

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_configure_gitea", boom)
    result = orchestrator._phase_gitea_configure(_ssh_with_tunnel())
    assert result.status == "failed"
    assert "OSError" in result.detail


def test_phase_seed_ok(orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_deploy.seeder import SeedResult

    orchestrator.state.gitea_token = "tok"
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._seeder.run_seed_for_repo",
        lambda **_kw: SeedResult(created=4, skipped=1, failed=0),
    )
    monkeypatch.setattr("nexus_deploy.orchestrator.Path.is_dir", lambda self: True)
    result = orchestrator._phase_seed(MagicMock())
    assert result.status == "ok"
    assert "created=4" in result.detail


def test_phase_seed_partial_when_some_failed_but_progress_made(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.seeder import SeedResult

    orchestrator.state.gitea_token = "tok"
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._seeder.run_seed_for_repo",
        lambda **_kw: SeedResult(created=2, skipped=1, failed=1),
    )
    monkeypatch.setattr("nexus_deploy.orchestrator.Path.is_dir", lambda self: True)
    result = orchestrator._phase_seed(MagicMock())
    assert result.status == "partial"


def test_phase_seed_failed_when_zero_progress(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.seeder import SeedResult

    orchestrator.state.gitea_token = "tok"
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._seeder.run_seed_for_repo",
        lambda **_kw: SeedResult(created=0, skipped=0, failed=5),
    )
    monkeypatch.setattr("nexus_deploy.orchestrator.Path.is_dir", lambda self: True)
    result = orchestrator._phase_seed(MagicMock())
    assert result.status == "failed"


def test_phase_seed_skipped_when_seeds_dir_missing(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator.state.gitea_token = "tok"
    monkeypatch.setattr("nexus_deploy.orchestrator.Path.is_dir", lambda self: False)
    result = orchestrator._phase_seed(MagicMock())
    assert result.status == "skipped"
    assert "missing" in result.detail


def test_phase_kestra_register_ok(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.kestra import RegisterResult, SystemFlowsResult

    fake = SystemFlowsResult(
        flows=(RegisterResult(name="git-sync", status="created"),),
        execution_state="SUCCESS",
        verify_skipped_reason=None,
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._kestra.run_register_system_flows",
        lambda *_a, **_kw: fake,
    )
    result = orchestrator._phase_kestra_register(_ssh_with_tunnel())
    assert result.status == "ok"
    assert "execution=SUCCESS" in result.detail


def test_phase_kestra_register_partial_when_admin_email_missing(
    minimal_config: NexusConfig,
) -> None:
    env = BootstrapEnv(domain="example.com")  # admin_email missing
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=env,
        enabled_services=["kestra"],
        repo_name="r",
        gitea_repo_owner="o",
    )
    result = orch._phase_kestra_register(MagicMock())
    assert result.status == "partial"
    assert "ADMIN_EMAIL" in result.detail


def test_phase_kestra_register_failed_on_transport(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    def boom(*_a: Any, **_kw: Any) -> Any:
        raise subprocess.CalledProcessError(returncode=1, cmd="x")

    monkeypatch.setattr("nexus_deploy.orchestrator._kestra.run_register_system_flows", boom)
    result = orchestrator._phase_kestra_register(_ssh_with_tunnel())
    assert result.status == "failed"
    assert "CalledProcessError" in result.detail


def test_phase_woodpecker_oauth_partial_when_domain_missing(
    minimal_config: NexusConfig,
) -> None:
    env = BootstrapEnv()  # no domain
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=env,
        enabled_services=["woodpecker"],
        repo_name="r",
        gitea_repo_owner="o",
    )
    orch.state.gitea_token = "tok"
    result = orch._phase_woodpecker_oauth(MagicMock())
    assert result.status == "partial"
    assert "DOMAIN" in result.detail


def test_phase_woodpecker_oauth_failed_when_rotation_half_complete(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If create succeeded but rotation didn't, the failed branch
    surfaces the half-complete state."""
    orchestrator.state.gitea_token = "tok"

    def fake_oauth(*_a: Any, **_kw: Any) -> tuple[Any, str | None, bool]:
        return (None, "rotation aborted mid-flight", True)

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_woodpecker_oauth_setup", fake_oauth)
    result = orchestrator._phase_woodpecker_oauth(_ssh_with_tunnel())
    assert result.status == "failed"
    assert "half-complete" in result.detail


def test_phase_woodpecker_oauth_partial_when_create_failed_no_rotation(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator.state.gitea_token = "tok"

    def fake_oauth(*_a: Any, **_kw: Any) -> tuple[Any, str | None, bool]:
        return (None, "create returned 422", False)

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_woodpecker_oauth_setup", fake_oauth)
    result = orchestrator._phase_woodpecker_oauth(_ssh_with_tunnel())
    assert result.status == "partial"


def test_phase_mirror_setup_partial_when_gh_token_missing(
    minimal_config: NexusConfig, minimal_env: BootstrapEnv
) -> None:
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=minimal_env,
        enabled_services=["gitea"],
        repo_name="r",
        gitea_repo_owner="o",
        gh_mirror_repos=["https://github.com/x/y"],
    )
    orch.state.gitea_token = "tok"
    result = orch._phase_mirror_setup(MagicMock())
    assert result.status == "partial"
    assert "GH_MIRROR_TOKEN" in result.detail


def test_phase_mirror_setup_partial_when_some_mirrors_failed(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator.gh_mirror_repos = ["https://github.com/x/y"]
    orchestrator.gh_mirror_token = "gh-tok"
    orchestrator.state.gitea_token = "tok"

    def fake_mirror(*_a: Any, **_kw: Any) -> MirrorSetupResult:
        return MirrorSetupResult(
            admin_uid=1,
            admin_uid_error="",
            mirrors=(
                MirrorResult(name="x", status="created"),
                MirrorResult(name="y", status="failed"),
            ),
            fork=None,
            collaborator_added_count=0,
            fork_synced=False,
        )

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_mirror_setup", fake_mirror)
    result = orchestrator._phase_mirror_setup(_ssh_with_tunnel())
    assert result.status == "partial"


def test_phase_mirror_setup_surfaces_sync_detail_in_phase_result(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression (PR #589 review): the sync_detail from run_mirror_setup
    must reach PhaseResult.detail so operators can see whether the
    upstream-fetch landed during this spin-up. Without this plumbing,
    a regression that drops sync_detail from the phase output would
    pass the lower-level test_run_mirror_setup_* tests but silently
    leave the operator without their diagnostic."""
    orchestrator.gh_mirror_repos = ["https://github.com/x/y"]
    orchestrator.gh_mirror_token = "gh-tok"
    orchestrator.state.gitea_token = "tok"

    def fake_mirror(*_a: Any, **_kw: Any) -> MirrorSetupResult:
        return MirrorSetupResult(
            admin_uid=1,
            admin_uid_error="",
            mirrors=(MirrorResult(name="y", status="created"),),
            fork=ForkResult(owner="user", name="user-fork", status="created"),
            collaborator_added_count=1,
            fork_synced=True,
            sync_detail="mirror synced (oldsha12 -> newsha34), merge_upstream=200",
        )

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_mirror_setup", fake_mirror)
    result = orchestrator._phase_mirror_setup(_ssh_with_tunnel())
    assert result.status == "ok"
    assert "mirrors=1" in result.detail
    assert "mirror synced (oldsha12 -> newsha34)" in result.detail
    assert "merge_upstream=200" in result.detail


def test_phase_mirror_setup_omits_sync_detail_when_empty(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync_detail is empty when no fork-sync was attempted (e.g. no
    user configured); PhaseResult.detail should NOT contain a trailing
    ' | ' separator for an absent diagnostic."""
    orchestrator.gh_mirror_repos = ["https://github.com/x/y"]
    orchestrator.gh_mirror_token = "gh-tok"
    orchestrator.state.gitea_token = "tok"

    def fake_mirror(*_a: Any, **_kw: Any) -> MirrorSetupResult:
        return MirrorSetupResult(
            admin_uid=1,
            admin_uid_error="",
            mirrors=(MirrorResult(name="y", status="created"),),
            fork=None,
            collaborator_added_count=0,
            fork_synced=False,
            sync_detail="",
        )

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_mirror_setup", fake_mirror)
    result = orchestrator._phase_mirror_setup(_ssh_with_tunnel())
    assert result.status == "ok"
    assert result.detail == "mirrors=1"


def test_phase_secret_sync_jupyter_skipped_when_not_enabled(
    minimal_config: NexusConfig, minimal_env: BootstrapEnv
) -> None:
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=minimal_env,
        enabled_services=["gitea"],  # NOT jupyter
        repo_name="r",
        gitea_repo_owner="o",
        project_id="p",
        infisical_token="t",
    )
    result = orch._phase_secret_sync_jupyter(MagicMock())
    assert result.status == "skipped"


def test_phase_secret_sync_jupyter_partial_when_creds_missing(
    minimal_config: NexusConfig, minimal_env: BootstrapEnv
) -> None:
    orch = Orchestrator(
        config=minimal_config,
        bootstrap_env=minimal_env,
        enabled_services=["jupyter"],
        repo_name="r",
        gitea_repo_owner="o",
        # project_id / infisical_token default None
    )
    result = orch._phase_secret_sync_jupyter(MagicMock())
    assert result.status == "partial"


def test_phase_secret_sync_jupyter_ok(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.secret_sync import SyncResult

    fake = SyncResult(
        pushed=5,
        skipped_invalid_name=0,
        skipped_multiline=0,
        failed_folders=0,
        collisions=0,
        succeeded_folders=2,
        wrote=True,
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._secret_sync.run_sync_for_stack",
        lambda *_a, **_kw: fake,
    )
    result = orchestrator._phase_secret_sync(MagicMock(), "jupyter")
    assert result.status == "ok"
    assert "pushed=5" in result.detail


def test_phase_secret_sync_partial_when_wrote_with_some_failures(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.secret_sync import SyncResult

    fake = SyncResult(
        pushed=3,
        skipped_invalid_name=0,
        skipped_multiline=0,
        failed_folders=1,
        collisions=0,
        succeeded_folders=2,
        wrote=True,
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._secret_sync.run_sync_for_stack",
        lambda *_a, **_kw: fake,
    )
    result = orchestrator._phase_secret_sync(MagicMock(), "jupyter")
    assert result.status == "partial"


def test_phase_secret_sync_outage_gate_ok(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """wrote=False but with some succeeded folders means the outage
    gate skipped the write — still 'ok'."""
    from nexus_deploy.secret_sync import SyncResult

    fake = SyncResult(
        pushed=0,
        skipped_invalid_name=0,
        skipped_multiline=0,
        failed_folders=0,
        collisions=0,
        succeeded_folders=2,
        wrote=False,
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._secret_sync.run_sync_for_stack",
        lambda *_a, **_kw: fake,
    )
    result = orchestrator._phase_secret_sync(MagicMock(), "jupyter")
    assert result.status == "ok"
    assert "outage" in result.detail


def test_phase_secret_sync_failed_on_transport(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_kw: Any) -> Any:
        raise OSError("network down")

    monkeypatch.setattr("nexus_deploy.orchestrator._secret_sync.run_sync_for_stack", boom)
    result = orchestrator._phase_secret_sync(MagicMock(), "jupyter")
    assert result.status == "failed"
    assert "OSError" in result.detail


def test_run_all_resets_results_between_runs(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-reset: running twice on the same instance produces independent
    results (no accumulation)."""
    monkeypatch.setattr("nexus_deploy.orchestrator.SSHClient", MagicMock())
    for phase_name in (
        "_phase_infisical_bootstrap",
        "_phase_services_configure",
        "_phase_forgejo_configure",
        "_phase_forgejo_runner_register",
        "_phase_gitea_configure",
        "_phase_compose_restart",
        "_phase_kestra_secret_sync",
        "_phase_seed",
        "_phase_kestra_register",
        "_phase_woodpecker_oauth",
        "_phase_woodpecker_apply",
        "_phase_mirror_setup",
        "_phase_mirror_seed_rerun",
        "_phase_mirror_finalize",
        "_phase_secret_sync_jupyter",
        "_phase_secret_sync_marimo",
        "_phase_secret_sync_code_server",
    ):
        monkeypatch.setattr(orchestrator, phase_name, lambda _ssh, n=phase_name: _ok_phase(n))
    r1 = orchestrator.run_all()
    r2 = orchestrator.run_all()
    # 17 phases per ``run_all`` invocation.
    assert len(r1.phases) == 17
    assert len(r2.phases) == 17


# ---------------------------------------------------------------------------
# Exception coverage — catch-all + module-specific exception types
# ---------------------------------------------------------------------------


def test_phase_infisical_bootstrap_unexpected_exception(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch-all branch (RuntimeError, not transport)."""

    def boom(**_kw: Any) -> Any:
        raise RuntimeError("unexpected")

    monkeypatch.setattr("nexus_deploy.orchestrator._infisical.InfisicalClient", boom)
    result = orchestrator._phase_infisical_bootstrap(MagicMock())
    assert result.status == "failed"
    assert "RuntimeError" in result.detail
    assert "unexpected" in result.detail.lower()


def test_phase_services_configure_failed_on_transport(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_kw: Any) -> Any:
        raise OSError("conn refused")

    monkeypatch.setattr("nexus_deploy.orchestrator._services.run_admin_setups", boom)
    result = orchestrator._phase_services_configure(MagicMock())
    assert result.status == "failed"
    assert "OSError" in result.detail


def test_phase_services_configure_unexpected_exception(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_kw: Any) -> Any:
        raise ValueError("oops")

    monkeypatch.setattr("nexus_deploy.orchestrator._services.run_admin_setups", boom)
    result = orchestrator._phase_services_configure(MagicMock())
    assert result.status == "failed"
    assert "ValueError" in result.detail


def test_phase_gitea_configure_unexpected_exception(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("oops")

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_configure_gitea", boom)
    result = orchestrator._phase_gitea_configure(_ssh_with_tunnel())
    assert result.status == "failed"
    assert "RuntimeError" in result.detail


def test_phase_seed_unexpected_exception(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator.state.gitea_token = "tok"

    def boom(**_kw: Any) -> Any:
        raise RuntimeError("oops")

    monkeypatch.setattr("nexus_deploy.orchestrator._seeder.run_seed_for_repo", boom)
    monkeypatch.setattr("nexus_deploy.orchestrator.Path.is_dir", lambda self: True)
    result = orchestrator._phase_seed(MagicMock())
    assert result.status == "failed"
    assert "RuntimeError" in result.detail


def test_phase_kestra_register_unexpected_exception(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("oops")

    monkeypatch.setattr("nexus_deploy.orchestrator._kestra.run_register_system_flows", boom)
    result = orchestrator._phase_kestra_register(_ssh_with_tunnel())
    assert result.status == "failed"
    assert "RuntimeError" in result.detail


def test_phase_kestra_register_partial_when_not_success(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """flows attempted but at least one failed → SystemFlowsResult.is_success=False."""
    from nexus_deploy.kestra import RegisterResult, SystemFlowsResult

    fake = SystemFlowsResult(
        flows=(RegisterResult(name="git-sync", status="failed"),),
        execution_state=None,
        verify_skipped_reason="execution failed",
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._kestra.run_register_system_flows",
        lambda *_a, **_kw: fake,
    )
    result = orchestrator._phase_kestra_register(_ssh_with_tunnel())
    assert result.status == "partial"


def test_phase_woodpecker_oauth_failed_on_gitea_error(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GiteaError branch (lines 486-491)."""
    from nexus_deploy.gitea import GiteaError

    orchestrator.state.gitea_token = "tok"

    def boom(*_a: Any, **_kw: Any) -> Any:
        raise GiteaError("API 500")

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_woodpecker_oauth_setup", boom)
    result = orchestrator._phase_woodpecker_oauth(_ssh_with_tunnel())
    assert result.status == "failed"
    assert "API 500" in result.detail


def test_phase_woodpecker_oauth_failed_on_transport(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator.state.gitea_token = "tok"

    def boom(*_a: Any, **_kw: Any) -> Any:
        raise OSError("conn refused")

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_woodpecker_oauth_setup", boom)
    result = orchestrator._phase_woodpecker_oauth(_ssh_with_tunnel())
    assert result.status == "failed"
    assert "OSError" in result.detail


def test_phase_woodpecker_oauth_unexpected_exception(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator.state.gitea_token = "tok"

    def boom(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("oops")

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_woodpecker_oauth_setup", boom)
    result = orchestrator._phase_woodpecker_oauth(_ssh_with_tunnel())
    assert result.status == "failed"
    assert "RuntimeError" in result.detail


def test_phase_woodpecker_oauth_ok_populates_state(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: result populated → state mutation + ok status."""
    orchestrator.state.gitea_token = "tok"

    def fake_oauth(*_a: Any, **_kw: Any) -> tuple[OAuthAppResult, str | None, bool]:
        return (
            OAuthAppResult(client_id="cid", client_secret="csec", name="Woodpecker CI"),
            None,
            False,
        )

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_woodpecker_oauth_setup", fake_oauth)
    result = orchestrator._phase_woodpecker_oauth(_ssh_with_tunnel())
    assert result.status == "ok"
    assert orchestrator.state.woodpecker_client_id == "cid"
    assert orchestrator.state.woodpecker_client_secret == "csec"


def test_phase_mirror_setup_failed_on_transport(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator.gh_mirror_repos = ["https://github.com/x/y"]
    orchestrator.gh_mirror_token = "gh-tok"
    orchestrator.state.gitea_token = "tok"

    def boom(*_a: Any, **_kw: Any) -> Any:
        raise OSError("conn refused")

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_mirror_setup", boom)
    result = orchestrator._phase_mirror_setup(_ssh_with_tunnel())
    assert result.status == "failed"
    assert "OSError" in result.detail


def test_phase_mirror_setup_failed_on_gitea_error(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.gitea import GiteaError

    orchestrator.gh_mirror_repos = ["https://github.com/x/y"]
    orchestrator.gh_mirror_token = "gh-tok"
    orchestrator.state.gitea_token = "tok"

    def boom(*_a: Any, **_kw: Any) -> Any:
        raise GiteaError("API 403")

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_mirror_setup", boom)
    result = orchestrator._phase_mirror_setup(_ssh_with_tunnel())
    assert result.status == "failed"
    assert "API 403" in result.detail


def test_phase_mirror_setup_unexpected_exception(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator.gh_mirror_repos = ["https://github.com/x/y"]
    orchestrator.gh_mirror_token = "gh-tok"
    orchestrator.state.gitea_token = "tok"

    def boom(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("oops")

    monkeypatch.setattr("nexus_deploy.orchestrator._gitea.run_mirror_setup", boom)
    result = orchestrator._phase_mirror_setup(_ssh_with_tunnel())
    assert result.status == "failed"
    assert "RuntimeError" in result.detail


def test_phase_secret_sync_unexpected_exception(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("oops")

    monkeypatch.setattr("nexus_deploy.orchestrator._secret_sync.run_sync_for_stack", boom)
    result = orchestrator._phase_secret_sync(MagicMock(), "jupyter")
    assert result.status == "failed"
    assert "RuntimeError" in result.detail


def test_phase_secret_sync_partial_when_no_usable_result(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """wrote=False AND no folders touched → no usable result → partial."""
    from nexus_deploy.secret_sync import SyncResult

    fake = SyncResult(
        pushed=0,
        skipped_invalid_name=0,
        skipped_multiline=0,
        failed_folders=0,
        collisions=0,
        succeeded_folders=0,
        wrote=False,
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._secret_sync.run_sync_for_stack",
        lambda *_a, **_kw: fake,
    )
    result = orchestrator._phase_secret_sync(MagicMock(), "jupyter")
    assert result.status == "partial"


# ---------------------------------------------------------------------------
# Pre-bootstrap pipeline phases. Each phase is exercised with a happy
# path + at least one failure / partial path to lock the PhaseResult
# contract.
# ---------------------------------------------------------------------------


def test_phase_service_env_happy_path(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """All renders ok → status=ok with the rendered/skipped counts in detail."""
    from nexus_deploy.service_env import ServiceEnvResult, ServiceRenderResult

    fake_result = ServiceEnvResult(
        services=(
            ServiceRenderResult(service="postgres", status="rendered"),
            ServiceRenderResult(service="kestra", status="rendered"),
        ),
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._service_env.render_all_env_files",
        lambda *_a, **_kw: fake_result,
    )
    # Skip the gitea-block append branch. Post-R3 #1 the
    # workspace_coords_complete check uses self.gitea_repo_owner (set
    # to "admin" by the fixture), so clearing the bootstrap_env mirror
    # alone wouldn't fail the guard. The actual skip happens because
    # the orchestrator fixture leaves gitea_user_username, _password,
    # _email at None — those three coords fail the all() check, which
    # is what we want here (this test focuses on the happy path of
    # render_all_env_files, not the gitea-append branch). The minimal
    # bootstrap_env is kept for hygiene. Comment corrected in PR #532
    # R8 #1.
    orchestrator.bootstrap_env = type(orchestrator.bootstrap_env)(
        domain="example.com",
        admin_email="admin@example.com",
        gitea_repo_owner=None,
    )
    orchestrator.project_root = tmp_path
    result = orchestrator._phase_service_env()
    assert result.status == "ok"
    assert "rendered=2" in result.detail


def test_phase_service_env_partial_when_failures(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Some renders failed but at least one succeeded → status=partial."""
    from nexus_deploy.service_env import ServiceEnvResult, ServiceRenderResult

    fake_result = ServiceEnvResult(
        services=(
            ServiceRenderResult(service="postgres", status="rendered"),
            ServiceRenderResult(service="kestra", status="failed", detail="oops"),
        ),
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._service_env.render_all_env_files",
        lambda *_a, **_kw: fake_result,
    )
    orchestrator.bootstrap_env = type(orchestrator.bootstrap_env)(
        domain="example.com",
        admin_email="admin@example.com",
        gitea_repo_owner=None,
    )
    orchestrator.project_root = tmp_path
    result = orchestrator._phase_service_env()
    assert result.status == "partial"
    assert "rendered=1" in result.detail
    assert "failed=1" in result.detail


def test_phase_service_env_failed_on_service_env_error(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """ServiceEnvError (e.g. SFTPGo with empty password) → status=failed."""
    from nexus_deploy.service_env import ServiceEnvError

    def _raises(*_a: Any, **_kw: Any) -> None:
        raise ServiceEnvError("SFTPGo password is empty")

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._service_env.render_all_env_files",
        _raises,
    )
    orchestrator.project_root = tmp_path
    result = orchestrator._phase_service_env()
    assert result.status == "failed"
    assert "SFTPGo" in result.detail


def test_phase_stack_sync_happy_path(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """rsync ok + cleanup ok → status=ok."""
    from nexus_deploy.stack_sync import CleanupResult, RsyncResult, StackSyncResult

    fake = StackSyncResult(
        rsync=(
            RsyncResult(service="postgres", status="synced"),
            RsyncResult(service="kestra", status="synced"),
        ),
        cleanup=CleanupResult(stopped=0, removed=3, failed=0),
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._stack_sync.run_stack_sync",
        lambda *_a, **_kw: fake,
    )
    orchestrator.project_root = tmp_path
    result = orchestrator._phase_stack_sync()
    assert result.status == "ok"
    assert "rsync_synced=2" in result.detail
    assert "cleanup_removed=3" in result.detail


def test_phase_stack_sync_failed_when_cleanup_unparseable(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """cleanup is None (no parseable RESULT) → status=failed."""
    from nexus_deploy.stack_sync import RsyncResult, StackSyncResult

    fake = StackSyncResult(
        rsync=(RsyncResult(service="postgres", status="synced"),),
        cleanup=None,
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._stack_sync.run_stack_sync",
        lambda *_a, **_kw: fake,
    )
    orchestrator.project_root = tmp_path
    result = orchestrator._phase_stack_sync()
    assert result.status == "failed"
    assert "no parseable RESULT" in result.detail


def test_phase_firewall_configure_zero_entry(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Empty firewall_rules → zero-entry mode → status=ok."""
    from nexus_deploy.firewall import GenerateResult, WriteResult

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._firewall.configure",
        lambda *_a, **_kw: (
            GenerateResult(compiled=(), redpanda=None, zero_entry=True),
            WriteResult(written=()),
        ),
    )
    orchestrator.firewall_json = "{}"
    orchestrator.project_root = tmp_path
    result = orchestrator._phase_firewall_configure()
    assert result.status == "ok"
    assert "zero-entry" in result.detail


def test_phase_firewall_configure_partial_when_skipped(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Skipped services → status=partial (per #531 R7 #4)."""
    from nexus_deploy.firewall import (
        CompiledOverride,
        GenerateResult,
        WriteResult,
    )

    fake_compiled = CompiledOverride(
        service="postgres",
        target_path=tmp_path / "postgres" / "docker-compose.firewall.yml",
        yaml_content="services: {}\n",
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._firewall.configure",
        lambda *_a, **_kw: (
            GenerateResult(
                compiled=(fake_compiled,),
                redpanda=None,
                skipped=("kestra",),
                zero_entry=False,
            ),
            WriteResult(written=(fake_compiled.target_path,)),
        ),
    )
    orchestrator.firewall_json = '{"postgres-1": {"port": 5432}, "kestra-1": {"port": 8080}}'
    orchestrator.project_root = tmp_path
    result = orchestrator._phase_firewall_configure()
    assert result.status == "partial"
    assert "skipped=1" in result.detail


def test_phase_firewall_configure_failed_on_value_error(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """ValueError (e.g. missing template token) → status=failed."""

    def _raises(**_kw: Any) -> None:
        raise ValueError("RedPanda template missing __REDPANDA_KAFKA_DOMAIN__")

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._firewall.configure",
        _raises,
    )
    orchestrator.project_root = tmp_path
    result = orchestrator._phase_firewall_configure()
    assert result.status == "failed"
    assert "REDPANDA_KAFKA_DOMAIN" in result.detail


def test_phase_compose_up_happy_path(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All containers started → status=ok."""
    from nexus_deploy.compose_runner import ComposeUpResult

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._compose_runner.run_compose_up",
        lambda *_a, **_kw: ComposeUpResult(started=10, failed=0),
    )
    result = orchestrator._phase_compose_up()
    assert result.status == "ok"
    assert "started=10" in result.detail


def test_phase_compose_up_partial_on_failures(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Some containers failed → status=partial."""
    from nexus_deploy.compose_runner import ComposeUpResult

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._compose_runner.run_compose_up",
        lambda *_a, **_kw: ComposeUpResult(started=8, failed=2),
    )
    result = orchestrator._phase_compose_up()
    assert result.status == "partial"
    assert "started=8" in result.detail
    assert "failed=2" in result.detail


def test_phase_infisical_provision_happy_path(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provision returns usable creds → state populated, status=ok."""
    from nexus_deploy.infisical import ProvisionResult

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._infisical.provision_admin",
        lambda *_a, **_kw: ProvisionResult(
            status="freshly-bootstrapped",
            token="real-token",
            project_id="proj-real",
        ),
    )
    orchestrator.admin_password_infisical = "pw"
    result = orchestrator._phase_infisical_provision()
    assert result.status == "ok"
    assert orchestrator.state.infisical_token == "real-token"
    assert orchestrator.state.project_id == "proj-real"
    assert orchestrator.infisical_token == "real-token"
    assert orchestrator.project_id == "proj-real"


def test_phase_infisical_provision_partial_on_dropped_creds(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """has_credentials=False → partial."""
    from nexus_deploy.infisical import ProvisionResult

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._infisical.provision_admin",
        lambda *_a, **_kw: ProvisionResult(status="loaded-existing", token=None, project_id=None),
    )
    # Reset to None so the post-bootstrap fallback doesn't mask the
    # partial result.
    orchestrator.state.infisical_token = None
    orchestrator.admin_password_infisical = "pw"
    result = orchestrator._phase_infisical_provision()
    assert result.status == "partial"
    assert "no usable credentials" in result.detail
    assert orchestrator.state.infisical_token is None


def test_phase_infisical_provision_skipped_when_password_missing(
    orchestrator: Orchestrator,
) -> None:
    """No admin password → status=skipped."""
    orchestrator.admin_password_infisical = None
    result = orchestrator._phase_infisical_provision()
    assert result.status == "skipped"
    assert "admin_password_infisical" in result.detail


def test_run_pre_bootstrap_runs_phases_in_order(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All 8 pre-bootstrap phases run in deterministic order:
    workspace-coords (first), service-env, firewall-configure,
    stack-sync, firewall-sync, global-env, compose-up,
    infisical-provision."""
    invocation_order: list[str] = []

    def _make_phase(name: str) -> Any:
        def _phase(self: Any) -> PhaseResult:
            invocation_order.append(name)
            return PhaseResult(name=name, status="ok")

        return _phase

    monkeypatch.setattr(Orchestrator, "_phase_workspace_coords", _make_phase("workspace-coords"))
    monkeypatch.setattr(Orchestrator, "_phase_service_env", _make_phase("service-env"))
    monkeypatch.setattr(
        Orchestrator,
        "_phase_firewall_configure",
        _make_phase("firewall-configure"),
    )
    monkeypatch.setattr(Orchestrator, "_phase_stack_sync", _make_phase("stack-sync"))
    monkeypatch.setattr(Orchestrator, "_phase_firewall_sync", _make_phase("firewall-sync"))
    monkeypatch.setattr(Orchestrator, "_phase_global_env", _make_phase("global-env"))
    monkeypatch.setattr(Orchestrator, "_phase_compose_up", _make_phase("compose-up"))
    monkeypatch.setattr(
        Orchestrator,
        "_phase_infisical_provision",
        _make_phase("infisical-provision"),
    )
    result = orchestrator.run_pre_bootstrap()
    # workspace-coords first (downstream phases gate on REPO_NAME etc.);
    # firewall-configure before stack-sync (rsync picks up overrides);
    # firewall-sync + global-env after stack-sync (use the synced state).
    assert invocation_order == [
        "workspace-coords",
        "service-env",
        "firewall-configure",
        "stack-sync",
        "firewall-sync",
        "global-env",
        "compose-up",
        "infisical-provision",
    ]
    assert [p.name for p in result.phases] == invocation_order
    assert result.is_success


def test_run_pre_bootstrap_aborts_on_failure(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A phase with status='failed' aborts the run; downstream phases skipped."""
    invocation_order: list[str] = []

    def _make_phase(name: str, status: Literal["ok", "failed"]) -> Any:
        def _phase(self: Any) -> PhaseResult:
            invocation_order.append(name)
            return PhaseResult(name=name, status=status)

        return _phase

    monkeypatch.setattr(
        Orchestrator, "_phase_workspace_coords", _make_phase("workspace-coords", "ok")
    )
    monkeypatch.setattr(Orchestrator, "_phase_service_env", _make_phase("service-env", "ok"))
    monkeypatch.setattr(
        Orchestrator,
        "_phase_stack_sync",
        _make_phase("stack-sync", "failed"),
    )
    monkeypatch.setattr(
        Orchestrator,
        "_phase_firewall_configure",
        _make_phase("firewall-configure", "ok"),
    )
    result = orchestrator.run_pre_bootstrap()
    # workspace-coords (ok) → service-env (ok) → firewall-configure (ok)
    # → stack-sync (failed) → abort. firewall-sync / global-env /
    # compose-up / infisical-provision must NOT run.
    assert invocation_order == [
        "workspace-coords",
        "service-env",
        "firewall-configure",
        "stack-sync",
    ]
    assert result.has_hard_failure


def test_run_pre_bootstrap_partial_continues_to_downstream(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Partial-success phase doesn't abort — all 8 phases still run."""
    invocation_order: list[str] = []

    def _make_phase(name: str, status: Literal["ok", "partial"]) -> Any:
        def _phase(self: Any) -> PhaseResult:
            invocation_order.append(name)
            return PhaseResult(name=name, status=status)

        return _phase

    monkeypatch.setattr(
        Orchestrator, "_phase_workspace_coords", _make_phase("workspace-coords", "ok")
    )
    monkeypatch.setattr(Orchestrator, "_phase_service_env", _make_phase("service-env", "ok"))
    monkeypatch.setattr(
        Orchestrator,
        "_phase_firewall_configure",
        _make_phase("firewall-configure", "ok"),
    )
    monkeypatch.setattr(
        Orchestrator,
        "_phase_stack_sync",
        _make_phase("stack-sync", "partial"),
    )
    monkeypatch.setattr(Orchestrator, "_phase_firewall_sync", _make_phase("firewall-sync", "ok"))
    monkeypatch.setattr(Orchestrator, "_phase_global_env", _make_phase("global-env", "ok"))
    monkeypatch.setattr(Orchestrator, "_phase_compose_up", _make_phase("compose-up", "ok"))
    monkeypatch.setattr(
        Orchestrator,
        "_phase_infisical_provision",
        _make_phase("infisical-provision", "ok"),
    )
    result = orchestrator.run_pre_bootstrap()
    assert len(invocation_order) == 8
    assert result.has_partial
    assert not result.has_hard_failure


def test_run_pre_bootstrap_resets_stale_credentials(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-state-reset (PR #532 R1 #4): re-running on the same instance
    after a previous run that produced partial credentials must NOT
    leak the stale token/project_id into the second run's stdout.
    Reset happens at the top of run_pre_bootstrap before any phase
    fires."""

    # Simulate a first run that left stale credentials on BOTH state
    # mirrors and the orchestrator's own fields. Both must be cleared
    # (R1 #4 cleared state; R2 #3 also clears self.fields so a follow-on
    # run_all() can't pick up stale creds via the post-bootstrap phase
    # gating).
    orchestrator.state.infisical_token = "stale-token-from-prior-run"
    orchestrator.state.project_id = "stale-proj-from-prior-run"
    orchestrator.infisical_token = "stale-token-from-prior-run"
    orchestrator.project_id = "stale-proj-from-prior-run"

    # Mock all phases to ok except infisical-provision which produces
    # status='partial' WITHOUT populating state (simulating the bug
    # condition: dropped credentials).
    def _ok_phase(_self: Any) -> PhaseResult:
        return PhaseResult(name="ok-phase", status="ok")

    def _partial_no_creds(_self: Any) -> PhaseResult:
        return PhaseResult(name="infisical-provision", status="partial", detail="dropped")

    monkeypatch.setattr(Orchestrator, "_phase_workspace_coords", _ok_phase)
    monkeypatch.setattr(Orchestrator, "_phase_service_env", _ok_phase)
    monkeypatch.setattr(Orchestrator, "_phase_firewall_configure", _ok_phase)
    monkeypatch.setattr(Orchestrator, "_phase_stack_sync", _ok_phase)
    monkeypatch.setattr(Orchestrator, "_phase_firewall_sync", _ok_phase)
    monkeypatch.setattr(Orchestrator, "_phase_global_env", _ok_phase)
    monkeypatch.setattr(Orchestrator, "_phase_compose_up", _ok_phase)
    monkeypatch.setattr(Orchestrator, "_phase_infisical_provision", _partial_no_creds)

    result = orchestrator.run_pre_bootstrap()
    assert result.has_partial
    # Stale credentials MUST be cleared on BOTH surfaces, even though
    # the infisical-provision phase didn't populate fresh ones.
    # mypy's narrowing flagged each ``is None`` assertion as
    # unreachable because the pre-test assignments above set the
    # attributes to specific str literals — even though the
    # orchestrator's reset block clears them at runtime. Casting
    # back to ``str | None`` re-widens the type so mypy doesn't
    # treat the asserts as dead code. Pre-existing CI failure on
    # main since #532 R1 #4 — fixed here.
    assert cast(str | None, orchestrator.state.infisical_token) is None
    assert cast(str | None, orchestrator.state.project_id) is None
    assert cast(str | None, orchestrator.infisical_token) is None
    assert cast(str | None, orchestrator.project_id) is None


def test_phase_service_env_skips_gitea_block_on_incomplete_coords(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """R-gitea-guard (PR #532 R1 #3): when ANY workspace coord is
    empty (e.g. gitea_user_password=None), the Gitea workspace block
    is NOT appended — refuses to write a broken block with empty
    PASSWORD/AUTHOR fields. Mirrors the CLI handler's
    workspace_coords_complete check."""
    from nexus_deploy.service_env import ServiceEnvResult, ServiceRenderResult

    fake_result = ServiceEnvResult(
        services=(ServiceRenderResult(service="postgres", status="rendered"),),
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._service_env.render_all_env_files",
        lambda *_a, **_kw: fake_result,
    )

    append_called = False

    def _spy_append(*_a: Any, **_kw: Any) -> tuple[str, ...]:
        nonlocal append_called
        append_called = True
        return ()

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._service_env.append_gitea_workspace_block",
        _spy_append,
    )

    # The orchestrator fixture already sets self.gitea_repo_owner +
    # self.repo_name (the canonical sources of truth post-R3 #1). We
    # override the user-cred coords here: username + email are present
    # but gitea_user_password=None. Since the workspace_coords_complete
    # check requires ALL 5 inputs (repo_owner, repo_name,
    # gitea_user_username, gitea_user_password, gitea_user_email) to
    # be non-empty, the missing password alone must skip the append —
    # otherwise we'd write an .env block with PASSWORD="" which breaks
    # the workspace git_clone at runtime. Comment updated in PR #532
    # R7 #3 to reflect the post-R3 source-of-truth + the actual coord
    # being missing.
    orchestrator.bootstrap_env = type(orchestrator.bootstrap_env)(
        domain="example.com",
        admin_email="admin@example.com",
        gitea_repo_owner="owner",
        gitea_user_email="ops@example.com",
    )
    orchestrator.gitea_user_username = "ops"
    orchestrator.gitea_user_password = None  # missing → workspace_coords_complete=False
    orchestrator.project_root = tmp_path

    result = orchestrator._phase_service_env()
    assert result.status == "ok"
    assert "gitea_appended=0" in result.detail
    assert append_called is False, (
        "append_gitea_workspace_block must NOT be called when any coord is empty"
    )


# ---------------------------------------------------------------------------
# `nexus-deploy run-pre-bootstrap` CLI handler tests.
# ---------------------------------------------------------------------------


def _setup_pre_bootstrap_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the 6 required env vars for run-pre-bootstrap.

    REPO_NAME + GITEA_REPO_OWNER are NOT required (workspace-coords
    derives them); ADMIN_USERNAME IS required.
    """
    for var, val in (
        ("ADMIN_EMAIL", "admin@example.com"),
        ("ENABLED_SERVICES", "gitea,kestra"),
        ("DOMAIN", "example.com"),
        ("ADMIN_USERNAME", "admin"),
        ("INFISICAL_PASS", "pw"),
        ("FIREWALL_RULES_JSON", "{}"),  # explicit zero-entry mode
    ):
        monkeypatch.setenv(var, val)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")


def test_cli_run_pre_bootstrap_unknown_arg_returns_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from nexus_deploy.__main__ import _run_pre_bootstrap

    rc = _run_pre_bootstrap(["--unknown"])
    assert rc == 2
    assert "unknown args" in capsys.readouterr().err


def test_cli_run_pre_bootstrap_missing_env_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _run_pre_bootstrap

    # ADMIN_EMAIL deliberately missing; set the rest.
    for var, val in (
        ("ENABLED_SERVICES", "gitea"),
        ("DOMAIN", "example.com"),
        ("ADMIN_USERNAME", "admin"),
        ("INFISICAL_PASS", "pw"),
        ("FIREWALL_RULES_JSON", "{}"),
    ):
        monkeypatch.setenv(var, val)
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")
    rc = _run_pre_bootstrap([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "missing required env" in err
    assert "ADMIN_EMAIL" in err


def test_cli_run_pre_bootstrap_missing_firewall_rules_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R-firewall-required (PR #532 R5 #2): FIREWALL_RULES_JSON is now
    required and has NO default. A missing/empty value must abort with
    rc=2 — falling back to "{}" silently triggers destructive cleanup
    of existing override files via the firewall module's zero-entry
    mode. Operators must pass "{}" explicitly to opt in."""
    from nexus_deploy.__main__ import _run_pre_bootstrap

    # All other required vars set; FIREWALL_RULES_JSON deliberately missing.
    for var, val in (
        ("ADMIN_EMAIL", "admin@example.com"),
        ("ENABLED_SERVICES", "gitea"),
        ("DOMAIN", "example.com"),
        ("ADMIN_USERNAME", "admin"),
        ("INFISICAL_PASS", "pw"),
    ):
        monkeypatch.setenv(var, val)
    monkeypatch.delenv("FIREWALL_RULES_JSON", raising=False)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")
    rc = _run_pre_bootstrap([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "missing required env" in err
    assert "FIREWALL_RULES_JSON" in err


def test_cli_run_pre_bootstrap_rc0_emits_credentials_to_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Happy path: orchestrator returns ok with populated creds → rc=0
    AND INFISICAL_TOKEN + PROJECT_ID on stdout (eval-able)."""
    from nexus_deploy.__main__ import _run_pre_bootstrap

    _setup_pre_bootstrap_env(monkeypatch)
    fake_result = OrchestratorResult(
        phases=(PhaseResult("p1", "ok"),),
        state=OrchestratorState(
            infisical_token="real-token",
            project_id="proj-real",
        ),
    )
    with patch.object(Orchestrator, "run_pre_bootstrap", return_value=fake_result):
        rc = _run_pre_bootstrap([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "INFISICAL_TOKEN=real-token" in out
    assert "PROJECT_ID=proj-real" in out


def test_cli_run_pre_bootstrap_rc1_on_partial_emits_empty_creds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Partial: e.g. infisical-provision dropped creds → rc=1 with
    empty INFISICAL_TOKEN + PROJECT_ID (eval clears stale values)."""
    from nexus_deploy.__main__ import _run_pre_bootstrap

    _setup_pre_bootstrap_env(monkeypatch)
    fake_result = OrchestratorResult(
        phases=(PhaseResult("infisical-provision", "partial"),),
        state=OrchestratorState(),  # empty token/project_id
    )
    with patch.object(Orchestrator, "run_pre_bootstrap", return_value=fake_result):
        rc = _run_pre_bootstrap([])
    assert rc == 1
    out = capsys.readouterr().out
    # shlex.quote of empty string → ''
    assert "INFISICAL_TOKEN=''" in out
    assert "PROJECT_ID=''" in out


def test_cli_run_pre_bootstrap_rc2_on_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus_deploy.__main__ import _run_pre_bootstrap

    _setup_pre_bootstrap_env(monkeypatch)
    fake_result = OrchestratorResult(
        phases=(PhaseResult("stack-sync", "failed"),),
        state=OrchestratorState(),
    )
    with patch.object(Orchestrator, "run_pre_bootstrap", return_value=fake_result):
        rc = _run_pre_bootstrap([])
    assert rc == 2


def test_cli_run_pre_bootstrap_transport_failure_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SSH/transport failure mid-run → rc=2 with stderr explanation."""
    from nexus_deploy.__main__ import _run_pre_bootstrap

    _setup_pre_bootstrap_env(monkeypatch)

    def _raises(self: Any) -> Any:
        import subprocess

        raise subprocess.TimeoutExpired(cmd=["ssh"], timeout=30)

    with patch.object(Orchestrator, "run_pre_bootstrap", _raises):
        rc = _run_pre_bootstrap([])
    assert rc == 2
    assert "transport failure" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Phase methods + critical regressions.
# ---------------------------------------------------------------------------


def test_phase_seed_skips_in_mirror_mode(orchestrator: Orchestrator) -> None:
    """R-mirror-seed-skip (Plan-agent catch): _phase_seed must early-skip
    when gh_mirror_repos is set, even if gitea_token is populated. Otherwise
    seeding the read-only mirror-readonly-* repo returns HTTP 423.
    Re-seeding against the user's fork happens in _phase_mirror_seed_rerun."""
    orchestrator.gh_mirror_repos = ["https://github.com/owner/repo.git"]
    orchestrator.state.gitea_token = "valid-token"
    result = orchestrator._phase_seed(MagicMock())
    assert result.status == "skipped"
    assert "mirror mode" in result.detail
    assert "mirror-seed-rerun" in result.detail


# --- _phase_workspace_coords ---


def test_phase_workspace_coords_dual_writes_user_identity_for_admin_fallback(
    minimal_env: BootstrapEnv,
) -> None:
    """R-admin-fallback (PR #533 R1 #3): in admin-fallback mode (no
    GITEA_USER_EMAIL / _PASS env), workspace-coords must populate
    self.gitea_user_username / _password / _email from admin coords
    so _phase_service_env's workspace-block-append guard passes.
    Otherwise the workspace block is silently skipped — breaking
    git-integrated stacks (jupyter/marimo/code-server etc.)."""
    orchestrator = Orchestrator(
        config=NexusConfig(
            admin_username="admin",
            gitea_admin_password="admin-pw",
        ),
        bootstrap_env=minimal_env,
        enabled_services=["gitea"],
        repo_name="",
        gitea_repo_owner="",
        domain="example.com",
        admin_username="admin",
        gitea_admin_pass="admin-pw",
        # No gitea_user_* — admin-fallback mode
        gitea_user_email=None,
        gitea_user_password=None,
        gitea_user_username=None,
    )
    result = orchestrator._phase_workspace_coords()
    assert result.status == "ok"
    # Critical: self.gitea_user_* must be populated for the workspace
    # block to be appended in admin-fallback mode.
    assert orchestrator.gitea_user_username == "admin"
    assert orchestrator.gitea_user_password == "admin-pw"
    assert orchestrator.gitea_user_email == "admin@example.com"


def test_phase_workspace_coords_dual_writes_state_and_self_field(
    orchestrator: Orchestrator,
) -> None:
    """R-dual-write: workspace-coords must populate state.* AND self.*
    AND bootstrap_env (where empty)."""
    orchestrator.domain = "nexus.example.com"
    orchestrator.admin_username = "admin"
    orchestrator.gitea_admin_pass = "admin-pw"
    orchestrator.bootstrap_env = BootstrapEnv(
        domain="nexus.example.com",
        admin_email="admin@example.com",
    )

    result = orchestrator._phase_workspace_coords()
    assert result.status == "ok"

    # state mirrors populated
    assert orchestrator.state.repo_name == "nexus-nexus-example-com-gitea"
    assert orchestrator.state.gitea_repo_owner == "admin"
    assert orchestrator.state.workspace_branch == "main"
    assert orchestrator.state.gitea_git_user == "admin"
    assert orchestrator.state.git_email == "admin@example.com"

    # self.* fields populated (the post-bootstrap phases gate on these)
    assert orchestrator.repo_name == "nexus-nexus-example-com-gitea"
    assert orchestrator.gitea_repo_owner == "admin"
    assert orchestrator.workspace_branch == "main"

    # bootstrap_env populated where empty
    assert orchestrator.bootstrap_env.gitea_repo_owner == "admin"
    assert orchestrator.bootstrap_env.repo_name == "nexus-nexus-example-com-gitea"


def test_phase_workspace_coords_mirror_mode_with_user(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror + user → fork name + user as owner. GitHub API mocked."""
    orchestrator.domain = "example.com"
    orchestrator.admin_username = "admin"
    orchestrator.gitea_admin_pass = "admin-pw"
    orchestrator.gh_mirror_repos = ["https://github.com/upstream/MyRepo.git"]
    orchestrator.gh_mirror_token = "ghp_xxx"
    orchestrator.gitea_user_email = "alice.bob@example.com"
    orchestrator.gitea_user_password = "user-pw"
    orchestrator.bootstrap_env = BootstrapEnv(
        domain="example.com",
        admin_email="admin@example.com",
    )

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._workspace_coords._default_http_runner",
        lambda _t, _r: "develop",
    )
    result = orchestrator._phase_workspace_coords()
    assert result.status == "ok"
    assert orchestrator.state.repo_name == "MyRepo_alice_bob"
    assert orchestrator.state.gitea_repo_owner == "alice.bob"
    assert orchestrator.state.workspace_branch == "develop"


def test_phase_workspace_coords_unexpected_exception_returns_failed(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("synthetic boom")

    monkeypatch.setattr("nexus_deploy.orchestrator._workspace_coords.derive", boom)
    result = orchestrator._phase_workspace_coords()
    assert result.status == "failed"
    assert "RuntimeError" in result.detail


# --- _phase_compose_restart ---


def test_phase_compose_restart_skips_on_empty(orchestrator: Orchestrator) -> None:
    orchestrator.state.restart_services = ()
    result = orchestrator._phase_compose_restart(MagicMock())
    assert result.status == "skipped"
    assert "no services" in result.detail


def test_phase_compose_restart_happy_path(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.compose_restart import RestartResult

    orchestrator.state.restart_services = ("kestra", "jupyter")
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._compose_restart.run_restart",
        lambda *_a, **_kw: RestartResult(restarted=2, failed=0),
    )
    result = orchestrator._phase_compose_restart(MagicMock())
    assert result.status == "ok"
    assert "restarted=2" in result.detail


def test_phase_compose_restart_partial_when_some_fail(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_deploy.compose_restart import RestartResult

    orchestrator.state.restart_services = ("a", "b", "c")
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._compose_restart.run_restart",
        lambda *_a, **_kw: RestartResult(restarted=1, failed=2),
    )
    result = orchestrator._phase_compose_restart(MagicMock())
    assert result.status == "partial"
    assert "restarted=1" in result.detail
    assert "failed=2" in result.detail


def test_phase_compose_restart_passes_self_ssh_host(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: must forward self.ssh_host to compose_restart so a
    non-default SSH_HOST_ALIAS reaches the restart loop."""
    from nexus_deploy.compose_restart import RestartResult

    captured: list[str] = []

    def _fake(_services: list[str], **kwargs: Any) -> RestartResult:
        captured.append(kwargs.get("host", ""))
        return RestartResult(restarted=1, failed=0)

    orchestrator.ssh_host = "custom-host"
    orchestrator.state.restart_services = ("kestra",)
    monkeypatch.setattr("nexus_deploy.orchestrator._compose_restart.run_restart", _fake)
    orchestrator._phase_compose_restart(MagicMock())
    assert captured == ["custom-host"]


# --- _phase_woodpecker_apply ---


def test_phase_woodpecker_apply_skipped_when_not_enabled(
    orchestrator: Orchestrator,
) -> None:
    orchestrator.enabled_services = ["kestra"]  # no woodpecker
    result = orchestrator._phase_woodpecker_apply(MagicMock())
    assert result.status == "skipped"
    assert "not enabled" in result.detail


def test_phase_woodpecker_apply_skipped_when_no_oauth_creds(
    orchestrator: Orchestrator,
) -> None:
    orchestrator.enabled_services = ["woodpecker"]
    orchestrator.state.woodpecker_client_id = None
    orchestrator.state.woodpecker_client_secret = None
    result = orchestrator._phase_woodpecker_apply(MagicMock())
    assert result.status == "skipped"
    assert "not populated" in result.detail


def test_phase_woodpecker_apply_partial_when_no_agent_secret(
    orchestrator: Orchestrator,
) -> None:
    orchestrator.enabled_services = ["woodpecker"]
    orchestrator.state.woodpecker_client_id = "wp-id"
    orchestrator.state.woodpecker_client_secret = "wp-secret"
    orchestrator.woodpecker_agent_secret = None
    result = orchestrator._phase_woodpecker_apply(MagicMock())
    assert result.status == "partial"
    assert "WOODPECKER_AGENT_SECRET" in result.detail


# --- _phase_mirror_seed_rerun ---


def test_phase_mirror_seed_rerun_skipped_when_not_mirror(
    orchestrator: Orchestrator,
) -> None:
    orchestrator.gh_mirror_repos = []
    result = orchestrator._phase_mirror_seed_rerun(MagicMock())
    assert result.status == "skipped"
    assert "not mirror mode" in result.detail


def test_phase_mirror_seed_rerun_skipped_when_no_fork(
    orchestrator: Orchestrator,
) -> None:
    orchestrator.gh_mirror_repos = ["https://github.com/o/r.git"]
    orchestrator.state.fork_name = None
    orchestrator.state.gitea_token = "tok"
    result = orchestrator._phase_mirror_seed_rerun(MagicMock())
    assert result.status == "skipped"
    assert "no fork" in result.detail


def test_phase_mirror_seed_rerun_mutates_state_to_fork_target(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """After re-seeding, state.repo_name + state.gitea_repo_owner must
    point at the fork (so mirror-finalize hits the right repo)."""
    from nexus_deploy.seeder import SeedResult

    orchestrator.gh_mirror_repos = ["https://github.com/o/r.git"]
    orchestrator.state.fork_name = "user-fork"
    orchestrator.state.fork_owner = "user"
    orchestrator.state.gitea_token = "tok"
    orchestrator.state.repo_name = "mirror-readonly-r"  # was mirror name
    orchestrator.state.gitea_repo_owner = "admin"

    seeds_dir = tmp_path / "examples" / "workspace-seeds"
    seeds_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._seeder.run_seed_for_repo",
        lambda **_kw: SeedResult(created=3, skipped=10, failed=0),
    )
    result = orchestrator._phase_mirror_seed_rerun(MagicMock())
    assert result.status == "ok"
    assert orchestrator.state.repo_name == "user-fork"
    assert orchestrator.state.gitea_repo_owner == "user"
    assert "user/user-fork" in result.detail


# --- _phase_mirror_finalize ---


def test_phase_mirror_finalize_skipped_when_not_mirror(
    orchestrator: Orchestrator,
) -> None:
    orchestrator.gh_mirror_repos = []
    result = orchestrator._phase_mirror_finalize(MagicMock())
    assert result.status == "skipped"


def test_phase_mirror_finalize_skipped_when_no_fork(
    orchestrator: Orchestrator,
) -> None:
    orchestrator.gh_mirror_repos = ["https://github.com/o/r.git"]
    orchestrator.state.fork_name = None
    result = orchestrator._phase_mirror_finalize(MagicMock())
    assert result.status == "skipped"


# --- _phase_kestra_secret_sync ---


def test_phase_kestra_secret_sync_skipped_when_not_enabled(
    orchestrator: Orchestrator,
) -> None:
    orchestrator.enabled_services = ["jupyter"]  # no kestra
    result = orchestrator._phase_kestra_secret_sync(MagicMock())
    assert result.status == "skipped"
    assert "kestra not enabled" in result.detail


def test_phase_kestra_secret_sync_skipped_when_no_infisical_creds(
    orchestrator: Orchestrator,
) -> None:
    orchestrator.enabled_services = ["kestra"]
    orchestrator.project_id = None
    orchestrator.infisical_token = None
    result = orchestrator._phase_kestra_secret_sync(MagicMock())
    assert result.status == "skipped"
    assert "PROJECT_ID" in result.detail or "INFISICAL_TOKEN" in result.detail


def test_phase_kestra_secret_sync_partial_when_kestra_pass_missing(
    minimal_env: BootstrapEnv,
) -> None:
    """NexusConfig is frozen — fresh Orchestrator with no kestra pw."""
    config_no_kestra = NexusConfig(
        admin_username="admin",
        gitea_admin_password="gitea-admin",
        kestra_admin_password=None,
    )
    orchestrator = Orchestrator(
        config=config_no_kestra,
        bootstrap_env=minimal_env,
        enabled_services=["kestra"],
        repo_name="r",
        gitea_repo_owner="o",
        project_id="p",
        infisical_token="t",
    )
    result = orchestrator._phase_kestra_secret_sync(MagicMock())
    assert result.status == "partial"
    assert "KESTRA_PASS" in result.detail


def test_phase_kestra_secret_sync_constructs_correct_stack_target(
    minimal_env: BootstrapEnv,
) -> None:
    """Issue #543: regression test pinning the Kestra-specific
    StackTarget overrides inside the orchestrator phase. Without
    these overrides the secret-sync would write to .infisical.env
    (Jupyter/Marimo default) with bare ``GITEA_TOKEN=`` keys
    instead of .env with ``SECRET_GITEA_TOKEN=<base64>``, and
    Kestra's EnvVarSecretProvider would fail to resolve any
    ``{{ secret('NAME') }}`` reference at runtime.

    Mocks ssh_run + KestraClient.wait_ready + run_sync_for_stack
    so the assertion is purely on the StackTarget shape passed in.
    """
    config = NexusConfig(
        admin_username="admin",
        gitea_admin_password="gitea-admin",
        kestra_admin_password="k-pw",
    )
    orchestrator = Orchestrator(
        config=config,
        bootstrap_env=minimal_env,
        enabled_services=["kestra"],
        repo_name="r",
        gitea_repo_owner="o",
        project_id="proj-1",
        infisical_token="inf-tok",
        domain="example.com",
    )
    orchestrator.state.gitea_token = "gt"
    from nexus_deploy.secret_sync import StackTarget, SyncResult

    captured: dict[str, StackTarget] = {}

    def _capture_run_sync(target: StackTarget, **kwargs: object) -> SyncResult:
        captured["target"] = target
        return SyncResult(
            pushed=10,
            skipped_invalid_name=0,
            skipped_multiline=0,
            failed_folders=0,
            collisions=0,
            succeeded_folders=1,
            wrote=True,
        )

    with (
        patch(
            "nexus_deploy.orchestrator._secret_sync.run_sync_for_stack",
            side_effect=_capture_run_sync,
        ),
        patch("nexus_deploy.orchestrator._kestra.KestraClient") as mock_client_cls,
    ):
        mock_client = MagicMock()
        mock_client.wait_ready.return_value = True
        mock_client_cls.return_value = mock_client
        ssh = MagicMock()
        ssh.port_forward.return_value.__enter__.return_value = 12345
        ssh.port_forward.return_value.__exit__.return_value = False
        orchestrator._phase_kestra_secret_sync(ssh)

    target = captured.get("target")
    assert target is not None
    # The five Kestra-specific overrides — each is load-bearing per
    # the comment block in orchestrator._phase_kestra_secret_sync.
    assert target.name == "kestra"
    assert target.key_prefix == "SECRET_"
    assert target.use_base64_values is True
    assert target.env_file_basename == ".env"
    assert target.legacy_env_file_basename is None
    assert target.force_recreate is True


# --- _phase_global_env ---


def test_phase_global_env_failed_on_malformed_json(
    orchestrator: Orchestrator,
) -> None:
    orchestrator.image_versions_json = "not valid json {"
    result = orchestrator._phase_global_env()
    assert result.status == "failed"
    assert "image_versions_json" in result.detail


def test_phase_global_env_renders_image_versions(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """global-env writes via ssh-stdin streaming (PR #533 R2 #2 — fixed
    heredoc injection risk). Verify the env_content reaches subprocess
    stdin, the cat command is the right shape, and the file path is
    /opt/docker-server/stacks/.env."""
    captured: dict[str, Any] = {}

    def _fake_run(args: list[str], **kwargs: Any) -> Any:
        captured["args"] = args
        captured["input"] = kwargs.get("input", "")
        cp = MagicMock()
        cp.returncode = 0
        cp.stdout = ""
        return cp

    orchestrator.image_versions_json = '{"node-exporter": "v1.2.3", "kestra": "v0.51"}'
    orchestrator.domain = "example.com"
    orchestrator.user_email = "user@example.com"
    monkeypatch.setattr("nexus_deploy.orchestrator.subprocess.run", _fake_run)
    result = orchestrator._phase_global_env()
    assert result.status == "ok"
    assert "images=2" in result.detail
    # ssh args: subprocess.run(["ssh", host, "cat > <path>"], input=...)
    assert captured["args"][0] == "ssh"
    assert captured["args"][1] == orchestrator.ssh_host
    assert "cat > /opt/docker-server/stacks/.env" in captured["args"][2]
    # env_content reaches stdin (NOT argv → no heredoc, no injection risk)
    env_content = captured["input"]
    assert "DOMAIN=example.com" in env_content
    assert "IMAGE_NODE_EXPORTER=v1.2.3" in env_content
    assert "IMAGE_KESTRA=v0.51" in env_content
    assert "USER_EMAIL=user@example.com" in env_content
    # No heredoc delimiter in the env_content (the source-of-bug)
    assert "NEXUS_GLOBAL_ENV_EOF" not in env_content


def test_phase_global_env_rejects_shell_unsafe_image_value(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-shell-unsafe-reject (PR #533 R3 #2): a malicious image-version
    value containing shell metacharacters must REJECT before write.

    The previous test (R2 #2) only asserted no heredoc-injection —
    but the global .env is later sourced (compose_runner.py legacy
    pattern), so an unescaped value with `$()` / backticks / `;` /
    `\\n` would still trigger remote command execution at source
    time. This test asserts the validation gate now rejects such
    values up-front with status='failed', refusing to write."""
    write_called = False

    def _fake_run(args: list[str], **kwargs: Any) -> Any:
        nonlocal write_called
        write_called = True
        cp = MagicMock()
        cp.returncode = 0
        return cp

    # Synthetic adversarial image value: contains newline + 'rm -rf /'.
    # If sourced unescaped, the rm command would execute on the server.
    orchestrator.image_versions_json = '{"adversarial": "v1.0\\nrm -rf /"}'
    monkeypatch.setattr("nexus_deploy.orchestrator.subprocess.run", _fake_run)
    result = orchestrator._phase_global_env()
    assert result.status == "failed"
    assert "shell-unsafe" in result.detail
    # Critically: the write subprocess MUST NOT have been called.
    assert not write_called, "validation must reject BEFORE writing the .env"


def test_phase_global_env_rejects_dollar_in_value(
    orchestrator: Orchestrator,
) -> None:
    """Same gate, different metacharacter — `$(cmd)` in a value would
    execute at source time."""
    orchestrator.image_versions_json = '{"foo": "v1.$(rm -rf /)"}'
    result = orchestrator._phase_global_env()
    assert result.status == "failed"
    assert "shell-unsafe" in result.detail


def test_phase_global_env_rejects_unsafe_image_versions_key(
    orchestrator: Orchestrator,
) -> None:
    """R-shell-unsafe-key-reject (PR #533 R5 #1): an image-versions
    key with shell metacharacters or whitespace would survive the
    existing dash→underscore normalization and produce an env-file
    line whose left-hand side breaks shell parsing OR injects
    commands when sourced. Reject keys that don't normalize to a
    valid POSIX shell variable name (^[A-Z_][A-Z0-9_]*$)."""
    orchestrator.image_versions_json = '{"foo;rm-rf": "v1.0"}'
    result = orchestrator._phase_global_env()
    assert result.status == "failed"
    assert "not a valid POSIX shell variable name" in result.detail
    assert "foo;rm-rf" in result.detail


def test_phase_global_env_rejects_image_versions_key_with_space(
    orchestrator: Orchestrator,
) -> None:
    """Keys with whitespace also fail the gate."""
    orchestrator.image_versions_json = '{"foo bar": "v1.0"}'
    result = orchestrator._phase_global_env()
    assert result.status == "failed"
    assert "not a valid POSIX shell variable name" in result.detail


def test_phase_global_env_rejects_unsafe_admin_email(
    orchestrator: Orchestrator,
) -> None:
    """ADMIN_EMAIL also goes through validation."""
    orchestrator.bootstrap_env = type(orchestrator.bootstrap_env)(
        domain="example.com",
        admin_email="admin@example.com; rm -rf /",
    )
    orchestrator.image_versions_json = "{}"
    result = orchestrator._phase_global_env()
    assert result.status == "failed"
    assert "shell-unsafe" in result.detail


def test_phase_global_env_accepts_normal_image_versions(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sanity: real image versions like ``treeverse/lakefs:1.73.0``,
    ``v1.2.3``, ``latest`` pass the validation gate."""
    captured: dict[str, Any] = {}

    def _fake_run(args: list[str], **kwargs: Any) -> Any:
        captured["input"] = kwargs.get("input", "")
        cp = MagicMock()
        cp.returncode = 0
        return cp

    orchestrator.image_versions_json = '{"lakefs": "treeverse/lakefs:1.73.0", "kestra": "v0.51.9"}'
    orchestrator.user_email = "user+admin@example.com"
    orchestrator.domain = "example.com"
    monkeypatch.setattr("nexus_deploy.orchestrator.subprocess.run", _fake_run)
    result = orchestrator._phase_global_env()
    assert result.status == "ok"
    assert "IMAGE_LAKEFS=treeverse/lakefs:1.73.0" in captured["input"]
    assert "IMAGE_KESTRA=v0.51.9" in captured["input"]


# --- _phase_firewall_sync ---


def test_phase_firewall_sync_failed_when_project_root_missing(
    orchestrator: Orchestrator, tmp_path: Any
) -> None:
    orchestrator.project_root = tmp_path / "does-not-exist"
    result = orchestrator._phase_firewall_sync()
    assert result.status == "failed"
    assert "is not a directory" in result.detail


def test_phase_firewall_sync_failed_when_local_stacks_dir_missing(
    orchestrator: Orchestrator, tmp_path: Any
) -> None:
    """R-destructive-footgun (PR #533 R1 #4): when project_root exists
    but the inner stacks/ dir is missing (e.g. checkout incomplete),
    Path.glob silently returns nothing — without an explicit guard
    we'd treat every remote firewall override as orphan and rm them.
    Must fail fast instead."""
    # project_root exists but stacks/ subdir does not
    orchestrator.project_root = tmp_path
    result = orchestrator._phase_firewall_sync()
    assert result.status == "failed"
    assert "local stacks dir" in result.detail
    assert "is missing" in result.detail
    assert "would rm every remote" in result.detail


def test_phase_firewall_sync_no_orphans_no_redpanda(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Empty local + empty remote firewall override list → no-op ok."""
    stacks_dir = tmp_path / "stacks"
    stacks_dir.mkdir()
    orchestrator.project_root = tmp_path
    orchestrator.enabled_services = ["jupyter"]  # no redpanda

    def _fake_run(_script: str, **_kw: Any) -> Any:
        cp = MagicMock()
        cp.stdout = ""
        cp.returncode = 0
        return cp

    monkeypatch.setattr("nexus_deploy.orchestrator._remote.ssh_run_script", _fake_run)
    result = orchestrator._phase_firewall_sync()
    assert result.status == "ok"
    assert "orphans_removed=0" in result.detail


# ---------------------------------------------------------------------------
# _phase_woodpecker_apply — full happy path + error paths
# ---------------------------------------------------------------------------
#
# Coverage gap before these: the existing 3 tests only exercise the
# skip / not-populated / no-agent-secret guards. The actual apply
# flow (write .env, rsync, docker compose up -d) and its four error
# paths (local-write OSError, rsync transport, compose-up rc!=0,
# compose-up timeout, compose-up unexpected) were never executed
# in tests.


@pytest.fixture
def woodpecker_enabled(orchestrator: Orchestrator) -> Orchestrator:
    """Reusable setup: woodpecker enabled + OAuth creds + agent secret
    populated, so every test below only differs in the error injection."""
    orchestrator.enabled_services = ["woodpecker"]
    orchestrator.state.woodpecker_client_id = "wp-id"
    orchestrator.state.woodpecker_client_secret = "wp-secret"
    orchestrator.woodpecker_agent_secret = "agent-secret"
    orchestrator.domain = "example.com"
    return orchestrator


def test_phase_woodpecker_apply_happy_path(
    woodpecker_enabled: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """End-to-end: write .env → rsync → compose up. Every external
    boundary mocked successful. Verifies status='ok' and that the
    rendered .env carries the OAuth creds we expect."""
    orchestrator = woodpecker_enabled
    woodpecker_dir = tmp_path / "stacks" / "woodpecker"
    woodpecker_dir.mkdir(parents=True)
    orchestrator.project_root = tmp_path

    rsync_mock = MagicMock()
    ssh_run_mock = MagicMock(return_value=MagicMock(returncode=0, output=""))
    monkeypatch.setattr("nexus_deploy.orchestrator._remote.rsync_to_remote", rsync_mock)
    monkeypatch.setattr("nexus_deploy.orchestrator._remote.ssh_run_script", ssh_run_mock)

    result = orchestrator._phase_woodpecker_apply(MagicMock())
    assert result.status == "ok"

    # The .env content must include the OAuth credentials. Operators
    # debugging a misconfigured woodpecker would look here first.
    env_content = (woodpecker_dir / ".env").read_text()
    assert "WOODPECKER_GITEA_CLIENT=wp-id" in env_content
    assert "WOODPECKER_GITEA_SECRET=wp-secret" in env_content
    assert "WOODPECKER_AGENT_SECRET=agent-secret" in env_content
    assert "DOMAIN=example.com" in env_content


def test_phase_woodpecker_apply_failed_when_stack_dir_missing(
    woodpecker_enabled: Orchestrator,
    tmp_path: Any,
) -> None:
    """If stack-sync didn't place stacks/woodpecker locally, the
    phase MUST fail-fast (not silently no-op) — the rsync below
    would otherwise upload an empty directory."""
    orchestrator = woodpecker_enabled
    orchestrator.project_root = tmp_path  # no stacks/woodpecker dir

    result = orchestrator._phase_woodpecker_apply(MagicMock())
    assert result.status == "failed"
    assert "stack-sync should have placed it" in result.detail


def test_phase_woodpecker_apply_failed_on_local_env_write_error(
    woodpecker_enabled: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Local .env write OSError is distinct from rsync/compose
    failures — distinct detail string so operators can tell from
    the log which boundary failed."""
    orchestrator = woodpecker_enabled
    woodpecker_dir = tmp_path / "stacks" / "woodpecker"
    woodpecker_dir.mkdir(parents=True)
    orchestrator.project_root = tmp_path

    # Simulate write_text raising OSError on the .env path.
    real_write_text = Path.write_text

    def fake_write_text(self: Path, *args: Any, **kw: Any) -> int:
        if self.name == ".env":
            raise OSError("disk full")
        return real_write_text(self, *args, **kw)

    monkeypatch.setattr(Path, "write_text", fake_write_text)

    result = orchestrator._phase_woodpecker_apply(MagicMock())
    assert result.status == "failed"
    assert "local write" in result.detail
    assert "OSError" in result.detail


def test_phase_woodpecker_apply_partial_on_rsync_transport_error(
    woodpecker_enabled: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """rsync failure → partial (not failed) — the ssh transport
    error is distinct from docker compose failure, so operators
    should investigate connectivity / disk on the server, not
    container logs. PR #533 R7 #2 finding."""
    orchestrator = woodpecker_enabled
    woodpecker_dir = tmp_path / "stacks" / "woodpecker"
    woodpecker_dir.mkdir(parents=True)
    orchestrator.project_root = tmp_path

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._remote.rsync_to_remote",
        MagicMock(side_effect=subprocess.CalledProcessError(255, ["rsync"])),
    )

    result = orchestrator._phase_woodpecker_apply(MagicMock())
    assert result.status == "partial"
    assert "rsync transport" in result.detail


def test_phase_woodpecker_apply_partial_on_compose_up_rc_nonzero(
    woodpecker_enabled: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """docker compose up rc!=0 → partial, with the stdout tail in
    the detail so operators see the compose error inline (PR #533
    R3 #1: --env-file via compose, not source)."""
    orchestrator = woodpecker_enabled
    woodpecker_dir = tmp_path / "stacks" / "woodpecker"
    woodpecker_dir.mkdir(parents=True)
    orchestrator.project_root = tmp_path

    monkeypatch.setattr("nexus_deploy.orchestrator._remote.rsync_to_remote", MagicMock())
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._remote.ssh_run_script",
        MagicMock(
            side_effect=subprocess.CalledProcessError(
                returncode=1,
                cmd=["ssh"],
                output="Error response from daemon: pull access denied for woodpecker/server",
            )
        ),
    )

    result = orchestrator._phase_woodpecker_apply(MagicMock())
    assert result.status == "partial"
    assert "docker compose up -d failed" in result.detail
    assert "rc=1" in result.detail


def test_phase_woodpecker_apply_partial_on_compose_up_timeout(
    woodpecker_enabled: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """ssh transport timeout during compose up → partial. Distinct
    diagnostic from compose-rc-nonzero: operator investigates
    connectivity, not container state."""
    orchestrator = woodpecker_enabled
    woodpecker_dir = tmp_path / "stacks" / "woodpecker"
    woodpecker_dir.mkdir(parents=True)
    orchestrator.project_root = tmp_path

    monkeypatch.setattr("nexus_deploy.orchestrator._remote.rsync_to_remote", MagicMock())
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._remote.ssh_run_script",
        MagicMock(side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=120)),
    )

    result = orchestrator._phase_woodpecker_apply(MagicMock())
    assert result.status == "partial"
    assert "ssh transport timeout" in result.detail


def test_phase_woodpecker_apply_failed_on_unexpected_exception(
    woodpecker_enabled: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Any non-(CalledProcessError|TimeoutExpired) Exception during
    compose-up → failed (not partial). These shouldn't happen at
    runtime; if one does, fail-loud so the operator notices."""
    orchestrator = woodpecker_enabled
    woodpecker_dir = tmp_path / "stacks" / "woodpecker"
    woodpecker_dir.mkdir(parents=True)
    orchestrator.project_root = tmp_path

    monkeypatch.setattr("nexus_deploy.orchestrator._remote.rsync_to_remote", MagicMock())
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._remote.ssh_run_script",
        MagicMock(side_effect=RuntimeError("paramiko meltdown")),
    )

    result = orchestrator._phase_woodpecker_apply(MagicMock())
    assert result.status == "failed"
    assert "unexpected" in result.detail
    assert "RuntimeError" in result.detail


# ---------------------------------------------------------------------------
# _phase_mirror_finalize — full execution paths
# ---------------------------------------------------------------------------
#
# Existing tests only exercise the two skip-gates (not mirror /
# no fork). The actual flow-sync re-trigger + git-restart loop
# (~75 lines incl. all four exception branches) was never hit.


@pytest.fixture
def mirror_finalize_ready(orchestrator: Orchestrator) -> Orchestrator:
    """Mirror mode + fork populated + kestra enabled + admin creds
    + admin email — the all-prereqs-met setup that exercises the
    flow-sync + git-restart code paths."""
    orchestrator.gh_mirror_repos = ["https://github.com/o/r.git"]
    orchestrator.state.fork_name = "user-fork"
    orchestrator.enabled_services = ["kestra", "jupyter", "marimo"]
    return orchestrator


def test_phase_mirror_finalize_happy_path_flow_and_restarts(
    mirror_finalize_ready: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both sub-steps succeed: flow-sync POST + git-restart loop.
    Status must be 'ok' AND the detail must surface both successes
    (flow_triggered=True + git_restarted=N)."""
    orchestrator = mirror_finalize_ready

    # KestraClient.execute_flow — successful path (mocked).
    kestra_client = MagicMock()
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._kestra.KestraClient",
        MagicMock(return_value=kestra_client),
    )
    # compose_restart.run_restart returns a RestartResult.
    restart_result = MagicMock(restarted=2, failed=0)
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._compose_restart.run_restart",
        MagicMock(return_value=restart_result),
    )

    ssh = MagicMock()
    ssh.port_forward.return_value.__enter__.return_value = 8085

    result = orchestrator._phase_mirror_finalize(ssh)
    assert result.status == "ok"
    assert "flow_triggered=True" in result.detail
    assert "git_restarted=2" in result.detail
    kestra_client.execute_flow.assert_called_once_with("system", "flow-sync")


def test_phase_mirror_finalize_partial_when_kestra_not_enabled(
    mirror_finalize_ready: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No kestra in enabled list → flow-sync is genuinely-skipped
    (NOT a partial trigger), but git-restart still runs. Status
    stays 'ok' because the (a) gate excludes 'kestra not enabled'
    from partial-ness — that's the legitimate skip case."""
    orchestrator = mirror_finalize_ready
    orchestrator.enabled_services = ["jupyter", "marimo"]  # no kestra

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._compose_restart.run_restart",
        MagicMock(return_value=MagicMock(restarted=1, failed=0)),
    )

    result = orchestrator._phase_mirror_finalize(MagicMock())
    assert result.status == "ok"
    assert "flow_triggered=False" in result.detail


def test_phase_mirror_finalize_partial_on_flow_sync_kestra_error(
    mirror_finalize_ready: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KestraError during execute_flow → flow_triggered stays False
    + kestra IS in enabled_services → partial. Detail must surface
    the kestra error message."""
    orchestrator = mirror_finalize_ready

    # Need to import KestraError to raise it.
    from nexus_deploy.kestra import KestraError

    kestra_client = MagicMock()
    kestra_client.execute_flow.side_effect = KestraError("HTTP 503 from kestra")
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._kestra.KestraClient",
        MagicMock(return_value=kestra_client),
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._compose_restart.run_restart",
        MagicMock(return_value=MagicMock(restarted=2, failed=0)),
    )

    ssh = MagicMock()
    ssh.port_forward.return_value.__enter__.return_value = 8085

    result = orchestrator._phase_mirror_finalize(ssh)
    assert result.status == "partial"
    assert "flow_skip=HTTP 503 from kestra" in result.detail


def test_phase_mirror_finalize_partial_on_flow_sync_transport_error(
    mirror_finalize_ready: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subprocess/OS error during port-forward setup → flow-sync
    abandoned, kestra IS enabled → partial. Distinct from KestraError
    (auth/HTTP) because the operator should investigate ssh
    transport, not the kestra server."""
    orchestrator = mirror_finalize_ready

    ssh = MagicMock()
    ssh.port_forward.side_effect = OSError("port forward setup failed")
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._compose_restart.run_restart",
        MagicMock(return_value=MagicMock(restarted=2, failed=0)),
    )

    result = orchestrator._phase_mirror_finalize(ssh)
    assert result.status == "partial"
    assert "transport" in result.detail
    assert "OSError" in result.detail


def test_phase_mirror_finalize_partial_on_git_restart_transport_error(
    mirror_finalize_ready: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compose_restart.run_restart raising CalledProcessError →
    partial with git_restart_transport_error in detail. Flow-sync
    success state is still surfaced in the detail for the operator."""
    orchestrator = mirror_finalize_ready

    kestra_client = MagicMock()
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._kestra.KestraClient",
        MagicMock(return_value=kestra_client),
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._compose_restart.run_restart",
        MagicMock(side_effect=subprocess.CalledProcessError(255, ["ssh"])),
    )

    ssh = MagicMock()
    ssh.port_forward.return_value.__enter__.return_value = 8085

    result = orchestrator._phase_mirror_finalize(ssh)
    assert result.status == "partial"
    assert "flow_triggered=True" in result.detail
    assert "git_restart_transport_error" in result.detail
    assert "CalledProcessError" in result.detail


def test_phase_mirror_finalize_partial_when_git_restart_reports_failures(
    mirror_finalize_ready: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compose_restart returns successfully but with failed>0 → partial.
    This is the per-service-failure path: rsync OK, compose error per-
    service. Detail must surface git_failed= count so operator can
    drill into which service died."""
    orchestrator = mirror_finalize_ready

    kestra_client = MagicMock()
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._kestra.KestraClient",
        MagicMock(return_value=kestra_client),
    )
    monkeypatch.setattr(
        "nexus_deploy.orchestrator._compose_restart.run_restart",
        MagicMock(return_value=MagicMock(restarted=1, failed=2)),
    )

    ssh = MagicMock()
    ssh.port_forward.return_value.__enter__.return_value = 8085

    result = orchestrator._phase_mirror_finalize(ssh)
    assert result.status == "partial"
    assert "git_restarted=1" in result.detail
    assert "git_failed=2" in result.detail


# ---------------------------------------------------------------------------
# _phase_firewall_sync — redpanda config-copy path
# ---------------------------------------------------------------------------
#
# Existing tests cover (a) project_root missing, (b) stacks/ missing,
# (c) no-orphans-no-redpanda happy path. The redpanda-enabled
# branch (~57 lines of mkdir+scp+chown+yaml selection) was uncovered.


def test_phase_firewall_sync_failed_when_redpanda_config_dir_missing(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """If redpanda is enabled but stacks/redpanda/config/ is missing
    locally, the phase MUST fail-fast — scp'ing from a non-existent
    source would silently no-op and leave the rendered firewall
    config dangling."""
    stacks_dir = tmp_path / "stacks"
    stacks_dir.mkdir()
    # No redpanda/ subdir created.
    orchestrator.project_root = tmp_path
    orchestrator.enabled_services = ["redpanda"]

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._remote.ssh_run_script",
        MagicMock(return_value=MagicMock(stdout="", returncode=0)),
    )

    result = orchestrator._phase_firewall_sync()
    assert result.status == "failed"
    assert "redpanda config dir" in result.detail
    assert "missing locally" in result.detail


def test_phase_firewall_sync_failed_when_no_redpanda_yaml(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Redpanda config dir exists but neither redpanda-firewall.yaml
    nor redpanda.yaml is present — fail-fast with the exact missing-
    yaml diagnostic."""
    redpanda_dir = tmp_path / "stacks" / "redpanda" / "config"
    redpanda_dir.mkdir(parents=True)
    orchestrator.project_root = tmp_path
    orchestrator.enabled_services = ["redpanda"]

    monkeypatch.setattr(
        "nexus_deploy.orchestrator._remote.ssh_run_script",
        MagicMock(return_value=MagicMock(stdout="", returncode=0)),
    )

    result = orchestrator._phase_firewall_sync()
    assert result.status == "failed"
    assert "neither redpanda-firewall.yaml nor redpanda.yaml" in result.detail


def test_phase_firewall_sync_copies_redpanda_firewall_yaml_when_present(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Happy path: redpanda enabled, redpanda-firewall.yaml present
    locally. The phase must scp THAT file (not the regular
    redpanda.yaml) and chown 101:101 on the server."""
    redpanda_dir = tmp_path / "stacks" / "redpanda" / "config"
    redpanda_dir.mkdir(parents=True)
    (redpanda_dir / "redpanda-firewall.yaml").write_text("# firewall config\n")
    (redpanda_dir / "redpanda.yaml").write_text("# regular config\n")
    orchestrator.project_root = tmp_path
    orchestrator.enabled_services = ["redpanda"]

    ssh_run_mock = MagicMock(return_value=MagicMock(stdout="", returncode=0))
    monkeypatch.setattr("nexus_deploy.orchestrator._remote.ssh_run_script", ssh_run_mock)
    scp_calls: list[list[str]] = []

    def fake_subprocess_run(args: list[str], **_kw: Any) -> Any:
        scp_calls.append(args)
        cp = MagicMock()
        cp.returncode = 0
        return cp

    monkeypatch.setattr("nexus_deploy.orchestrator.subprocess.run", fake_subprocess_run)

    result = orchestrator._phase_firewall_sync()
    assert result.status == "ok"
    # scp must have been called with the firewall variant, not the
    # regular yaml.
    assert any("redpanda-firewall.yaml" in arg for call in scp_calls for arg in call)
    # And one of the ssh_run_script invocations carries the
    # chown/chmod fallback chain.
    ssh_scripts = [str(call.args[0]) for call in ssh_run_mock.call_args_list]
    assert any("chown -R 101:101" in s for s in ssh_scripts)
    assert any("chmod -R 777" in s for s in ssh_scripts)


# ---------------------------------------------------------------------------
# _transport_detail — a phase failure must be diagnosable in one run
# ---------------------------------------------------------------------------


def test_transport_detail_carries_rc_and_the_output_tail() -> None:
    """The exact case that cost a deploy cycle: the remote script said
    precisely what was wrong and the phase threw it away."""
    from nexus_deploy.orchestrator import _transport_detail

    exc = subprocess.CalledProcessError(
        2,
        ["ssh", "nexus", "bash", "-s"],
        output="→ syncing\nsort: separator must be exactly one character long: ''\n",
    )
    detail = _transport_detail(exc)

    assert "CalledProcessError" in detail
    assert "rc=2" in detail
    assert "separator must be exactly one character long" in detail


def test_transport_detail_never_includes_the_command() -> None:
    """`exc.cmd` can carry secrets through env-var-prefixed forms."""
    from nexus_deploy.orchestrator import _transport_detail

    exc = subprocess.CalledProcessError(
        1,
        ["ssh", "nexus", "SECRET_TOKEN=hunter2 some-command"],
        output="failed",
    )
    detail = _transport_detail(exc)

    assert "hunter2" not in detail
    assert "SECRET_TOKEN" not in detail


def test_transport_detail_collapses_newlines_into_one_line() -> None:
    """PhaseResult details are rendered one per line in the phase log."""
    from nexus_deploy.orchestrator import _transport_detail

    exc = subprocess.CalledProcessError(1, ["x"], output="a\nb\n\nc")
    assert "\n" not in _transport_detail(exc)


def test_transport_detail_reports_the_timeout_not_a_missing_rc() -> None:
    from nexus_deploy.orchestrator import _transport_detail

    exc = subprocess.TimeoutExpired(cmd=["ssh", "h"], timeout=480)
    detail = _transport_detail(exc)

    assert "TimeoutExpired" in detail
    assert "timeout=480s" in detail
    assert "rc=" not in detail


def test_transport_detail_handles_an_exception_with_no_output() -> None:
    from nexus_deploy.orchestrator import _transport_detail

    assert _transport_detail(OSError("boom")) == "transport (OSError)"


@pytest.mark.parametrize(
    ("output", "secret"),
    [
        # The one that broke the contract: infisical's provision script
        # prints its bearer token on stdout, base64-encoded. base64 is
        # an encoding, not redaction.
        ("RESULT status=loaded-existing token=aGVsbG8= project_id=abc", "aGVsbG8="),
        # Underscore-prefixed names are the common shape here, and a
        # naive \b anchor would miss every one of them.
        ("SECRET_GITEA_TOKEN=czoZGVhZGJlZWY= wrote=1", "czoZGVhZGJlZWY="),
        ("GITEA_ADMIN_PASSWORD=hunter2", "hunter2"),
        ("r2_secret_access_key=AKIAsomething", "AKIAsomething"),
    ],
)
def test_transport_detail_redacts_credential_assignments(output: str, secret: str) -> None:
    """This repository is public and its CI logs are world-readable."""
    from nexus_deploy.orchestrator import _transport_detail

    detail = _transport_detail(subprocess.CalledProcessError(1, ["ssh"], output=output))

    assert secret not in detail
    assert "<redacted>" in detail


def test_transport_detail_keeps_the_diagnostic_parts() -> None:
    """Redaction must not cost the thing the tail exists for."""
    from nexus_deploy.orchestrator import _transport_detail

    detail = _transport_detail(
        subprocess.CalledProcessError(
            2, ["ssh"], output="pushed=128 failed=0 wrote=1 — sort: separator must be one char"
        )
    )

    assert "pushed=128" in detail
    assert "failed=0" in detail
    assert "sort: separator must be one char" in detail
    assert "<redacted>" not in detail


def test_transport_detail_redacts_before_truncating() -> None:
    """A value split across the 280-char cut must not survive as a
    fragment, so the scrub has to run on the full text first."""
    from nexus_deploy.orchestrator import _transport_detail

    noise = "x" * 400
    detail = _transport_detail(
        subprocess.CalledProcessError(1, ["ssh"], output=f"{noise} token=SUPERSECRETVALUE")
    )

    assert "SUPERSECRET" not in detail


# Forgejo phases — behaviour, not just phase-count bookkeeping
# ---------------------------------------------------------------------------


def _forgejo_orchestrator(**overrides: Any) -> Orchestrator:
    """An orchestrator with Forgejo enabled and its credentials set."""
    fields: dict[str, Any] = {
        "admin_username": "admin",
        "forgejo_admin_password": "fj-admin",
        "forgejo_user_password": "fj-user",
        "forgejo_runner_secret": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
    }
    fields.update(overrides.pop("config", {}))
    config = NexusConfig(**fields)
    return Orchestrator(
        config=config,
        bootstrap_env=BootstrapEnv(
            domain="example.com",
            admin_email="admin@example.com",
            gitea_user_email="student@example.com",
        ),
        enabled_services=overrides.pop("enabled_services", ["forgejo", "forgejo-runner"]),
        project_id="proj-id",
        infisical_token="infi-token",
        **overrides,
    )


def test_forgejo_configure_skipped_when_stack_disabled() -> None:
    orch = _forgejo_orchestrator(enabled_services=["kestra"])
    result = orch._phase_forgejo_configure(MagicMock())

    assert result.status == "skipped"
    assert "not enabled" in result.detail


def test_forgejo_configure_partial_without_admin_password() -> None:
    """No admin password means no account can be created — and with
    INSTALL_LOCK on, no account means the UI is locked for good."""
    orch = _forgejo_orchestrator(config={"forgejo_admin_password": ""})
    result = orch._phase_forgejo_configure(MagicMock())

    assert result.status == "partial"
    assert "FORGEJO_ADMIN_PASS" in result.detail


def test_forgejo_configure_provisions_admin_and_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake(ssh: Any, accounts: Any, **kwargs: Any) -> Any:
        captured["accounts"] = accounts
        from nexus_deploy.forgejo import ConfigureResult

        return ConfigureResult(status="configured", detail="accounts=admin, student")

    monkeypatch.setattr("nexus_deploy.forgejo.run_configure", _fake)
    result = _forgejo_orchestrator()._phase_forgejo_configure(MagicMock())

    assert result.status == "ok"
    accounts = captured["accounts"]
    assert [a.username for a in accounts] == ["admin", "student"]
    assert accounts[0].admin is True
    assert accounts[1].admin is False


def test_forgejo_configure_skips_the_user_when_it_collides_with_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stack where user_email's local part is `admin` must not try to
    create the same account twice with two different passwords."""
    captured: dict[str, Any] = {}

    def _fake(ssh: Any, accounts: Any, **kwargs: Any) -> Any:
        captured["accounts"] = accounts
        from nexus_deploy.forgejo import ConfigureResult

        return ConfigureResult(status="configured", detail="accounts=admin")

    monkeypatch.setattr("nexus_deploy.forgejo.run_configure", _fake)
    orch = _forgejo_orchestrator()
    orch.bootstrap_env = dataclasses.replace(
        orch.bootstrap_env, gitea_user_email="admin@example.com"
    )
    result = orch._phase_forgejo_configure(MagicMock())

    assert result.status == "ok"
    assert [a.username for a in captured["accounts"]] == ["admin"]


def test_forgejo_configure_failure_is_partial_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken optional stack must not abandon the remaining phases."""
    from nexus_deploy.forgejo import ConfigureResult

    monkeypatch.setattr(
        "nexus_deploy.forgejo.run_configure",
        lambda *a, **k: ConfigureResult(status="failed", detail="forgejo admin exited 1"),
    )
    result = _forgejo_orchestrator()._phase_forgejo_configure(MagicMock())

    assert result.status == "partial"


def test_forgejo_runner_register_skipped_when_stack_disabled() -> None:
    orch = _forgejo_orchestrator(enabled_services=["kestra"])
    result = orch._phase_forgejo_runner_register(MagicMock())

    assert result.status == "skipped"


def test_forgejo_runner_register_partial_without_secret() -> None:
    orch = _forgejo_orchestrator(config={"forgejo_runner_secret": ""})
    result = orch._phase_forgejo_runner_register(MagicMock())

    assert result.status == "partial"
    assert "FORGEJO_RUNNER_SECRET" in result.detail


def test_forgejo_runner_register_passes_the_secret_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake(ssh: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        from nexus_deploy.forgejo_runner import RegisterResult

        return RegisterResult(status="registered", detail="name=nexus-runner")

    monkeypatch.setattr("nexus_deploy.forgejo_runner.run_register", _fake)
    result = _forgejo_orchestrator()._phase_forgejo_runner_register(MagicMock())

    assert result.status == "ok"
    assert captured["secret"] == "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"


def test_forgejo_runner_register_failure_is_partial_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus_deploy.forgejo_runner import RegisterResult

    monkeypatch.setattr(
        "nexus_deploy.forgejo_runner.run_register",
        lambda *a, **k: RegisterResult(status="failed", detail="forgejo-cli exited 1"),
    )
    result = _forgejo_orchestrator()._phase_forgejo_runner_register(MagicMock())

    assert result.status == "partial"


def test_forgejo_runner_register_skipped_when_only_the_forge_is_enabled() -> None:
    """The forge is core and always on; the runner is opt-in. Telling a
    forge with no runner about a runner secret would create a
    registration nobody can use."""
    orch = _forgejo_orchestrator(enabled_services=["forgejo"])
    result = orch._phase_forgejo_runner_register(MagicMock())

    assert result.status == "skipped"
    assert "forgejo-runner" in result.detail


def test_forgejo_configure_runs_without_the_runner_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Account provisioning belongs to the forge, so it must not depend
    on CI being enabled."""
    from nexus_deploy.forgejo import ConfigureResult

    monkeypatch.setattr(
        "nexus_deploy.forgejo.run_configure",
        lambda *a, **k: ConfigureResult(status="configured", detail="accounts=admin"),
    )
    orch = _forgejo_orchestrator(enabled_services=["forgejo"])

    assert orch._phase_forgejo_configure(MagicMock()).status == "ok"
