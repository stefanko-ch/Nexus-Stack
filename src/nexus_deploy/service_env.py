"""Per-service ``.env`` file generation.

~30 service-specific renderers turn :class:`NexusConfig` +
:class:`BootstrapEnv` into the per-service ``stacks/<svc>/.env``
files (plus the occasional sidecar config — ``garage.toml``,
``s3.json``, the pg-ducklake bootstrap SQL, etc.). Each renderer is a
pure function with snapshot-tested output; the only subprocess shells
out to ``htpasswd -nbB`` for Filestash's bcrypt admin password.

Architecture:

* :class:`EnvSpec` ties a service name to an enabled-check and a
  render function. The render function takes :class:`NexusConfig`
  + :class:`BootstrapEnv` and returns :class:`RenderedEnv` with the
  KEY=value dict plus optional sidecar files (SQL, JSON, TOML).
* Specs are listed in :data:`_SPECS` in a stable order so per-stack
  snapshot diffs stay readable.
* :func:`render_all_env_files` iterates specs, calls render, writes
  each ``.env`` (and its sidecar files) atomically via
  ``tempfile.mkstemp`` + ``os.replace`` — same pattern as
  :func:`setup.configure_ssh`.
* :func:`append_gitea_workspace_block` is a separate post-pass:
  the Gitea workspace .env block (idempotent ``cat >> .env`` with
  marker-block sed-strip) is appended to jupyter / marimo /
  code-server / meltano / prefect when Gitea is enabled.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from nexus_deploy.config import NexusConfig, service_host
from nexus_deploy.infisical import BootstrapEnv

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SidecarFile:
    """A non-.env file produced alongside a service's .env (e.g.
    ``stacks/seaweedfs/s3.json``, ``stacks/garage/garage.toml``,
    ``stacks/pg-ducklake/init/00-ducklake-bootstrap.sql``)."""

    relative_path: str
    content: str
    mode: int = 0o644


@dataclass(frozen=True)
class RenderedEnv:
    """Result of a single service's render function.

    ``env_vars`` becomes ``KEY=value`` lines in the ``.env`` file —
    values are emitted verbatim with no quoting (matching the legacy
    bash heredocs, which also wrote unquoted values). Service-specific
    escaping that the consumer expects (e.g. Filestash's ``$$`` for
    docker-compose-substitution-in-bcrypt) happens inside the
    individual render function before the value reaches this struct.
    ``sidecars`` are extra files written alongside.
    ``mode`` is the ``.env`` permission mode — most services use
    0o644; SFTPGo uses 0o600 because it stores admin credentials
    in cleartext.
    """

    env_vars: dict[str, str] = field(default_factory=dict)
    sidecars: tuple[SidecarFile, ...] = ()
    mode: int = 0o644
    skip_reason: str | None = None  # set by render fns when guards fail


@dataclass(frozen=True)
class EnvSpec:
    """Per-service env-file spec.

    ``enabled_check`` returns True when the service should have its
    ``.env`` rendered. Most services are simple ``"<svc>" in enabled``
    membership; some have additional guards (e.g. wikijs needs
    ``WIKIJS_DB_PASS`` non-empty, dify needs both DB + ADMIN passwords).
    The guard is encoded inside the render function (returning
    ``RenderedEnv(skip_reason=...)``) rather than the enabled_check
    so the result count carries the explicit reason.

    ``render`` is a pure callable: takes config + env, returns
    :class:`RenderedEnv`. No I/O — writing happens in
    :func:`render_all_env_files`.
    """

    service_name: str
    enabled_check: Callable[[list[str]], bool]
    render: Callable[[NexusConfig, BootstrapEnv], RenderedEnv]


@dataclass(frozen=True)
class ServiceRenderResult:
    service: str
    status: Literal["rendered", "skipped-not-enabled", "skipped-guard", "failed"]
    detail: str = ""


@dataclass(frozen=True)
class ServiceEnvResult:
    """Aggregate return from :func:`render_all_env_files`."""

    services: tuple[ServiceRenderResult, ...]

    @property
    def rendered(self) -> int:
        return sum(1 for s in self.services if s.status == "rendered")

    @property
    def skipped(self) -> int:
        return sum(1 for s in self.services if s.status.startswith("skipped"))

    @property
    def failed(self) -> int:
        return sum(1 for s in self.services if s.status == "failed")

    @property
    def is_success(self) -> bool:
        return self.failed == 0


class ServiceEnvError(Exception):
    """Raised for hard-fail conditions that should abort the deploy
    (e.g. SFTPGo with empty password — the legacy bash exits 1 with
    a red banner; the Python equivalent raises so the orchestrator
    surfaces rc=2)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_enabled(name: str) -> Callable[[list[str]], bool]:
    """Standard membership check used by most services."""
    return lambda enabled: name in enabled


def _empty(value: str | None) -> bool:
    """Treat None and "" identically — matches bash ``[ -z "$VAR" ]``."""
    return value is None or value == ""


def _escape_sql(value: str) -> str:
    """SQL-escape a value for a single-quoted string literal —
    doubles every single quote. Used for pg-ducklake's S3-secret
    bootstrap."""
    return value.replace("'", "''")


def _bcrypt_password(plaintext: str) -> str:
    """bcrypt-hash a password via the system ``htpasswd -nbBC 10``
    binary. ``htpasswd`` is provided by ``apache2-utils`` on the
    deploy runner; the binary path is not
    parameterised because every CI runner that runs this code has
    apache2-utils installed.

    Returns the bcrypt hash with ``$`` characters un-escaped; the
    caller (Filestash render) handles the docker-compose-specific
    ``$$`` escape since that's a transport-format concern, not a
    hash concern.
    """
    proc = subprocess.run(
        ["htpasswd", "-nbBC", "10", "x", plaintext],
        capture_output=True,
        text=True,
        check=True,
    )
    # htpasswd output: ``x:$2y$10$...``; we want everything after the ``x:``.
    line = proc.stdout.strip()
    return line.split(":", 1)[1]


# ---------------------------------------------------------------------------
# Per-service render functions
# ---------------------------------------------------------------------------
#
# Each returns a RenderedEnv (or RenderedEnv(skip_reason=...) when a
# guard fails).
#
# Convention: a config field that's None or "" produces an empty
# string in the rendered .env line — same as the bash ``${VAR:-}``
# expansion semantic. Tests pin this via per-stack snapshots.


def _render_infisical(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Infisical compose substitutes ENCRYPTION_KEY / AUTH_SECRET /
    POSTGRES_PASSWORD (no INFISICAL_ prefix)."""
    return RenderedEnv(
        env_vars={
            "ENCRYPTION_KEY": c.infisical_encryption_key or "",
            "AUTH_SECRET": c.infisical_auth_secret or "",
            "POSTGRES_PASSWORD": c.infisical_db_password or "",
        },
    )


_PROMETHEUS_REMOTE_WRITE_PLACEHOLDER = "# {{ REMOTE_WRITE_BLOCK }}"


def _render_prometheus_remote_write_block(e: BootstrapEnv) -> str:
    """Build the Prometheus ``remote_write`` config block for the
    grafana stack's prometheus.yml, or a no-op comment when the
    monitoring env vars are unset.

    Two guards must BOTH hold for an active ``remote_write`` block:
    (1) endpoint set, (2) token set. Either missing → the block becomes
    a single-line ``# remote_write disabled`` comment so Prometheus
    happily starts with today's behaviour. This is the
    backwards-compatibility contract from #607: existing stacks
    without Conductor-injected secrets see zero behaviour change.
    (``tenant_id`` is NOT a guard — it has a domain fallback at
    render time, so an unset tenant_id never disables the block.)

    SECURITY: the Bearer token lives inline in the rendered
    prometheus.yml. The file is mode 0o644 (must be readable by the
    non-root Prometheus container process — see :func:`_render_grafana`);
    secrecy rests on the host-access barrier (SSH behind CF Tunnel +
    email OTP). Tenant-label injection happens at the central vmauth
    proxy server-side; the relabel rule below is informational
    defense-in-depth (a malicious tenant can NOT use it to spoof
    another tenant's bucket).

    CARDINALITY: the ``go_*`` / ``process_*`` / ``promhttp_*`` drop
    relabel is the highest-priority cardinality defuse from
    Nexus-Conductor #23 — those series are useless for cross-stack
    monitoring and inflate the central VM's series count per stack.
    """
    endpoint = (e.monitoring_endpoint or "").strip()
    token = (e.monitoring_token or "").strip()
    if not endpoint or not token:
        return "# remote_write disabled — set MONITORING_ENDPOINT and MONITORING_TOKEN to enable"
    # Tenant defaults to the stack's domain when TENANT_ID is unset —
    # matches Conductor's expectation that each stack maps 1:1 to a
    # distinct token + tenant pair (its token IS what authorizes the
    # tenant label assignment at vmauth).
    tenant = (e.tenant_id or e.domain or "").strip()
    # Strip trailing slash on the endpoint so we don't end up with
    # `https://host//api/v1/write` — Prometheus would 404 on that.
    endpoint = endpoint.rstrip("/")
    # YAML quoting: emit url / credentials / replacement as JSON-quoted
    # strings. YAML 1.2 is a JSON superset, so any json.dumps(str)
    # output is a valid YAML scalar and handles every problematic
    # character (\" embedded quotes, \\ backslashes, leading {[!,
    # `: ` mapping separators, trailing `#` comment markers, control
    # chars). Without this, an operator-supplied endpoint or token
    # with a YAML-significant character would silently produce an
    # invalid prometheus.yml — Prometheus would refuse to start with
    # a parse error pointing at our generated file. Tokens from some
    # providers contain `=` padding and `_` / `-` which are safe, but
    # we don't want to hand-audit every possible token format.
    url_yaml = json.dumps(f"{endpoint}/api/v1/write")
    token_yaml = json.dumps(token)
    tenant_yaml = json.dumps(tenant)
    return (
        "remote_write:\n"
        f"  - url: {url_yaml}\n"
        "    authorization:\n"
        "      type: Bearer\n"
        f"      credentials: {token_yaml}\n"
        "    write_relabel_configs:\n"
        "      # Cardinality defuse (Conductor #23): drop Prometheus-runtime\n"
        "      # series that have no value for cross-stack monitoring.\n"
        "      - source_labels: [__name__]\n"
        "        regex: '(go_|process_|promhttp_).*'\n"
        "        action: drop\n"
        "      # Informational tenant label — vmauth enforces the real one\n"
        "      # server-side from the token mapping; this is defense-in-depth.\n"
        "      - target_label: tenant\n"
        f"        replacement: {tenant_yaml}\n"
    )


def _render_grafana(
    c: NexusConfig, e: BootstrapEnv, *, prometheus_template: str | None = None
) -> RenderedEnv:
    """Grafana env vars + generated ``prometheus.yml`` sidecar.

    Prometheus' YAML config doesn't support env-var substitution in
    ``remote_write.url`` / ``authorization.credentials`` (only
    ``external_labels`` + a couple of narrow places, per the
    Prometheus docs), so the URL + Bearer token must be baked into
    the config file at render time. We read ``prometheus.yml.template``
    from the grafana stack dir (the human-editable source) and replace
    the single ``{{ REMOTE_WRITE_BLOCK }}`` placeholder with either a
    real ``remote_write`` config or a one-line disabled comment.

    The template file itself is NOT consumed at runtime by Prometheus —
    only the generated ``prometheus.yml`` (gitignored) is bind-mounted
    into the container. Re-generated on every spin-up with the current
    env vars.

    Mode 0o644 (not 0o600 despite the token-in-cleartext): this file
    is bind-mounted into the prometheus container which runs as a
    non-root UID — a stricter mode would lock Prometheus itself out
    of its own config. Token secrecy still rests on the host-access
    barrier (SSH behind CF Tunnel + email OTP).
    """
    # Template content is normally injected by ``render_all_env_files``
    # via a special-case dispatch (parallel to jupyter's spark_enabled
    # kwarg) so the template lives under the same ``stacks_dir`` the
    # rest of the renderer writes into — works with the repo checkout,
    # with installed wheels (where ``stacks/`` is NOT in the
    # site-packages), and with non-standard stacks_dir paths (custom
    # test fixtures). The ``_load_prometheus_template()`` fallback is
    # kept for direct test callers that invoke ``_render_grafana``
    # without going through the orchestration layer.
    template = (
        prometheus_template if prometheus_template is not None else _load_prometheus_template()
    )
    # Fail-fast on template drift: if the placeholder is missing,
    # str.replace silently no-ops and the renderer would produce a
    # prometheus.yml without ANY remote_write block — even when the
    # operator has set MONITORING_ENDPOINT + MONITORING_TOKEN expecting
    # metrics to flow. Catch this at render time so the deploy aborts
    # with an actionable message instead of silently failing to push.
    if _PROMETHEUS_REMOTE_WRITE_PLACEHOLDER not in template:
        raise ServiceEnvError(
            "stacks/grafana/prometheus.yml.template is missing the "
            f"{_PROMETHEUS_REMOTE_WRITE_PLACEHOLDER!r} placeholder — "
            "remote_write rendering can't proceed. Restore the placeholder "
            "(usually at the very bottom of the template) or revert local "
            "edits to that file. Aborting to avoid a silent monitoring-off "
            "deploy.",
        )
    remote_write_block = _render_prometheus_remote_write_block(e)
    prometheus_yml = template.replace(
        _PROMETHEUS_REMOTE_WRITE_PLACEHOLDER, remote_write_block.rstrip("\n")
    )
    return RenderedEnv(
        env_vars={
            "GRAFANA_ADMIN_USER": c.admin_username or "admin",
            "GRAFANA_ADMIN_PASSWORD": c.grafana_admin_password or "",
        },
        sidecars=(
            # mode 0o644: this file is bind-mounted INTO the prometheus
            # container (see stacks/grafana/docker-compose.yml's
            # `./prometheus.yml:/etc/prometheus/prometheus.yml:ro`), and
            # the prom/prometheus image runs as a non-root UID (65534
            # since 2.x). A 0o600 file owned by the host deploy user
            # would be unreadable inside the container, causing
            # Prometheus to fail to start with "permission denied".
            # The Bearer token in this file is still protected by:
            # (a) host-level access requires SSH which is locked behind
            # the Cloudflare Tunnel + email OTP, (b) the same token is
            # already pushed to Infisical + lives in Actions secrets —
            # the file is not the only place it exists. Matches the
            # mode of other bind-mounted configs in this stack
            # (loki-config.yml, promtail-config.yml).
            SidecarFile(relative_path="prometheus.yml", content=prometheus_yml, mode=0o644),
        ),
    )


def _load_prometheus_template() -> str:
    """Load ``stacks/grafana/prometheus.yml.template`` from the repo.

    Resolved relative to this Python file: the package layout has
    ``src/nexus_deploy/service_env.py`` and ``stacks/grafana/...`` as
    siblings under the project root. Tests can monkey-patch this
    function to inject a fixture template.
    """
    project_root = Path(__file__).resolve().parents[2]
    template_path = project_root / "stacks" / "grafana" / "prometheus.yml.template"
    return template_path.read_text(encoding="utf-8")


def _render_dagster(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(env_vars={"DAGSTER_DB_PASSWORD": c.dagster_db_password or ""})


def _render_kestra(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(
        env_vars={
            "KESTRA_ADMIN_USER": e.admin_email or "",
            "KESTRA_ADMIN_PASSWORD": c.kestra_admin_password or "",
            "KESTRA_DB_PASSWORD": c.kestra_db_password or "",
            "KESTRA_URL": f"https://{service_host('kestra', e.domain or '', e.subdomain_separator)}",
        },
    )


def _render_cloudbeaver(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(
        env_vars={
            "CB_SERVER_NAME": "Nexus CloudBeaver",
            "CB_SERVER_URL": f"https://{service_host('cloudbeaver', e.domain or '', e.subdomain_separator)}",
            "CB_ADMIN_NAME": "nexus-cloudbeaver",
            "CB_ADMIN_PASSWORD": c.cloudbeaver_admin_password or "",
        },
    )


def _render_meilisearch(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Meilisearch: MEILI_MASTER_KEY gates ALL API endpoints (read +
    write + admin). CF Access at the edge is the outer perimeter; the
    master key is the inner per-request auth Meilisearch's own
    admin/data endpoints check.

    Fail-fast guard (same pattern as SFTPGo): if the master key is
    empty/missing we raise instead of silently writing an empty
    MEILI_MASTER_KEY into the .env. Without it Meilisearch with
    MEILI_ENV=production refuses to start, so silent-empty would
    produce a container that restart-loops with a cryptic error
    instead of a clear deploy-time failure pointing at the missing
    Tofu/Infisical sync. Most common cause for an empty key on an
    existing deploy: spin-up was run before initial-setup applied
    the new random_password.meilisearch_master_key resource —
    operator needs to `tofu apply` the stack module first."""
    if _empty(c.meilisearch_master_key):
        raise ServiceEnvError(
            "Meilisearch enabled but MEILI_MASTER_KEY is empty — run "
            "`tofu apply` (initial-setup workflow) to generate "
            "random_password.meilisearch_master_key + push to Infisical, "
            "then re-run spin-up. Aborting to avoid a restart-looping "
            "container with no auth.",
        )
    return RenderedEnv(env_vars={"MEILI_MASTER_KEY": c.meilisearch_master_key or ""})


def _render_hedgedoc(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """HedgeDoc: needs CMD_DOMAIN (composed from BootstrapEnv.domain
    + subdomain_separator), the random_password-backed session
    secret, and a dedicated Postgres password. The admin email +
    password used by the services-configure hook to seed the
    admin account are NOT rendered into ``.env`` — the hook reads
    them straight from :class:`NexusConfig` /
    :class:`BootstrapEnv`, and the docker-compose doesn't reference
    them either. We still guard their non-emptyness here so the
    failure mode (locked-out HedgeDoc with no admin) surfaces at
    the same deploy phase as the other missing secrets, with one
    actionable error message for the operator.

    Infisical naming reference (operators grepping the error
    message should find these keys directly):

    - ``/hedgedoc/HEDGEDOC_SESSION_SECRET`` — empty → HedgeDoc
      generates one at runtime and rotates it on every container
      restart, silently logging users out.
    - ``/hedgedoc/HEDGEDOC_DB_PASSWORD`` — empty → dedicated
      Postgres init crashes with a cryptic auth error.
    - ``/hedgedoc/HEDGEDOC_PASSWORD`` — empty → services-configure
      hook seeds an account with empty password, and with
      CMD_ALLOW_EMAIL_REGISTER=false (the post-#618 default)
      that leaves HedgeDoc with no way to log in at all.
    - ``/hedgedoc/HEDGEDOC_USERNAME`` (=BootstrapEnv.admin_email)
      — same failure mode as empty password.
    """
    missing = []
    if _empty(c.hedgedoc_session_secret):
        missing.append("HEDGEDOC_SESSION_SECRET (Infisical /hedgedoc)")
    if _empty(c.hedgedoc_db_password):
        missing.append("HEDGEDOC_DB_PASSWORD (Infisical /hedgedoc)")
    if _empty(c.hedgedoc_admin_password):
        missing.append("HEDGEDOC_PASSWORD (Infisical /hedgedoc)")
    if _empty(e.admin_email):
        missing.append("HEDGEDOC_USERNAME (Infisical /hedgedoc, = BootstrapEnv.admin_email)")
    if missing:
        raise ServiceEnvError(
            f"HedgeDoc enabled but {', '.join(missing)} empty — run "
            "`tofu apply` (initial-setup workflow) to generate "
            "random_password.hedgedoc_session_secret + "
            "random_password.hedgedoc_db_password + "
            "random_password.hedgedoc_admin "
            "+ push to Infisical, then re-run spin-up. Aborting to avoid "
            "an insecure-sessions / DB-auth-failure / lockout container.",
        )
    domain_host = service_host("hedgedoc", e.domain or "", e.subdomain_separator)
    return RenderedEnv(
        env_vars={
            "HEDGEDOC_SESSION_SECRET": c.hedgedoc_session_secret or "",
            "HEDGEDOC_DB_PASSWORD": c.hedgedoc_db_password or "",
            "HEDGEDOC_DOMAIN": domain_host,
        },
    )


def _render_lakekeeper(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Lakekeeper: Iceberg REST Catalog. Needs dedicated Postgres
    DSN + LAKEKEEPER__BASE_URI (double-underscore, that's Lakekeeper's
    nested-config separator convention) for absolute-URL generation in the
    catalog responses (Iceberg clients follow these to reach the
    metadata endpoints).

    Fail-fast guard (same pattern as Meilisearch / HedgeDoc): empty
    DB password crashes the Postgres init on first start with a
    cryptic auth-failed log. Abort at deploy time with a clear
    error pointing at the missing Tofu apply / Infisical sync.

    LAKEKEEPER_DOMAIN is composed from BootstrapEnv.domain via
    service_host so multi-tenant forks with subdomain_separator='-'
    get the flat-subdomain hostname (lakekeeper-user1.example.com)
    instead of lakekeeper.user1.example.com.
    """
    if _empty(c.lakekeeper_db_password):
        raise ServiceEnvError(
            "Lakekeeper enabled but LAKEKEEPER_DB_PASSWORD is empty — "
            "run `tofu apply` (initial-setup workflow) to generate "
            "random_password.lakekeeper_db_password + push to Infisical, "
            "then re-run spin-up. Aborting to avoid a restart-looping "
            "Postgres container with no auth.",
        )
    domain_host = service_host("lakekeeper", e.domain or "", e.subdomain_separator)
    return RenderedEnv(
        env_vars={
            "LAKEKEEPER_DB_PASSWORD": c.lakekeeper_db_password or "",
            "LAKEKEEPER_DOMAIN": domain_host,
        },
    )


def _render_evidence(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Evidence: SQL+markdown BI runtime. The bundled sample project
    queries the in-stack Postgres via env-var interpolation, so we
    pipe through the existing ``postgres_password`` field (no
    dedicated Evidence secret to manage) plus the absolute public
    URL Evidence uses for OG tags + canonical links.

    No fail-fast guard: Evidence renders pages even without a working
    data source (it just shows query errors inline), and the operator
    may legitimately be wiring an external warehouse instead of the
    in-stack Postgres. Leaving the password empty produces an
    "auth failed" message on the affected query rather than a crashed
    container.
    """
    domain_host = service_host("evidence", e.domain or "", e.subdomain_separator)
    return RenderedEnv(
        env_vars={
            "POSTGRES_PASSWORD": c.postgres_password or "",
            "EVIDENCE_BASE_URL": f"https://{domain_host}",
        },
    )


def _render_litellm(
    c: NexusConfig, e: BootstrapEnv, *, litellm_config_template: str | None = None
) -> RenderedEnv:
    """LiteLLM Proxy: env vars + a generated ``config.yaml`` sidecar
    that maps OpenAI-compatible model names to backend providers.

    The shipped ``config.yaml.template`` (in ``stacks/litellm/``) is the
    operator-editable source of truth — committed to git, survives
    spin-up cycles. The renderer copies it verbatim to the generated
    ``config.yaml`` (gitignored, bind-mounted into the container).
    Alternative operator workflow: add models via the /ui at runtime;
    STORE_MODEL_IN_DB persists those in Postgres across restarts.

    Template is normally injected by ``render_all_env_files`` (parallel
    to Grafana's ``prometheus_template`` dispatch) so it works with
    the repo checkout, with installed wheels, and with custom
    stacks_dir fixtures. The ``_load_litellm_config_template()``
    fallback is kept for direct test callers that bypass orchestration.

    Fail-fast guard: master key + salt key + DB password must all be
    set. Without master_key LiteLLM rejects all requests; without
    salt_key the DB-stored derived keys can't be verified; without
    db_password the Postgres init crashes.
    """
    if _empty(c.litellm_master_key) or _empty(c.litellm_salt_key) or _empty(c.litellm_db_password):
        missing = [
            name
            for name, value in (
                ("LITELLM_MASTER_KEY", c.litellm_master_key),
                ("LITELLM_SALT_KEY", c.litellm_salt_key),
                ("LITELLM_DB_PASSWORD", c.litellm_db_password),
            )
            if _empty(value)
        ]
        raise ServiceEnvError(
            f"LiteLLM enabled but {', '.join(missing)} empty — run "
            "`tofu apply` (initial-setup workflow) to generate the "
            "random_password.litellm_master_key + random_password.litellm_salt_key + "
            "random_password.litellm_db_password resources + push to "
            "Infisical, then re-run spin-up. Aborting to avoid an "
            "auth-bypass / DB-auth-failure container.",
        )
    config_yaml = (
        litellm_config_template
        if litellm_config_template is not None
        else _load_litellm_config_template()
    )
    return RenderedEnv(
        env_vars={
            "LITELLM_MASTER_KEY": c.litellm_master_key or "",
            "LITELLM_SALT_KEY": c.litellm_salt_key or "",
            "LITELLM_DB_PASSWORD": c.litellm_db_password or "",
            "LITELLM_UI_USERNAME": c.admin_username or "admin",
        },
        sidecars=(
            # mode 0o644: bind-mounted into the litellm container which
            # runs as non-root; the api_keys in this file (if any) are
            # protected by the host-access barrier (SSH behind CF Tunnel
            # + email OTP) just like .env files for other services.
            SidecarFile(relative_path="config.yaml", content=config_yaml, mode=0o644),
        ),
    )


def _load_litellm_config_template() -> str:
    """Load ``stacks/litellm/config.yaml.template`` from the repo.

    Resolved relative to this Python file. Tests can monkey-patch
    this function to inject a fixture template (same pattern as
    :func:`_load_prometheus_template`).
    """
    project_root = Path(__file__).resolve().parents[2]
    template_path = project_root / "stacks" / "litellm" / "config.yaml.template"
    return template_path.read_text(encoding="utf-8")


def _render_mage(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(env_vars={"MAGE_ADMIN_PASSWORD": c.mage_admin_password or ""})


def _render_minio(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(
        env_vars={
            "MINIO_ROOT_USER": "nexus-minio",
            "MINIO_ROOT_PASSWORD": c.minio_root_password or "",
        },
    )


def _render_sftpgo(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Fail-fast: empty admin OR user password aborts the deploy.

    Raises :class:`ServiceEnvError` so the CLI maps to rc=2. Mode
    0o600 because the file holds the admin credential in cleartext.
    """
    if _empty(c.sftpgo_admin_password) or _empty(c.sftpgo_user_password):
        raise ServiceEnvError(
            "SFTPGo: SFTPGO_ADMIN_PASSWORD and SFTPGO_USER_PASSWORD "
            "must both be set in SECRETS_JSON. Run `tofu apply` to "
            "regenerate the random_password resources.",
        )
    return RenderedEnv(
        env_vars={"SFTPGO_ADMIN_PASSWORD": c.sftpgo_admin_password or ""},
        mode=0o600,
    )


def _render_redpanda_console(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """The env var is REDPANDA_ADMIN_PASS (not _PASSWORD) — kept
    that way so external tooling/docs that read
    stacks/redpanda-console/.env see the same key."""
    return RenderedEnv(env_vars={"REDPANDA_ADMIN_PASS": c.redpanda_admin_password or ""})


def _render_hoppscotch(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    domain = e.domain or ""
    db_pass = c.hoppscotch_db_password or ""
    host = service_host("hoppscotch", domain, e.subdomain_separator)
    base = f"https://{host}"
    return RenderedEnv(
        env_vars={
            "DATABASE_URL": (
                f"postgres://nexus-hoppscotch:{db_pass}@hoppscotch-db:5432/hoppscotch"
            ),
            "POSTGRES_PASSWORD": db_pass,
            "JWT_SECRET": c.hoppscotch_jwt_secret or "",
            "SESSION_SECRET": c.hoppscotch_session_secret or "",
            "DATA_ENCRYPTION_KEY": c.hoppscotch_encryption_key or "",
            "REDIRECT_URL": base,
            "WHITELISTED_ORIGINS": base,
            "VITE_BASE_URL": base,
            "VITE_SHORTCODE_BASE_URL": base,
            "VITE_ADMIN_URL": f"{base}/admin",
            "VITE_BACKEND_GQL_URL": f"{base}/backend/graphql",
            "VITE_BACKEND_WS_URL": f"wss://{host}/backend/graphql",
            "VITE_BACKEND_API_URL": f"{base}/backend/v1",
            "VITE_ALLOWED_AUTH_PROVIDERS": "EMAIL",
            "MAILER_USE_CUSTOM_CONFIGS": "true",
            "MAILER_SMTP_ENABLE": "false",
            "TOKEN_SALT_COMPLEXITY": "10",
            "MAGIC_LINK_TOKEN_VALIDITY": "3",
            "REFRESH_TOKEN_VALIDITY": "604800000",
            "ACCESS_TOKEN_VALIDITY": "86400000",
            "ENABLE_SUBPATH_BASED_ACCESS": "false",
        },
    )


def _render_meltano(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(env_vars={"MELTANO_DB_PASSWORD": c.meltano_db_password or ""})


def _render_soda(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(env_vars={"SODA_DB_PASSWORD": c.soda_db_password or ""})


def _render_postgres(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(env_vars={"POSTGRES_PASSWORD": c.postgres_password or ""})


def _render_pg_ducklake(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Two-path bootstrap SQL emission.

    - **S3 path** (all 5 Hetzner vars present incl. region): emit
      ``duckdb.drop_secret('ducklake_s3')`` (idempotent, wrapped in
      DO/EXCEPTION) + ``duckdb.create_simple_secret(...)`` + ``ALTER
      SYSTEM SET ducklake.default_table_path = 's3://<bucket>/';``
      + ``SELECT pg_reload_conf();``.
    - **Local fallback** (any S3 var missing): emit ``ALTER SYSTEM
      SET ducklake.default_table_path = '/var/lib/ducklake/';
      SELECT pg_reload_conf();`` only — no drop_secret on the
      fallback path.

    The SQL goes into ``stacks/pg-ducklake/init/00-ducklake-bootstrap.sql``
    as a sidecar. pg-ducklake's container runs ``init/`` SQL files
    on first start; the per-spin-up re-apply for credential rotation
    is handled by the pg-ducklake admin-setup hook in
    :mod:`nexus_deploy.services`.
    """
    has_s3 = (
        bool(c.hetzner_s3_server)
        and bool(c.hetzner_s3_access_key)
        and bool(c.hetzner_s3_secret_key)
        and bool(c.hetzner_s3_bucket_pgducklake)
    )
    has_s3 = has_s3 and bool(c.hetzner_s3_region)
    if has_s3:
        bucket_sql = _escape_sql(c.hetzner_s3_bucket_pgducklake or "")
        sql = f"""-- Auto-generated by nexus_deploy.service_env.
-- Re-applied via 'docker exec ... psql -f' after every spin-up
-- to handle credential rotation.

-- Drop existing secret if present (idempotent for credential rotation)
DO $$ BEGIN
    PERFORM duckdb.drop_secret('ducklake_s3');
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- Create S3 secret for DuckLake Parquet storage
SELECT duckdb.create_simple_secret(
    type := 'S3',
    name := 'ducklake_s3',
    key_id := '{_escape_sql(c.hetzner_s3_access_key or "")}',
    secret := '{_escape_sql(c.hetzner_s3_secret_key or "")}',
    region := '{_escape_sql(c.hetzner_s3_region or "")}',
    endpoint := '{_escape_sql(c.hetzner_s3_server or "")}',
    url_style := 'path',
    scope := 's3://{bucket_sql}/'
);

-- Set default storage path for new DuckLake tables
ALTER SYSTEM SET ducklake.default_table_path = 's3://{bucket_sql}/';
SELECT pg_reload_conf();
"""
    else:
        sql = """-- Auto-generated by nexus_deploy.service_env.
-- No Hetzner Object Storage configured - using local volume fallback
ALTER SYSTEM SET ducklake.default_table_path = '/var/lib/ducklake/';
SELECT pg_reload_conf();
"""
    return RenderedEnv(
        env_vars={"PG_DUCKLAKE_PASSWORD": c.pgducklake_password or ""},
        sidecars=(SidecarFile(relative_path="init/00-ducklake-bootstrap.sql", content=sql),),
    )


def _render_pgadmin(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """pgAdmin .env + a sidecar ``pgpass`` file consumed by the
    pre-configured Nexus PostgreSQL server (servers.json references
    ``PassFile: /pgpass``).

    Format is the standard libpq pgpass: ``host:port:db:user:password``.
    Written 0o644 (not 0o600) because the file is owned by the
    deploy-runner user but read inside the container by the
    ``pgadmin`` user (uid 5050) — libpq's 0o600 check doesn't
    apply because pgAdmin uses the PassFile via its own loader,
    not libpq. The file lives at /opt/docker-server/stacks/pgadmin/
    on the host, only reachable via SSH (CF Tunnel + key auth).
    """
    pgpass_content = f"postgres:5432:postgres:nexus-postgres:{c.postgres_password or ''}\n"
    return RenderedEnv(
        env_vars={
            "ADMIN_EMAIL": e.admin_email or "",
            "PGADMIN_PASSWORD": c.pgadmin_password or "",
        },
        sidecars=(SidecarFile(relative_path="pgpass", content=pgpass_content, mode=0o644),),
    )


def _render_prefect(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Prefect: DB + UI vars + R2 credentials.

    R2_* are exposed in stacks/prefect/.env (the same pattern Jupyter
    uses for HETZNER_S3_*) so seeded flows can read them via
    ``os.environ["R2_ENDPOINT"]`` etc. without a separate Infisical
    secret-sync setup. Empty values are kept as empty strings — the
    flow can detect that and raise a clear 'configure R2 first'
    error instead of crashing with KeyError at runtime.
    """
    return RenderedEnv(
        env_vars={
            "PREFECT_DB_PASSWORD": c.prefect_db_password or "",
            "PREFECT_UI_API_URL": f"https://{service_host('prefect', e.domain or '', e.subdomain_separator)}/api",
            "R2_ENDPOINT": c.r2_data_endpoint or "",
            "R2_ACCESS_KEY": c.r2_data_access_key or "",
            "R2_SECRET_KEY": c.r2_data_secret_key or "",
            "R2_BUCKET": c.r2_data_bucket or "",
        },
    )


def _render_windmill(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(
        env_vars={
            "WINDMILL_DB_PASSWORD": c.windmill_db_password or "",
            "WINDMILL_SUPERADMIN_SECRET": c.windmill_superadmin_secret or "",
            "DOMAIN": e.domain or "",
        },
    )


def _render_superset(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(
        env_vars={
            "SUPERSET_ADMIN_PASSWORD": c.superset_admin_password or "",
            "SUPERSET_DB_PASSWORD": c.superset_db_password or "",
            "SUPERSET_SECRET_KEY": c.superset_secret_key or "",
            "ADMIN_EMAIL": e.admin_email or "",
            "DOMAIN": e.domain or "",
        },
    )


def _render_openmetadata(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """OpenMetadata admin password is NOT written to .env. It's
    pushed to Infisical (key ``OPENMETADATA_PASSWORD``) and applied
    to the running stack via REST in :func:`services.run_admin_setups`.
    Writing it here would only widen the on-disk secret-exposure
    surface."""
    return RenderedEnv(
        env_vars={
            "OPENMETADATA_DB_PASSWORD": c.openmetadata_db_password or "",
            "OPENMETADATA_AIRFLOW_PASSWORD": c.openmetadata_airflow_password or "",
            "OPENMETADATA_FERNET_KEY": c.openmetadata_fernet_key or "",
            "OPENMETADATA_PRINCIPAL_DOMAIN": e.om_principal_domain or "",
        },
    )


def _render_gitea(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(
        env_vars={
            "GITEA_DB_PASSWORD": c.gitea_db_password or "",
            "DOMAIN": e.domain or "",
        },
    )


def _render_clickhouse(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(env_vars={"CLICKHOUSE_ADMIN_PASSWORD": c.clickhouse_admin_password or ""})


def _render_trino(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Cross-service references: Trino's catalog connectors need the
    ClickHouse admin password and Postgres password from THEIR
    respective tofu secrets, not Trino's own. Pulls directly from
    the same NexusConfig."""
    return RenderedEnv(
        env_vars={
            "CLICKHOUSE_ADMIN_PASSWORD": c.clickhouse_admin_password or "",
            "POSTGRES_PASSWORD": c.postgres_password or "",
        },
    )


def _render_rustfs(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    return RenderedEnv(
        env_vars={
            "RUSTFS_ACCESS_KEY": "nexus-rustfs",
            "RUSTFS_SECRET_KEY": c.rustfs_root_password or "",
        },
    )


def _render_seaweedfs(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """SeaweedFS: .env + s3.json sidecar with admin identity."""
    s3_json = json.dumps(
        {
            "identities": [
                {
                    "name": "admin",
                    "credentials": [
                        {
                            "accessKey": "nexus-seaweedfs",
                            "secretKey": c.seaweedfs_admin_password or "",
                        },
                    ],
                    "actions": ["Admin", "Read", "Write", "List", "Tagging"],
                },
            ],
        },
        indent=2,
    )
    return RenderedEnv(
        env_vars={
            "SEAWEEDFS_ACCESS_KEY": "nexus-seaweedfs",
            "SEAWEEDFS_SECRET_KEY": c.seaweedfs_admin_password or "",
        },
        sidecars=(SidecarFile(relative_path="s3.json", content=s3_json + "\n"),),
    )


def _render_garage(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Garage: .env (admin token only) + garage.toml sidecar with
    full configuration. The ``root_domain`` values
    (``.s3.garage.localhost`` / ``.web.garage.localhost``) are pinned
    by Garage's CLI bucket-resolution logic — do NOT change without
    auditing that behaviour."""
    toml = f"""# Auto-generated by nexus_deploy.service_env.
metadata_dir = "/var/lib/garage/meta"
data_dir = "/var/lib/garage/data"
db_engine = "lmdb"
replication_factor = 1

rpc_bind_addr = "[::]:3901"
rpc_secret = "{c.garage_rpc_secret or ""}"

[s3_api]
s3_region = "garage"
api_bind_addr = "[::]:3900"
root_domain = ".s3.garage.localhost"

[s3_web]
bind_addr = "[::]:3902"
root_domain = ".web.garage.localhost"

[admin]
api_bind_addr = "[::]:3903"
admin_token = "{c.garage_admin_token or ""}"
"""
    return RenderedEnv(
        env_vars={"GARAGE_ADMIN_TOKEN": c.garage_admin_token or ""},
        sidecars=(SidecarFile(relative_path="garage.toml", content=toml),),
    )


def _render_lakefs(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Two-path: Hetzner S3 backend if all 4 S3 vars set, else local
    blockstore."""
    has_s3 = (
        bool(c.hetzner_s3_server)
        and bool(c.hetzner_s3_region)
        and bool(c.hetzner_s3_access_key)
        and bool(c.hetzner_s3_secret_key)
    )
    db_pass = c.lakefs_db_password or ""
    domain = e.domain or ""
    common = {
        "LAKEFS_DATABASE_TYPE": "postgres",
        "LAKEFS_DATABASE_POSTGRES_CONNECTION_STRING": (
            f"postgres://nexus-lakefs:{db_pass}@lakefs-db:5432/lakefs?sslmode=disable"
        ),
        "LAKEFS_AUTH_ENCRYPT_SECRET_KEY": c.lakefs_encrypt_secret or "",
        # ``s3.`` is the sub-prefix lakefs uses for virtual-host-style
        # S3 routing; it's prepended to whatever the operator-facing
        # ``lakefs`` hostname resolves to. For dot-form tenants the
        # full hostname is ``s3.lakefs.example.com``; for flat-
        # subdomain tenants it's ``s3.lakefs-user1.example.com``.
        "LAKEFS_GATEWAYS_S3_DOMAIN_NAME": (
            f"s3.{service_host('lakefs', domain, e.subdomain_separator)}"
        ),
        "POSTGRES_PASSWORD": db_pass,
    }
    if has_s3:
        s3_block = {
            "LAKEFS_BLOCKSTORE_TYPE": "s3",
            "LAKEFS_BLOCKSTORE_S3_ENDPOINT": f"https://{c.hetzner_s3_server}",
            "LAKEFS_BLOCKSTORE_S3_FORCE_PATH_STYLE": "true",
            "LAKEFS_BLOCKSTORE_S3_DISCOVER_BUCKET_REGION": "false",
            "LAKEFS_BLOCKSTORE_S3_REGION": c.hetzner_s3_region or "",
            "LAKEFS_BLOCKSTORE_S3_CREDENTIALS_ACCESS_KEY_ID": c.hetzner_s3_access_key or "",
            "LAKEFS_BLOCKSTORE_S3_CREDENTIALS_SECRET_ACCESS_KEY": c.hetzner_s3_secret_key or "",
        }
    else:
        s3_block = {
            "LAKEFS_BLOCKSTORE_TYPE": "local",
            "LAKEFS_BLOCKSTORE_LOCAL_PATH": "/data",
        }
    # Order matters for snapshot stability.
    ordered: dict[str, str] = {}
    ordered["LAKEFS_DATABASE_TYPE"] = common["LAKEFS_DATABASE_TYPE"]
    ordered["LAKEFS_DATABASE_POSTGRES_CONNECTION_STRING"] = common[
        "LAKEFS_DATABASE_POSTGRES_CONNECTION_STRING"
    ]
    ordered["LAKEFS_AUTH_ENCRYPT_SECRET_KEY"] = common["LAKEFS_AUTH_ENCRYPT_SECRET_KEY"]
    for k, v in s3_block.items():
        ordered[k] = v
    ordered["LAKEFS_GATEWAYS_S3_DOMAIN_NAME"] = common["LAKEFS_GATEWAYS_S3_DOMAIN_NAME"]
    ordered["POSTGRES_PASSWORD"] = common["POSTGRES_PASSWORD"]
    return RenderedEnv(env_vars=ordered)


def _render_filestash(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Filestash: bcrypt admin password + conditional CONFIG_JSON
    base64.

    Special handling:
    - If admin password is set, run ``htpasswd -nbBC 10`` to generate
      bcrypt hash. Escape ``$`` → ``$$`` for docker-compose env parsing.
    - Each S3 backend (R2 / Hetzner / External) gates on
      endpoint+access+secret+bucket — empty bucket disables that
      connection (mirrors legacy ``[ -n "$X_BUCKET" ]`` guards).
    - CONFIG_JSON shape matches legacy: ``connections`` list (label
      + type=s3) + ``middleware.identity_provider`` (passthrough,
      direct strategy) + ``middleware.attribute_mapping`` with
      ``related_backend`` (label of first configured backend) and
      ``params`` (per-label dict, with full S3 creds; path encoded
      as ``/<bucket>/`` — leading + trailing slash). The two ``params``
      values are JSON-stringified because Filestash encrypts them
      individually.
    """
    label_r2 = "R2 Datalake"
    label_hetzner = "Hetzner Storage"
    domain = e.domain or ""
    admin_hash = ""
    if not _empty(c.filestash_admin_password):
        raw = _bcrypt_password(c.filestash_admin_password or "")
        admin_hash = raw.replace("$", "$$")
    has_r2 = bool(
        c.r2_data_endpoint and c.r2_data_access_key and c.r2_data_secret_key and c.r2_data_bucket,
    )
    has_hetzner = bool(
        c.hetzner_s3_server
        and c.hetzner_s3_access_key
        and c.hetzner_s3_secret_key
        and c.hetzner_s3_bucket_general,
    )
    has_external = bool(
        c.external_s3_endpoint
        and c.external_s3_access_key
        and c.external_s3_secret_key
        and c.external_s3_bucket,
    )
    has_any_s3 = has_r2 or has_hetzner or has_external

    env_vars = {
        "ADMIN_PASSWORD": admin_hash,
        "DOMAIN": domain,
    }
    if has_any_s3:
        connections: list[dict[str, str]] = []
        params: dict[str, dict[str, str]] = {}
        related_backend = ""
        if has_r2:
            connections.append({"type": "s3", "label": label_r2})
            params[label_r2] = {
                "type": "s3",
                "access_key_id": c.r2_data_access_key or "",
                "secret_access_key": c.r2_data_secret_key or "",
                "endpoint": c.r2_data_endpoint or "",
                "region": "auto",
                "path": f"/{c.r2_data_bucket or ''}/",
            }
            related_backend = label_r2
        if has_hetzner:
            connections.append({"type": "s3", "label": label_hetzner})
            params[label_hetzner] = {
                "type": "s3",
                "access_key_id": c.hetzner_s3_access_key or "",
                "secret_access_key": c.hetzner_s3_secret_key or "",
                "endpoint": f"https://{c.hetzner_s3_server}",
                "region": c.hetzner_s3_region or "",
                "path": f"/{c.hetzner_s3_bucket_general or ''}/",
            }
            if not related_backend:
                related_backend = label_hetzner
        if has_external:
            ext_label = c.external_s3_label or "External Storage"
            connections.append({"type": "s3", "label": ext_label})
            params[ext_label] = {
                "type": "s3",
                "access_key_id": c.external_s3_access_key or "",
                "secret_access_key": c.external_s3_secret_key or "",
                "endpoint": c.external_s3_endpoint or "",
                "region": c.external_s3_region or "",
                "path": f"/{c.external_s3_bucket or ''}/",
            }
            if not related_backend:
                related_backend = ext_label
        config: dict[str, object] = {
            "connections": connections,
            "middleware": {
                "identity_provider": {
                    "type": "passthrough",
                    "params": json.dumps({"strategy": "direct"}),
                },
                "attribute_mapping": {
                    "related_backend": related_backend,
                    "params": json.dumps(params),
                },
            },
        }
        config_b64 = base64.b64encode(json.dumps(config).encode("utf-8")).decode("ascii")
        # Insert CONFIG_JSON BEFORE ADMIN_PASSWORD to match legacy ordering.
        env_vars = {
            "CONFIG_JSON": config_b64,
            "ADMIN_PASSWORD": admin_hash,
            "DOMAIN": domain,
        }
    return RenderedEnv(env_vars=env_vars)


def _render_woodpecker(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Guard: skip if WOODPECKER_AGENT_SECRET is empty.

    Gitea OAuth client+secret start as empty placeholders (compose
    substitutes ``${WOODPECKER_GITEA_CLIENT}`` without ``:-``, so
    the keys MUST exist in .env even before the OAuth phase
    populates them). The real values are appended later by the
    ``_phase_woodpecker_apply`` orchestrator phase."""
    if _empty(c.woodpecker_agent_secret):
        return RenderedEnv(skip_reason="WOODPECKER_AGENT_SECRET empty")
    return RenderedEnv(
        env_vars={
            "DOMAIN": e.domain or "",
            "WOODPECKER_AGENT_SECRET": c.woodpecker_agent_secret or "",
            "WOODPECKER_ADMIN": c.admin_username or "",
            "WOODPECKER_GITEA_CLIENT": "",
            "WOODPECKER_GITEA_SECRET": "",
        },
    )


def _render_spark(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Spark: optional Hetzner S3 + worker config defaults."""
    s3_endpoint = f"https://{c.hetzner_s3_server}" if c.hetzner_s3_server else ""
    return RenderedEnv(
        env_vars={
            "HETZNER_S3_ENDPOINT": s3_endpoint,
            "HETZNER_S3_ACCESS_KEY": c.hetzner_s3_access_key or "",
            "HETZNER_S3_SECRET_KEY": c.hetzner_s3_secret_key or "",
            "HETZNER_S3_BUCKET": c.hetzner_s3_bucket_general or "",
            "SPARK_WORKER_CORES": "2",
            "SPARK_WORKER_MEMORY": "3g",
        },
    )


def _render_flink(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    s3_endpoint = f"https://{c.hetzner_s3_server}" if c.hetzner_s3_server else ""
    return RenderedEnv(
        env_vars={
            "HETZNER_S3_ENDPOINT": s3_endpoint,
            "HETZNER_S3_ACCESS_KEY": c.hetzner_s3_access_key or "",
            "HETZNER_S3_SECRET_KEY": c.hetzner_s3_secret_key or "",
            "HETZNER_S3_BUCKET": c.hetzner_s3_bucket_general or "",
            "FLINK_TASKMANAGER_SLOTS": "2",
        },
    )


def _render_dinky(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Dinky: admin password optional. If empty, the .env is still
    rendered (dinky uses its own internal default password); no
    operator warning is plumbed through — Dinky's first-login flow
    forces a password change anyway."""
    return RenderedEnv(env_vars={"DINKY_ADMIN_PASSWORD": c.dinky_admin_password or ""})


def _render_jupyter(c: NexusConfig, e: BootstrapEnv, *, spark_enabled: bool) -> RenderedEnv:
    """Jupyter: SPARK_MASTER conditional on whether the spark stack
    is enabled.

    The ``spark_enabled`` arg is injected by :func:`render_all_env_files`
    so the render function stays pure (no global state)."""
    spark_master = "spark://spark-master:7077" if spark_enabled else "local[*]"
    s3_endpoint = f"https://{c.hetzner_s3_server}" if c.hetzner_s3_server else ""
    return RenderedEnv(
        env_vars={
            "SPARK_MASTER": spark_master,
            "HETZNER_S3_ENDPOINT": s3_endpoint,
            "HETZNER_S3_ACCESS_KEY": c.hetzner_s3_access_key or "",
            "HETZNER_S3_SECRET_KEY": c.hetzner_s3_secret_key or "",
            "HETZNER_S3_BUCKET": c.hetzner_s3_bucket_general or "",
        },
    )


def _render_marimo(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Marimo: HETZNER_S3_* land in ``.infisical.env`` via the
    secret-sync block (same pattern as Jupyter), and the Gitea
    workspace coordinates land in ``.env`` via
    :func:`append_gitea_workspace_block` AFTER this render runs.

    This render itself emits no env vars — but it MUST exist so
    that ``stacks/marimo/.env`` is created (even if empty); without
    a base file, the Gitea-append helper sees ``not env_path.exists()``
    and silently skips, leaving Marimo with no ``GITEA_REPO_URL`` /
    ``GITEA_USERNAME`` / ``GITEA_PASSWORD`` / ``REPO_NAME`` plumbed
    through to the container — the bug the user observed in
    initial-setup test surfaced — Marimo wasn't connected to Gitea
    and the workspace repo wasn't visible in the Marimo UI.

    SPARK_CONNECT_URL is hardcoded in stacks/marimo/docker-compose.yml's
    ``environment:`` block at ``sc://spark-connect:15002``. Compose
    gives ``environment:`` precedence over values coming from
    ``env_file:`` (.env / .infisical.env), so:
      - We deliberately don't write SPARK_CONNECT_URL to .env here.
      - Setting it as an Infisical secret would land in
        ``.infisical.env`` but be SHADOWED by the compose
        ``environment:`` value — Infisical override won't actually
        take effect.
    To swap clusters, edit the ``SPARK_CONNECT_URL`` line in
    stacks/marimo/docker-compose.yml directly (or override it with
    a docker-compose.override.yml) — there is no env-file path that
    can replace the value.
    """
    del c, e  # no derived vars at the moment; the file is intentionally minimal
    return RenderedEnv(env_vars={})


def _render_code_server(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """code-server: Gitea-append pattern (like Marimo).

    The ``.env`` file is unconditionally created so
    :func:`append_gitea_workspace_block` can append the Gitea workspace
    block — same bug-class fix as the Marimo placeholder (commit
    fb586ab). Without the .env file, the Gitea-append step silently
    skips and the entrypoint can't clone the workspace repo.

    All other code-server config lives in the docker-compose.yml's
    entrypoint (clone logic, --auth flag, extension-seed-on-first-start
    copy) or in the image (dbt venv, DuckDB CLI).
    """
    del c, e  # no derived vars
    return RenderedEnv(env_vars={})


def _render_s3manager(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """s3manager consumes generic ACCESS_KEY_ID / SECRET_ACCESS_KEY /
    REGION / ENDPOINT (not Hetzner-prefixed)."""
    return RenderedEnv(
        env_vars={
            "ACCESS_KEY_ID": c.hetzner_s3_access_key or "",
            "SECRET_ACCESS_KEY": c.hetzner_s3_secret_key or "",
            "REGION": c.hetzner_s3_region or "",
            "ENDPOINT": c.hetzner_s3_server or "",
            "USE_SSL": "true",
        },
    )


def _render_wikijs(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Guard: WIKIJS_DB_PASS must be non-empty."""
    if _empty(c.wikijs_db_password):
        return RenderedEnv(skip_reason="WIKIJS_DB_PASS empty")
    return RenderedEnv(env_vars={"WIKIJS_DB_PASSWORD": c.wikijs_db_password or ""})


def _render_appsmith(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Dual guard: APPSMITH_ENCRYPTION_PASSWORD AND _SALT both required."""
    if _empty(c.appsmith_encryption_password) or _empty(c.appsmith_encryption_salt):
        return RenderedEnv(
            skip_reason="APPSMITH_ENCRYPTION_PASSWORD + _SALT both required",
        )
    return RenderedEnv(
        env_vars={
            "APPSMITH_ENCRYPTION_PASSWORD": c.appsmith_encryption_password or "",
            "APPSMITH_ENCRYPTION_SALT": c.appsmith_encryption_salt or "",
            "APPSMITH_DISABLE_TELEMETRY": "true",
            "APPSMITH_DISABLE_INTERCOM": "true",
        },
    )


def _render_nocodb(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Triple guard: DB_PASS + ADMIN_PASS + JWT_SECRET all required."""
    if (
        _empty(c.nocodb_db_password)
        or _empty(c.nocodb_admin_password)
        or _empty(c.nocodb_jwt_secret)
    ):
        return RenderedEnv(skip_reason="NOCODB_DB_PASS + _ADMIN_PASS + _JWT_SECRET all required")
    db_pass = c.nocodb_db_password or ""
    return RenderedEnv(
        env_vars={
            "NC_DB": f"pg://nocodb-db:5432?u=nexus-nocodb&p={db_pass}&d=nocodb",
            "NC_AUTH_JWT_SECRET": c.nocodb_jwt_secret or "",
            "NC_ADMIN_EMAIL": e.admin_email or "",
            "NC_ADMIN_PASSWORD": c.nocodb_admin_password or "",
            "NC_PUBLIC_URL": f"https://{service_host('nocodb', e.domain or '', e.subdomain_separator)}",
            "NOCODB_DB_PASSWORD": db_pass,
        },
    )


def _render_dify(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Dual guard: DIFY_DB_PASS + DIFY_ADMIN_PASS both required."""
    if _empty(c.dify_db_password) or _empty(c.dify_admin_password):
        return RenderedEnv(skip_reason="DIFY_DB_PASS + _ADMIN_PASS both required")
    return RenderedEnv(
        env_vars={
            "DIFY_DB_PASSWORD": c.dify_db_password or "",
            "DIFY_REDIS_PASSWORD": c.dify_redis_password or "",
            "DIFY_SECRET_KEY": c.dify_secret_key or "",
            "DIFY_ADMIN_PASSWORD": c.dify_admin_password or "",
            "DIFY_WEAVIATE_API_KEY": c.dify_weaviate_api_key or "",
            "DIFY_SANDBOX_API_KEY": c.dify_sandbox_api_key or "",
            "DIFY_PLUGIN_DAEMON_KEY": c.dify_plugin_daemon_key or "",
            "DIFY_PLUGIN_INNER_API_KEY": c.dify_plugin_inner_api_key or "",
        },
    )


# ---------------------------------------------------------------------------
# Spec table — order is stable across releases for snapshot diffs.
# ---------------------------------------------------------------------------


# Wrapper for cross-spec dependencies. Jupyter needs the spark-enabled
# flag, which can't be baked into a static EnvSpec because it depends
# on which OTHER stacks the operator has enabled. The placeholder sits
# in _SPECS for ordering; the real render is invoked via the
# cross-spec branch inside render_all_env_files below.
def _placeholder_jupyter(c: NexusConfig, e: BootstrapEnv) -> RenderedEnv:
    """Never invoked at runtime — see render_all_env_files."""
    raise NotImplementedError(
        "jupyter render needs spark_enabled context; should be dispatched via "
        "the cross-spec branch in render_all_env_files, not via this placeholder",
    )


_SPECS: tuple[EnvSpec, ...] = (
    EnvSpec("infisical", _is_enabled("infisical"), _render_infisical),
    EnvSpec("grafana", _is_enabled("grafana"), _render_grafana),
    EnvSpec("dagster", _is_enabled("dagster"), _render_dagster),
    EnvSpec("kestra", _is_enabled("kestra"), _render_kestra),
    EnvSpec("cloudbeaver", _is_enabled("cloudbeaver"), _render_cloudbeaver),
    EnvSpec("meilisearch", _is_enabled("meilisearch"), _render_meilisearch),
    EnvSpec("hedgedoc", _is_enabled("hedgedoc"), _render_hedgedoc),
    EnvSpec("litellm", _is_enabled("litellm"), _render_litellm),
    EnvSpec("lakekeeper", _is_enabled("lakekeeper"), _render_lakekeeper),
    EnvSpec("evidence", _is_enabled("evidence"), _render_evidence),
    EnvSpec("mage", _is_enabled("mage"), _render_mage),
    EnvSpec("minio", _is_enabled("minio"), _render_minio),
    EnvSpec("sftpgo", _is_enabled("sftpgo"), _render_sftpgo),
    EnvSpec("redpanda-console", _is_enabled("redpanda-console"), _render_redpanda_console),
    EnvSpec("hoppscotch", _is_enabled("hoppscotch"), _render_hoppscotch),
    EnvSpec("meltano", _is_enabled("meltano"), _render_meltano),
    EnvSpec("soda", _is_enabled("soda"), _render_soda),
    EnvSpec("postgres", _is_enabled("postgres"), _render_postgres),
    EnvSpec("pg-ducklake", _is_enabled("pg-ducklake"), _render_pg_ducklake),
    EnvSpec("pgadmin", _is_enabled("pgadmin"), _render_pgadmin),
    EnvSpec("prefect", _is_enabled("prefect"), _render_prefect),
    EnvSpec("windmill", _is_enabled("windmill"), _render_windmill),
    EnvSpec("superset", _is_enabled("superset"), _render_superset),
    EnvSpec("openmetadata", _is_enabled("openmetadata"), _render_openmetadata),
    EnvSpec("gitea", _is_enabled("gitea"), _render_gitea),
    EnvSpec("clickhouse", _is_enabled("clickhouse"), _render_clickhouse),
    EnvSpec("trino", _is_enabled("trino"), _render_trino),
    EnvSpec("rustfs", _is_enabled("rustfs"), _render_rustfs),
    EnvSpec("seaweedfs", _is_enabled("seaweedfs"), _render_seaweedfs),
    EnvSpec("garage", _is_enabled("garage"), _render_garage),
    EnvSpec("lakefs", _is_enabled("lakefs"), _render_lakefs),
    EnvSpec("filestash", _is_enabled("filestash"), _render_filestash),
    EnvSpec("woodpecker", _is_enabled("woodpecker"), _render_woodpecker),
    EnvSpec("spark", _is_enabled("spark"), _render_spark),
    EnvSpec("flink", _is_enabled("flink"), _render_flink),
    EnvSpec("dinky", _is_enabled("dinky"), _render_dinky),
    EnvSpec("jupyter", _is_enabled("jupyter"), _placeholder_jupyter),  # closure-replaced
    EnvSpec("marimo", _is_enabled("marimo"), _render_marimo),
    EnvSpec("code-server", _is_enabled("code-server"), _render_code_server),
    EnvSpec("s3manager", _is_enabled("s3manager"), _render_s3manager),
    EnvSpec("wikijs", _is_enabled("wikijs"), _render_wikijs),
    EnvSpec("appsmith", _is_enabled("appsmith"), _render_appsmith),
    EnvSpec("nocodb", _is_enabled("nocodb"), _render_nocodb),
    EnvSpec("dify", _is_enabled("dify"), _render_dify),
)


# ---------------------------------------------------------------------------
# Atomic write + orchestration
# ---------------------------------------------------------------------------


def _format_env_line(key: str, value: str) -> str:
    """Render a single ``KEY=value`` line: no quoting, value as-is,
    newline-terminated.

    Values containing newlines or shell meta-characters are caught
    at the NexusConfig validation layer (random_password resources
    don't produce newlines, so the unquoted form is safe).
    """
    return f"{key}={value}\n"


def _render_env_file_content(env_vars: dict[str, str]) -> str:
    """Build the full ``.env`` file content from the dict."""
    return "".join(_format_env_line(k, v) for k, v in env_vars.items())


def _atomic_write(target: Path, content: str, *, mode: int = 0o644) -> None:
    """Write content to target atomically. mkstemp in same dir +
    fchmod + fdopen + replace. Same pattern as
    :func:`setup.configure_ssh`."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_str)
    fd_owned_by_caller = True
    try:
        try:
            os.fchmod(fd, mode)
        except Exception:
            os.close(fd)
            fd_owned_by_caller = False
            raise
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            fd_owned_by_caller = False
            f.write(content)
        tmp_path.replace(target)
    except Exception:
        if fd_owned_by_caller:
            with contextlib.suppress(OSError):
                os.close(fd)
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def render_all_env_files(
    config: NexusConfig,
    env: BootstrapEnv,
    enabled: list[str],
    *,
    stacks_dir: Path,
) -> ServiceEnvResult:
    """For each spec where ``enabled_check`` returns True, call its
    render function and write the result.

    Returns counts (rendered, skipped, failed). Hard-fail conditions
    (SFTPGo with empty password) raise :class:`ServiceEnvError` —
    the caller (CLI) maps to rc=2.
    """
    results: list[ServiceRenderResult] = []
    spark_enabled = "spark" in enabled
    # Grafana renders ``prometheus.yml`` from a template that lives
    # alongside the docker-compose at ``stacks_dir/grafana/``. Read it
    # ONCE here so the renderer stays a pure (config, env) → result
    # function and operationally works regardless of where the package
    # was installed from. If grafana is enabled, the template MUST be
    # in stacks_dir — silent fallback to a repo-relative loader would
    # either fail with a confusing site-packages path or render from
    # a totally different file than the operator is editing.
    prometheus_template: str | None = None
    if "grafana" in enabled:
        template_path = stacks_dir / "grafana" / "prometheus.yml.template"
        try:
            prometheus_template = template_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ServiceEnvError(
                f"grafana enabled but prometheus.yml.template is unreadable at "
                f"{template_path} ({type(exc).__name__}). The template ships with "
                "stacks/grafana/ and must be present in the stacks_dir passed to "
                "render_all_env_files. Restore the file (re-clone the repo or "
                "git checkout stacks/grafana/prometheus.yml.template) or disable "
                "grafana before retrying.",
            ) from exc

    # LiteLLM: same template-loading pattern as Grafana — config.yaml
    # lives at stacks_dir/litellm/config.yaml.template (operator-editable
    # source of truth) and the renderer copies it to the generated
    # config.yaml. Fail-fast if grafana-style: template MUST be present
    # when the service is enabled.
    litellm_config_template: str | None = None
    if "litellm" in enabled:
        litellm_template_path = stacks_dir / "litellm" / "config.yaml.template"
        try:
            litellm_config_template = litellm_template_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ServiceEnvError(
                f"litellm enabled but config.yaml.template is unreadable at "
                f"{litellm_template_path} ({type(exc).__name__}). The template "
                "ships with stacks/litellm/ and must be present in the "
                "stacks_dir passed to render_all_env_files. Restore the file "
                "(re-clone the repo or git checkout "
                "stacks/litellm/config.yaml.template) or disable litellm "
                "before retrying.",
            ) from exc

    for spec in _SPECS:
        if not spec.enabled_check(enabled):
            results.append(
                ServiceRenderResult(service=spec.service_name, status="skipped-not-enabled"),
            )
            continue

        # Cross-spec dependencies: jupyter needs spark_enabled, grafana
        # needs the prometheus.yml.template loaded from stacks_dir.
        if spec.service_name == "jupyter":
            rendered = _render_jupyter(config, env, spark_enabled=spark_enabled)
        elif spec.service_name == "grafana":
            rendered = _render_grafana(config, env, prometheus_template=prometheus_template)
        elif spec.service_name == "litellm":
            rendered = _render_litellm(config, env, litellm_config_template=litellm_config_template)
        else:
            rendered = spec.render(config, env)

        if rendered.skip_reason is not None:
            results.append(
                ServiceRenderResult(
                    service=spec.service_name,
                    status="skipped-guard",
                    detail=rendered.skip_reason,
                ),
            )
            continue

        # Write the .env file (overwrite).
        env_path = stacks_dir / spec.service_name / ".env"
        env_content = _render_env_file_content(rendered.env_vars)
        try:
            _atomic_write(env_path, env_content, mode=rendered.mode)
            for sidecar in rendered.sidecars:
                sidecar_path = stacks_dir / spec.service_name / sidecar.relative_path
                _atomic_write(sidecar_path, sidecar.content, mode=sidecar.mode)
        except OSError as exc:
            results.append(
                ServiceRenderResult(
                    service=spec.service_name,
                    status="failed",
                    detail=f"write failure ({type(exc).__name__})",
                ),
            )
            continue

        results.append(ServiceRenderResult(service=spec.service_name, status="rendered"))

    return ServiceEnvResult(services=tuple(results))


# ---------------------------------------------------------------------------
# Gitea workspace block (append-mode for jupyter / marimo / code-server /
# meltano / prefect when Gitea is enabled).
# ---------------------------------------------------------------------------

# Marker pair for idempotent strip+append. Block markers are pinned
# strings: ``_strip_gitea_block()`` finds (and removes) any block a
# previous run wrote before appending the new one. Diverging markers
# would cause re-runs to stack a second block.
_GITEA_BLOCK_BEGIN = "# >>> Gitea workspace repo (auto-generated, do not edit)"
_GITEA_BLOCK_END = "# <<< Gitea workspace repo"

# Services that get the Gitea block appended.
_GITEA_APPEND_TARGETS: tuple[str, ...] = (
    "jupyter",
    "marimo",
    "code-server",
    "meltano",
    "prefect",
)


@dataclass(frozen=True)
class GiteaWorkspaceConfig:
    """Inputs for the Gitea workspace block append.

    Captures the result of the workspace-coords + credentials
    derivation. The orchestrator computes these BEFORE calling
    :func:`append_gitea_workspace_block` since they depend on
    mirror-mode + user-vs-admin selection.
    """

    gitea_repo_url: str
    gitea_username: str
    gitea_password: str
    git_author_name: str
    git_author_email: str
    repo_name: str
    # Default branch of the workspace repo. Derived from the
    # mirrored upstream's default-branch detection in
    # :mod:`nexus_deploy.workspace_coords` (stays "main" for
    # non-mirrored workspaces). Used by stacks whose runtime needs the
    # explicit branch — e.g. the Prefect manifest's `pull:` step
    # which calls `git_clone(repository=..., branch=$WORKSPACE_BRANCH)`.
    # Fresh installs still get a working clone via the env-var
    # default in the seed manifest if this field were ever empty.
    workspace_branch: str = "main"


def _strip_gitea_block(content: str) -> str:
    """Remove any existing ``# >>> Gitea workspace ...`` to ``# <<<``
    block (idempotent re-run)."""
    pattern = re.compile(
        rf"\n?{re.escape(_GITEA_BLOCK_BEGIN)}.*?{re.escape(_GITEA_BLOCK_END)}\n?",
        re.DOTALL,
    )
    return pattern.sub("\n", content).rstrip() + "\n" if content else ""


def _render_gitea_workspace_block(cfg: GiteaWorkspaceConfig) -> str:
    """Render the marker-wrapped Gitea workspace block."""
    return f"""\
{_GITEA_BLOCK_BEGIN}
GITEA_URL=http://gitea:3000
GITEA_REPO_URL={cfg.gitea_repo_url}
GITEA_USERNAME={cfg.gitea_username}
GITEA_PASSWORD={cfg.gitea_password}
GIT_AUTHOR_NAME={cfg.git_author_name}
GIT_AUTHOR_EMAIL={cfg.git_author_email}
GIT_COMMITTER_NAME={cfg.git_author_name}
GIT_COMMITTER_EMAIL={cfg.git_author_email}
REPO_NAME={cfg.repo_name}
WORKSPACE_BRANCH={cfg.workspace_branch}
{_GITEA_BLOCK_END}
"""


def append_gitea_workspace_block(
    cfg: GiteaWorkspaceConfig,
    enabled: list[str],
    *,
    stacks_dir: Path,
) -> tuple[str, ...]:
    """For each git-integrated service in :data:`_GITEA_APPEND_TARGETS`
    that is in the enabled list, idempotently strip + append the
    Gitea workspace block to its ``.env`` file.

    Returns the tuple of services that got the block appended.
    """
    block = _render_gitea_workspace_block(cfg)
    appended: list[str] = []
    for svc in _GITEA_APPEND_TARGETS:
        if svc not in enabled:
            continue
        env_path = stacks_dir / svc / ".env"
        if not env_path.exists():
            # Service is enabled but its main render didn't run (maybe
            # spec-not-found; skip gracefully).
            continue
        existing = env_path.read_text(encoding="utf-8")
        cleaned = _strip_gitea_block(existing)
        if cleaned and not cleaned.endswith("\n"):
            cleaned += "\n"
        new_content = cleaned + block
        _atomic_write(env_path, new_content, mode=0o644)
        appended.append(svc)
    return tuple(appended)
