"""Infisical bootstrap — folder creation + per-folder secret upsert.

Canonical surface for pushing the SECRETS_JSON payload into Infisical
on the server. The flow:

- :func:`compute_folders` — pure data, takes :class:`NexusConfig` +
  :class:`BootstrapEnv` and returns the list of :class:`FolderSpec` in
  source order. Empty values are silently skipped so operator UI edits
  in Infisical survive a re-bootstrap (see issue #504).
- :class:`InfisicalClient` carries project_id / env / token / push_dir.
- :meth:`InfisicalClient.bootstrap` writes per-folder JSON files into
  ``push_dir``, rsyncs them to the server, and runs a server-side curl
  loop that POSTs each folder (200 + 409 both treated as success) and
  PATCHes the corresponding ``secrets/batch`` payload. Returns
  :class:`BootstrapResult` with pushed/failed counts.
- :func:`provision_admin` — separate helper for one-time admin-account
  creation, called once after the initial Infisical container start.

Batching every API call into one SSH round-trip matters: a full
bootstrap is ~80 calls, and round-trip latency dominates if each one
opens its own SSH session.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from nexus_deploy import _remote
from nexus_deploy.config import NexusConfig, service_host

# Server-side Infisical endpoint.
_INFISICAL_HOST = "localhost"
_INFISICAL_PORT = 8070
_FOLDERS_PATH = "/api/v2/folders"
_SECRETS_BATCH_PATH = "/api/v4/secrets/batch"

# Server-side path where the rsync upload lands and the curl loop reads.
_REMOTE_PUSH_DIR = "/tmp/infisical-push"  # noqa: S108 — transient, removed by the curl loop's final cleanup step

# Server-side path where the deploy SSH user can find an
# operator-managed Infisical token; falls back to the env-supplied
# token when absent.
_REMOTE_TOKEN_FALLBACK_FILE = "/opt/docker-server/.infisical-token"  # noqa: S105 — file PATH, not a credential value


@dataclass(frozen=True)
class BootstrapEnv:
    """Configuration values that come from outside ``SECRETS_JSON``.

    The folder payloads reference values that come from a mix of
    sources — config.tfvars (DOMAIN, ADMIN_EMAIL), workflow inputs
    (SSH_PRIVATE_KEY_CONTENT, WOODPECKER_GITEA_*), other tofu
    outputs, etc. Rather than reach into ``os.environ`` from inside
    :func:`compute_folders`, we take them as a typed dataclass so
    callers can also build folders from fixtures in tests.

    Fields are ``str | None`` so a missing/empty value causes the
    corresponding key to be skipped from the upsert payload via the
    per-folder skip-empty pass.
    """

    domain: str | None = None
    admin_email: str | None = None
    gitea_user_email: str | None = None
    gitea_user_username: str | None = None
    gitea_repo_owner: str | None = None
    repo_name: str | None = None
    om_principal_domain: str | None = None
    woodpecker_gitea_client: str | None = None
    woodpecker_gitea_secret: str | None = None
    ssh_private_key_base64: str | None = None
    # Issue #540: separator used to compose service hostnames under
    # DOMAIN. ``"."`` (default) yields ``kestra.example.com``;
    # multi-tenant forks set ``"-"`` to yield ``kestra-user1.example.com``
    # which matches the flat-subdomain DNS records Tofu provisions for
    # that tenant. Always a string (never None) because downstream
    # f-strings always interpolate it; the tfvars parser normalises
    # an empty value to ``"."``.
    subdomain_separator: str = "."
    # Issue #607: optional Prometheus ``remote_write`` target for
    # centralised cross-stack monitoring (see Nexus-Conductor #23).
    # When both ``monitoring_endpoint`` and ``monitoring_token`` are
    # set, the grafana stack renders a ``prometheus.yml`` with a
    # ``remote_write`` block pointing at ``<endpoint>/api/v1/write``
    # with a Bearer token; otherwise it renders today's no-remote_write
    # variant. ``tenant_id`` defaults to ``domain`` when empty — vmauth
    # enforces tenant labels server-side from the token mapping anyway,
    # so the relabel rule we inject is informational defense-in-depth.
    monitoring_endpoint: str | None = None
    monitoring_token: str | None = None
    tenant_id: str | None = None


@dataclass(frozen=True)
class FolderSpec:
    """One Infisical folder to create + a dict of secrets to upsert into it.

    ``secrets`` is the ALREADY-FILTERED set: empty/None values were
    dropped at construction time by :func:`_filter_empty`. The
    skip-empty contract from #504 (preserve operator UI edits) is
    enforced here.
    """

    name: str
    secrets: dict[str, str]

    def folder_payload(self, project_id: str, env: str) -> dict[str, str]:
        """Match the bash: ``jq -n '{projectId, environment, name, path: "/"}'``."""
        return {
            "projectId": project_id,
            "environment": env,
            "name": self.name,
            "path": "/",
        }

    def secrets_payload(self, project_id: str, env: str) -> dict[str, object]:
        """Match the bash secrets-batch shape: ``mode: "upsert"`` + secrets list."""
        return {
            "projectId": project_id,
            "environment": env,
            "secretPath": f"/{self.name}",
            "mode": "upsert",
            "secrets": [{"secretKey": k, "secretValue": v} for k, v in self.secrets.items()],
        }


@dataclass(frozen=True)
class BootstrapResult:
    """Outcome of an end-to-end bootstrap.

    ``pushed`` and ``failed`` come from the server-side curl loop's
    final ``echo "$OK:$FAIL"`` — they count successful vs errored
    secrets-batch PATCHes, NOT folder POSTs (folder POSTs are
    fire-and-forget per the legacy logic). ``folders_built`` is the
    count of FolderSpecs we wrote to the push dir, including ones that
    ended up with zero secrets after skip-empty.
    """

    folders_built: int
    pushed: int
    failed: int


# ---------------------------------------------------------------------------
# Provision-admin — readiness probe + admin-bootstrap + project-create
# + credential persistence. Returns the (token, project_id) consumed by
# the push-secrets step (:class:`BootstrapResult`).
# ---------------------------------------------------------------------------


# Server-side paths where the freshly-minted token + project_id are
# persisted on first run, so subsequent spin-ups can load them without
# re-bootstrapping.
_REMOTE_TOKEN_PATH = "/opt/docker-server/.infisical-token"  # noqa: S105 — file path
_REMOTE_PROJECT_ID_PATH = "/opt/docker-server/.infisical-project-id"


ProvisionStatus = Literal[
    "freshly-bootstrapped",  # /admin/bootstrap + /workspace + creds saved
    "loaded-existing",  # already initialized + saved-cred files readable
    "loaded-existing-missing-creds",  # initialized but cred files empty/missing — operator must destroy-all
    "already-bootstrapped-no-saved-creds",  # API returned "already" but no saved file (state mismatch)
    "bootstrap-failed",  # /admin/bootstrap returned an unparseable body
    "project-create-failed",  # /workspace returned no project.id
    "not-ready",  # readiness probe timed out
]


@dataclass(frozen=True)
class ProvisionResult:
    """Outcome of :func:`provision_admin`.

    On the success paths (``freshly-bootstrapped`` / ``loaded-existing``)
    ``token`` + ``project_id`` are populated and the caller can proceed
    to push secrets via :class:`InfisicalClient`. On every other status
    they are ``None`` and the caller should warn-and-skip the push step
    (downstream stacks reading from Infisical degrade gracefully).
    """

    status: ProvisionStatus
    token: str | None  # Bearer token for /api/v2/workspace + downstream pushes
    project_id: str | None  # Workspace ("project") id for the secret push folders

    @property
    def has_credentials(self) -> bool:
        """True iff this run produced a (token, project_id) usable for downstream pushes."""
        return self.token is not None and self.project_id is not None


# RESULT line emitted by the rendered bash script. token is base64-encoded
# (matches the same argv-safe transport pattern infisical bootstrap +
# secret_sync.py use); project_id is plain (uuid-shaped, never has shell-
# special chars — but anchored alphanumeric + dash for defence in depth).
_PROVISION_RESULT_RE = re.compile(
    r"^RESULT status=(?P<status>[a-z-]+)"
    r"(?: token=(?P<token>[A-Za-z0-9+/=]+))?"
    r"(?: project_id=(?P<project_id>[A-Za-z0-9_-]+))?$",
    re.MULTILINE,
)


def render_provision_admin_script(
    *,
    admin_email: str,
    admin_password: str,
    organization_name: str = "Nexus",
    project_name: str = "Nexus Stack",
    base_url: str = "http://localhost:8070",
    saved_token_path: str = _REMOTE_TOKEN_PATH,
    saved_project_path: str = _REMOTE_PROJECT_ID_PATH,
    container_wait_seconds: int = 60,
    http_wait_seconds: int = 120,
) -> str:
    """Render the server-side bash that probes readiness, decides
    init-state, and either loads saved creds or bootstraps a new admin
    + project.

    Two-stage readiness: docker container Status == "running"
    (``container_wait_seconds`` ceiling) AND HTTP body of
    ``/api/v1/admin/config`` contains ``initialized``
    (``http_wait_seconds`` ceiling). Without the second check, the
    admin-bootstrap POST would race against Infisical's data-provider
    init and 401.

    Init-branch:
    - ``"initialized":true`` body → load creds from
      ``{saved_token_path}`` + ``{saved_project_path}`` (mode 600,
      written on first run). Empty/missing files → ``loaded-existing-
      missing-creds`` (operator must run destroy-all + re-init).
    - else → POST ``/api/v1/admin/bootstrap`` with email + password +
      organization_name → extract ``identity.credentials.token`` +
      ``organization.id``. Then POST ``/api/v2/workspace`` with
      project_name + organizationId → extract ``project.id`` (or
      legacy ``workspace.id``). Save token + project_id to disk.

    All API calls keep the freshly-minted token in env vars / mode-600
    curl --config tmpfile, NEVER in argv. The token IS embedded in the
    RESULT line (base64-encoded) so the runner can extract it; that's
    the contract used by gitea-configure + woodpecker-oauth.
    """
    email_q = shlex.quote(admin_email)
    pw_q = shlex.quote(admin_password)
    org_q = shlex.quote(organization_name)
    project_q = shlex.quote(project_name)
    url_q = shlex.quote(base_url)
    tok_path_q = shlex.quote(saved_token_path)
    proj_path_q = shlex.quote(saved_project_path)
    return f"""set -euo pipefail
ADMIN_EMAIL={email_q}
ADMIN_PW={pw_q}
ORG_NAME={org_q}
PROJECT_NAME={project_q}
BASE_URL={url_q}
SAVED_TOKEN_PATH={tok_path_q}
SAVED_PROJECT_PATH={proj_path_q}

# Stage 1: wait for docker container to be running.
SECONDS=0
while [ "$SECONDS" -lt {container_wait_seconds} ]; do
    STATUS=$(docker inspect --format='{{{{.State.Status}}}}' infisical 2>/dev/null || echo "")
    [ "$STATUS" = "running" ] && break
    sleep 2
done

# Stage 2: wait for /admin/config body to mention 'initialized'.
READY=false
SECONDS=0
while [ "$SECONDS" -lt {http_wait_seconds} ]; do
    BODY=$(curl -s --connect-timeout 3 --max-time 5 \\
        "$BASE_URL/api/v1/admin/config" 2>/dev/null || echo "")
    if echo "$BODY" | grep -q 'initialized'; then
        READY=true
        break
    fi
    sleep 3
done
if [ "$READY" != "true" ]; then
    echo "RESULT status=not-ready"
    exit 0
fi

# Stage 3: re-fetch /admin/config to determine init state.
INIT_BODY=$(curl -s --max-time 10 "$BASE_URL/api/v1/admin/config" 2>/dev/null || echo "")
if echo "$INIT_BODY" | grep -q '"initialized":true'; then
    SAVED_TOKEN=$(cat "$SAVED_TOKEN_PATH" 2>/dev/null || echo "")
    SAVED_PROJECT=$(cat "$SAVED_PROJECT_PATH" 2>/dev/null || echo "")
    if [ -z "$SAVED_TOKEN" ] || [ -z "$SAVED_PROJECT" ]; then
        echo "RESULT status=loaded-existing-missing-creds"
        exit 0
    fi
    TOKEN_B64=$(printf '%s' "$SAVED_TOKEN" | base64 | tr -d '\\n')
    echo "RESULT status=loaded-existing token=$TOKEN_B64 project_id=$SAVED_PROJECT"
    exit 0
fi

# Stage 4: fresh bootstrap. POST /admin/bootstrap with email + password
# + organization name. NEXUS_E / NEXUS_PW / NEXUS_ORG route the values
# through env vars to jq — never `--arg`, which would land them in
# jq's argv.
BOOTSTRAP_BODY=$(NEXUS_E="$ADMIN_EMAIL" NEXUS_PW="$ADMIN_PW" NEXUS_ORG="$ORG_NAME" jq -n \\
    '{{email: env.NEXUS_E, password: env.NEXUS_PW, organization: env.NEXUS_ORG}}')
BOOTSTRAP_RESP=$(printf '%s' "$BOOTSTRAP_BODY" | curl -s -X POST \\
    "$BASE_URL/api/v1/admin/bootstrap" \\
    --max-time 30 \\
    -H 'Content-Type: application/json' \\
    --data-binary @- 2>/dev/null || echo "")

if echo "$BOOTSTRAP_RESP" | grep -qi 'already'; then
    echo "RESULT status=already-bootstrapped-no-saved-creds"
    exit 0
fi

NEW_TOKEN=$(echo "$BOOTSTRAP_RESP" | jq -r '.identity.credentials.token // empty' 2>/dev/null)
ORG_ID=$(echo "$BOOTSTRAP_RESP" | jq -r '.organization.id // empty' 2>/dev/null)
if [ -z "$NEW_TOKEN" ] || [ -z "$ORG_ID" ]; then
    echo "RESULT status=bootstrap-failed"
    exit 0
fi

# Stage 5: create the workspace ("project" in v2 API). Bearer token via
# mode-600 curl --config tmpfile, NOT -H argv.
TOKEN_CFG=$(mktemp)
chmod 600 "$TOKEN_CFG"
trap 'rm -f "$TOKEN_CFG"' EXIT
printf 'header = "Authorization: Bearer %s"\\n' "$NEW_TOKEN" > "$TOKEN_CFG"
PROJECT_BODY=$(NEXUS_PN="$PROJECT_NAME" NEXUS_OID="$ORG_ID" jq -n \\
    '{{projectName: env.NEXUS_PN, organizationId: env.NEXUS_OID}}')
PROJECT_RESP=$(printf '%s' "$PROJECT_BODY" | curl -s --config "$TOKEN_CFG" \\
    -X POST "$BASE_URL/api/v2/workspace" \\
    --max-time 30 \\
    -H 'Content-Type: application/json' \\
    --data-binary @- 2>/dev/null || echo "")
NEW_PROJECT=$(echo "$PROJECT_RESP" | jq -r '.project.id // .workspace.id // empty' 2>/dev/null)
if [ -z "$NEW_PROJECT" ] || [ "$NEW_PROJECT" = "null" ]; then
    echo "RESULT status=project-create-failed"
    exit 0
fi

# Stage 6: persist for next spin-up. mode 600 — these files contain
# the bearer token + workspace id. cat-then-chmod is the standard
# pattern (the file is created by the redirect; chmod tightens it
# before any further read).
printf '%s' "$NEW_TOKEN" > "$SAVED_TOKEN_PATH"
chmod 600 "$SAVED_TOKEN_PATH"
printf '%s' "$NEW_PROJECT" > "$SAVED_PROJECT_PATH"
chmod 600 "$SAVED_PROJECT_PATH"

NEW_TOKEN_B64=$(printf '%s' "$NEW_TOKEN" | base64 | tr -d '\\n')
echo "RESULT status=freshly-bootstrapped token=$NEW_TOKEN_B64 project_id=$NEW_PROJECT"
"""


def parse_provision_result(stdout: str) -> ProvisionResult | None:
    """Extract the RESULT line from the rendered script's stdout. Returns
    None if no parseable RESULT line exists.

    The caller (``provision_admin``) substitutes a
    ``ProvisionResult(status="not-ready", ...)`` for the None — and
    the CLI dispatcher then maps that to **rc=1** (soft-fail, warn-
    and-continue), NOT rc=2. Real transport failures (SSH connection
    drops, timeouts) raise ``CalledProcessError`` / ``OSError`` from
    the runner BEFORE we reach this parser, and those are what the
    CLI's rc=2 branch catches. Without a RESULT line the script ran
    end-to-end but didn't reach the success path — that's a soft
    Infisical-bootstrap-not-ready signal, not a transport break."""
    import base64

    match = _PROVISION_RESULT_RE.search(stdout)
    if match is None:
        return None
    g = match.groupdict()
    status: ProvisionStatus = g["status"]  # type: ignore[assignment]
    token_b64 = g.get("token")
    project_id = g.get("project_id")
    token: str | None = None
    if token_b64:
        try:
            token = base64.b64decode(token_b64).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            # Malformed base64 → drop to no-token path; the status line
            # itself is still useful for the operator-facing log.
            token = None
    return ProvisionResult(
        status=status,
        token=token,
        project_id=project_id,
    )


def provision_admin(
    *,
    admin_email: str,
    admin_password: str,
    organization_name: str = "Nexus",
    project_name: str = "Nexus Stack",
    host: str = "nexus",
    script_runner: Callable[[str], subprocess.CompletedProcess[str]] | None = None,
) -> ProvisionResult:
    """Render + run the provision script via SSH, parse result.

    ``host`` selects which ssh-config alias the remote script runs
    against. Defaults to ``"nexus"`` for back-compat with existing
    callers; orchestrator passes its ``self.ssh_host`` so a non-default
    ``SSH_HOST_ALIAS`` reaches every pre-bootstrap phase uniformly
    (PR #532 R2 #2).

    ``script_runner`` is a DI seam for tests; production callers pass
    None and get :func:`_remote.ssh_run_script` (script-via-stdin so
    secrets never reach argv / ps).
    """
    if not admin_email or not admin_password:
        return ProvisionResult(status="not-ready", token=None, project_id=None)
    runner = script_runner or (lambda s: _remote.ssh_run_script(s, host=host))
    script = render_provision_admin_script(
        admin_email=admin_email,
        admin_password=admin_password,
        organization_name=organization_name,
        project_name=project_name,
    )
    completed = runner(script)
    parsed = parse_provision_result(completed.stdout)
    if parsed is None:
        # No RESULT line → treat as not-ready; CLI dispatcher maps to rc=1
        # (warn-and-continue) so the deploy doesn't abort on a transient
        # Infisical hiccup.
        return ProvisionResult(status="not-ready", token=None, project_id=None)
    return parsed


def _filter_empty(items: Mapping[str, str | None]) -> dict[str, str]:
    """Apply the skip-empty rule (mirrors the operator-edit-preserve hardening from #504).

    Drops entries where the value is ``None`` or the empty string. The
    bash form was ``[ -z "$2" ] && shift 2 && continue`` — same
    behaviour, typed.
    """
    return {k: v for k, v in items.items() if v is not None and v != ""}


def compute_folders(config: NexusConfig, env: BootstrapEnv) -> list[FolderSpec]:
    """Build the ordered list of Infisical folders to push.

    Each :class:`FolderSpec` corresponds to one logical group of
    secrets (config, r2-datalake, hetzner-s3, gitea, …). Conditional
    folders (R2, Hetzner-S3, External-S3, SSH, Woodpecker OAuth) are
    only emitted when their gating fields are populated, so a partial
    deployment doesn't push empty folders.
    """
    folders: list[FolderSpec] = []

    # Resolve the same fallbacks the schema in :mod:`config` applies
    # at dump time, so pushed values match the bash-eval consumers
    # exactly (admin_username default + EXTERNAL_S3_* explicit
    # defaults).
    admin_username = config.admin_username or "admin"
    external_s3_label = config.external_s3_label or "External Storage"
    external_s3_region = config.external_s3_region or "auto"

    folders.append(
        FolderSpec(
            "config",
            _filter_empty(
                {
                    "DOMAIN": env.domain,
                    "ADMIN_EMAIL": env.admin_email,
                    "ADMIN_USERNAME": admin_username,
                }
            ),
        )
    )

    if (
        config.r2_data_endpoint
        and config.r2_data_access_key
        and config.r2_data_secret_key
        and config.r2_data_bucket
    ):
        folders.append(
            FolderSpec(
                "r2-datalake",
                _filter_empty(
                    {
                        "R2_ENDPOINT": config.r2_data_endpoint,
                        "R2_ACCESS_KEY": config.r2_data_access_key,
                        "R2_SECRET_KEY": config.r2_data_secret_key,
                        "R2_BUCKET": config.r2_data_bucket,
                    }
                ),
            )
        )

    if config.hetzner_s3_server and config.hetzner_s3_access_key and config.hetzner_s3_secret_key:
        # Fallback chain for canonical HETZNER_S3_BUCKET (used by ad-hoc
        # workloads): prefer _general (workloads bucket by convention),
        # fall back to _lakefs (always populated when LakeFS-aware path runs).
        default_bucket = config.hetzner_s3_bucket_general or config.hetzner_s3_bucket_lakefs or ""
        folders.append(
            FolderSpec(
                "hetzner-s3",
                _filter_empty(
                    {
                        "HETZNER_S3_ENDPOINT": f"https://{config.hetzner_s3_server}",
                        "HETZNER_S3_REGION": config.hetzner_s3_region,
                        "HETZNER_S3_ACCESS_KEY": config.hetzner_s3_access_key,
                        "HETZNER_S3_SECRET_KEY": config.hetzner_s3_secret_key,
                        "HETZNER_S3_BUCKET": default_bucket,
                        "HETZNER_S3_BUCKET_LAKEFS": config.hetzner_s3_bucket_lakefs,
                        "HETZNER_S3_BUCKET_GENERAL": config.hetzner_s3_bucket_general,
                        "HETZNER_S3_BUCKET_PGDUCKLAKE": config.hetzner_s3_bucket_pgducklake,
                    }
                ),
            )
        )

    if (
        config.external_s3_endpoint
        and config.external_s3_access_key
        and config.external_s3_secret_key
        and config.external_s3_bucket
    ):
        folders.append(
            FolderSpec(
                "external-s3",
                _filter_empty(
                    {
                        "EXTERNAL_S3_ENDPOINT": config.external_s3_endpoint,
                        "EXTERNAL_S3_REGION": external_s3_region,
                        "EXTERNAL_S3_ACCESS_KEY": config.external_s3_access_key,
                        "EXTERNAL_S3_SECRET_KEY": config.external_s3_secret_key,
                        "EXTERNAL_S3_BUCKET": config.external_s3_bucket,
                        "EXTERNAL_S3_LABEL": external_s3_label,
                    }
                ),
            )
        )

    folders.append(
        FolderSpec(
            "infisical",
            _filter_empty(
                {
                    "INFISICAL_USERNAME": env.admin_email,
                    "INFISICAL_PASSWORD": config.infisical_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "portainer",
            _filter_empty(
                {
                    "PORTAINER_USERNAME": admin_username,
                    "PORTAINER_PASSWORD": config.portainer_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "uptime-kuma",
            _filter_empty(
                {
                    "UPTIME_KUMA_USERNAME": admin_username,
                    "UPTIME_KUMA_PASSWORD": config.kuma_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "grafana",
            _filter_empty(
                {
                    "GRAFANA_USERNAME": admin_username,
                    "GRAFANA_PASSWORD": config.grafana_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "n8n",
            _filter_empty(
                {
                    "N8N_USERNAME": env.admin_email,
                    "N8N_PASSWORD": config.n8n_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "dagster",
            _filter_empty({"DAGSTER_DB_PASSWORD": config.dagster_db_password}),
        )
    )
    folders.append(
        FolderSpec(
            "kestra",
            _filter_empty(
                {
                    "KESTRA_USERNAME": env.admin_email,
                    "KESTRA_PASSWORD": config.kestra_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "metabase",
            _filter_empty(
                {
                    "METABASE_USERNAME": env.admin_email,
                    "METABASE_PASSWORD": config.metabase_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "superset",
            _filter_empty(
                {
                    "SUPERSET_USERNAME": "admin",
                    "SUPERSET_PASSWORD": config.superset_admin_password,
                    "SUPERSET_DB_PASSWORD": config.superset_db_password,
                    "SUPERSET_SECRET_KEY": config.superset_secret_key,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "cloudbeaver",
            _filter_empty(
                {
                    "CLOUDBEAVER_USERNAME": "nexus-cloudbeaver",
                    "CLOUDBEAVER_PASSWORD": config.cloudbeaver_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "meilisearch",
            _filter_empty(
                {
                    "MEILISEARCH_MASTER_KEY": config.meilisearch_master_key,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "hedgedoc",
            _filter_empty(
                {
                    "HEDGEDOC_USERNAME": env.admin_email,
                    "HEDGEDOC_PASSWORD": config.hedgedoc_admin_password,
                    "HEDGEDOC_SESSION_SECRET": config.hedgedoc_session_secret,
                    "HEDGEDOC_DB_PASSWORD": config.hedgedoc_db_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "litellm",
            _filter_empty(
                {
                    "LITELLM_MASTER_KEY": config.litellm_master_key,
                    "LITELLM_SALT_KEY": config.litellm_salt_key,
                    "LITELLM_DB_PASSWORD": config.litellm_db_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "lakekeeper",
            _filter_empty(
                {
                    "LAKEKEEPER_DB_PASSWORD": config.lakekeeper_db_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "mage",
            _filter_empty(
                {
                    "MAGE_USERNAME": env.gitea_user_email or env.admin_email,
                    "MAGE_PASSWORD": config.mage_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "minio",
            _filter_empty(
                {
                    "MINIO_ROOT_USER": "nexus-minio",
                    "MINIO_ROOT_PASSWORD": config.minio_root_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "sftpgo",
            _filter_empty(
                {
                    "SFTPGO_ADMIN_USERNAME": "nexus-sftpgo",
                    "SFTPGO_ADMIN_PASSWORD": config.sftpgo_admin_password,
                    "SFTPGO_USER_USERNAME": "nexus-default",
                    "SFTPGO_USER_PASSWORD": config.sftpgo_user_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "nocodb",
            _filter_empty(
                {
                    "NOCODB_USERNAME": env.admin_email,
                    "NOCODB_PASSWORD": config.nocodb_admin_password,
                    "NOCODB_DB_PASSWORD": config.nocodb_db_password,
                    "NOCODB_JWT_SECRET": config.nocodb_jwt_secret,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "appsmith",
            _filter_empty(
                {
                    "APPSMITH_ENCRYPTION_PASSWORD": config.appsmith_encryption_password,
                    "APPSMITH_ENCRYPTION_SALT": config.appsmith_encryption_salt,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "dinky",
            _filter_empty(
                {
                    "DINKY_USERNAME": "admin",
                    "DINKY_PASSWORD": config.dinky_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "dify",
            _filter_empty(
                {
                    "DIFY_USERNAME": env.admin_email,
                    "DIFY_PASSWORD": config.dify_admin_password,
                    "DIFY_DB_PASSWORD": config.dify_db_password,
                    "DIFY_SECRET_KEY": config.dify_secret_key,
                    "DIFY_REDIS_PASSWORD": config.dify_redis_password,
                    "DIFY_WEAVIATE_API_KEY": config.dify_weaviate_api_key,
                    "DIFY_SANDBOX_API_KEY": config.dify_sandbox_api_key,
                    "DIFY_PLUGIN_DAEMON_KEY": config.dify_plugin_daemon_key,
                    "DIFY_PLUGIN_INNER_API_KEY": config.dify_plugin_inner_api_key,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "rustfs",
            _filter_empty(
                {
                    "RUSTFS_ACCESS_KEY": "nexus-rustfs",
                    "RUSTFS_SECRET_KEY": config.rustfs_root_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "seaweedfs",
            _filter_empty(
                {
                    "SEAWEEDFS_ACCESS_KEY": "nexus-seaweedfs",
                    "SEAWEEDFS_SECRET_KEY": config.seaweedfs_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "garage",
            _filter_empty({"GARAGE_ADMIN_TOKEN": config.garage_admin_token}),
        )
    )
    folders.append(
        FolderSpec(
            "lakefs",
            _filter_empty(
                {
                    "LAKEFS_DB_PASSWORD": config.lakefs_db_password,
                    "LAKEFS_ACCESS_KEY_ID": config.lakefs_admin_access_key,
                    "LAKEFS_SECRET_ACCESS_KEY": config.lakefs_admin_secret_key,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "filestash",
            _filter_empty(
                {
                    "FILESTASH_S3_BUCKET": config.hetzner_s3_bucket_general,
                    "FILESTASH_ADMIN_PASSWORD": config.filestash_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "redpanda",
            _filter_empty(
                {
                    "REDPANDA_SASL_USERNAME": "nexus-redpanda",
                    "REDPANDA_SASL_PASSWORD": config.redpanda_admin_password,
                    "REDPANDA_KAFKA_PUBLIC_URL": (
                        f"redpanda-kafka.{env.domain}:9092" if env.domain else None
                    ),
                    "REDPANDA_SCHEMA_REGISTRY_PUBLIC_URL": (
                        f"redpanda-schema-registry.{env.domain}:18081" if env.domain else None
                    ),
                    "REDPANDA_ADMIN_PUBLIC_URL": (
                        f"redpanda-admin.{env.domain}:9644" if env.domain else None
                    ),
                    "REDPANDA_CONNECT_PUBLIC_URL": (
                        f"redpanda-connect-api.{env.domain}:4195" if env.domain else None
                    ),
                }
            ),
        )
    )
    folders.append(
        FolderSpec("meltano", _filter_empty({"MELTANO_DB_PASSWORD": config.meltano_db_password}))
    )
    folders.append(
        FolderSpec(
            "postgres",
            _filter_empty(
                {
                    "POSTGRES_USERNAME": "nexus-postgres",
                    "POSTGRES_PASSWORD": config.postgres_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "pg-ducklake",
            _filter_empty(
                {
                    "PG_DUCKLAKE_USERNAME": "nexus-pgducklake",
                    "PG_DUCKLAKE_PASSWORD": config.pgducklake_password,
                    "PG_DUCKLAKE_DATABASE": "ducklake",
                    "PG_DUCKLAKE_S3_BUCKET": config.hetzner_s3_bucket_pgducklake,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "pgadmin",
            _filter_empty(
                {
                    "PGADMIN_USERNAME": env.admin_email,
                    "PGADMIN_PASSWORD": config.pgadmin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec("prefect", _filter_empty({"PREFECT_DB_PASSWORD": config.prefect_db_password}))
    )
    folders.append(
        FolderSpec(
            "windmill",
            _filter_empty(
                {
                    "WINDMILL_ADMIN_EMAIL": env.admin_email,
                    "WINDMILL_ADMIN_PASSWORD": config.windmill_admin_password,
                    "WINDMILL_DB_PASSWORD": config.windmill_db_password,
                    "WINDMILL_SUPERADMIN_SECRET": config.windmill_superadmin_secret,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "openmetadata",
            _filter_empty(
                {
                    "OPENMETADATA_USERNAME": (
                        f"admin@{env.om_principal_domain}" if env.om_principal_domain else None
                    ),
                    "OPENMETADATA_PASSWORD": config.openmetadata_admin_password,
                    "OPENMETADATA_DB_PASSWORD": config.openmetadata_db_password,
                }
            ),
        )
    )
    # Gitea: GITEA_REPO_URL is built from DOMAIN + repo_owner + repo_name
    # with the same `${REPO_NAME:-nexus-${DOMAIN//./-}-gitea}` fallback
    # the bash carried at L2300.
    repo_name = env.repo_name or (
        f"nexus-{env.domain.replace('.', '-')}-gitea" if env.domain else None
    )
    repo_owner = env.gitea_repo_owner or admin_username
    gitea_repo_url = (
        f"https://{service_host('git', env.domain, env.subdomain_separator)}"
        f"/{repo_owner}/{repo_name}.git"
        if env.domain and repo_owner and repo_name
        else None
    )
    folders.append(
        FolderSpec(
            "gitea",
            _filter_empty(
                {
                    "GITEA_ADMIN_USERNAME": admin_username,
                    "GITEA_ADMIN_PASSWORD": config.gitea_admin_password,
                    "GITEA_USER_USERNAME": env.gitea_user_username,
                    "GITEA_USER_PASSWORD": config.gitea_user_password,
                    "GITEA_REPO_URL": gitea_repo_url,
                    "GITEA_DB_PASSWORD": config.gitea_db_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "clickhouse",
            _filter_empty(
                {
                    "CLICKHOUSE_USERNAME": "nexus-clickhouse",
                    "CLICKHOUSE_PASSWORD": config.clickhouse_admin_password,
                }
            ),
        )
    )
    folders.append(
        FolderSpec(
            "wikijs",
            _filter_empty(
                {
                    "WIKIJS_USERNAME": env.gitea_user_email or env.admin_email,
                    "WIKIJS_PASSWORD": config.wikijs_admin_password,
                    "WIKIJS_DB_PASSWORD": config.wikijs_db_password,
                }
            ),
        )
    )
    # Woodpecker: agent_secret unconditional, OAuth pair optional.
    woodpecker_secrets: dict[str, str | None] = {
        "WOODPECKER_AGENT_SECRET": config.woodpecker_agent_secret,
    }
    if env.woodpecker_gitea_client:
        woodpecker_secrets["WOODPECKER_GITEA_CLIENT"] = env.woodpecker_gitea_client
    if env.woodpecker_gitea_secret:
        woodpecker_secrets["WOODPECKER_GITEA_SECRET"] = env.woodpecker_gitea_secret
    folders.append(FolderSpec("woodpecker", _filter_empty(woodpecker_secrets)))

    if env.ssh_private_key_base64:
        folders.append(
            FolderSpec(
                "ssh",
                _filter_empty({"SSH_PRIVATE_KEY_BASE64": env.ssh_private_key_base64}),
            )
        )

    return folders


# Type aliases for the runner injection points used in tests.
SshRunner = Callable[[str], subprocess.CompletedProcess[str]]
RsyncRunner = Callable[[Path, str], subprocess.CompletedProcess[str]]


@dataclass
class InfisicalClient:
    """Bundles the project_id / env / token / push_dir for a bootstrap call.

    Stateless except for the ``push_dir`` it manages on the local
    filesystem. The actual server-side execution is via the injected
    ``ssh_runner`` / ``rsync_runner`` callables — defaults wire to
    :mod:`nexus_deploy._remote`, tests pass mocks.
    """

    project_id: str
    env: str
    token: str
    push_dir: Path = Path("/tmp/infisical-push")  # noqa: S108 — public
    # path; the same dir on the server is what the curl loop reads.
    # There's nothing secret in the path itself; the JSON files inside
    # contain secret values but are removed by the server-side
    # `rm -rf` at the end of the bootstrap.

    def encode_payloads(self, folders: list[FolderSpec]) -> dict[str, str]:
        """Return the f-NAME.json + s-NAME.json file-name → JSON-text mapping.

        Pure function — useful for tests that want to verify the exact
        bytes that would be written to disk without touching the
        filesystem.

        Output uses ``json.dumps(..., separators=(",", ":"),
        sort_keys=False)`` to keep the encoding compact and stable
        while preserving the source-order of the secrets list defined
        in :func:`compute_folders`.
        """
        out: dict[str, str] = {}
        for spec in folders:
            out[f"f-{spec.name}.json"] = json.dumps(
                spec.folder_payload(self.project_id, self.env), separators=(",", ":")
            )
            out[f"s-{spec.name}.json"] = json.dumps(
                spec.secrets_payload(self.project_id, self.env), separators=(",", ":")
            )
        return out

    def _build_remote_loop(self) -> str:
        """Build the server-side bash that POSTs folders + PATCHes secrets."""
        token_quoted = shlex.quote(self.token)
        folders_url = f"http://{_INFISICAL_HOST}:{_INFISICAL_PORT}{_FOLDERS_PATH}"
        secrets_url = f"http://{_INFISICAL_HOST}:{_INFISICAL_PORT}{_SECRETS_BATCH_PATH}"
        # `printf '%s'` instead of `echo`: bash's built-in `echo` can
        # eat a leading `-n` / `-e` / `-E` as an option flag, blanking
        # the captured TOKEN if a token happens to start with one.
        # Infisical tokens are alphanumeric in practice, but the
        # printf form costs nothing and rules out the edge case.
        # FAIL-detection: a PATCH counts as failed if either curl's
        # exit status is non-zero (transport failures: connect refused,
        # DNS errors, timeouts) or the response body contains the
        # literal substring '"error"'. Both error classes feed the FAIL
        # counter, never silently counted as OK.
        return f"""
TOKEN=$(cat {_REMOTE_TOKEN_FALLBACK_FILE} 2>/dev/null || printf '%s' {token_quoted})
if [ -z "$TOKEN" ]; then echo '0:0'; exit 0; fi
OK=0; FAIL=0
for f in {_REMOTE_PUSH_DIR}/f-*.json; do
    curl -s -X POST '{folders_url}' \\
        -H "Authorization: Bearer $TOKEN" \\
        -H 'Content-Type: application/json' \\
        -d @"$f" >/dev/null 2>&1 || true
done
for f in {_REMOTE_PUSH_DIR}/s-*.json; do
    RESULT=$(curl -s -X PATCH '{secrets_url}' \\
        -H "Authorization: Bearer $TOKEN" \\
        -H 'Content-Type: application/json' \\
        -d @"$f" 2>&1)
    CURL_RC=$?
    if [ "$CURL_RC" -ne 0 ] || echo "$RESULT" | grep -q '"error"'; then
        FAIL=$((FAIL+1))
    else
        OK=$((OK+1))
    fi
done
rm -rf {_REMOTE_PUSH_DIR}
echo "$OK:$FAIL"
"""

    def bootstrap(
        self,
        folders: list[FolderSpec],
        *,
        ssh_runner: SshRunner | None = None,
        rsync_runner: RsyncRunner | None = None,
    ) -> BootstrapResult:
        """Write payloads, rsync, run the curl loop. Return push counts.

        Default runners come from :mod:`nexus_deploy._remote`; tests
        override both via the kwargs.

        Local payload files (which contain secret values) are removed
        in a ``finally`` block whether the rsync/ssh succeeds, fails,
        or raises. The server-side ``/tmp/infisical-push`` is removed
        by the curl loop's last step. No secrets-at-rest on either end after a
        bootstrap call returns.

        The remote bash script is fed to ``ssh nexus bash -s`` via
        stdin (:func:`_remote.ssh_run_script`), NOT as an argv. The
        script embeds the Infisical token (shlex-quoted), and stdin
        keeps it out of ``ps``, CI argv-logging, and any
        ``CalledProcessError`` / ``TimeoutExpired`` exception messages
        that would otherwise dump the full argv.
        """
        ssh = ssh_runner or (lambda script: _remote.ssh_run_script(script))
        rsync = rsync_runner or (
            lambda local, remote: _remote.rsync_to_remote(local, remote, delete=True)
        )

        # Restrictive perms because the JSON contains secret values.
        # Dir 0o700 + files 0o600 mean only the owner can read; rsync
        # preserves perms by default, so the server-side mirror inherits
        # the same protection.
        self.push_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Re-chmod in case the dir pre-existed with looser perms (mkdir's
        # mode is only applied at creation, ignored when exist_ok=True
        # and the dir is already there).
        self.push_dir.chmod(0o700)

        # ENTIRE materialise+push+execute path is wrapped in try/finally
        # so the cleanup of secret-bearing files runs even if write_text
        # / chmod / rsync / ssh fails mid-flight. The previous version
        # only wrapped the rsync+ssh phase, leaving the write loop
        # outside protection — a disk-full or permission error during
        # writes would leave half-written f-/s-*.json files in push_dir
        # with secret values still in them.
        try:
            # 1a. Clear stale files from prior runs so deleted folders
            #     don't ship to the server (matches `rsync --delete`
            #     semantics on the upload side).
            for stale in self.push_dir.glob("[fs]-*.json"):
                stale.unlink()

            # 1b. Atomic create-with-mode-0o600 via os.open. Avoids
            #     the TOCTOU race of `write_text` then `chmod`, where
            #     the file briefly exists with the umask-derived mode
            #     (often 0o644) before the chmod tightens it.
            for filename, body in self.encode_payloads(folders).items():
                payload_path = self.push_dir / filename
                fd = os.open(
                    str(payload_path),
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                    0o600,
                )
                # Explicit encoding + newline so the bytes-on-disk match
                # across macOS / Linux / CI runners regardless of locale.
                # Same encoding the snapshot tests assume.
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                    f.write(body)

            # 2. rsync to server.
            rsync(self.push_dir, f"nexus:{_REMOTE_PUSH_DIR}/")

            # 3. Run the server-side curl loop.
            completed = ssh(self._build_remote_loop())

            # 4. Parse the final `OK:FAIL` line. The server's stdout
            #    may include earlier echoes (warnings from the
            #    baseline-capture step); take the last line.
            last_line = completed.stdout.strip().splitlines()[-1] if completed.stdout else "0:0"
            try:
                ok_str, fail_str = last_line.split(":", 1)
                pushed = int(ok_str)
                failed = int(fail_str)
            except (ValueError, IndexError):
                # Unparseable output is itself a failure signal.
                pushed = 0
                failed = len(folders)

            return BootstrapResult(folders_built=len(folders), pushed=pushed, failed=failed)
        finally:
            # Best-effort: secret-bearing payloads must not survive a
            # bootstrap call (success OR failure). We delete only the
            # f-/s-*.json files we wrote, not the directory itself —
            # the dir may pre-exist with operator state we don't own.
            for payload in self.push_dir.glob("[fs]-*.json"):
                payload.unlink(missing_ok=True)
