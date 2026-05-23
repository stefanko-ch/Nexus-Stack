"""Top-level deploy pipeline.

The orchestrator's ``run_pre_bootstrap`` + ``run_all`` cover the
per-stack / per-service phases; this module covers everything that
sits above and around them:

1. R2 credentials load + ``os.environ`` injection
2. ``tofu state list`` pre-flight
3. config.tfvars parse + Gitea identity derivation
4. Read 6 tofu outputs (secrets, image_versions, enabled_services,
   firewall_rules, ssh_service_token, server_ip)
5. SSH known_hosts cleanup (``ssh-keygen -R``)
6. ``setup.configure_ssh`` → ``setup.wait_for_ssh`` →
   ``setup.ensure_jq`` → ``setup.ensure_rclone``. rclone MUST be
   installed before step 7 — otherwise the Round-6 bucket-
   reachability probe sees rc=127 (command not found) and aborts
   the spinup with rc=2. (Historical: pre-Round-6 the same
   missing-rclone case silently fresh-started instead, leading
   to data loss on the next teardown — see ensure_rclone's
   docstring.)
7. ``s3_restore.restore_from_s3(phase="filesystem")`` — rclone-syncs
   the FS bind-mount trees onto local SSD; fresh-start exits 0
8. ``setup.ensure_data_dirs`` — chowns the rsync'd trees to
   container UIDs (1000:1000 for gitea, 70:70 for postgres,
   999:999 for redis); runs BEFORE compose-up
9. Docker Hub login (when creds set)
10. ``setup.setup_wetty_ssh_agent`` (when wetty enabled)
11. ``Orchestrator.run_pre_bootstrap`` — last phase is
    ``_phase_compose_up``, so containers come up reading the
    seeded bind-mounts
12. ``s3_restore.restore_from_s3(phase="postgres")`` — ``docker
    exec pg_restore`` against the now-running gitea-db + dify-db
13. ``Orchestrator.run_all`` — gitea-configure et al. see the
    restored database
14. Display service URLs from ``tofu output service_urls``

Everything runs in-process — no subprocess CLI invocations of
``python -m nexus_deploy <subcommand>``, no ``eval`` of stdout
payloads. State flows through Python objects between steps.

The ``run_pipeline`` function is the public entry; the CLI handler
in ``__main__.py:_run_pipeline`` is a thin wrapper that reads
workflow-secret env vars and calls this.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from nexus_deploy import s3_restore as _s3_restore
from nexus_deploy import setup as _setup
from nexus_deploy import tfvars as _tfvars
from nexus_deploy import tofu as _tofu
from nexus_deploy.config import ConfigError, NexusConfig, service_host
from nexus_deploy.infisical import BootstrapEnv
from nexus_deploy.orchestrator import Orchestrator, OrchestratorResult
from nexus_deploy.ssh import SSHClient

# Cloudflare-Tunnel SSH endpoint. Built via :func:`service_host` so
# multi-tenant forks with ``subdomain_separator='-'`` get the flat
# form ``ssh-user1.example.com`` instead of ``ssh.user1.example.com``,
# matching the DNS records Tofu provisions for that tenant.


class PipelineError(Exception):
    """Pipeline pre-flight or step failed unrecoverably.

    Distinct from PhaseResult.status='failed' which the orchestrator
    uses for in-pipeline phase outcomes — this exception is raised by
    the wrapper code that runs BEFORE / AROUND the orchestrator
    (tofu reads, R2 creds, ssh setup) and SHOULD abort the deploy.
    """


@dataclass(frozen=True)
class PipelineResult:
    """Bundle of the orchestrator's two outcomes + the service URLs.

    Returned by :func:`run_pipeline` for the CLI handler to format
    the post-deploy banner. Tests assert against this directly
    instead of capturing stdout.
    """

    pre_bootstrap: OrchestratorResult
    run_all: OrchestratorResult
    service_urls: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineOptions:
    """Workflow-secret inputs the CLI handler reads from env vars.

    Bundled into a frozen dataclass so callers can construct
    deterministic test fixtures and so the function signature stays
    short. ``infisical_env`` defaults to "dev" — anything else is
    opt-in.
    """

    ssh_private_key_content: str | None = None
    gh_mirror_token: str | None = None
    gh_mirror_repos: str | None = None
    dockerhub_user: str | None = None
    dockerhub_token: str | None = None
    infisical_env: str = "dev"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ssh_keygen_cleanup(*targets: str) -> None:
    """Run ``ssh-keygen -R <target>`` for each non-empty target.

    Failures are silent: if the entry doesn't exist in known_hosts,
    ssh-keygen exits non-zero, but that's expected on a fresh
    runner. Captured output is discarded — operators don't need to
    see the "Host added/removed" diagnostic for this prep step.

    PR #535 R2 #1: also suppresses ``TimeoutExpired`` so a hung
    ssh-keygen (the timeout is a defence against an unkillable child,
    not a meaningful deadline) can't abort the deploy. ``check=False``
    means CalledProcessError doesn't fire today, but the suppress is
    kept defensively in case a future change flips ``check=True``.
    """
    for target in targets:
        if not target:
            continue
        with contextlib.suppress(
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            OSError,
        ):
            subprocess.run(
                ["ssh-keygen", "-R", target],
                check=False,
                capture_output=True,
                timeout=10.0,
            )


def _docker_hub_login(host: str, dockerhub_user: str, dockerhub_token: str) -> None:
    """Pipe the token over ssh-stdin into ``docker login --password-stdin``.

    PR #533 R2 #2 / R3 #2 lessons: we DON'T use ``cat > <path>``-style
    redirects with potentially-untrusted values, but the docker CLI
    itself reads ``--password-stdin`` for exactly this case (token
    via stdin, never argv → never visible in ``ps``). Username goes
    through argv (it's not a secret per Docker Hub's threat model)
    BUT must be shell-quoted: ssh receives the third argv element as
    a single shell command string, and an unquoted username with a
    space / metachar would be parsed by the remote shell. PR #535 R1
    #1: shlex.quote prevents an attacker who controls DOCKERHUB_USER
    (e.g. via a compromised CI secret) from injecting arbitrary
    commands into the remote ``docker login`` line.
    """
    quoted_user = shlex.quote(dockerhub_user)
    subprocess.run(
        ["ssh", host, f"docker login -u {quoted_user} --password-stdin"],
        input=dockerhub_token,
        check=True,
        capture_output=True,
        text=True,
        timeout=30.0,
    )


def _b64_encode_ssh_key(content: str | None) -> str:
    """Base64-encode the SSH private key for the BootstrapEnv.

    Encodes ``base64(<key>+\\n)`` — the trailing newline matches the
    on-disk format produced by ``echo "$X" | base64`` so consumers
    don't need to special-case "with-newline" vs "without-newline".
    Empty/None input returns the empty string (preventing a stray
    ``Cg==`` from being treated as a populated key).
    """
    import base64

    if not content:
        return ""
    # Append trailing newline before encoding for compatibility with
    # the on-disk format produced by ``echo "$X" | base64``.
    encoded = base64.b64encode((content + "\n").encode("utf-8"))
    return encoded.decode("ascii").replace("\n", "")


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------


def run_pipeline(
    *,
    project_root: Path,
    options: PipelineOptions,
    # DI seams (production callers leave these None):
    tofu_runner: _tofu.TofuRunner | None = None,
    docker_hub_login: Callable[[str, str, str], None] | None = None,
) -> PipelineResult:
    """Run the full deploy pipeline.

    Exit-code semantics as the CLI handler maps them:
    - Hard failure (PipelineError raised) → CLI returns rc=2 (abort).
    - Orchestrator hard failure (any phase status='failed') →
      PipelineError raised, rc=2.
    - Orchestrator partial (any phase status='partial') OR clean run
      → CLI returns rc=0 (deploy succeeded; partial surfaces as
      stderr warning, NOT non-zero exit).

    The rc=0-on-partial contract was tightened in PR #535 R0/R1 — a
    non-zero exit in spin-up.yml's ``shell: bash -e`` step would
    fail the workflow even when the deploy completed successfully.
    Partial is operator-visible via the orchestrator's per-phase
    log emitted to stderr.

    ``tofu_runner`` and ``docker_hub_login`` are DI seams for tests;
    production callers pass None.
    """
    # 1. R2 credentials env-injection (BEFORE any tofu call — the R2
    #    backend reads AWS_* from os.environ at tofu-binary startup).
    #    PR #535 R4 #2: wrap TofuError → PipelineError so a malformed
    #    .r2-credentials file is reported as a pipeline pre-flight
    #    failure (rc=2 + actionable message) instead of being
    #    classified as "unexpected error" by the CLI handler.
    creds_file = project_root / "tofu" / ".r2-credentials"
    try:
        creds = _tofu.load_r2_credentials(creds_file)
    except _tofu.TofuError as exc:
        raise PipelineError(
            f"could not load {creds_file}: {exc} — delete the file or fix it to KEY=value form",
        ) from exc
    if creds is not None:
        os.environ["AWS_ACCESS_KEY_ID"] = creds.access_key_id
        os.environ["AWS_SECRET_ACCESS_KEY"] = creds.secret_access_key

    # 2. tofu state pre-flight.
    tofu_dir = project_root / "tofu" / "stack"
    runner = tofu_runner if tofu_runner is not None else _tofu.TofuRunner(tofu_dir=tofu_dir)
    if not runner.state_list_ok():
        # PR #535 R2 #2: surface the actual cause when available so
        # operators can distinguish "state not initialised" from
        # "tofu binary missing" / "backend timed out" / "rc=N + stderr".
        # The gate stays on state_list_ok() (preserves DI/Mock contract
        # in tests). diagnose_state() is only called for the error
        # message; we type-check the return so a MagicMock-generated
        # attribute (which would yield a Mock, not a real str) cleanly
        # falls back to the generic message instead of stringifying
        # the Mock object into the operator-facing error.
        reason_obj = runner.diagnose_state() if hasattr(runner, "diagnose_state") else None
        reason: str | None = reason_obj if isinstance(reason_obj, str) else None
        if reason:
            raise PipelineError(
                f"OpenTofu state at {tofu_dir} not usable: {reason} — "
                "run the initial-setup workflow first if state is missing",
            )
        raise PipelineError(
            f"OpenTofu state at {tofu_dir} is not initialised — "
            "run the initial-setup workflow first",
        )

    # 3. config.tfvars + identity derivation.
    #    PR #535 R4 #3: wrap TfvarsError → PipelineError. tfvars.parse
    #    raises on missing/unreadable config.tfvars; without the wrap
    #    the CLI surfaces it as "unexpected error (TfvarsError)" which
    #    masks an obviously-actionable preflight issue.
    tfvars_path = tofu_dir / "config.tfvars"
    try:
        tfvars_config = _tfvars.parse(tfvars_path)
    except _tfvars.TfvarsError as exc:
        raise PipelineError(f"could not load {tfvars_path}: {exc}") from exc
    if not tfvars_config.domain:
        raise PipelineError(
            f"{tfvars_path} is missing a non-empty 'domain' value",
        )
    identity = _tfvars.derive_gitea_identity(tfvars_config)

    # 4. Read tofu outputs. Required ones use no default → raise on
    #    missing. Optional ones default to safe empty values.
    secrets_json = runner.output_json("secrets", default={})
    if not secrets_json:
        raise PipelineError(
            "tofu output -json secrets is empty — state corrupt or Tofu not yet applied",
        )
    try:
        config = NexusConfig.from_secrets_json(json.dumps(secrets_json))
    except ConfigError as exc:
        raise PipelineError(f"could not parse secrets JSON: {exc}") from exc

    # PR #535 R4 #1: outputs whose empty/default values would be
    # destructive must be REQUIRED — no default → TofuError on
    # missing → wrapped to PipelineError. The previous safe-looking
    # defaults (``[]`` / ``{}``) silently triggered destructive
    # downstream behavior when state was partially applied:
    # ``enabled_services=[]`` makes the stack-sync phase remove ALL
    # remote stacks, and ``firewall_rules={}`` puts firewall-configure
    # into zero-entry mode (wiping existing per-stack overrides).
    # state_list_ok() above doesn't catch the partial-apply case
    # (state file exists, but the specific outputs were never
    # populated by a complete tofu run).
    try:
        image_versions = runner.output_json("image_versions")
        enabled_services_raw = runner.output_json("enabled_services")
        firewall_rules = runner.output_json("firewall_rules")
        ssh_service_token = runner.output_json("ssh_service_token")
    except _tofu.TofuError as exc:
        raise PipelineError(
            f"required tofu output missing or invalid: {exc} — "
            "state may be partially applied; re-run initial-setup",
        ) from exc
    # ``server_ip`` is optional — missing means ssh-keygen cleanup
    # has fewer targets. ``persistent_volume_id`` is gone in the
    # RFC 0001 cutover; persistence lives in R2 via s3_restore.
    server_ip = runner.output_raw("server_ip", default="")

    if not isinstance(enabled_services_raw, list):
        raise PipelineError(
            f"tofu output enabled_services is {type(enabled_services_raw).__name__}, expected list",
        )
    enabled_services: list[str] = [str(s) for s in enabled_services_raw]

    # 5. SSH known_hosts cleanup — best-effort, never fatal.
    ssh_host_dns = service_host("ssh", tfvars_config.domain, tfvars_config.subdomain_separator)
    _ssh_keygen_cleanup(ssh_host_dns, server_ip)

    # 6-10. Setup chain + orchestrator. Single ExitStack owns the
    # SSHClient lifetime so an early exception still tears it down.
    with contextlib.ExitStack() as stack:
        cf_client_id = ""
        cf_client_secret = ""
        if isinstance(ssh_service_token, dict):
            cf_client_id = str(ssh_service_token.get("client_id") or "")
            cf_client_secret = str(ssh_service_token.get("client_secret") or "")
        _setup.configure_ssh(
            _setup.SSHConfigSpec(
                ssh_host=ssh_host_dns,
                cf_client_id=cf_client_id,
                cf_client_secret=cf_client_secret,
            ),
        )
        readiness = _setup.wait_for_ssh()
        if not readiness.succeeded:
            raise PipelineError(
                f"SSH did not become ready after {readiness.attempts} attempts: "
                f"{readiness.last_error[:500]}",
            )

        ssh = stack.enter_context(SSHClient("nexus"))
        _setup.ensure_jq(ssh)
        # rclone MUST be installed before restore_from_s3 runs. Without
        # this, the rendered restore script's `rclone lsd / rclone lsf`
        # calls return rc=127 (command not found), which the Round-6
        # reachability probe correctly flags as "bucket not reachable"
        # and aborts the spinup with rc=2. The PRE-Round-6 behavior was
        # even worse: a missing rclone silently fresh-started the spinup
        # and the next teardown overwrote real R2 data with empty
        # snapshots. See ensure_rclone's docstring for the full
        # rationale.
        _setup.ensure_rclone(ssh)

        # RFC 0001 cutover wire-up — split into two halves because
        # pg_restore needs the gitea-db / dify-db containers running
        # (``docker exec`` target), while the filesystem rsync MUST
        # land BEFORE compose-up (the containers come up reading
        # the seeded bind-mounts).
        #
        # Halve 1 (here, pre-compose): pull only the filesystem
        # trees (gitea repos/lfs, dify storage/weaviate/plugins).
        # On a fresh-start the script short-circuits with rc=0; on
        # an existing snapshot rclone-syncs the trees onto local SSD.
        s3_fs_result = _s3_restore.restore_from_s3(ssh, phase="filesystem")
        # rclone writes restored files as the SSH user (root), but
        # gitea + postgres containers expect their container UIDs
        # on the bind-mount sources. Idempotent — fine to run on
        # an empty fresh-start tree too. Must run AFTER the
        # filesystem rsync (so chown -R sees the rsync'd files) and
        # BEFORE compose-up (so containers start with the right
        # ownership in place).
        _setup.ensure_data_dirs(ssh)
        if isinstance(s3_fs_result, _s3_restore.S3RestoreApplied):
            sys.stderr.write(
                f"✓ s3-restore (filesystem): applied snapshot {s3_fs_result.snapshot_timestamp}\n",
            )
        elif s3_fs_result.reason == "fresh_start_empty_s3":
            sys.stderr.write(
                "→ s3-restore: bucket empty, fresh-start (first spinup of new "
                "persistence bucket)\n",
            )
        # The other two skip reasons are intentionally not logged here:
        #   - feature_flag_off: silent by design — the stack hasn't
        #     opted in to S3 persistence, so logging would just add
        #     noise to every spinup of stacks that don't use it.
        #   - no_endpoint_env: restore_from_s3 already wrote its own
        #     stderr line (it lists the specific missing env vars,
        #     which is the actionable info the operator needs).

        if options.dockerhub_user and options.dockerhub_token:
            login_fn = docker_hub_login if docker_hub_login is not None else _docker_hub_login
            login_fn("nexus", options.dockerhub_user, options.dockerhub_token)

        if "wetty" in enabled_services:
            _setup.setup_wetty_ssh_agent(ssh)

        # Build the BootstrapEnv + Orchestrator. workspace-coords
        # phase fills repo_name / gitea_repo_owner / etc. inside
        # run_pre_bootstrap; here we pre-populate the inputs it needs.
        bootstrap_env = BootstrapEnv(
            domain=tfvars_config.domain,
            admin_email=identity.admin_email,
            gitea_user_email=identity.gitea_user_email or None,
            gitea_user_username=identity.gitea_user_username or None,
            om_principal_domain=identity.om_principal_domain or None,
            ssh_private_key_base64=_b64_encode_ssh_key(options.ssh_private_key_content),
            subdomain_separator=tfvars_config.subdomain_separator,
            monitoring_endpoint=os.environ.get("MONITORING_ENDPOINT") or None,
            monitoring_token=os.environ.get("MONITORING_TOKEN") or None,
            tenant_id=os.environ.get("TENANT_ID") or None,
        )
        gh_mirror_repos_list = (
            [s.strip() for s in (options.gh_mirror_repos or "").split(",") if s.strip()]
            if options.gh_mirror_repos
            else []
        )
        orchestrator = Orchestrator(
            config=config,
            bootstrap_env=bootstrap_env,
            enabled_services=enabled_services,
            domain=tfvars_config.domain,
            admin_username=config.admin_username or "",
            user_email=tfvars_config.user_email_raw,
            gitea_admin_pass=config.gitea_admin_password,
            admin_password_infisical=config.infisical_admin_password,
            gitea_user_email=identity.gitea_user_email or None,
            gitea_user_username=identity.gitea_user_username or None,
            gitea_user_password=config.gitea_user_password,
            firewall_json=json.dumps(firewall_rules),
            image_versions_json=json.dumps(image_versions),
            gh_mirror_token=options.gh_mirror_token,
            gh_mirror_repos=gh_mirror_repos_list,
            woodpecker_agent_secret=config.woodpecker_agent_secret,
            project_root=project_root,
            infisical_env=options.infisical_env,
        )

        pre_result = orchestrator.run_pre_bootstrap()
        if pre_result.has_hard_failure:
            raise PipelineError(
                "pre-bootstrap pipeline aborted (see per-phase log above)",
            )

        # Halve 2 of RFC 0001 restore: pg_restore now that
        # compose-up has run (last phase of run_pre_bootstrap),
        # so gitea-db and dify-db containers are up + accepting
        # ``docker exec``. Must run BEFORE ``run_all`` because
        # the gitea-configure phase later inspects/mutates the
        # gitea database — restored snapshot has to be in place
        # first or gitea-configure would write into a soon-to-be-
        # clobbered database. Fresh-start short-circuits at rc=0.
        s3_pg_result = _s3_restore.restore_from_s3(ssh, phase="postgres")
        if isinstance(s3_pg_result, _s3_restore.S3RestoreApplied):
            sys.stderr.write(
                f"✓ s3-restore (postgres): applied snapshot {s3_pg_result.snapshot_timestamp}\n",
            )
        # No need to re-log fresh_start_empty_s3 here — the
        # filesystem halve above already emitted that diagnostic.

        all_result = orchestrator.run_all()
        if all_result.has_hard_failure:
            raise PipelineError(
                "post-bootstrap pipeline aborted (see per-phase log above)",
            )

    # 11. Service URLs (display only — failure is non-fatal).
    service_urls_raw = runner.output_json("service_urls", default={})
    if isinstance(service_urls_raw, dict):
        service_urls: dict[str, str] = {str(k): str(v) for k, v in service_urls_raw.items()}
    else:
        service_urls = {}

    return PipelineResult(
        pre_bootstrap=pre_result,
        run_all=all_result,
        service_urls=service_urls,
    )


@dataclass(frozen=True)
class SnapshotResult:
    """Outcome of :func:`run_snapshot`.

    Wraps an ``s3_restore.S3SnapshotSkipped`` or
    ``S3SnapshotApplied`` so callers don't need to import
    ``s3_restore`` to branch on the result.
    """

    outcome: _s3_restore.S3SnapshotSkipped | _s3_restore.S3SnapshotApplied


def run_snapshot(
    *,
    project_root: Path,
    stack_slug: str,
    template_version: str,
    tofu_runner: _tofu.TofuRunner | None = None,
) -> SnapshotResult:
    """Push current persistent state to R2 before a teardown.

    Counterpart to :func:`run_pipeline` for the *teardown* side:
    reuses the same R2-creds / tofu-state / SSH-setup pre-flight,
    but skips secret reads, orchestrator phases, and service-URL
    banners — none of which apply when we're tearing down. After
    SSH is up, delegates to :func:`s3_restore.snapshot_to_s3`,
    which implements the atomicity contract.

    Exit-code semantics on the CLI side:

    - Hard failure (PipelineError raised) → rc=2, teardown MUST
      abort (operator-fixable: tofu state missing, ssh wait
      timeout, R2 creds broken).
    - ``snapshot_to_s3`` itself raises CalledProcessError on
      remote-script failure (rclone drift, pg_dump error,
      compose-stop error) — propagates out, CLI maps to rc=2.
      Teardown MUST abort: an unverified snapshot followed by
      ``tofu destroy`` would lose data.
    - Snapshot returns ``S3SnapshotSkipped(reason='feature_flag_off')``
      → rc=0, this stack hasn't opted in to S3 persistence;
      caller proceeds with legacy teardown path.
    - Snapshot returns ``S3SnapshotSkipped(reason='no_endpoint_env')``
      → rc=2, flag is on but credentials missing; teardown MUST
      abort to avoid data loss.
    - Snapshot returns ``S3SnapshotSkipped(reason='no_state_to_snapshot')``
      → rc=0, partially-deployed fork (no ``tofu apply`` ever
      ran against ``tofu/stack``, e.g. spin-up aborted at the
      Hetzner capacity step). Nothing on the server to snapshot;
      teardown proceeds and ``tofu destroy`` is also a no-op
      against the empty state. See issue #564.
    - Snapshot returns ``S3SnapshotSkipped(reason='no_snapshot_source')``
      → rc=0, partial state exists in ``tofu/stack`` (e.g. a few
      Cloudflare-side resources that the orchestrator created
      before failing) but neither ``hcloud_server.main`` nor the
      ``ssh_service_token`` output (sourced from the
      ``cloudflare_zero_trust_access_service_token.ssh`` resource)
      is in state. No server, no way (and no need) to snapshot;
      teardown proceeds to reap the partial Cloudflare-side
      resources via ``tofu destroy``. See mid-2026-05 deads7-fork
      observation.
    - Snapshot returns ``S3SnapshotApplied`` → rc=0, safe to
      proceed with ``tofu destroy``.

    **Feature-flag short-circuit:** when ``NEXUS_S3_PERSISTENCE``
    is not exactly ``"true"`` we return the ``feature_flag_off``
    outcome immediately, before touching R2 creds / tofu state /
    SSH. This keeps the function callable on stacks that haven't
    opted in (e.g. local tests, direct imports outside the CLI):
    a caller that bypasses the ``_s3_snapshot`` CLI's own early
    check would otherwise hit ``PipelineError`` for a missing
    tofu state on a torn-down stack that was never going to
    snapshot in the first place.
    """
    # 0. Feature-flag short-circuit — must be the very first
    #    check, before any R2 / tofu / SSH side-effects, so direct
    #    callers (tests, programmatic use) get the same skip
    #    semantics the CLI handler provides.
    if not _s3_restore.is_enabled():
        return SnapshotResult(
            outcome=_s3_restore.S3SnapshotSkipped(reason="feature_flag_off"),
        )

    # 1. R2 credentials (identical to run_pipeline step 1).
    creds_file = project_root / "tofu" / ".r2-credentials"
    try:
        creds = _tofu.load_r2_credentials(creds_file)
    except _tofu.TofuError as exc:
        raise PipelineError(
            f"could not load {creds_file}: {exc} — delete the file or fix it to KEY=value form",
        ) from exc
    if creds is not None:
        os.environ["AWS_ACCESS_KEY_ID"] = creds.access_key_id
        os.environ["AWS_SECRET_ACCESS_KEY"] = creds.secret_access_key

    # 2. tofu state pre-flight (identical to run_pipeline step 2,
    #    plus an issue-#564 carve-out for the "stack was never
    #    spun up" case).
    tofu_dir = project_root / "tofu" / "stack"
    runner = tofu_runner if tofu_runner is not None else _tofu.TofuRunner(tofu_dir=tofu_dir)
    if not runner.state_list_ok():
        reason_obj = runner.diagnose_state() if hasattr(runner, "diagnose_state") else None
        reason: str | None = reason_obj if isinstance(reason_obj, str) else None
        # Issue #564: distinguish "no state to snapshot" (partial
        # deploy: setup-control-plane succeeded, spin-up aborted
        # before tofu apply — e.g. Hetzner capacity exhausted)
        # from a real state-list failure (binary missing, R2
        # auth/timeout, etc.). The former is a legitimate no-op:
        # the subsequent tofu destroy will also be a no-op, and
        # teardown should be allowed to complete green so the
        # operator can recover without falling back to
        # destroy-all. We narrowly match on the "No state file
        # was found" substring that diagnose_state() surfaces
        # verbatim from tofu's stderr.
        if reason and "No state file was found" in reason:
            return SnapshotResult(
                outcome=_s3_restore.S3SnapshotSkipped(
                    reason="no_state_to_snapshot",
                ),
            )
        if reason:
            raise PipelineError(
                f"OpenTofu state at {tofu_dir} not usable: {reason} — "
                "nothing to teardown (already destroyed?)",
            )
        raise PipelineError(
            f"OpenTofu state at {tofu_dir} is not initialised — nothing to teardown",
        )

    # 3. config.tfvars → domain → ssh host (subset of run_pipeline step 3).
    tfvars_path = tofu_dir / "config.tfvars"
    try:
        tfvars_config = _tfvars.parse(tfvars_path)
    except _tfvars.TfvarsError as exc:
        raise PipelineError(f"could not load {tfvars_path}: {exc}") from exc
    if not tfvars_config.domain:
        raise PipelineError(
            f"{tfvars_path} is missing a non-empty 'domain' value",
        )

    # 4. ssh_service_token + server_ip from tofu outputs.
    #
    # `state_list_ok` already passed (step 2), so SOME state exists in
    # tofu/stack — but that doesn't mean the `ssh_service_token`
    # output (declared in `tofu/stack/outputs.tf`, sourced from the
    # `cloudflare_zero_trust_access_service_token.ssh` resource) is
    # in it. Observed mid-2026-05: a scheduled teardown on a deads7
    # fork where setup ran ✅ but Spin Up was never triggered (so
    # neither the Hetzner server nor the CF Access service-token
    # resource got applied) fired exit-2 daily on this very step.
    # Without an SSH service token there's also no Hetzner server
    # reachable via SSH — there is nothing TO snapshot, the same
    # legitimate no-op as issue #564 just one branch deeper. Skip
    # with `no_snapshot_source`; the subsequent `tofu destroy` will
    # still reap whatever stack-side partial resources ARE in state
    # (typically Cloudflare DNS records, tunnel resources, Access
    # applications that the orchestrator created before failing — NOT
    # the R2 state bucket or Cloudflare KV namespace; those live in
    # `tofu/control-plane`, not here) so the teardown remains useful,
    # just not an SSH-driven one.
    #
    # Real TofuError causes (tofu binary missing, R2 backend auth) at
    # THIS point would be surprising — step 2 already exercised the
    # binary + state backend successfully — but still possible if
    # transient. Surface those as PipelineError so the operator sees
    # the actual cause rather than a silent skip.
    #
    # output_json(default=None) would collapse ALL three failure modes
    # (binary missing, non-zero exit, invalid JSON) into the graceful
    # no_snapshot_source branch. We only want that for the specific
    # "output not declared in state" case — tofu reports this via a
    # well-known stderr marker. Anything else re-raises as PipelineError.
    #
    # SECURITY: tofu stderr can contain provider/backend credential
    # material (Cloudflare API tokens shown in plan diffs, Hetzner
    # auth-error tokens, R2 SignatureDoesNotMatch leaking partial
    # keys). Read the stderr ONLY to match the well-known "output
    # not declared" marker; never include it in the PipelineError
    # message. Same convention as TofuRunner's own error wrapping
    # (see test_output_raw_error_message_does_not_leak_subprocess_stderr).
    try:
        ssh_service_token = runner.output_json("ssh_service_token")
    except _tofu.TofuError as exc:
        cause = exc.__cause__
        stderr = ""
        if isinstance(cause, subprocess.CalledProcessError) and isinstance(cause.stderr, str):
            stderr = cause.stderr
        # Case-insensitive: OpenTofu emits "No outputs found" with a
        # capital N (see opentofu/internal/command/views/output.go:297),
        # while "The output variable requested could not be found in
        # the state file" is lowercase. Normalize both to lowercase so
        # neither path silently slips through to the hard-failure branch.
        stderr_lower = stderr.lower()
        if "could not be found in the state" in stderr_lower or "no outputs found" in stderr_lower:
            ssh_service_token = None
        else:
            raise PipelineError(
                f"tofu output -json ssh_service_token failed in {tofu_dir} "
                "(state_list_ok already passed at step 2 — likely transient "
                "R2 backend auth/timeout or tofu binary issue). "
                "Operator: rerun `tofu output -json ssh_service_token` "
                f"in {tofu_dir} to see the actual provider error. "
                "(Tofu stderr is held inside the chained CalledProcessError "
                "but deliberately not included in this message — it can "
                "carry CF API tokens, Hetzner auth tokens, or R2 signature "
                "fragments.)",
            ) from exc
    if ssh_service_token is None:
        # Output absent / null. Before treating this as "no server to
        # snapshot", VERIFY hcloud_server.main isn't sitting in state
        # too. hcloud_server.main and the CF Access service-token are
        # independent resources: a partial state could have created
        # the server (so it has data on it) but failed before / after
        # the token. Silently skipping the snapshot in that case would
        # let `tofu destroy` nuke the server with data on it. Surface
        # this as a hard PipelineError instead — operator must either
        # re-apply the missing token resource so we can SSH-snapshot,
        # or manually back up the server before destroy-all.
        #
        # state_contains() raises TofuError on backend failure — wrap
        # to honor run_snapshot's PipelineError contract instead of
        # surfacing as "unexpected error" in the CLI dispatcher.
        try:
            server_in_state = runner.state_contains("hcloud_server.main")
        except _tofu.TofuError as exc:
            raise PipelineError(
                f"tofu state list failed in {tofu_dir} when checking whether "
                "hcloud_server.main is in state — can't safely decide "
                "snapshot vs skip. Likely transient R2 backend / auth issue. "
                f"Operator: rerun `tofu state list` in {tofu_dir} to see "
                "the actual provider error before retrying teardown. (Tofu "
                "stderr is held inside the chained CalledProcessError but "
                "deliberately not included in this message to avoid leaking "
                "provider credentials.)",
            ) from exc
        if server_in_state:
            raise PipelineError(
                f"Dangerous partial state in {tofu_dir}: hcloud_server.main "
                "is in state but ssh_service_token output is absent — the "
                "server may have data but the pipeline can't SSH to snapshot "
                "it. `tofu destroy` would lose that data. Operator action: "
                "either re-apply the missing CF Access service-token "
                "resources so a snapshot becomes possible, or manually back "
                "up the server before running destroy-all.",
            )
        return SnapshotResult(
            outcome=_s3_restore.S3SnapshotSkipped(
                reason="no_snapshot_source",
            ),
        )
    server_ip = runner.output_raw("server_ip", default="")

    # 5. SSH known_hosts cleanup — same pattern as run_pipeline.
    ssh_host_dns = service_host("ssh", tfvars_config.domain, tfvars_config.subdomain_separator)
    _ssh_keygen_cleanup(ssh_host_dns, server_ip)

    # 6. configure_ssh → wait_for_ssh → SSHClient → snapshot.
    with contextlib.ExitStack() as stack:
        cf_client_id = ""
        cf_client_secret = ""
        if isinstance(ssh_service_token, dict):
            cf_client_id = str(ssh_service_token.get("client_id") or "")
            cf_client_secret = str(ssh_service_token.get("client_secret") or "")
        _setup.configure_ssh(
            _setup.SSHConfigSpec(
                ssh_host=ssh_host_dns,
                cf_client_id=cf_client_id,
                cf_client_secret=cf_client_secret,
            ),
        )
        readiness = _setup.wait_for_ssh()
        if not readiness.succeeded:
            raise PipelineError(
                f"SSH did not become ready after {readiness.attempts} attempts: "
                f"{readiness.last_error[:500]}",
            )
        ssh = stack.enter_context(SSHClient("nexus"))
        outcome = _s3_restore.snapshot_to_s3(
            ssh,
            stack_slug=stack_slug,
            template_version=template_version,
        )
    return SnapshotResult(outcome=outcome)


def format_done_banner(result: PipelineResult) -> str:
    """Render the post-deploy banner.

    Returns the banner as a single string for the CLI handler to
    print to stdout.
    """
    lines: list[str] = [
        "",
        "╔═══════════════════════════════════════════════════════════════╗",
        "║                    ✅ Deployment Complete!                    ║",
        "╚═══════════════════════════════════════════════════════════════╝",
        "",
        "🔗 Your Services:",
    ]
    if result.service_urls:
        for name in sorted(result.service_urls):
            lines.append(f"   {name}: {result.service_urls[name]}")
    else:
        lines.append("   (service URLs not available)")
    lines.extend(
        [
            "",
            "📌 SSH Access:",
            "   ssh nexus",
            "",
            "🔐 View credentials:",
            "   Credentials available in Infisical",
            "",
        ],
    )
    return "\n".join(lines)
