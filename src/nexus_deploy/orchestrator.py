"""Top-level orchestrator for the deploy pipeline.

Single Python entrypoint that calls every module function in
sequence and handles state-passing in-process via one
:class:`OrchestratorState` mutated as phases run. Three values
still need to escape to bash for the surviving compose-restart +
Woodpecker .env write logic:

* ``RESTART_SERVICES``  — compose-restart loop reads this
* ``WOODPECKER_GITEA_CLIENT`` — written into stacks/woodpecker/.env
* ``WOODPECKER_GITEA_SECRET`` — written into stacks/woodpecker/.env

Other state (``GITEA_TOKEN``, ``FORK_NAME``, ``FORK_OWNER``) is
consumed entirely inside the orchestrator and never exits Python.

Phase order (deterministic):

1. infisical bootstrap            (push all secret folders to Infisical)
2. services configure             (REST + exec admin-setup hooks)
3. gitea configure                (admin/user create+sync, repo, token)
4. seed                           (push examples/workspace-seeds/ to repo)
5. kestra register-system-flows   (system.git-sync + flow-sync)
6. gitea woodpecker-oauth         (provision OAuth app for Woodpecker CI)
7. gitea mirror-setup             (per-mirror migrate + fork; if mirrors)
8. secret-sync jupyter            (Infisical → Jupyter .infisical.env)
9. secret-sync marimo             (Infisical → Marimo .infisical.env)

Each phase produces a :class:`PhaseResult`. A phase with status="failed"
aborts the orchestrator (early exit, downstream phases skipped). A
phase with status="partial" continues — operator gets a yellow
warning, downstream phases still run. Same rc=0/1/2 dispatch as
all other CLIs in the package.

``contextlib.ExitStack`` manages the SSH client lifetime in
:meth:`Orchestrator.run_all`. Each phase that needs an HTTP
port-forward to the nexus server opens it inside its own method
via a local ``with ssh.port_forward(...)`` block so the tunnel
is torn down before the phase returns — the ExitStack is not
passed into phases.
"""

from __future__ import annotations

import contextlib
import re
import shlex
import socket
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from nexus_deploy import _remote
from nexus_deploy import compose_restart as _compose_restart
from nexus_deploy import compose_runner as _compose_runner
from nexus_deploy import firewall as _firewall
from nexus_deploy import gitea as _gitea
from nexus_deploy import infisical as _infisical
from nexus_deploy import kestra as _kestra
from nexus_deploy import secret_sync as _secret_sync
from nexus_deploy import seeder as _seeder
from nexus_deploy import service_env as _service_env
from nexus_deploy import services as _services
from nexus_deploy import stack_sync as _stack_sync
from nexus_deploy import workspace_coords as _workspace_coords
from nexus_deploy.config import NexusConfig
from nexus_deploy.infisical import BootstrapEnv
from nexus_deploy.ssh import SSHClient

# Server-side stacks dir mirror (matches compose_runner / stack_sync /
# compose_restart). Used by _phase_global_env + _phase_firewall_sync +
# _phase_woodpecker_apply for path construction.
_REMOTE_STACKS_DIR = "/opt/docker-server/stacks"


@dataclass
class OrchestratorState:
    """Mutable state populated as phases run.

    Replaces the bash eval-tempfile-handoff pattern with in-process
    Python attributes. Each phase reads what it needs and writes
    its outputs.

    The ``restart_services`` + ``woodpecker_*`` fields are
    additionally emitted to stdout at the end so the surviving
    shell glue (compose-restart loop + Woodpecker .env writer)
    can consume them. ``gitea_token`` / ``fork_*`` stay in-process.
    """

    gitea_token: str | None = None
    restart_services: tuple[str, ...] = ()
    woodpecker_client_id: str | None = None
    woodpecker_client_secret: str | None = None
    fork_name: str | None = None
    fork_owner: str | None = None
    # infisical_token + project_id are POPULATED by
    # _phase_infisical_provision (running BEFORE _phase_infisical_bootstrap),
    # so pre-bootstrap callers don't need to pass them in the
    # constructor.
    #
    # Note: post-bootstrap phases currently gate on the
    # ``self.infisical_token`` / ``self.project_id`` orchestrator fields,
    # not on these state mirrors. ``_phase_infisical_provision`` writes
    # to BOTH (state + self.field) so a single full-pipeline run sees
    # the values everywhere. State stays as the canonical record for
    # the CLI's stdout emission (PR #532 R2 #5).
    infisical_token: str | None = None
    project_id: str | None = None

    # workspace-coords slots populated by _phase_workspace_coords —
    # repo_name / gitea_repo_owner / workspace_branch / Gitea git
    # identity. Same dual-write pattern as infisical_token /
    # project_id: the phase writes to BOTH state.* (for stdout
    # emission) AND self.* on the orchestrator (for downstream
    # phases that gate on the orchestrator fields).
    # _phase_mirror_setup later mutates state.repo_name +
    # state.gitea_repo_owner to point at the user's fork (so the
    # mirror-seed-rerun + git-restart phases hit the right repo).
    repo_name: str | None = None
    gitea_repo_owner: str | None = None
    gitea_repo_url: str | None = None
    workspace_branch: str = "main"
    gitea_git_user: str | None = None
    gitea_git_pass: str | None = None
    git_author: str | None = None
    git_email: str | None = None


@dataclass(frozen=True)
class PhaseResult:
    """Outcome of a single phase. Same shape as the per-module
    Result dataclasses (RsyncResult, OAuthAppResult, etc.)."""

    name: str
    status: Literal["ok", "partial", "failed", "skipped"]
    detail: str = ""


@dataclass(frozen=True)
class OrchestratorResult:
    """Return value from :meth:`Orchestrator.run_all`."""

    phases: tuple[PhaseResult, ...]
    state: OrchestratorState

    @property
    def is_success(self) -> bool:
        """All phases ok or skipped (no failed, no partial)."""
        return all(p.status in ("ok", "skipped") for p in self.phases)

    @property
    def has_partial(self) -> bool:
        """At least one phase produced status='partial' (yellow warn)."""
        return any(p.status == "partial" for p in self.phases)

    @property
    def has_hard_failure(self) -> bool:
        return any(p.status == "failed" for p in self.phases)


def _allocate_free_port() -> int:
    """Same primitive as :func:`__main__._allocate_free_port`. Inlined
    here so orchestrator.py doesn't depend on __main__."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


@dataclass
class Orchestrator:
    """Top-level pipeline runner.

    Construct with the per-deploy inputs, then call :meth:`run_all`.
    State accumulates across phases on ``self.state``.
    """

    config: NexusConfig
    bootstrap_env: BootstrapEnv
    enabled_services: list[str]
    # repo_name / gitea_repo_owner / workspace_branch are POPULATED
    # by _phase_workspace_coords during run_pre_bootstrap. Kept as
    # constructor fields so post-bootstrap-only callers (run_all
    # without run_pre_bootstrap) can still pre-seed them — same
    # back-compat shape as infisical_token / project_id.
    repo_name: str = ""
    gitea_repo_owner: str = ""
    workspace_branch: str = "main"
    gh_mirror_repos: list[str] = field(default_factory=list)
    gh_mirror_token: str | None = None
    gitea_user_username: str | None = None
    gitea_user_email: str | None = None
    gitea_user_password: str | None = None
    ssh_host: str = "nexus"
    project_id: str | None = None
    infisical_token: str | None = None
    infisical_env: str = "dev"

    # Pre-bootstrap pipeline inputs. All optional to keep back-compat
    # with post-bootstrap-only callers (run_all). When unset, phases
    # that need them surface as status='skipped' with a clear detail.
    cf_client_id: str | None = None  # Cloudflare Access Service Token id
    cf_client_secret: str | None = None  # Cloudflare Access Service Token secret
    persistent_volume_id: str = "0"  # Hetzner Cloud volume id; "0" = no volume
    # Repository checkout root on the runner — phases derive
    # ``project_root / "stacks"`` for per-service compose/.env paths.
    # Renamed from ``stacks_dir`` in PR #532 R2 #1: STACKS_DIR is
    # ``PROJECT_ROOT/stacks`` (the actual stacks dir), so wiring that
    # env var into a field of the same name and then appending
    # ``/"stacks"`` produced a broken ``.../stacks/stacks/...`` path.
    # The CLI handler now reads ``PROJECT_ROOT`` instead.
    project_root: Path = field(default_factory=lambda: Path.cwd())
    firewall_json: str = "{}"  # raw `tofu output -json firewall_rules` body
    domain: str = ""  # for firewall RedPanda rendering
    admin_password_infisical: str | None = None  # for infisical provision-admin

    # workspace-coords + global-env inputs. All optional; phases skip
    # with status='partial'/'skipped' when their required inputs are
    # missing.
    admin_username: str = ""  # for workspace-coords admin-fallback
    user_email: str = ""  # passed into global-env's stacks/.env
    gitea_admin_pass: str | None = None  # for workspace-coords git_pass fallback
    image_versions_json: str = "{}"  # raw `tofu output -json image_versions` body
    woodpecker_agent_secret: str | None = None  # for woodpecker_apply .env write

    state: OrchestratorState = field(default_factory=OrchestratorState)
    results: list[PhaseResult] = field(default_factory=list)

    def run_all(self) -> OrchestratorResult:
        """Execute all phases in deterministic order.

        ExitStack ensures any opened ssh-tunnels / temp-files clean
        up before return, even on early-fail. A phase with
        status='failed' aborts the run; status='partial' continues
        with a recorded warning.

        Resets ``self.results`` so re-invoking the same instance does
        not duplicate prior phase outputs. ``self.state`` is left as-is
        (production callers create a fresh ``Orchestrator`` per run;
        tests may pre-seed state to skip earlier phases).
        """
        self.results = []
        with contextlib.ExitStack() as stack:
            ssh = stack.enter_context(SSHClient(self.ssh_host))
            # Phases interleave to honor state-handoff dependencies:
            #   - compose-restart consumes state.restart_services from gitea
            #   - kestra-secret-sync runs BEFORE kestra-register
            #   - woodpecker-apply consumes state.woodpecker_* from oauth
            #   - mirror-seed-rerun consumes state.fork_* from mirror-setup
            #   - mirror-finalize is best-effort wakeup after mirror-seed
            phases: list[Callable[[SSHClient], PhaseResult]] = [
                self._phase_infisical_bootstrap,
                self._phase_services_configure,
                self._phase_gitea_configure,
                self._phase_compose_restart,
                self._phase_kestra_secret_sync,
                self._phase_kestra_register,
                self._phase_seed,  # skipped in mirror mode
                self._phase_woodpecker_oauth,
                self._phase_woodpecker_apply,
                self._phase_mirror_setup,
                self._phase_mirror_seed_rerun,
                self._phase_mirror_finalize,
                self._phase_secret_sync_jupyter,
                self._phase_secret_sync_marimo,
                self._phase_secret_sync_code_server,
            ]
            for phase in phases:
                result = phase(ssh)
                self.results.append(result)
                if result.status == "failed":
                    break
        return OrchestratorResult(phases=tuple(self.results), state=self.state)

    # -----------------------------------------------------------------
    # Phase methods. Each calls into the existing migrated module's
    # public function with the right slice of state; failures are
    # caught and converted into PhaseResult instead of propagating
    # so the orchestrator decides whether to abort or continue.
    # -----------------------------------------------------------------

    def _phase_infisical_bootstrap(self, ssh: SSHClient) -> PhaseResult:
        """Push secrets to Infisical via :func:`infisical.compute_folders`
        + :meth:`InfisicalClient.bootstrap`. Reads
        ``self.config`` + ``self.bootstrap_env``; needs project_id +
        infisical_token from env (set up by the CLI handler)."""
        if not self.project_id or not self.infisical_token:
            return PhaseResult(
                name="infisical-bootstrap",
                status="skipped",
                detail="PROJECT_ID or INFISICAL_TOKEN missing",
            )
        try:
            client = _infisical.InfisicalClient(
                project_id=self.project_id,
                env=self.infisical_env,
                token=self.infisical_token,
                push_dir=Path("/tmp/infisical-push"),  # noqa: S108
            )
            folders = _infisical.compute_folders(self.config, self.bootstrap_env)
            result = client.bootstrap(folders)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="infisical-bootstrap",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="infisical-bootstrap",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        if result.failed > 0:
            return PhaseResult(
                name="infisical-bootstrap",
                status="partial",
                detail=f"built={result.folders_built} pushed={result.pushed} failed={result.failed}",
            )
        return PhaseResult(
            name="infisical-bootstrap",
            status="ok",
            detail=f"built={result.folders_built} pushed={result.pushed}",
        )

    def _phase_services_configure(self, ssh: SSHClient) -> PhaseResult:
        """REST + exec admin-setup hooks via
        :func:`services.run_admin_setups`."""
        try:
            result = _services.run_admin_setups(
                self.config,
                self.bootstrap_env,
                self.enabled_services,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="services-configure",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="services-configure",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        if result.failed > 0:
            return PhaseResult(
                name="services-configure",
                status="partial",
                detail=(
                    f"configured={result.configured} already-configured={result.already_configured} "
                    f"skipped-not-ready={result.skipped_not_ready} failed={result.failed}"
                ),
            )
        return PhaseResult(
            name="services-configure",
            status="ok",
            detail=(
                f"configured={result.configured} already-configured={result.already_configured} "
                f"skipped-not-ready={result.skipped_not_ready}"
            ),
        )

    def _phase_gitea_configure(self, ssh: SSHClient) -> PhaseResult:
        """Synchronous Gitea configure via :func:`gitea.run_configure_gitea`.
        Populates ``state.gitea_token`` + ``state.restart_services``."""
        if "gitea" not in self.enabled_services:
            return PhaseResult(name="gitea-configure", status="skipped", detail="gitea not enabled")
        if not self.config.gitea_admin_password:
            return PhaseResult(
                name="gitea-configure",
                status="partial",
                detail="GITEA_ADMIN_PASS missing — basic-auth would 401",
            )
        local_port = _allocate_free_port()
        try:
            with ssh.port_forward(local_port, "localhost", 3200) as port:
                result = _gitea.run_configure_gitea(
                    self.config,
                    base_url=f"http://localhost:{port}",
                    ssh=ssh,
                    admin_email=self.bootstrap_env.admin_email or "",
                    gitea_user_email=self.gitea_user_email,
                    gitea_user_password=self.gitea_user_password,
                    repo_name=self.repo_name,
                    gitea_repo_owner=self.gitea_repo_owner,
                    is_mirror_mode=bool(self.gh_mirror_repos),
                    enabled_services=self.enabled_services,
                )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="gitea-configure",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="gitea-configure",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        # Populate state — token may be None on partial mint failure.
        self.state.gitea_token = result.token
        self.state.restart_services = tuple(result.restart_services)
        if not result.is_success:
            return PhaseResult(
                name="gitea-configure",
                status="partial",
                detail="some sub-step failed (see stderr)",
            )
        return PhaseResult(name="gitea-configure", status="ok")

    def _phase_seed(self, ssh: SSHClient) -> PhaseResult:
        """Push examples/workspace-seeds/ to the workspace repo via
        :func:`seeder.run_seed_for_repo`. Needs ``state.gitea_token``.

        In mirror mode this phase MUST skip — seeding the read-only
        ``mirror-readonly-<repo>`` returns HTTP 423 (Gitea pull-mirror
        lock). Re-seeding against the user's fork happens later via
        ``_phase_mirror_seed_rerun``, after ``_phase_mirror_setup``
        populates ``state.fork_*``.
        """
        # Mirror-mode skip — without this gate mirror deploys would
        # 423 here even though the phase itself has no bug.
        if self.gh_mirror_repos:
            return PhaseResult(
                name="seed",
                status="skipped",
                detail="mirror mode — seed deferred to mirror-seed-rerun phase",
            )
        if not self.state.gitea_token:
            return PhaseResult(
                name="seed",
                status="skipped",
                detail="no gitea_token (gitea phase did not produce one)",
            )
        seeds_root = Path("examples/workspace-seeds")
        if not seeds_root.is_dir():
            return PhaseResult(
                name="seed",
                status="skipped",
                detail="examples/workspace-seeds/ missing",
            )
        try:
            result = _seeder.run_seed_for_repo(
                repo_owner=self.gitea_repo_owner,
                repo_name=self.repo_name,
                root=seeds_root,
                token=self.state.gitea_token,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="seed",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="seed",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        if result.failed > 0:
            if result.created + result.skipped == 0:
                return PhaseResult(
                    name="seed",
                    status="failed",
                    detail=f"created=0 skipped=0 failed={result.failed}",
                )
            return PhaseResult(
                name="seed",
                status="partial",
                detail=f"created={result.created} skipped={result.skipped} failed={result.failed}",
            )
        return PhaseResult(
            name="seed",
            status="ok",
            detail=f"created={result.created} skipped={result.skipped}",
        )

    def _phase_kestra_register(self, ssh: SSHClient) -> PhaseResult:
        """Register system.git-sync + system.flow-sync via
        :func:`kestra.run_register_system_flows`. Port-forwards to
        kestra's container (8085 host → 8080 inside)."""
        if "kestra" not in self.enabled_services:
            return PhaseResult(
                name="kestra-register", status="skipped", detail="kestra not enabled"
            )
        if not self.config.kestra_admin_password:
            return PhaseResult(
                name="kestra-register",
                status="partial",
                detail="KESTRA_PASS missing — basic-auth would 401",
            )
        admin_email = self.bootstrap_env.admin_email or ""
        if not admin_email:
            return PhaseResult(
                name="kestra-register",
                status="partial",
                detail="ADMIN_EMAIL missing",
            )
        local_port = _allocate_free_port()
        try:
            with ssh.port_forward(local_port, "localhost", 8085) as port:
                result = _kestra.run_register_system_flows(
                    self.config,
                    base_url=f"http://localhost:{port}",
                    repo_owner=self.gitea_repo_owner,
                    repo_name=self.repo_name,
                    branch=self.workspace_branch,
                    admin_email=admin_email,
                )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="kestra-register",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="kestra-register",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        if not result.is_success:
            return PhaseResult(
                name="kestra-register",
                status="partial",
                detail=f"execution={result.execution_state or 'skipped'}",
            )
        return PhaseResult(
            name="kestra-register",
            status="ok",
            detail=f"flows={len(result.flows)} execution={result.execution_state or 'skipped'}",
        )

    def _phase_woodpecker_oauth(self, ssh: SSHClient) -> PhaseResult:
        """Provision Woodpecker OAuth via
        :func:`gitea.run_woodpecker_oauth_setup`. Populates
        ``state.woodpecker_client_id`` + ``state.woodpecker_client_secret``."""
        if "woodpecker" not in self.enabled_services:
            return PhaseResult(
                name="woodpecker-oauth", status="skipped", detail="woodpecker not enabled"
            )
        if not self.state.gitea_token:
            return PhaseResult(
                name="woodpecker-oauth",
                status="skipped",
                detail="no gitea_token from prior phase",
            )
        domain = self.bootstrap_env.domain or ""
        if not domain:
            return PhaseResult(
                name="woodpecker-oauth",
                status="partial",
                detail="DOMAIN missing",
            )
        local_port = _allocate_free_port()
        try:
            with ssh.port_forward(local_port, "localhost", 3200) as port:
                result, error, rotation_started = _gitea.run_woodpecker_oauth_setup(
                    base_url=f"http://localhost:{port}",
                    domain=domain,
                    gitea_token=self.state.gitea_token,
                    admin_username=self.config.admin_username or "admin",
                    subdomain_separator=self.bootstrap_env.subdomain_separator,
                )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="woodpecker-oauth",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except _gitea.GiteaError as exc:
            return PhaseResult(
                name="woodpecker-oauth",
                status="failed",
                detail=str(exc),
            )
        except Exception as exc:
            return PhaseResult(
                name="woodpecker-oauth",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        if result is None:
            # Half-completed rotation = abort (delete invalidated old creds).
            if rotation_started:
                return PhaseResult(
                    name="woodpecker-oauth",
                    status="failed",
                    detail=f"rotation half-complete: {error}",
                )
            return PhaseResult(
                name="woodpecker-oauth",
                status="partial",
                detail=error or "create failed (no rotation started)",
            )
        self.state.woodpecker_client_id = result.client_id
        self.state.woodpecker_client_secret = result.client_secret
        return PhaseResult(name="woodpecker-oauth", status="ok", detail="created")

    def _phase_mirror_setup(self, ssh: SSHClient) -> PhaseResult:
        """Mirror-mode provisioning via :func:`gitea.run_mirror_setup`.
        Populates ``state.fork_name`` + ``state.fork_owner`` if a fork
        was created. Skipped when no GH_MIRROR_REPOS configured."""
        if not self.gh_mirror_repos:
            return PhaseResult(
                name="mirror-setup", status="skipped", detail="no mirrors configured"
            )
        if not self.state.gitea_token:
            return PhaseResult(
                name="mirror-setup",
                status="skipped",
                detail="no gitea_token from prior phase",
            )
        if not self.gh_mirror_token:
            return PhaseResult(
                name="mirror-setup",
                status="partial",
                detail="GH_MIRROR_TOKEN missing",
            )
        if self.gitea_user_username and not self.config.gitea_admin_password:
            return PhaseResult(
                name="mirror-setup",
                status="partial",
                detail="GITEA_ADMIN_PASS required for fork-mode mirror",
            )
        local_port = _allocate_free_port()
        try:
            with ssh.port_forward(local_port, "localhost", 3200) as port:
                result = _gitea.run_mirror_setup(
                    base_url=f"http://localhost:{port}",
                    admin_username=self.config.admin_username or "admin",
                    admin_password=self.config.gitea_admin_password or "",
                    gitea_token=self.state.gitea_token,
                    gitea_user_username=self.gitea_user_username,
                    gh_mirror_repos=self.gh_mirror_repos,
                    gh_mirror_token=self.gh_mirror_token,
                    workspace_branch=self.workspace_branch,
                )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="mirror-setup",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except _gitea.GiteaError as exc:
            return PhaseResult(name="mirror-setup", status="failed", detail=str(exc))
        except Exception as exc:
            return PhaseResult(
                name="mirror-setup",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        if result.fork is not None and result.fork.status in ("created", "already_exists"):
            self.state.fork_name = result.fork.name
            self.state.fork_owner = result.fork.owner
        if not result.is_success:
            return PhaseResult(
                name="mirror-setup",
                status="partial",
                detail=f"mirrors={len(result.mirrors)} (some failed)",
            )
        return PhaseResult(
            name="mirror-setup", status="ok", detail=f"mirrors={len(result.mirrors)}"
        )

    def _phase_secret_sync(self, ssh: SSHClient, stack: str) -> PhaseResult:
        """Common impl for jupyter + marimo secret-sync."""
        if stack not in self.enabled_services:
            return PhaseResult(
                name=f"secret-sync-{stack}",
                status="skipped",
                detail=f"{stack} not enabled",
            )
        if not self.project_id or not self.infisical_token:
            return PhaseResult(
                name=f"secret-sync-{stack}",
                status="partial",
                detail="PROJECT_ID or INFISICAL_TOKEN missing",
            )
        target = _secret_sync.StackTarget(name=stack)
        try:
            result = _secret_sync.run_sync_for_stack(
                target,
                project_id=self.project_id,
                infisical_token=self.infisical_token,
                infisical_env=self.infisical_env,
                gitea_token=self.state.gitea_token or "",
                host=self.ssh_host,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name=f"secret-sync-{stack}",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name=f"secret-sync-{stack}",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        if not result.wrote and result.failed_folders == 0 and result.succeeded_folders == 0:
            return PhaseResult(
                name=f"secret-sync-{stack}",
                status="partial",
                detail="no usable result (see prior warnings)",
            )
        if result.wrote and result.failed_folders > 0:
            return PhaseResult(
                name=f"secret-sync-{stack}",
                status="partial",
                detail=f"pushed={result.pushed} failed_folders={result.failed_folders}",
            )
        if not result.wrote:
            return PhaseResult(
                name=f"secret-sync-{stack}",
                status="ok",
                detail="kept previous (outage gate)",
            )
        return PhaseResult(
            name=f"secret-sync-{stack}", status="ok", detail=f"pushed={result.pushed}"
        )

    def _phase_secret_sync_jupyter(self, ssh: SSHClient) -> PhaseResult:
        return self._phase_secret_sync(ssh, "jupyter")

    def _phase_secret_sync_marimo(self, ssh: SSHClient) -> PhaseResult:
        return self._phase_secret_sync(ssh, "marimo")

    def _phase_secret_sync_code_server(self, ssh: SSHClient) -> PhaseResult:
        return self._phase_secret_sync(ssh, "code-server")

    # ---------------------------------------------------------------------
    # Pre-bootstrap pipeline phases.
    #
    # These run BEFORE the infisical-bootstrap phase. Each wraps an
    # already-implemented module's public function and converts its
    # result/exception into a PhaseResult — a unified place to chain
    # them with state-handoff.
    #
    # The pre-bootstrap phases come in two clusters:
    #
    # 1. **Local-only** (don't need an SSHClient): service-env render,
    #    firewall override generation.
    #
    # 2. **Server-side** (use the wrapped helper's own ssh.run_script
    #    plumbing): stack-sync, compose up, infisical provision-admin.
    #    These don't need the orchestrator's shared SSHClient because
    #    their helper functions invoke ``ssh <host>`` via subprocess
    #    independently — they accept ``host=self.ssh_host`` so a
    #    non-default ``SSH_HOST_ALIAS`` reaches every phase uniformly
    #    (caught in PR #532 R2 #2).
    #
    # Both clusters' phase methods take no parameters (no shared
    # SSHClient, no ssh arg) — the run_pre_bootstrap loop calls them as
    # ``phase()``. The previous design passed a None-cast-as-SSHClient
    # for signature consistency with the existing phases; that was a
    # runtime-contract footgun and was removed in PR #532 R1 #2.
    # ---------------------------------------------------------------------

    def _phase_service_env(self) -> PhaseResult:
        """Render per-service ``stacks/<svc>/.env`` files locally + (when
        Gitea is enabled) append the Gitea workspace block to the
        Gitea-integrated stacks.

        Local-only — no SSH context needed. Pre-bootstrap phases drop
        the ``ssh`` arg from their signature (caught in PR #532 R1 #2:
        passing a None-cast-as-SSHClient is a runtime-contract footgun
        even if the current body uses ``del ssh``).
        """
        try:
            result = _service_env.render_all_env_files(
                self.config,
                self.bootstrap_env,
                self.enabled_services,
                stacks_dir=self.project_root / "stacks",
            )
        except _service_env.ServiceEnvError as exc:
            # Hard-fail conditions (e.g. SFTPGo with empty password) —
            # the legacy bash exits 1 with a red banner; the Python
            # equivalent raises so we surface it here.
            return PhaseResult(
                name="service-env",
                status="failed",
                detail=str(exc),
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="service-env",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="service-env",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )

        # Optionally append the Gitea workspace block. Mirrors the CLI
        # handler's `workspace_coords_complete` check exactly — the 5
        # input coords (repo_owner, repo_name, gitea_user_username,
        # gitea_user_password, gitea_user_email) must all be non-empty.
        # The remaining GiteaWorkspaceConfig fields (gitea_repo_url,
        # git_author_name) are derived from these inputs, so they don't
        # need a separate guard. Otherwise we'd write a broken Gitea
        # block (empty PASSWORD/AUTHOR fields) that's harder to diagnose
        # than a missing block. Caught in PR #532 R1 #3, comment
        # corrected in R4 #2.
        gitea_appended_count = 0
        gitea_user_email_value = self.gitea_user_email or self.bootstrap_env.gitea_user_email
        # Single source of truth: self.gitea_repo_owner (required
        # constructor field). The bootstrap_env mirror exists for the
        # in-script seeder/secret-sync path but should NOT diverge from
        # the orchestrator's own field. Caught in PR #532 R3 #1.
        workspace_coords_complete = all(
            (
                self.gitea_repo_owner,
                self.repo_name,
                self.gitea_user_username,
                self.gitea_user_password,
                gitea_user_email_value,
            ),
        )
        if "gitea" in self.enabled_services and workspace_coords_complete:
            gitea_repo_url = f"http://gitea:3000/{self.gitea_repo_owner}/{self.repo_name}.git"
            try:
                cfg = _service_env.GiteaWorkspaceConfig(
                    gitea_repo_url=gitea_repo_url,
                    gitea_username=self.gitea_user_username or "",
                    gitea_password=self.gitea_user_password or "",
                    git_author_name=self.gitea_user_username or "",
                    git_author_email=gitea_user_email_value or "",
                    repo_name=self.repo_name,
                    workspace_branch=self.workspace_branch,
                )
                appended = _service_env.append_gitea_workspace_block(
                    cfg,
                    self.enabled_services,
                    stacks_dir=self.project_root / "stacks",
                )
                gitea_appended_count = len(appended)
            except OSError as exc:
                return PhaseResult(
                    name="service-env",
                    status="partial",
                    detail=(
                        f"rendered={result.rendered} but gitea-block append "
                        f"failed: {type(exc).__name__}"
                    ),
                )

        if result.failed > 0:
            if result.rendered == 0:
                return PhaseResult(
                    name="service-env",
                    status="failed",
                    detail=f"rendered=0 failed={result.failed}",
                )
            return PhaseResult(
                name="service-env",
                status="partial",
                detail=(
                    f"rendered={result.rendered} skipped={result.skipped} "
                    f"failed={result.failed} gitea_appended={gitea_appended_count}"
                ),
            )
        return PhaseResult(
            name="service-env",
            status="ok",
            detail=(
                f"rendered={result.rendered} skipped={result.skipped} "
                f"gitea_appended={gitea_appended_count}"
            ),
        )

    def _phase_stack_sync(self) -> PhaseResult:
        """Rsync each enabled stack to ``/opt/docker-server/stacks/<svc>/``
        and clean up disabled stack directories on the server.

        Uses ``run_stack_sync`` which manages its own rsync subprocess
        + cleanup ssh.run_script invocation independently — the
        orchestrator's shared SSHClient is not consumed here, so the
        signature drops the ``ssh`` arg.
        """
        try:
            result = _stack_sync.run_stack_sync(
                self.project_root / "stacks",
                self.enabled_services,
                host=self.ssh_host,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="stack-sync",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="stack-sync",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        cleanup_failed = result.cleanup.failed if result.cleanup is not None else 0
        cleanup_removed = result.cleanup.removed if result.cleanup is not None else 0
        cleanup_missing_or_unparseable = result.cleanup is None
        if cleanup_missing_or_unparseable:
            # No parseable RESULT from the cleanup script — same hard-fail
            # contract as the per-CLI handler maps to rc=2.
            return PhaseResult(
                name="stack-sync",
                status="failed",
                detail=(
                    f"rsync_synced={result.synced} rsync_failed={result.failed_rsync} "
                    "cleanup script produced no parseable RESULT"
                ),
            )
        if result.failed_rsync > 0 or cleanup_failed > 0:
            return PhaseResult(
                name="stack-sync",
                status="partial",
                detail=(
                    f"rsync_synced={result.synced} rsync_failed={result.failed_rsync} "
                    f"cleanup_removed={cleanup_removed} cleanup_failed={cleanup_failed}"
                ),
            )
        return PhaseResult(
            name="stack-sync",
            status="ok",
            detail=(f"rsync_synced={result.synced} cleanup_removed={cleanup_removed}"),
        )

    def _phase_firewall_configure(self) -> PhaseResult:
        """Generate per-service ``docker-compose.firewall.yml`` overrides
        and (when RedPanda has firewall ports) the dual-listener override
        + substituted ``redpanda-firewall.yaml``.

        Local-only — the rendered files are written to ``stacks/<svc>/``
        on the runner. The subsequent server-side scp + orphan-cleanup
        loop runs as part of the post-bootstrap pipeline.
        """
        try:
            gen, write = _firewall.configure(
                firewall_json=self.firewall_json,
                stacks_dir=self.project_root,
                domain=self.domain,
            )
        except (ValueError, FileNotFoundError) as exc:
            return PhaseResult(
                name="firewall-configure",
                status="failed",
                detail=str(exc),
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="firewall-configure",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="firewall-configure",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )

        if gen.zero_entry:
            if write.failed:
                return PhaseResult(
                    name="firewall-configure",
                    status="partial",
                    detail=(
                        f"zero-entry mode but stale-cleanup had {len(write.failed)} failure(s)"
                    ),
                )
            return PhaseResult(
                name="firewall-configure",
                status="ok",
                detail="zero-entry (no rules)",
            )

        if gen.skipped:
            # Per #531 R7 #4: skipped services mean Tofu requested a rule
            # but compose.yml was unparseable → existing override stays
            # in place but state may be inconsistent with Tofu.
            return PhaseResult(
                name="firewall-configure",
                status="partial",
                detail=(
                    f"rendered={len(gen.compiled)} skipped={len(gen.skipped)} "
                    f"redpanda={'yes' if gen.redpanda else 'no'}"
                ),
            )
        if write.failed:
            return PhaseResult(
                name="firewall-configure",
                status="partial",
                detail=(
                    f"rendered={len(gen.compiled)} written={len(write.written)} "
                    f"failed={len(write.failed)}"
                ),
            )
        return PhaseResult(
            name="firewall-configure",
            status="ok",
            detail=(f"rendered={len(gen.compiled)} redpanda={'yes' if gen.redpanda else 'no'}"),
        )

    def _phase_compose_up(self) -> PhaseResult:
        """Start containers in parallel via
        :func:`compose_runner.run_compose_up`.

        ``run_compose_up`` invokes ``ssh <host> 'bash -s'`` via
        subprocess internally, where ``<host>`` is ``self.ssh_host``
        (default ``"nexus"``, override via ``SSH_HOST_ALIAS``). The
        orchestrator's shared SSHClient is not consumed here, so the
        signature drops the ``ssh`` arg. Docstring updated in PR #532
        R7 #1 — was 'ssh nexus' before R2 #2 plumbed host through.
        """
        try:
            result = _compose_runner.run_compose_up(
                self.enabled_services,
                host=self.ssh_host,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="compose-up",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="compose-up",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        if result.failed > 0:
            return PhaseResult(
                name="compose-up",
                status="partial",
                detail=f"started={result.started} failed={result.failed}",
            )
        return PhaseResult(
            name="compose-up",
            status="ok",
            detail=f"started={result.started}",
        )

    def _phase_infisical_provision(self) -> PhaseResult:
        """Bootstrap the Infisical admin + workspace.

        On success, populates BOTH the state mirrors
        (``self.state.infisical_token`` + ``self.state.project_id``,
        for the CLI's stdout emission) AND the orchestrator's own
        fields (``self.infisical_token`` + ``self.project_id``, which
        the post-bootstrap phases gate on). On a partial/failed
        outcome, the fields stay None — ``run_pre_bootstrap`` zeros
        BOTH surfaces at start so a re-run can't carry stale creds
        (PR #532 R1 #4 + R2 #3). Note: there is NO read-fallback to
        constructor-provided creds — callers wanting to bypass this
        phase should use ``run_all`` directly with ``infisical_token``
        + ``project_id`` set in the constructor (docstring corrected
        in PR #532 R7 #2; previously claimed a fallback that didn't
        exist).

        ``provision_admin`` manages its own ssh.run_script call —
        no shared SSHClient context, so the signature drops ``ssh``.
        ``host=self.ssh_host`` is passed through (PR #532 R2 #2).
        """
        admin_email = self.bootstrap_env.admin_email or ""
        admin_password = self.admin_password_infisical or ""
        if not admin_email or not admin_password:
            return PhaseResult(
                name="infisical-provision",
                status="skipped",
                detail="ADMIN_EMAIL or admin_password_infisical missing",
            )
        try:
            result = _infisical.provision_admin(
                admin_email=admin_email,
                admin_password=admin_password,
                host=self.ssh_host,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="infisical-provision",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="infisical-provision",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )

        if not result.has_credentials:
            # Same contract as #530 R2 #4: rc=1 (soft-fail) when the
            # provision didn't produce usable credentials. Pre-bootstrap
            # caller should treat this as 'continue without secret push'.
            return PhaseResult(
                name="infisical-provision",
                status="partial",
                detail=f"status={result.status} (no usable credentials)",
            )

        # Populate state for downstream phases.
        self.state.infisical_token = result.token
        self.state.project_id = result.project_id
        # Also populate the orchestrator's input fields so the existing
        # _phase_infisical_bootstrap (which reads self.project_id /
        # self.infisical_token) finds the values.
        self.project_id = result.project_id
        self.infisical_token = result.token

        return PhaseResult(
            name="infisical-provision",
            status="ok",
            detail=f"status={result.status}",
        )

    # ---------------------------------------------------------------------
    # Pre-bootstrap pipeline extensions.
    #
    # Three phases run during ``run_pre_bootstrap``:
    #
    # 1. _phase_workspace_coords — derives REPO_NAME / GITEA_REPO_OWNER
    #    / WORKSPACE_BRANCH etc. from raw env via workspace_coords.derive,
    #    dual-writes to state + self.field + bootstrap_env (same pattern
    #    as _phase_infisical_provision).
    # 2. _phase_firewall_sync — server-side cleanup of stale firewall
    #    overrides (rsync didn't --delete) + RedPanda config copy +
    #    chown 101:101 / chmod 777 fallback.
    # 3. _phase_global_env — writes /opt/docker-server/stacks/.env on
    #    the server with DOMAIN + ADMIN_EMAIL + image versions. Other
    #    services source this via compose's `env_file: ../../.env`.
    # ---------------------------------------------------------------------

    def _phase_workspace_coords(self) -> PhaseResult:
        """Derive workspace-repo coordinates and dual-write them.

        Calls :func:`workspace_coords.derive` with raw constructor
        inputs, then writes the 8 derived fields to BOTH:

        - ``self.state.*``  — for the CLI's stdout emission
        - ``self.field``    — for downstream phases that gate on the
          orchestrator field (gitea / seed / kestra / woodpecker / etc.)
        - ``self.bootstrap_env.gitea_user_email`` — synced so the
          downstream Infisical-bootstrap secret push uses the same
          user-email value the workspace block was rendered against.

        Mirrors the pattern from ``_phase_infisical_provision``: state
        + self + bootstrap_env all see the same value, so a single full
        run_all + run_pre_bootstrap pipeline doesn't need any external
        eval-handoff.

        The GitHub API call (default-branch detection) only fires in
        mirror mode when ``GH_MIRROR_TOKEN`` is set; gracefully falls
        back to ``"main"`` on any error path.
        """
        try:
            inputs = _workspace_coords.WorkspaceInputs(
                domain=self.domain or self.bootstrap_env.domain or "",
                admin_username=self.admin_username or self.config.admin_username or "",
                admin_email=self.bootstrap_env.admin_email or "",
                gitea_admin_pass=self.gitea_admin_pass or self.config.gitea_admin_password,
                gitea_user_email=self.gitea_user_email,
                gitea_user_pass=self.gitea_user_password,
                gh_mirror_repos=",".join(self.gh_mirror_repos) if self.gh_mirror_repos else None,
                gh_mirror_token=self.gh_mirror_token,
            )
            coords = _workspace_coords.derive(inputs)
        except Exception as exc:
            return PhaseResult(
                name="workspace-coords",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )

        # Dual-write: state mirrors (for stdout emission to surviving
        # bash) AND orchestrator constructor fields (for downstream
        # phases that gate on self.repo_name / self.gitea_repo_owner /
        # self.workspace_branch / self.gitea_user_*).
        self.state.repo_name = coords.repo_name
        self.state.gitea_repo_owner = coords.gitea_repo_owner
        self.state.gitea_repo_url = coords.gitea_repo_url
        self.state.workspace_branch = coords.workspace_branch
        self.state.gitea_git_user = coords.gitea_git_user
        self.state.gitea_git_pass = coords.gitea_git_pass
        self.state.git_author = coords.git_author
        self.state.git_email = coords.git_email
        self.repo_name = coords.repo_name
        self.gitea_repo_owner = coords.gitea_repo_owner
        self.workspace_branch = coords.workspace_branch
        # PR #533 R1 #3: also dual-write the user-identity constructor
        # fields, since _phase_service_env's workspace-block-append
        # guard reads self.gitea_user_username / _password / _email.
        # In admin-fallback mode (no GITEA_USER_EMAIL / _PASS env), the
        # legacy bash filled these from admin coords; the orchestrator
        # must replicate that behavior so the workspace block IS
        # appended. Existing constructor values win — tests can
        # pre-seed alternative identities.
        self.gitea_user_username = self.gitea_user_username or coords.gitea_git_user or None
        self.gitea_user_password = self.gitea_user_password or coords.gitea_git_pass or None
        self.gitea_user_email = self.gitea_user_email or coords.git_email or None
        # bootstrap_env mirrors — synced so the downstream Infisical-
        # bootstrap secret push uses the same user identity the
        # workspace block was rendered against. BootstrapEnv is frozen
        # (deliberate — it's an input snapshot for compute_folders),
        # so we use dataclasses.replace to produce a new instance with
        # the workspace-coords fields filled in. Existing non-empty
        # fields take precedence: tests / callers that pre-populate
        # bootstrap_env can override the derived values.
        from dataclasses import replace as _dc_replace

        self.bootstrap_env = _dc_replace(
            self.bootstrap_env,
            gitea_user_email=self.bootstrap_env.gitea_user_email or coords.git_email or None,
            gitea_user_username=(
                self.bootstrap_env.gitea_user_username or coords.gitea_git_user or None
            ),
            gitea_repo_owner=(
                self.bootstrap_env.gitea_repo_owner or coords.gitea_repo_owner or None
            ),
            repo_name=self.bootstrap_env.repo_name or coords.repo_name or None,
        )

        return PhaseResult(
            name="workspace-coords",
            status="ok",
            detail=(
                f"repo={coords.gitea_repo_owner}/{coords.repo_name} "
                f"branch={coords.workspace_branch}"
            ),
        )

    def _phase_firewall_sync(self) -> PhaseResult:
        """Server-side cleanup of stale firewall overrides + RedPanda
        config copy.

        Three sub-steps, each fail-fast on transport error:

        1. **Orphan-cleanup**: list ``stacks/<svc>/docker-compose.firewall.yml``
           files locally + on the server; remove the remote ones that
           aren't in the local set. Stack-sync's rsync runs without
           ``--delete``, so without this step a removed firewall rule
           leaves a stale override on the server that compose-up
           layers in, leaking the host port.

        2. **RedPanda config copy**: when redpanda is enabled, scp
           the (possibly firewall-substituted) ``redpanda.yaml`` to
           ``/opt/.../redpanda/config/``. ``chown -R 101:101`` (RedPanda's
           user) with ``chmod -R 777`` fallback.

        3. **Stale RedPanda firewall yaml removal**: if the local
           ``redpanda-firewall.yaml`` is absent (Python firewall
           configure removed it), remove the server-side copy too —
           via ``sudo rm -f`` (RedPanda chowned the dir to 101:101 in
           a prior firewall-on deploy, the nexus user can't unlink it
           without sudo).

        All failures here are SAFETY-critical (host port could stay
        exposed despite Tofu closing it), so this phase only emits
        ``status='ok'`` or ``status='failed'`` — never ``partial``.
        """
        if not self.project_root or not self.project_root.is_dir():
            return PhaseResult(
                name="firewall-sync",
                status="failed",
                detail=f"project_root {self.project_root} is not a directory",
            )

        stacks_dir_local = self.project_root / "stacks"
        # PR #533 R1 #4 — destructive-footgun guard. Without this check,
        # a missing local stacks/ dir would yield empty Path.glob and we'd
        # treat EVERY remote firewall override as an orphan and rm them.
        # That's catastrophic if project_root is mis-set or the checkout
        # is incomplete. Fail fast instead.
        if not stacks_dir_local.is_dir():
            return PhaseResult(
                name="firewall-sync",
                status="failed",
                detail=(
                    f"local stacks dir {stacks_dir_local} is missing — "
                    "refusing to compute orphan list (would rm every remote firewall override)"
                ),
            )
        try:
            # Step 1: orphan cleanup
            local_overrides = sorted(
                str(p.relative_to(stacks_dir_local))
                for p in stacks_dir_local.glob("*/docker-compose.firewall.yml")
            )
            # PR #533 R4 #2 + R8 #1: use `find` (not `ls | sort || true`).
            # `find -name … -printf '%P\n'` returns 0 on the legitimate
            # "no matches" case (empty stdout) AND propagates a non-
            # zero rc on real errors (unreadable subdir, etc.). The
            # `set -euo pipefail` ensures `find` failures inside the
            # `find | sort` pipeline aren't masked by `sort`'s exit
            # code. cd is bare so a missing /opt/…/stacks fails fast
            # → CalledProcessError → status='failed'. No `|| true`
            # anywhere — every error path now propagates.
            remote_listing = _remote.ssh_run_script(
                f"set -euo pipefail\n"
                f"cd {_REMOTE_STACKS_DIR}\n"
                "find . -mindepth 2 -maxdepth 2 -name docker-compose.firewall.yml "
                "-type f -printf '%P\\n' | sort",
                host=self.ssh_host,
                check=True,
            )
            remote_overrides = sorted(
                line.strip() for line in remote_listing.stdout.splitlines() if line.strip()
            )
            orphans = [r for r in remote_overrides if r not in local_overrides]
            if orphans:
                # PR #533 R2 #1: fail-fast on per-orphan rm failure. Without
                # this, a permission-denied (or any non-zero) rm in the
                # middle of the loop would be masked by a later success and
                # the script would exit 0 — phase reports ok even though
                # stale firewall overrides remain on the server, leaving
                # host ports exposed despite Tofu closing them. set -e
                # propagates the first failure as the script's rc; check=True
                # then converts it to CalledProcessError → status='failed'.
                rm_script = "set -e\n" + "\n".join(
                    f"rm -f {_REMOTE_STACKS_DIR}/{shlex.quote(orphan)}" for orphan in orphans
                )
                _remote.ssh_run_script(rm_script, host=self.ssh_host, check=True)

            # Step 2: RedPanda config copy (when enabled)
            redpanda_copied = False
            if "redpanda" in self.enabled_services:
                redpanda_local = stacks_dir_local / "redpanda" / "config"
                if not redpanda_local.is_dir():
                    return PhaseResult(
                        name="firewall-sync",
                        status="failed",
                        detail=f"redpanda config dir {redpanda_local} missing locally",
                    )
                # Use redpanda-firewall.yaml if it exists locally, else redpanda.yaml.
                rp_firewall_yaml = redpanda_local / "redpanda-firewall.yaml"
                rp_normal_yaml = redpanda_local / "redpanda.yaml"
                source = rp_firewall_yaml if rp_firewall_yaml.is_file() else rp_normal_yaml
                if not source.is_file():
                    return PhaseResult(
                        name="firewall-sync",
                        status="failed",
                        detail=f"neither redpanda-firewall.yaml nor redpanda.yaml exists in {redpanda_local}",
                    )
                # mkdir, scp, then chown 101:101 with chmod 777 fallback.
                _remote.ssh_run_script(
                    f"mkdir -p {_REMOTE_STACKS_DIR}/redpanda/config",
                    host=self.ssh_host,
                    check=True,
                )
                subprocess.run(
                    [
                        "scp",
                        "-q",
                        str(source),
                        f"{self.ssh_host}:{_REMOTE_STACKS_DIR}/redpanda/config/redpanda.yaml",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                # Remove old root redpanda.yaml from previous deploys.
                _remote.ssh_run_script(
                    f"rm -f {_REMOTE_STACKS_DIR}/redpanda/redpanda.yaml || true",
                    host=self.ssh_host,
                    check=False,
                )
                # chown 101:101 (RedPanda's container user) on the
                # config dir so the rootless container can read it.
                # Fall back to chmod 777 when chown fails — typically
                # because uid 101 doesn't exist on the host as a real
                # user (some minimal images / FS layouts disallow
                # chown to a numeric uid that's not in /etc/passwd).
                # Both paths use sudo: the nexus user can't
                # chown/chmod files owned by 101:101 from a previous
                # firewall-on deploy without escalation. PR #533 R4 #3
                # corrected the comment — was: "sudo isn't available"
                # which contradicted the still-sudo'd fallback.
                chown_script = (
                    f"sudo chown -R 101:101 {_REMOTE_STACKS_DIR}/redpanda/config "
                    f"|| sudo chmod -R 777 {_REMOTE_STACKS_DIR}/redpanda/config"
                )
                _remote.ssh_run_script(chown_script, host=self.ssh_host, check=True)
                redpanda_copied = True

            # Step 3: stale RedPanda firewall yaml removal
            if (
                "redpanda" in self.enabled_services
                and not (
                    stacks_dir_local / "redpanda" / "config" / "redpanda-firewall.yaml"
                ).is_file()
            ):
                _remote.ssh_run_script(
                    f"sudo rm -f {_REMOTE_STACKS_DIR}/redpanda/config/redpanda-firewall.yaml",
                    host=self.ssh_host,
                    check=True,
                )

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="firewall-sync",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="firewall-sync",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )

        detail_parts = [f"orphans_removed={len(orphans)}"]
        if redpanda_copied:
            detail_parts.append("redpanda=copied")
        return PhaseResult(
            name="firewall-sync",
            status="ok",
            detail=" ".join(detail_parts),
        )

    def _phase_global_env(self) -> PhaseResult:
        """Write the global ``/opt/docker-server/stacks/.env`` on the server.

        Contains DOMAIN + ADMIN_EMAIL + ADMIN_USERNAME + USER_EMAIL + the
        IMAGE_VERSIONS_JSON map (parsed and emitted as ``IMAGE_<NAME>=<value>``
        lines: dashes → underscores, uppercase, ``IMAGE_`` prefix).

        Compose stacks reference this via ``env_file: ../../.env`` so a
        single update propagates to all 40+ services without per-stack
        edits.

        Runs AFTER stack-sync (which already mkdir -p's the remote
        stacks dir) so we don't need an extra ssh round-trip.
        """
        import json as _json

        try:
            image_versions = _json.loads(self.image_versions_json or "{}")
            if not isinstance(image_versions, dict):
                image_versions = {}
        except _json.JSONDecodeError as exc:
            return PhaseResult(
                name="global-env",
                status="failed",
                detail=f"image_versions_json malformed: {type(exc).__name__}",
            )

        # PR #533 R3 #2: validate every value before writing. The
        # global .env is consumed by compose's ``env_file:``
        # directive (literal-string semantics; quoted values would
        # surface as literal characters in the rendered service
        # env). The safe intersection is "values without shell
        # metacharacters". Reject up-front instead of trying to
        # escape — image versions and emails legitimately need
        # alphanum + ``.-_:/@+`` only.
        shell_unsafe = re.compile(r"[\s$`\\();&|<>!?*\[\]{}\"'\n\r]")

        def _validate_value(label: str, value: str) -> str | None:
            """Return error string if value is shell-unsafe, else None."""
            if shell_unsafe.search(value):
                return f"{label} contains shell-unsafe character(s); refusing to write .env"
            return None

        # PR #533 R5 #1: validate KEYS too. A malicious / invalid
        # image-versions key (e.g. one containing ';', whitespace, or
        # a newline) would survive normalization (the existing
        # ``replace("-","_").upper()`` only handles dashes), get
        # written as ``IMAGE_<bad-key>=<value>``, and either break
        # the env-file format outright OR become an injection vector
        # when the file is later sourced. Tofu emits image-versions
        # keys from image-versions.tfvars where contributors control
        # the names, so this is a defense-in-depth gate, not just
        # paranoia. The post-normalization name must be a valid
        # POSIX shell var name.
        valid_var_name = re.compile(r"^[A-Z_][A-Z0-9_]*$")

        admin_email_value = self.bootstrap_env.admin_email or ""
        admin_username_value = self.admin_username or self.config.admin_username or ""
        validations = [
            ("DOMAIN", self.domain),
            ("ADMIN_EMAIL", admin_email_value),
            ("ADMIN_USERNAME", admin_username_value),
            ("USER_EMAIL", self.user_email),
        ]
        for key, value in image_versions.items():
            normalized_key = "IMAGE_" + str(key).replace("-", "_").upper()
            if not valid_var_name.match(normalized_key):
                return PhaseResult(
                    name="global-env",
                    status="failed",
                    detail=(
                        f"image_versions key {key!r} normalizes to {normalized_key!r}, "
                        "which is not a valid POSIX shell variable name; refusing to write .env"
                    ),
                )
            validations.append((f"image_versions[{key}]", str(value)))
        for label, value in validations:
            err = _validate_value(label, value)
            if err is not None:
                return PhaseResult(
                    name="global-env",
                    status="failed",
                    detail=err,
                )

        lines = [
            "# Auto-generated global config - DO NOT EDIT",
            "# Managed by OpenTofu via image-versions.tfvars",
            "",
            "# Domain for service URLs",
            f"DOMAIN={self.domain}",
            "",
            "# Admin credentials",
            f"ADMIN_EMAIL={admin_email_value}",
            f"ADMIN_USERNAME={admin_username_value}",
            f"USER_EMAIL={self.user_email}",
            "",
            "# Docker image versions",
            "# Keys are transformed to environment variables by:",
            "#   - replacing '-' with '_'",
            "#   - converting to upper-case",
            "#   - prefixing with 'IMAGE_'",
        ]
        for key, value in image_versions.items():
            normalized = "IMAGE_" + str(key).replace("-", "_").upper()
            lines.append(f"{normalized}={value}")
        env_content = "\n".join(lines) + "\n"

        try:
            # PR #533 R2 #2: write env_content via ssh-stdin streaming
            # (NOT a heredoc). The previous heredoc-with-fixed-delimiter
            # approach was a heredoc-injection risk: any image-version
            # value or USER_EMAIL containing the literal string
            # "NEXUS_GLOBAL_ENV_EOF" on a line by itself would terminate
            # the heredoc early and the rest of env_content would be
            # interpreted as shell commands on the server. Streaming
            # via stdin removes the delimiter entirely — the ssh
            # command is just `cat > <path>`, env_content goes through
            # stdin where bash treats it as bytes, not script source.
            subprocess.run(
                ["ssh", self.ssh_host, f"cat > {_REMOTE_STACKS_DIR}/.env"],
                input=env_content,
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="global-env",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="global-env",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )

        return PhaseResult(
            name="global-env",
            status="ok",
            detail=f"images={len(image_versions)}",
        )

    # ---------------------------------------------------------------------
    # Post-bootstrap pipeline phases.
    #
    # Each runs during ``run_all`` after the bootstrap phases finish:
    #
    # 1. _phase_compose_restart  — ssh-loop for state.restart_services
    # 2. _phase_kestra_secret_sync — kestra readiness wait → secret-sync
    #                                CLI invoke → restart-readiness wait
    # 3. _phase_woodpecker_apply — write stacks/woodpecker/.env, rsync,
    #                              ssh docker compose up -d
    # 4. _phase_mirror_seed_rerun — re-seed the user's fork after
    #                               state.fork_* is populated
    # 5. _phase_mirror_finalize  — flow-sync re-trigger + git-restart
    #                              loop (combined; both best-effort)
    # ---------------------------------------------------------------------

    def _phase_compose_restart(self, ssh: SSHClient) -> PhaseResult:
        """Restart services in ``state.restart_services``.

        Populated by ``_phase_gitea_configure`` after the DB-password sync —
        services that integrate with Gitea need a restart to pick up the
        new GITEA_TOKEN they couldn't see at first compose-up.

        Skipped on empty list (no integrators enabled). Best-effort
        per-service: a single failed restart doesn't abort the deploy
        but is counted as failed in the result.
        """
        del ssh  # uses compose_restart's own ssh.run_script
        services = list(self.state.restart_services)
        if not services:
            return PhaseResult(
                name="compose-restart",
                status="skipped",
                detail="no services to restart",
            )
        try:
            result = _compose_restart.run_restart(services, host=self.ssh_host)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="compose-restart",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="compose-restart",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        if result.failed > 0:
            return PhaseResult(
                name="compose-restart",
                status="partial",
                detail=f"restarted={result.restarted} failed={result.failed}",
            )
        return PhaseResult(
            name="compose-restart",
            status="ok",
            detail=f"restarted={result.restarted}",
        )

    def _phase_kestra_secret_sync(self, ssh: SSHClient) -> PhaseResult:
        """Sync Infisical secrets + GITEA_TOKEN into Kestra's env.

        Three steps:

        1. Wait for Kestra to be ready (auth-aware probe via
           :meth:`KestraClient.wait_ready`). Budget: 480s (60x8s).
        2. Invoke the existing ``secret_sync.run_sync_for_stack``
           helper for the kestra stack — that helper handles the
           SECRET_<KEY>=<base64> append + force-recreate.
        3. Wait for Kestra to come back up after the force-recreate.
           Budget: 180s (60x3s; faster because warm cache).

        Skipped when kestra not enabled OR Infisical creds missing.
        Partial when EITHER wait_ready times out (we then skip
        run_sync_for_stack entirely — pushing secrets to a Kestra
        whose basic-auth layer isn't ready yet would 401) OR the
        sync produced any folder-fetch failure. Failed only on
        transport error. Docstring corrected in PR #533 R4 #1
        (was: "secret-sync still attempts" — not what the
        implementation does).
        """
        if "kestra" not in self.enabled_services:
            return PhaseResult(
                name="kestra-secret-sync",
                status="skipped",
                detail="kestra not enabled",
            )
        if not self.project_id or not self.infisical_token:
            return PhaseResult(
                name="kestra-secret-sync",
                status="skipped",
                detail="PROJECT_ID or INFISICAL_TOKEN missing",
            )
        if not self.config.kestra_admin_password:
            return PhaseResult(
                name="kestra-secret-sync",
                status="partial",
                detail="KESTRA_PASS missing — readiness probe would 401",
            )
        admin_email = self.bootstrap_env.admin_email or ""
        if not admin_email:
            return PhaseResult(
                name="kestra-secret-sync",
                status="partial",
                detail="ADMIN_EMAIL missing",
            )
        local_port = _allocate_free_port()
        try:
            with ssh.port_forward(local_port, "localhost", 8085) as port:
                client = _kestra.KestraClient(
                    base_url=f"http://localhost:{port}",
                    username=admin_email,
                    password=self.config.kestra_admin_password,
                )
                # Step 1: wait for Kestra to be ready. 480s = 60x8s budget.
                if not client.wait_ready(timeout_s=480.0, interval_s=8.0):
                    return PhaseResult(
                        name="kestra-secret-sync",
                        status="partial",
                        detail="kestra readiness probe timed out (480s)",
                    )

                # Step 2: invoke secret-sync helper (kestra stack).
                # The Kestra stack needs five overrides vs. the
                # Jupyter/Marimo defaults so the rendered SECRET_<key>
                # block lands where Kestra's EnvVarSecretProvider can
                # actually find it (Issue #543):
                #   - env_file_basename=".env" (not .infisical.env;
                #     Kestra's compose loads .env directly, no separate
                #     legacy file)
                #   - legacy_env_file_basename=None (the
                #     StackTarget default is ``.env``, intended as the
                #     migration-from-legacy strip target for the
                #     Jupyter/Marimo path that writes to
                #     ``.infisical.env``. For Kestra the SECRET block
                #     IS written to ``.env`` itself; without this
                #     None-override the remote script's legacy-strip
                #     step would sed-strip the just-written
                #     ``BEGIN/END nexus-secret-sync`` block out of
                #     the same ``.env`` and the mv would wipe its
                #     own output. ``None`` skips the legacy-strip
                #     branch entirely — kestra has no migration
                #     concern.)
                #   - key_prefix="SECRET_" (Kestra's
                #     ``{{ secret('GITEA_TOKEN') }}`` looks up env var
                #     ``SECRET_GITEA_TOKEN``)
                #   - use_base64_values=True (Kestra's
                #     EnvVarSecretProvider expects base64-encoded
                #     values for the SECRET_<key> form)
                #   - force_recreate=True (compose `up -d` alone
                #     wouldn't restart kestra to re-read .env;
                #     --force-recreate is the cheapest reload primitive)
                # Mirrors the construction in __main__._secret_sync.
                target = _secret_sync.StackTarget(
                    name="kestra",
                    key_prefix="SECRET_",
                    use_base64_values=True,
                    env_file_basename=".env",
                    legacy_env_file_basename=None,
                    force_recreate=True,
                )
                sync_result = _secret_sync.run_sync_for_stack(
                    target,
                    project_id=self.project_id,
                    infisical_token=self.infisical_token,
                    infisical_env=self.infisical_env,
                    gitea_token=self.state.gitea_token or "",
                    host=self.ssh_host,
                )

                # Step 3: wait for Kestra to come back up after force-
                # recreate. 180s = 60x3s budget (warm cache).
                if not client.wait_ready(timeout_s=180.0, interval_s=3.0):
                    return PhaseResult(
                        name="kestra-secret-sync",
                        status="partial",
                        detail="post-restart readiness timed out (180s)",
                    )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="kestra-secret-sync",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="kestra-secret-sync",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )

        if sync_result.wrote and sync_result.failed_folders > 0:
            return PhaseResult(
                name="kestra-secret-sync",
                status="partial",
                detail=(f"pushed={sync_result.pushed} failed_folders={sync_result.failed_folders}"),
            )
        if not sync_result.wrote:
            return PhaseResult(
                name="kestra-secret-sync",
                status="ok",
                detail="kept previous (outage gate)",
            )
        return PhaseResult(
            name="kestra-secret-sync",
            status="ok",
            detail=f"pushed={sync_result.pushed}",
        )

    def _phase_woodpecker_apply(self, ssh: SSHClient) -> PhaseResult:
        """Write the OAuth-populated stacks/woodpecker/.env, rsync to
        server, run ``docker compose up -d``.

        Reads ``state.woodpecker_client_id`` +
        ``state.woodpecker_client_secret`` populated by
        ``_phase_woodpecker_oauth``.

        Skipped when woodpecker not enabled OR OAuth phase didn't
        produce credentials. Best-effort: ``docker compose up -d``
        failure is ``partial`` (the ssh transport itself succeeded;
        the operator can investigate via container logs).
        """
        del ssh  # uses _remote helpers directly
        if "woodpecker" not in self.enabled_services:
            return PhaseResult(
                name="woodpecker-apply",
                status="skipped",
                detail="woodpecker not enabled",
            )
        client_id = self.state.woodpecker_client_id
        client_secret = self.state.woodpecker_client_secret
        if not client_id or not client_secret:
            return PhaseResult(
                name="woodpecker-apply",
                status="skipped",
                detail="woodpecker_client_id / woodpecker_client_secret not populated",
            )
        if not self.woodpecker_agent_secret:
            return PhaseResult(
                name="woodpecker-apply",
                status="partial",
                detail="WOODPECKER_AGENT_SECRET not set",
            )

        woodpecker_dir = self.project_root / "stacks" / "woodpecker"
        if not woodpecker_dir.is_dir():
            return PhaseResult(
                name="woodpecker-apply",
                status="failed",
                detail=f"{woodpecker_dir} missing — stack-sync should have placed it",
            )

        env_path = woodpecker_dir / ".env"
        env_content = (
            "# Auto-generated - DO NOT COMMIT\n"
            f"DOMAIN={self.domain or self.bootstrap_env.domain or ''}\n"
            f"WOODPECKER_AGENT_SECRET={self.woodpecker_agent_secret}\n"
            f"WOODPECKER_ADMIN={self.admin_username or self.config.admin_username or 'admin'}\n"
            f"WOODPECKER_GITEA_CLIENT={client_id}\n"
            f"WOODPECKER_GITEA_SECRET={client_secret}\n"
        )
        # PR #533 R7 #2: split rsync from docker-compose so the two
        # error paths produce actionable distinct details. Previously
        # both were 'transport (CalledProcessError)' which couldn't
        # tell an operator whether to investigate ssh connectivity
        # or container logs.
        try:
            env_path.write_text(env_content, encoding="utf-8")
        except OSError as exc:
            return PhaseResult(
                name="woodpecker-apply",
                status="failed",
                detail=f"local write ({type(exc).__name__})",
            )

        try:
            # Rsync the woodpecker dir (NOT just the .env — server may
            # need updated docker-compose.yml + any contributor edits
            # too). Same pattern as the legacy bash.
            _remote.rsync_to_remote(
                woodpecker_dir,
                f"{self.ssh_host}:{_REMOTE_STACKS_DIR}/woodpecker/",
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            # rsync transport — distinct from compose-up failure;
            # operator should check ssh connectivity / disk on the
            # server.
            return PhaseResult(
                name="woodpecker-apply",
                status="partial",
                detail=f"rsync transport ({type(exc).__name__})",
            )

        # docker compose up -d. PR #533 R3 #1: use compose's
        # ``--env-file`` flag instead of ``source`` to pick up
        # IMAGE_WOODPECKER_* image versions. Compose parses the
        # env-file with its own KEY=VALUE format (no shell
        # interpretation), so a malicious image-version value
        # containing ``$()`` / backticks / ``;`` / ``\n`` cannot
        # trigger remote command execution.
        up_script = (
            f"cd {_REMOTE_STACKS_DIR}/woodpecker "
            f"&& docker compose --env-file {_REMOTE_STACKS_DIR}/.env up -d"
        )
        try:
            _remote.ssh_run_script(up_script, host=self.ssh_host, check=True)
        except subprocess.CalledProcessError as exc:
            # docker compose returned non-zero — service-level failure
            # (image pull failed, container crashed at startup, port
            # collision, …). Forward the captured stdout to the
            # detail so operators see the compose error inline.
            stdout_excerpt = (exc.output or "").strip().splitlines()[-1:] if exc.output else []
            tail = stdout_excerpt[0] if stdout_excerpt else "no stdout captured"
            return PhaseResult(
                name="woodpecker-apply",
                status="partial",
                detail=f"docker compose up -d failed (rc={exc.returncode}): {tail[:120]}",
            )
        except subprocess.TimeoutExpired as exc:
            # Genuine ssh transport timeout — operator should
            # investigate connectivity, not container state.
            return PhaseResult(
                name="woodpecker-apply",
                status="partial",
                detail=f"ssh transport timeout ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="woodpecker-apply",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )

        return PhaseResult(
            name="woodpecker-apply",
            status="ok",
            detail="started with Gitea forge",
        )

    def _phase_mirror_seed_rerun(self, ssh: SSHClient) -> PhaseResult:
        """Re-seed examples/workspace-seeds/ against the user's fork.

        In mirror mode ``_phase_seed`` skipped; this phase runs after
        ``_phase_mirror_setup`` populates ``state.fork_name`` +
        ``state.fork_owner`` and re-uses the seeder helper against the
        fork.

        Skipped when not in mirror mode OR no fork was created.
        """
        del ssh  # seeder uses its own HTTP runner
        if not self.gh_mirror_repos:
            return PhaseResult(
                name="mirror-seed-rerun",
                status="skipped",
                detail="not mirror mode",
            )
        fork_name = self.state.fork_name
        fork_owner = self.state.fork_owner
        if not fork_name or not fork_owner:
            return PhaseResult(
                name="mirror-seed-rerun",
                status="skipped",
                detail="no fork populated by _phase_mirror_setup",
            )
        if not self.state.gitea_token:
            return PhaseResult(
                name="mirror-seed-rerun",
                status="skipped",
                detail="no gitea_token",
            )
        seeds_root = Path("examples/workspace-seeds")
        if not seeds_root.is_dir():
            return PhaseResult(
                name="mirror-seed-rerun",
                status="skipped",
                detail="examples/workspace-seeds/ missing",
            )
        try:
            result = _seeder.run_seed_for_repo(
                repo_owner=fork_owner,
                repo_name=fork_name,
                root=seeds_root,
                token=self.state.gitea_token,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="mirror-seed-rerun",
                status="failed",
                detail=f"transport ({type(exc).__name__})",
            )
        except Exception as exc:
            return PhaseResult(
                name="mirror-seed-rerun",
                status="failed",
                detail=f"unexpected ({type(exc).__name__})",
            )
        if result.failed > 0 and result.created + result.skipped == 0:
            return PhaseResult(
                name="mirror-seed-rerun",
                status="failed",
                detail=f"created=0 skipped=0 failed={result.failed}",
            )
        if result.failed > 0:
            return PhaseResult(
                name="mirror-seed-rerun",
                status="partial",
                detail=(
                    f"created={result.created} skipped={result.skipped} failed={result.failed}"
                ),
            )
        # In mirror mode the fork inherited many files from upstream;
        # POST returns 422 for those (existing-already), counted as
        # "skipped" — that's the expected steady-state.
        # Mutate state.repo_name + state.gitea_repo_owner here so the
        # downstream mirror-finalize phase (and any later observer)
        # sees the user's fork as the canonical workspace target.
        self.state.repo_name = fork_name
        self.state.gitea_repo_owner = fork_owner
        return PhaseResult(
            name="mirror-seed-rerun",
            status="ok",
            detail=(
                f"created={result.created} skipped={result.skipped} target={fork_owner}/{fork_name}"
            ),
        )

    def _phase_mirror_finalize(self, ssh: SSHClient) -> PhaseResult:
        """Mirror-mode wakeup: flow-sync re-trigger + git-restart loop.

        Combined into one phase because both share the ``mirror mode``
        gate AND are best-effort post-fork-population wakeups (failure
        of either is non-blocking; one combined PhaseResult is fine).

        - **Flow-sync re-trigger**: POST
          ``/api/v1/executions/system/flow-sync`` so the seeded flow
          appears in Kestra's UI within ~10s. Runs only if Kestra is
          enabled + admin-creds available.
        - **Git-restart loop**: restart jupyter / marimo / code-server /
          meltano / prefect to pick up the latest fork content. Runs
          for whichever subset of those is enabled.
        """
        if not self.gh_mirror_repos:
            return PhaseResult(
                name="mirror-finalize",
                status="skipped",
                detail="not mirror mode",
            )
        if not self.state.fork_name:
            return PhaseResult(
                name="mirror-finalize",
                status="skipped",
                detail="no fork populated",
            )

        flow_triggered = False
        flow_skipped_reason: str | None = None
        # Sub-step 1: flow-sync re-trigger (Kestra-gated)
        if (
            "kestra" in self.enabled_services
            and self.config.kestra_admin_password
            and self.bootstrap_env.admin_email
        ):
            local_port = _allocate_free_port()
            try:
                with ssh.port_forward(local_port, "localhost", 8085) as port:
                    client = _kestra.KestraClient(
                        base_url=f"http://localhost:{port}",
                        username=self.bootstrap_env.admin_email,
                        password=self.config.kestra_admin_password,
                    )
                    client.execute_flow("system", "flow-sync")
                    flow_triggered = True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                flow_skipped_reason = f"transport ({type(exc).__name__})"
            except _kestra.KestraError as exc:
                flow_skipped_reason = str(exc)
            except Exception as exc:
                flow_skipped_reason = f"unexpected ({type(exc).__name__})"
        else:
            flow_skipped_reason = "kestra not enabled or admin-creds missing"

        # Sub-step 2: git-restart loop (subset of git-integrated services).
        git_services = [
            svc
            for svc in ("jupyter", "marimo", "code-server", "meltano", "prefect")
            if svc in self.enabled_services
        ]
        try:
            restart_result = _compose_restart.run_restart(git_services, host=self.ssh_host)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return PhaseResult(
                name="mirror-finalize",
                status="partial",
                detail=(
                    f"flow_triggered={flow_triggered} "
                    f"git_restart_transport_error={type(exc).__name__}"
                ),
            )
        except Exception as exc:
            return PhaseResult(
                name="mirror-finalize",
                status="partial",
                detail=(
                    f"flow_triggered={flow_triggered} git_restart_unexpected={type(exc).__name__}"
                ),
            )

        details = [
            f"flow_triggered={flow_triggered}",
            f"git_restarted={restart_result.restarted}",
        ]
        if restart_result.failed:
            details.append(f"git_failed={restart_result.failed}")
        if flow_skipped_reason and not flow_triggered:
            details.append(f"flow_skip={flow_skipped_reason}")

        # Partial when EITHER:
        #   (a) Kestra was enabled but the flow-sync re-trigger didn't
        #       fire (covers transport failure, KestraError, or
        #       missing admin creds — anything that left
        #       flow_triggered=False despite kestra being in scope).
        #   (b) Git-restart loop reported any per-service failure.
        # When kestra is NOT enabled, flow_triggered stays False but
        # the (a) gate excludes it from partial-ness — that's the
        # legitimate "no flow-sync to trigger" case. PR #533 R6 #2
        # corrected the comment — was: "only ALL-failed → partial",
        # which contradicted the actual logic.
        is_partial = (
            not flow_triggered and "kestra" in self.enabled_services
        ) or restart_result.failed > 0
        return PhaseResult(
            name="mirror-finalize",
            status="partial" if is_partial else "ok",
            detail=" ".join(details),
        )

    def run_pre_bootstrap(self) -> OrchestratorResult:
        """Run the pre-bootstrap pipeline: service-env →
        firewall-configure → stack-sync → compose-up →
        infisical-provision. (Order corrected in PR #532 R5 #1 so
        firewall overrides are part of what stack-sync rsyncs to the
        server.)

        Resets ``self.results`` AND the credentials on BOTH
        ``self.state`` (``infisical_token`` + ``project_id``) and the
        orchestrator's own ``self.infisical_token`` / ``self.project_id``
        fields, so a re-invocation on the same instance can't leak
        stale credentials from a prior run — neither into the current
        rc=1 stdout emission (state) nor into a downstream call to
        :meth:`run_all` whose post-bootstrap phases gate on the fields.
        Caught in PR #532 R1 #4 (state) and R2 #3 (fields). Other state
        slots (gitea_token / woodpecker_* / fork_*) stay because they're
        populated by post-bootstrap phases and a re-run would naturally
        re-set them.

        Failure of any phase aborts the run; partial-success phases
        continue. Same rc=0/1/2 dispatch contract as :meth:`run_all`.

        The phases here don't need the orchestrator's shared SSHClient
        — the wrapped helpers each manage their own subprocess / ssh
        invocations independently. That's why this method doesn't
        open an ExitStack-managed ssh context (in contrast to
        :meth:`run_all`), and why pre-bootstrap phases drop the ``ssh``
        arg from their signature (per PR #532 R1 #2 — passing a
        None-cast-as-SSHClient is a runtime-contract footgun).
        """
        self.results = []
        # Reset credentials on BOTH state mirrors and the orchestrator's
        # own fields so a re-run can't carry over stale token / project_id
        # from a previous invocation that produced rc=1. State guards the
        # rc=1 stdout emission; the self.fields guard the post-bootstrap
        # phases (infisical-bootstrap, secret-sync) when the same instance
        # is later passed to run_all. Caught in PR #532 R2 #3.
        self.state.infisical_token = None
        self.state.project_id = None
        self.infisical_token = None
        self.project_id = None
        # PR #532 R2 #3 dual-write reset pattern for the 8
        # workspace-coords slots: clear BOTH state.* AND self.* so a
        # re-run on the same instance can't carry stale values into
        # the second run's stdout emission. Other state slots
        # (gitea_token / woodpecker_* / fork_*) reset themselves
        # naturally in run_all.
        self.state.repo_name = None
        self.state.gitea_repo_owner = None
        self.state.gitea_repo_url = None
        self.state.workspace_branch = "main"
        self.state.gitea_git_user = None
        self.state.gitea_git_pass = None
        self.state.git_author = None
        self.state.git_email = None
        self.repo_name = ""
        self.gitea_repo_owner = ""
        self.workspace_branch = "main"
        # Phase ordering (order matters; downstream phases gate on
        # state populated by upstream ones):
        #   workspace-coords — derive REPO_NAME etc. (other phases gate
        #                      on these; must run FIRST)
        #   service-env      — writes per-stack .env files locally
        #                      (consumes workspace-coords for gitea
        #                      block append)
        #   firewall-configure — writes per-stack
        #                        docker-compose.firewall.yml overrides
        #                        locally (must be BEFORE stack-sync so
        #                        rsync picks them up)
        #   stack-sync       — rsyncs everything in stacks/<svc>/ to
        #                      the server (without --delete)
        #   firewall-sync    — server-side orphan cleanup + RedPanda
        #                      config copy + chown 101:101 fallback.
        #                      AFTER stack-sync so the rsync's already
        #                      pushed the new overrides up; cleanup
        #                      removes the stale ones the rsync didn't
        #                      delete.
        #   global-env       — writes /opt/docker-server/stacks/.env
        #                      (DOMAIN + image versions). AFTER
        #                      stack-sync (which mkdir -p's the dir) so
        #                      we save an ssh round-trip.
        #   compose-up       — sees the synced overrides → containers
        #                      start with correct firewall exposure
        #   infisical-provision — bootstraps Infisical admin + workspace
        phases: list[Callable[[], PhaseResult]] = [
            self._phase_workspace_coords,  # NEW (4b1)
            self._phase_service_env,
            self._phase_firewall_configure,
            self._phase_stack_sync,
            self._phase_firewall_sync,  # NEW (4b1)
            self._phase_global_env,  # NEW (4b1)
            self._phase_compose_up,
            self._phase_infisical_provision,
        ]
        for phase in phases:
            result = phase()
            self.results.append(result)
            if result.status == "failed":
                break
        return OrchestratorResult(phases=tuple(self.results), state=self.state)


# Module-level helper so the CLI handler can shell out cleanly.
__all__ = [
    "Orchestrator",
    "OrchestratorResult",
    "OrchestratorState",
    "PhaseResult",
]
