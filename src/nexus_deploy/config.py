"""Typed parsing of ``tofu output -json secrets``.

:class:`NexusConfig` is the canonical representation of the
SECRETS_JSON payload produced by the OpenTofu stack. It is built from
either a raw JSON string (:meth:`NexusConfig.from_secrets_json`) or
directly from the tofu CLI (:meth:`NexusConfig.from_tofu_output`), and
is the single source of truth for the secret schema consumed by the
rest of ``nexus_deploy``.

Field-mapping ground truth: every entry in ``_FIELDS`` is one
``(bash_var, json_key, fallback)`` tuple. Adding a new secret means
editing ``_FIELDS`` here AND adding the matching tofu variable.

Out of scope (these are read elsewhere):
- ``DOMAIN`` / ``ADMIN_EMAIL`` — read from ``config.tfvars`` via
  :mod:`nexus_deploy.tfvars`, not from ``tofu output secrets``.
- ``CF_ACCESS_CLIENT_ID`` / ``CF_ACCESS_CLIENT_SECRET`` — read from
  the separate ``tofu output ssh_service_token``.
- ``IMAGE_VERSIONS_JSON`` — separate ``tofu output image_versions``.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError


class ConfigError(Exception):
    """Raised when SECRETS_JSON parsing fails (malformed JSON, schema mismatch)."""


# ---------------------------------------------------------------------------
# Field schema — single source of truth.
#
# Each tuple: (bash_var_name, json_key, fallback_when_missing).
#
# `bash_var_name` is what `dump_shell()` emits for downstream shell
# consumers via `eval`. `json_key` is the snake_case key from
# `tofu output -json secrets`. `fallback` is the value substituted when
# the JSON key is absent or empty:
#   - "" is the overwhelming majority (omit-if-empty)
#   - "admin" is the admin_username default
#   - "External Storage" / "auto" are explicit non-empty defaults
# ---------------------------------------------------------------------------
_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("ADMIN_USERNAME", "admin_username", "admin"),
    ("INFISICAL_PASS", "infisical_admin_password", ""),
    ("INFISICAL_ENCRYPTION_KEY", "infisical_encryption_key", ""),
    ("INFISICAL_AUTH_SECRET", "infisical_auth_secret", ""),
    ("INFISICAL_DB_PASSWORD", "infisical_db_password", ""),
    ("PORTAINER_PASS", "portainer_admin_password", ""),
    ("KUMA_PASS", "kuma_admin_password", ""),
    ("GRAFANA_PASS", "grafana_admin_password", ""),
    ("DAGSTER_DB_PASS", "dagster_db_password", ""),
    ("KESTRA_PASS", "kestra_admin_password", ""),
    ("KESTRA_DB_PASS", "kestra_db_password", ""),
    ("N8N_PASS", "n8n_admin_password", ""),
    ("METABASE_PASS", "metabase_admin_password", ""),
    ("SUPERSET_PASS", "superset_admin_password", ""),
    ("SUPERSET_DB_PASS", "superset_db_password", ""),
    ("SUPERSET_SECRET", "superset_secret_key", ""),
    ("CLOUDBEAVER_PASS", "cloudbeaver_admin_password", ""),
    ("MEILISEARCH_MASTER_KEY", "meilisearch_master_key", ""),
    ("HEDGEDOC_SESSION_SECRET", "hedgedoc_session_secret", ""),
    ("HEDGEDOC_DB_PASS", "hedgedoc_db_password", ""),
    ("HEDGEDOC_ADMIN_PASS", "hedgedoc_admin_password", ""),
    ("LITELLM_MASTER_KEY", "litellm_master_key", ""),
    ("LITELLM_SALT_KEY", "litellm_salt_key", ""),
    ("LITELLM_DB_PASS", "litellm_db_password", ""),
    ("LAKEKEEPER_DB_PASS", "lakekeeper_db_password", ""),
    ("MAGE_PASS", "mage_admin_password", ""),
    ("MINIO_ROOT_PASS", "minio_root_password", ""),
    ("SFTPGO_ADMIN_PASS", "sftpgo_admin_password", ""),
    ("SFTPGO_USER_PASS", "sftpgo_user_password", ""),
    ("HOPPSCOTCH_DB_PASS", "hoppscotch_db_password", ""),
    ("HOPPSCOTCH_JWT", "hoppscotch_jwt_secret", ""),
    ("HOPPSCOTCH_SESSION", "hoppscotch_session_secret", ""),
    ("HOPPSCOTCH_ENCRYPTION", "hoppscotch_encryption_key", ""),
    ("MELTANO_DB_PASS", "meltano_db_password", ""),
    ("SODA_DB_PASS", "soda_db_password", ""),
    ("REDPANDA_ADMIN_PASS", "redpanda_admin_password", ""),
    ("POSTGRES_PASS", "postgres_password", ""),
    ("PG_DUCKLAKE_PASS", "pgducklake_password", ""),
    ("HETZNER_S3_BUCKET_PGDUCKLAKE", "hetzner_s3_bucket_pgducklake", ""),
    ("PGADMIN_PASS", "pgadmin_password", ""),
    ("PREFECT_DB_PASS", "prefect_db_password", ""),
    ("RUSTFS_ROOT_PASS", "rustfs_root_password", ""),
    ("SEAWEEDFS_ADMIN_PASS", "seaweedfs_admin_password", ""),
    ("GARAGE_ADMIN_TOKEN", "garage_admin_token", ""),
    ("GARAGE_RPC_SECRET", "garage_rpc_secret", ""),
    ("LAKEFS_DB_PASS", "lakefs_db_password", ""),
    ("LAKEFS_ENCRYPT_SECRET", "lakefs_encrypt_secret", ""),
    ("LAKEFS_ADMIN_ACCESS_KEY", "lakefs_admin_access_key", ""),
    ("LAKEFS_ADMIN_SECRET_KEY", "lakefs_admin_secret_key", ""),
    ("HETZNER_S3_SERVER", "hetzner_s3_server", ""),
    ("HETZNER_S3_REGION", "hetzner_s3_region", ""),
    ("HETZNER_S3_ACCESS_KEY", "hetzner_s3_access_key", ""),
    ("HETZNER_S3_SECRET_KEY", "hetzner_s3_secret_key", ""),
    ("HETZNER_S3_BUCKET", "hetzner_s3_bucket_lakefs", ""),
    ("HETZNER_S3_BUCKET_GENERAL", "hetzner_s3_bucket_general", ""),
    ("EXTERNAL_S3_ENDPOINT", "external_s3_endpoint", ""),
    ("EXTERNAL_S3_REGION", "external_s3_region", "auto"),
    ("EXTERNAL_S3_ACCESS_KEY", "external_s3_access_key", ""),
    ("EXTERNAL_S3_SECRET_KEY", "external_s3_secret_key", ""),
    ("EXTERNAL_S3_BUCKET", "external_s3_bucket", ""),
    ("EXTERNAL_S3_LABEL", "external_s3_label", "External Storage"),
    ("R2_DATA_ENDPOINT", "r2_data_endpoint", ""),
    ("R2_DATA_ACCESS_KEY", "r2_data_access_key", ""),
    ("R2_DATA_SECRET_KEY", "r2_data_secret_key", ""),
    ("R2_DATA_BUCKET", "r2_data_bucket", ""),
    ("FILESTASH_ADMIN_PASSWORD", "filestash_admin_password", ""),
    ("WINDMILL_ADMIN_PASS", "windmill_admin_password", ""),
    ("WINDMILL_DB_PASS", "windmill_db_password", ""),
    ("WINDMILL_SUPERADMIN_SECRET", "windmill_superadmin_secret", ""),
    ("OPENMETADATA_ADMIN_PASS", "openmetadata_admin_password", ""),
    ("OPENMETADATA_DB_PASS", "openmetadata_db_password", ""),
    ("OPENMETADATA_AIRFLOW_PASS", "openmetadata_airflow_password", ""),
    ("OPENMETADATA_FERNET_KEY", "openmetadata_fernet_key", ""),
    ("GITEA_ADMIN_PASS", "gitea_admin_password", ""),
    ("GITEA_USER_PASS", "gitea_user_password", ""),
    ("GITEA_DB_PASS", "gitea_db_password", ""),
    ("CLICKHOUSE_ADMIN_PASS", "clickhouse_admin_password", ""),
    ("WIKIJS_ADMIN_PASS", "wikijs_admin_password", ""),
    ("WIKIJS_DB_PASS", "wikijs_db_password", ""),
    ("WOODPECKER_AGENT_SECRET", "woodpecker_agent_secret", ""),
    ("NOCODB_ADMIN_PASS", "nocodb_admin_password", ""),
    ("NOCODB_DB_PASS", "nocodb_db_password", ""),
    ("NOCODB_JWT_SECRET", "nocodb_jwt_secret", ""),
    ("DINKY_ADMIN_PASS", "dinky_admin_password", ""),
    ("APPSMITH_ENCRYPTION_PASSWORD", "appsmith_encryption_password", ""),
    ("APPSMITH_ENCRYPTION_SALT", "appsmith_encryption_salt", ""),
    ("DIFY_ADMIN_PASS", "dify_admin_password", ""),
    ("DIFY_DB_PASS", "dify_db_password", ""),
    ("DIFY_REDIS_PASS", "dify_redis_password", ""),
    ("DIFY_SECRET_KEY", "dify_secret_key", ""),
    ("DIFY_WEAVIATE_API_KEY", "dify_weaviate_api_key", ""),
    ("DIFY_SANDBOX_API_KEY", "dify_sandbox_api_key", ""),
    ("DIFY_PLUGIN_DAEMON_KEY", "dify_plugin_daemon_key", ""),
    ("DIFY_PLUGIN_INNER_API_KEY", "dify_plugin_inner_api_key", ""),
    ("DOCKERHUB_USER", "dockerhub_username", ""),
    ("DOCKERHUB_TOKEN", "dockerhub_token", ""),
)


class NexusConfig(BaseModel):
    """Typed view of ``tofu output -json secrets``.

    All fields are ``str | None`` to mirror jq's ``// empty`` semantics:
    a missing or null JSON value parses as ``None`` and renders as the
    empty string in :meth:`dump_shell`. Per-field fallbacks (admin
    username, the two ``EXTERNAL_S3_*`` overwrites) are applied at
    :meth:`dump_shell` time, not at parse time, so the round-trip
    (parse → dump → re-parse) is lossless for actual JSON inputs.

    ``frozen=True`` because a config is constructed once per deploy and
    must not mutate; ``extra="ignore"`` so adding a new tofu output key
    doesn't break parsing for unrelated callers (additive evolution).
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    admin_username: str | None = None
    infisical_admin_password: str | None = None
    infisical_encryption_key: str | None = None
    infisical_auth_secret: str | None = None
    infisical_db_password: str | None = None
    portainer_admin_password: str | None = None
    kuma_admin_password: str | None = None
    grafana_admin_password: str | None = None
    dagster_db_password: str | None = None
    kestra_admin_password: str | None = None
    kestra_db_password: str | None = None
    n8n_admin_password: str | None = None
    metabase_admin_password: str | None = None
    superset_admin_password: str | None = None
    superset_db_password: str | None = None
    superset_secret_key: str | None = None
    cloudbeaver_admin_password: str | None = None
    meilisearch_master_key: str | None = None
    hedgedoc_session_secret: str | None = None
    hedgedoc_db_password: str | None = None
    hedgedoc_admin_password: str | None = None
    litellm_master_key: str | None = None
    litellm_salt_key: str | None = None
    litellm_db_password: str | None = None
    lakekeeper_db_password: str | None = None
    mage_admin_password: str | None = None
    minio_root_password: str | None = None
    sftpgo_admin_password: str | None = None
    sftpgo_user_password: str | None = None
    hoppscotch_db_password: str | None = None
    hoppscotch_jwt_secret: str | None = None
    hoppscotch_session_secret: str | None = None
    hoppscotch_encryption_key: str | None = None
    meltano_db_password: str | None = None
    soda_db_password: str | None = None
    redpanda_admin_password: str | None = None
    postgres_password: str | None = None
    pgducklake_password: str | None = None
    hetzner_s3_bucket_pgducklake: str | None = None
    pgadmin_password: str | None = None
    prefect_db_password: str | None = None
    rustfs_root_password: str | None = None
    seaweedfs_admin_password: str | None = None
    garage_admin_token: str | None = None
    garage_rpc_secret: str | None = None
    lakefs_db_password: str | None = None
    lakefs_encrypt_secret: str | None = None
    lakefs_admin_access_key: str | None = None
    lakefs_admin_secret_key: str | None = None
    hetzner_s3_server: str | None = None
    hetzner_s3_region: str | None = None
    hetzner_s3_access_key: str | None = None
    hetzner_s3_secret_key: str | None = None
    hetzner_s3_bucket_lakefs: str | None = None
    hetzner_s3_bucket_general: str | None = None
    external_s3_endpoint: str | None = None
    external_s3_region: str | None = None
    external_s3_access_key: str | None = None
    external_s3_secret_key: str | None = None
    external_s3_bucket: str | None = None
    external_s3_label: str | None = None
    r2_data_endpoint: str | None = None
    r2_data_access_key: str | None = None
    r2_data_secret_key: str | None = None
    r2_data_bucket: str | None = None
    filestash_admin_password: str | None = None
    windmill_admin_password: str | None = None
    windmill_db_password: str | None = None
    windmill_superadmin_secret: str | None = None
    openmetadata_admin_password: str | None = None
    openmetadata_db_password: str | None = None
    openmetadata_airflow_password: str | None = None
    openmetadata_fernet_key: str | None = None
    gitea_admin_password: str | None = None
    gitea_user_password: str | None = None
    gitea_db_password: str | None = None
    clickhouse_admin_password: str | None = None
    wikijs_admin_password: str | None = None
    wikijs_db_password: str | None = None
    woodpecker_agent_secret: str | None = None
    nocodb_admin_password: str | None = None
    nocodb_db_password: str | None = None
    nocodb_jwt_secret: str | None = None
    dinky_admin_password: str | None = None
    appsmith_encryption_password: str | None = None
    appsmith_encryption_salt: str | None = None
    dify_admin_password: str | None = None
    dify_db_password: str | None = None
    dify_redis_password: str | None = None
    dify_secret_key: str | None = None
    dify_weaviate_api_key: str | None = None
    dify_sandbox_api_key: str | None = None
    dify_plugin_daemon_key: str | None = None
    dify_plugin_inner_api_key: str | None = None
    dockerhub_username: str | None = None
    dockerhub_token: str | None = None

    # Schema is exposed for tests + tooling so they don't re-derive it.
    FIELDS: ClassVar[tuple[tuple[str, str, str], ...]] = _FIELDS

    @classmethod
    def from_secrets_json(cls, raw: str) -> NexusConfig:
        """Parse the output of ``tofu output -json secrets``.

        ``raw`` may be the literal string ``"{}"`` (the fallback when
        tofu state is missing), in which case every field is ``None``
        and :meth:`dump_shell` emits the per-field defaults from
        ``_FIELDS``.
        """
        # ConfigError messages do NOT include the underlying exception's
        # `str(exc)` even though Python lets us. pydantic ValidationError's
        # default repr embeds the offending input values, and
        # JSONDecodeError can include a snippet of the raw input near the
        # parse failure — both can carry secret bytes from SECRETS_JSON.
        # The original exception is still available via `__cause__` when
        # operators reproduce locally with a debugger; the printed CLI
        # error stays free of raw input.
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigError("SECRETS_JSON is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ConfigError(f"SECRETS_JSON must be a JSON object, got {type(payload).__name__}")
        try:
            return cls.model_validate(payload)
        except ValidationError as exc:  # pragma: no cover — every field is Optional[str]
            # Reachable only if a future field gains stricter validation.
            raise ConfigError("SECRETS_JSON failed validation") from exc

    @classmethod
    def from_tofu_output(cls, tofu_dir: Path = Path("tofu/stack")) -> NexusConfig:
        """Run ``tofu output -json secrets`` in ``tofu_dir`` and parse.

        Includes the "tofu failed → treat as empty config" fallback so
        callers can rely on a usable :class:`NexusConfig` even when the
        tofu state is missing or the CLI is unavailable.
        """
        try:
            completed = subprocess.run(
                ["tofu", "output", "-json", "secrets"],
                cwd=tofu_dir,
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return cls.from_secrets_json("{}")
        return cls.from_secrets_json(completed.stdout)

    def dump_shell(self) -> str:
        """Render bash assignments for ``eval``-style consumption.

        Each entry in :data:`_FIELDS` becomes a ``VAR=value`` line in
        source order (not alphabetical), so reviewers can scan the
        block top-to-bottom alongside the schema definition. Values
        are passed through :func:`shlex.quote` because the emitted
        block is consumed via ``eval``; without quoting, an embedded
        ``$``, backtick, or ``;`` in a secret value would trigger
        command substitution / variable expansion / command
        termination at eval time.
        """
        lines: list[str] = []
        for bash_var, json_key, fallback in _FIELDS:
            value = getattr(self, json_key)
            if value is None or value == "":
                value = fallback
            lines.append(f"{bash_var}={shlex.quote(value)}")
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Service hostname composition (Issue #540)
# ---------------------------------------------------------------------------


def service_host(prefix: str, domain: str, separator: str = ".") -> str:
    """Compose a service hostname under the configured subdomain separator.

    Standard single-tenant installs use ``separator='.'`` and produce
    the dot form ``<prefix>.<domain>``. Multi-tenant forks (e.g. an
    education / classroom admin panel built on top of Nexus-Stack)
    provision tenants under a shared base domain via flat subdomains:
    setting ``separator='-'`` on a tenant
    whose ``DOMAIN`` is ``user1.example.com`` produces
    ``<prefix>-user1.example.com`` — which matches the DNS records
    Tofu provisions for that tenant.

    Examples::

        service_host("kestra", "example.com")            # → "kestra.example.com"
        service_host("kestra", "user1.example.com", "-") # → "kestra-user1.example.com"
        service_host("ssh",    "example.com")            # → "ssh.example.com"

    Empty / falsy ``domain`` returns just ``prefix`` (the caller is
    expected to guard against this — every legitimate caller has a
    domain by the time service URLs are built).
    """
    if not domain:
        return prefix
    return f"{prefix}{separator}{domain}"
