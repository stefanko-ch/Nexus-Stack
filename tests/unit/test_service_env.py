"""Tests for nexus_deploy.service_env.

Snapshot tests for representative services + special-case tests
for the 6 quirks (SFTPGo fail-fast, Filestash bcrypt+jq+base64,
pg-ducklake SQL escape, SeaweedFS/Garage sidecar files, LakeFS
2-paths, Gitea append-block idempotency).
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from syrupy.assertion import SnapshotAssertion

from nexus_deploy.config import NexusConfig
from nexus_deploy.infisical import BootstrapEnv
from nexus_deploy.service_env import (
    GiteaWorkspaceConfig,
    ServiceEnvError,
    _atomic_write,
    _bcrypt_password,
    _empty,
    _escape_sql,
    _format_env_line,
    _render_env_file_content,
    _render_filestash,
    _render_grafana,
    _render_lakefs,
    _render_pg_ducklake,
    _render_prometheus_remote_write_block,
    _render_seaweedfs,
    _render_sftpgo,
    _strip_gitea_block,
    append_gitea_workspace_block,
    render_all_env_files,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def full_config() -> NexusConfig:
    """A NexusConfig populated with every field — used as the
    snapshot baseline."""
    return NexusConfig(
        admin_username="admin",
        infisical_admin_password="infi-admin-pw",
        infisical_encryption_key="infi-enc-key",
        infisical_auth_secret="infi-auth-sec",
        infisical_db_password="infi-db-pw",
        portainer_admin_password="port-pw",
        kuma_admin_password="kuma-pw",
        grafana_admin_password="graf-pw",
        dagster_db_password="dagster-pw",
        kestra_admin_password="kestra-pw",
        kestra_db_password="kestra-db-pw",
        n8n_admin_password="n8n-pw",
        metabase_admin_password="meta-pw",
        superset_admin_password="superset-pw",
        superset_db_password="superset-db",
        superset_secret_key="superset-key",
        cloudbeaver_admin_password="cb-pw",
        meilisearch_master_key="meili-master-key-32chars-xxxxxxx",
        mage_admin_password="mage-pw",
        minio_root_password="minio-pw",
        sftpgo_admin_password="sftpgo-admin",
        sftpgo_user_password="sftpgo-user",
        hoppscotch_db_password="hoppscotch-db",
        hoppscotch_jwt_secret="hoppscotch-jwt",
        hoppscotch_session_secret="hoppscotch-session",
        hoppscotch_encryption_key="hoppscotch-enc",
        meltano_db_password="meltano-pw",
        soda_db_password="soda-pw",
        redpanda_admin_password="redpanda-pw",
        postgres_password="pg-pw",
        pgducklake_password="ducklake-pw",
        hetzner_s3_bucket_pgducklake="ducklake-bucket",
        pgadmin_password="pgadmin-pw",
        prefect_db_password="prefect-pw",
        rustfs_root_password="rustfs-pw",
        seaweedfs_admin_password="seaweed-pw",
        garage_admin_token="garage-token",
        garage_rpc_secret="garage-rpc",
        lakefs_db_password="lakefs-db",
        lakefs_encrypt_secret="lakefs-enc",
        lakefs_admin_access_key="lakefs-key",
        lakefs_admin_secret_key="lakefs-sec",
        hetzner_s3_server="fsn1.your-objectstorage.com",
        hetzner_s3_region="fsn1",
        hetzner_s3_access_key="hetzner-access",
        hetzner_s3_secret_key="hetzner-secret",
        hetzner_s3_bucket_lakefs="lakefs-bucket",
        hetzner_s3_bucket_general="general-bucket",
        external_s3_endpoint="",
        external_s3_region="auto",
        external_s3_access_key="",
        external_s3_secret_key="",
        external_s3_bucket="",
        external_s3_label="External Storage",
        r2_data_endpoint="https://r2.cloudflare.com/account",
        r2_data_access_key="r2-access",
        r2_data_secret_key="r2-secret",
        r2_data_bucket="r2-bucket",
        filestash_admin_password="filestash-pw",
        windmill_admin_password="windmill-admin",
        windmill_db_password="windmill-db",
        windmill_superadmin_secret="windmill-super",
        openmetadata_admin_password="om-admin",
        openmetadata_db_password="om-db",
        openmetadata_airflow_password="om-airflow",
        openmetadata_fernet_key="om-fernet",
        gitea_admin_password="gitea-admin",
        gitea_user_password="gitea-user",
        gitea_db_password="gitea-db",
        clickhouse_admin_password="ch-pw",
        wikijs_admin_password="wiki-admin",
        wikijs_db_password="wiki-db",
        woodpecker_agent_secret="wp-agent-sec",
        nocodb_admin_password="nocodb-admin",
        nocodb_db_password="nocodb-db",
        nocodb_jwt_secret="nocodb-jwt",
        dinky_admin_password="dinky-pw",
        appsmith_encryption_password="appsmith-enc-pw",
        appsmith_encryption_salt="appsmith-salt",
        dify_admin_password="dify-admin",
        dify_db_password="dify-db",
        dify_redis_password="dify-redis",
        dify_secret_key="dify-secret",
        dify_weaviate_api_key="dify-weaviate",
        dify_sandbox_api_key="dify-sandbox",
        dify_plugin_daemon_key="dify-daemon",
        dify_plugin_inner_api_key="dify-inner",
    )


@pytest.fixture
def full_env() -> BootstrapEnv:
    return BootstrapEnv(
        domain="example.com",
        admin_email="admin@example.com",
        gitea_user_email="user@example.com",
        gitea_user_username="user",
        gitea_repo_owner="admin",
        repo_name="nexus-example-com-gitea",
        om_principal_domain="example.com",
        woodpecker_gitea_client="wp-client-id",
        woodpecker_gitea_secret="wp-client-secret",
        ssh_private_key_base64="c2g6c2g6Cg==",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_empty_treats_none_and_empty_string_alike() -> None:
    assert _empty(None) is True
    assert _empty("") is True
    assert _empty("x") is False
    assert _empty(" ") is False  # not stripped — matches the canonical layout


def test_escape_sql_doubles_single_quotes() -> None:
    assert _escape_sql("plain") == "plain"
    assert _escape_sql("a'b") == "a''b"
    assert _escape_sql("''") == "''''"


def test_format_env_line_no_quoting_newline_terminated() -> None:
    assert _format_env_line("KEY", "value") == "KEY=value\n"
    # Empty value still produces KEY=\n (matches the canonical layout `${VAR:-}`)
    assert _format_env_line("KEY", "") == "KEY=\n"


def test_render_env_file_content_in_dict_order() -> None:
    out = _render_env_file_content({"A": "1", "B": "2", "C": "3"})
    assert out == "A=1\nB=2\nC=3\n"


# ---------------------------------------------------------------------------
# Meilisearch — fail-fast guard
# ---------------------------------------------------------------------------


def test_meilisearch_raises_on_empty_master_key(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """R-guard: empty master key aborts the deploy with a fail-fast
    ServiceEnvError rather than silently writing MEILI_MASTER_KEY=''
    into the .env. Compose has MEILI_ENV=production, so Meilisearch
    would refuse to start and the container would restart-loop with
    a cryptic error — much harder to diagnose than a clear deploy-
    time abort pointing at the missing Tofu apply / Infisical sync."""
    from nexus_deploy.service_env import _render_meilisearch

    config = full_config.model_copy(update={"meilisearch_master_key": ""})
    with pytest.raises(ServiceEnvError, match="MEILI_MASTER_KEY"):
        _render_meilisearch(config, full_env)


# ---------------------------------------------------------------------------
# Grafana — prometheus.yml remote_write rendering (issue #607)
# ---------------------------------------------------------------------------
#
# Backwards-compatibility contract: when MONITORING_ENDPOINT or
# MONITORING_TOKEN is unset, prometheus.yml must contain a single
# "# remote_write disabled" comment (no remote_write block) so today's
# behaviour is preserved for every stack without Conductor enrolment.
# When BOTH are set, the rendered config must contain a valid
# remote_write block with Bearer auth, the (go_|process_|promhttp_)
# cardinality-drop relabel (Conductor #23 highest-pri defuse), and a
# tenant label. Sidecar is mode 0o644 (NOT 0o600) because it's
# bind-mounted into the non-root prometheus container — see the
# _is_0o644 test below for the full reasoning.


def test_grafana_remote_write_disabled_when_both_unset(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """No env vars → disabled comment, no remote_write block."""
    env = full_env  # full_env has neither monitoring_endpoint nor monitoring_token
    rendered = _render_grafana(full_config, env)
    sidecar = next((s for s in rendered.sidecars if s.relative_path == "prometheus.yml"), None)
    assert sidecar is not None
    assert "# remote_write disabled" in sidecar.content
    assert "remote_write:" not in sidecar.content


def test_grafana_remote_write_disabled_when_only_endpoint_set(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """Endpoint without token → still disabled (no auth = no push).
    Both are required; partial config silently no-ops the push side."""
    env = BootstrapEnv(
        **{
            **{k: getattr(full_env, k) for k in full_env.__dataclass_fields__},
            "monitoring_endpoint": "https://metrics.example.com",
        }
    )
    rendered = _render_grafana(full_config, env)
    sidecar = next(s for s in rendered.sidecars if s.relative_path == "prometheus.yml")
    assert "remote_write:" not in sidecar.content


def test_grafana_remote_write_disabled_when_only_token_set(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """Token without endpoint → still disabled (no destination)."""
    env = BootstrapEnv(
        **{
            **{k: getattr(full_env, k) for k in full_env.__dataclass_fields__},
            "monitoring_token": "fake-token-xxx",
        }
    )
    rendered = _render_grafana(full_config, env)
    sidecar = next(s for s in rendered.sidecars if s.relative_path == "prometheus.yml")
    assert "remote_write:" not in sidecar.content


def test_grafana_remote_write_block_when_both_set(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """Happy path: endpoint + token → full remote_write block with
    /api/v1/write path, Bearer auth, cardinality-drop relabel, tenant
    label (defaulting to domain)."""
    env = BootstrapEnv(
        **{
            **{k: getattr(full_env, k) for k in full_env.__dataclass_fields__},
            "monitoring_endpoint": "https://metrics.example.com",
            "monitoring_token": "fake-token-xxx",
        }
    )
    rendered = _render_grafana(full_config, env)
    sidecar = next(s for s in rendered.sidecars if s.relative_path == "prometheus.yml")
    content = sidecar.content
    assert "remote_write:" in content
    # url / credentials / replacement are emitted as JSON-quoted YAML
    # scalars so YAML-significant characters in operator-supplied
    # values (#, : , leading {/[) can't break the rendered config.
    assert '- url: "https://metrics.example.com/api/v1/write"' in content
    assert "type: Bearer" in content
    assert 'credentials: "fake-token-xxx"' in content
    # Cardinality defuse — Conductor #23 highest-priority.
    assert "(go_|process_|promhttp_).*" in content
    assert "action: drop" in content
    # Tenant label defaults to domain when tenant_id is unset.
    assert "target_label: tenant" in content
    assert 'replacement: "example.com"' in content


def test_grafana_tenant_id_overrides_domain_when_set(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """Conductor can pin a different tenant_id (e.g. class-id) — the
    renderer must use it instead of falling back to domain."""
    env = BootstrapEnv(
        **{
            **{k: getattr(full_env, k) for k in full_env.__dataclass_fields__},
            "monitoring_endpoint": "https://metrics.example.com",
            "monitoring_token": "fake-token",
            "tenant_id": "class-2026-spring-cohort-a",
        }
    )
    rendered = _render_grafana(full_config, env)
    sidecar = next(s for s in rendered.sidecars if s.relative_path == "prometheus.yml")
    assert 'replacement: "class-2026-spring-cohort-a"' in sidecar.content
    assert 'replacement: "example.com"' not in sidecar.content


def test_grafana_trailing_slash_on_endpoint_is_stripped(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """Operator might paste https://metrics.example.com/ with a slash.
    The renderer must not produce //api/v1/write (would 404)."""
    env = BootstrapEnv(
        **{
            **{k: getattr(full_env, k) for k in full_env.__dataclass_fields__},
            "monitoring_endpoint": "https://metrics.example.com/",
            "monitoring_token": "fake-token",
        }
    )
    rendered = _render_grafana(full_config, env)
    sidecar = next(s for s in rendered.sidecars if s.relative_path == "prometheus.yml")
    assert '- url: "https://metrics.example.com/api/v1/write"' in sidecar.content
    assert "//api/v1/write" not in sidecar.content


def test_grafana_prometheus_sidecar_mode_is_0o644(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """Mode must be 0o644: this file is bind-mounted into the
    prometheus container which runs as a non-root UID (65534 in
    prom/prometheus 2.x+). A stricter mode like 0o600 owned by the
    host deploy user would lock the container's prometheus process
    out of its own config and the container would fail to start with
    "permission denied". The token-in-cleartext concern is offset by
    the host-access barrier (SSH behind CF Tunnel + email OTP) +
    the token's redundant presence in Infisical + Actions secrets."""
    env = BootstrapEnv(
        **{
            **{k: getattr(full_env, k) for k in full_env.__dataclass_fields__},
            "monitoring_endpoint": "https://metrics.example.com",
            "monitoring_token": "fake-token",
        }
    )
    rendered = _render_grafana(full_config, env)
    sidecar = next(s for s in rendered.sidecars if s.relative_path == "prometheus.yml")
    assert sidecar.mode == 0o644


def test_grafana_raises_when_template_placeholder_missing(
    full_config: NexusConfig, full_env: BootstrapEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SAFETY: if the prometheus.yml.template is edited and the
    {{ REMOTE_WRITE_BLOCK }} placeholder gets removed/renamed,
    str.replace silently no-ops — the rendered prometheus.yml would
    contain no remote_write block even when the operator has set
    MONITORING_ENDPOINT + MONITORING_TOKEN expecting metrics to flow.
    Renderer must fail-fast with a clear ServiceEnvError pointing at
    the template so the deploy aborts instead of silently dropping
    monitoring data."""
    import nexus_deploy.service_env as svc_env

    # Monkey-patch the template loader to return a template WITHOUT
    # the placeholder — simulates an operator who hand-edited the
    # file and accidentally stripped the marker line.
    monkeypatch.setattr(
        svc_env,
        "_load_prometheus_template",
        lambda: "global:\n  scrape_interval: 15s\n# (placeholder accidentally removed)\n",
    )
    env = BootstrapEnv(
        **{
            **{k: getattr(full_env, k) for k in full_env.__dataclass_fields__},
            "monitoring_endpoint": "https://metrics.example.com",
            "monitoring_token": "fake-token",
        }
    )
    with pytest.raises(ServiceEnvError, match="REMOTE_WRITE_BLOCK"):
        _render_grafana(full_config, env)


def test_grafana_remote_write_block_unit_no_tenant_falls_back_empty() -> None:
    """Edge case unit-test on the helper: when BOTH tenant_id and
    domain are None, the tenant replacement field is an empty string
    (operator misconfig — would still write but show up as `tenant=`
    in vmauth, easy to spot in Grafana). Pass-through, not aborted."""
    e = BootstrapEnv(
        monitoring_endpoint="https://metrics.example.com",
        monitoring_token="fake-token",
        # domain explicitly None, tenant_id None
    )
    block = _render_prometheus_remote_write_block(e)
    # JSON-quoted empty string: "" — still valid YAML, no spoof risk.
    assert 'replacement: ""\n' in block


def test_grafana_remote_write_block_yaml_quotes_dangerous_chars() -> None:
    """Operator-supplied values may contain YAML-significant chars
    (#, ': ', leading {/[, backslashes, quotes). Each must be emitted
    as a JSON-quoted YAML scalar so the rendered prometheus.yml stays
    valid no matter what's in the secrets. Without this, Prometheus
    would refuse to start with a parse error pointing at our generated
    file — operator-debugging-nightmare territory.

    Pins the invariant against any future refactor that switches back
    to bare string interpolation."""
    import json as _json

    e = BootstrapEnv(
        monitoring_endpoint="https://metrics.example.com/api: hello # comment",
        monitoring_token='evil"token\\with{leading-brace',
        tenant_id="weird: tenant #with comment",
    )
    block = _render_prometheus_remote_write_block(e)
    # JSON quoting is the contract — every problematic value is wrapped
    # in "..." with proper escaping. Verify by parsing the JSON-quoted
    # field back and confirming the original value round-trips.
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- url:"):
            quoted = stripped[len("- url:") :].strip()
            # Round-trip via json.loads — would raise if the YAML
            # scalar wasn't a valid JSON string.
            value = _json.loads(quoted)
            assert "api: hello # comment" in value
        elif stripped.startswith("credentials:"):
            quoted = stripped[len("credentials:") :].strip()
            value = _json.loads(quoted)
            assert value == 'evil"token\\with{leading-brace'
        elif stripped.startswith("replacement:"):
            quoted = stripped[len("replacement:") :].strip()
            value = _json.loads(quoted)
            assert value == "weird: tenant #with comment"


# ---------------------------------------------------------------------------
# SFTPGo — fail-fast guard
# ---------------------------------------------------------------------------


def test_sftpgo_raises_on_empty_admin_password(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """R-guard: empty admin password aborts the deploy with a
    fail-fast ServiceEnvError rather than silently writing an
    insecure config."""
    config = full_config.model_copy(update={"sftpgo_admin_password": ""})
    with pytest.raises(ServiceEnvError, match="SFTPGO_ADMIN_PASSWORD"):
        _render_sftpgo(config, full_env)


def test_sftpgo_raises_on_empty_user_password(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    config = full_config.model_copy(update={"sftpgo_user_password": ""})
    with pytest.raises(ServiceEnvError, match="SFTPGO_USER_PASSWORD"):
        _render_sftpgo(config, full_env)


def test_sftpgo_renders_with_mode_0o600(full_config: NexusConfig, full_env: BootstrapEnv) -> None:
    """R-security: SFTPGo .env mode is 0o600 (admin credential in cleartext)."""
    rendered = _render_sftpgo(full_config, full_env)
    assert rendered.mode == 0o600
    assert rendered.env_vars == {"SFTPGO_ADMIN_PASSWORD": "sftpgo-admin"}


# ---------------------------------------------------------------------------
# pg-ducklake — conditional S3 bootstrap SQL with SQL escape
# ---------------------------------------------------------------------------


def test_pg_ducklake_local_only_when_no_s3(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """No Hetzner S3 → fallback SQL only sets local table path."""
    config = full_config.model_copy(update={"hetzner_s3_server": ""})
    rendered = _render_pg_ducklake(config, full_env)
    assert len(rendered.sidecars) == 1
    sql = rendered.sidecars[0].content
    assert "ducklake.default_table_path = '/var/lib/ducklake/'" in sql
    assert "create_simple_secret" not in sql
    assert "drop_secret" not in sql


def test_pg_ducklake_with_s3_creates_secret(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    rendered = _render_pg_ducklake(full_config, full_env)
    sql = rendered.sidecars[0].content
    assert "duckdb.create_simple_secret(" in sql
    assert "duckdb.drop_secret('ducklake_s3')" in sql
    assert "key_id := 'hetzner-access'" in sql
    assert "endpoint := 'fsn1.your-objectstorage.com'" in sql
    assert "scope := 's3://ducklake-bucket/'" in sql
    assert "ducklake.default_table_path = 's3://ducklake-bucket/'" in sql
    assert "pg_reload_conf()" in sql


def test_pg_ducklake_sql_escapes_single_quotes_in_secret(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """R-injection: a secret containing single quotes must be SQL-escaped."""
    config = full_config.model_copy(update={"hetzner_s3_secret_key": "evil'; DROP TABLE--"})
    rendered = _render_pg_ducklake(config, full_env)
    sql = rendered.sidecars[0].content
    # Single quotes doubled, no unescaped '
    assert "secret := 'evil''; DROP TABLE--'" in sql
    # The dangerous unquoted form must NOT appear
    assert "'; DROP TABLE--';" not in sql.replace("''", "")


def test_pg_ducklake_sidecar_path_is_init_subdir(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    rendered = _render_pg_ducklake(full_config, full_env)
    assert rendered.sidecars[0].relative_path == "init/00-ducklake-bootstrap.sql"


# ---------------------------------------------------------------------------
# SeaweedFS — sidecar s3.json
# ---------------------------------------------------------------------------


def test_seaweedfs_renders_s3_json_sidecar(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    rendered = _render_seaweedfs(full_config, full_env)
    assert len(rendered.sidecars) == 1
    sidecar = rendered.sidecars[0]
    assert sidecar.relative_path == "s3.json"
    # Parse it back and check shape
    import json as _json

    parsed = _json.loads(sidecar.content)
    assert parsed["identities"][0]["name"] == "admin"
    assert parsed["identities"][0]["credentials"][0]["accessKey"] == "nexus-seaweedfs"
    assert parsed["identities"][0]["credentials"][0]["secretKey"] == "seaweed-pw"
    assert "Admin" in parsed["identities"][0]["actions"]


# ---------------------------------------------------------------------------
# LakeFS — 2-path conditional (S3 vs local)
# ---------------------------------------------------------------------------


def test_lakefs_local_when_no_s3(full_config: NexusConfig, full_env: BootstrapEnv) -> None:
    """When Hetzner S3 vars are missing, LakeFS falls back to local
    blockstore."""
    config = full_config.model_copy(update={"hetzner_s3_server": ""})
    rendered = _render_lakefs(config, full_env)
    assert rendered.env_vars["LAKEFS_BLOCKSTORE_TYPE"] == "local"
    assert "LAKEFS_BLOCKSTORE_LOCAL_PATH" in rendered.env_vars
    assert "LAKEFS_BLOCKSTORE_S3_ENDPOINT" not in rendered.env_vars


def test_lakefs_s3_path_emits_all_s3_fields(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    rendered = _render_lakefs(full_config, full_env)
    assert rendered.env_vars["LAKEFS_BLOCKSTORE_TYPE"] == "s3"
    assert (
        rendered.env_vars["LAKEFS_BLOCKSTORE_S3_ENDPOINT"] == "https://fsn1.your-objectstorage.com"
    )
    assert rendered.env_vars["LAKEFS_BLOCKSTORE_S3_REGION"] == "fsn1"
    assert "LAKEFS_BLOCKSTORE_LOCAL_PATH" not in rendered.env_vars


def test_lakefs_postgres_connection_string_includes_password(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    rendered = _render_lakefs(full_config, full_env)
    assert "lakefs-db" in rendered.env_vars["LAKEFS_DATABASE_POSTGRES_CONNECTION_STRING"]


# ---------------------------------------------------------------------------
# Filestash — bcrypt + jq + base64
# ---------------------------------------------------------------------------


def test_bcrypt_password_returns_bcrypt_hash() -> None:
    """Sanity test that htpasswd is callable and returns a bcrypt hash."""
    if subprocess.run(["which", "htpasswd"], capture_output=True).returncode != 0:
        pytest.skip("htpasswd not installed (apache2-utils)")
    result = _bcrypt_password("test-pw")
    assert result.startswith("$2y$") or result.startswith("$2a$") or result.startswith("$2b$")


def test_filestash_escapes_dollar_signs_for_compose(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """R-quirk: bcrypt hashes contain ``$`` which needs ``$$`` for
    docker-compose env parsing."""
    with patch("nexus_deploy.service_env._bcrypt_password", return_value="$2y$10$hash"):
        rendered = _render_filestash(full_config, full_env)
    assert rendered.env_vars["ADMIN_PASSWORD"] == "$$2y$$10$$hash"


def test_filestash_no_admin_password_means_empty_admin_field(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    config = full_config.model_copy(update={"filestash_admin_password": ""})
    rendered = _render_filestash(config, full_env)
    assert rendered.env_vars["ADMIN_PASSWORD"] == ""


def test_filestash_emits_config_json_when_s3_configured(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """At least one S3 backend (R2 in this fixture) → CONFIG_JSON
    base64-encoded."""
    with patch("nexus_deploy.service_env._bcrypt_password", return_value="$2y$10$hash"):
        rendered = _render_filestash(full_config, full_env)
    assert "CONFIG_JSON" in rendered.env_vars
    # Base64-decode and parse
    import base64
    import json as _json

    decoded = base64.b64decode(rendered.env_vars["CONFIG_JSON"]).decode()
    parsed = _json.loads(decoded)
    assert "connections" in parsed
    # We have R2 + Hetzner configured in fixture, External is empty
    labels = [c["label"] for c in parsed["connections"]]
    assert "R2 Datalake" in labels
    assert "Hetzner Storage" in labels
    # Middleware shape (legacy parity): identity_provider + attribute_mapping
    assert "middleware" in parsed
    assert parsed["middleware"]["identity_provider"]["type"] == "passthrough"
    assert parsed["middleware"]["attribute_mapping"]["related_backend"] == "R2 Datalake"
    # params is JSON-stringified per legacy (Filestash encrypts each)
    decoded_params = _json.loads(parsed["middleware"]["attribute_mapping"]["params"])
    # Bucket paths must be /<bucket>/ (leading + trailing slash)
    assert decoded_params["R2 Datalake"]["path"] == "/r2-bucket/"
    assert decoded_params["Hetzner Storage"]["path"] == "/general-bucket/"


def test_filestash_no_config_json_when_no_s3(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """No S3 backends → no CONFIG_JSON line."""
    no_s3 = full_config.model_copy(
        update={
            "r2_data_endpoint": "",
            "r2_data_access_key": "",
            "hetzner_s3_server": "",
            "hetzner_s3_access_key": "",
            "external_s3_endpoint": "",
            "external_s3_access_key": "",
        },
    )
    with patch("nexus_deploy.service_env._bcrypt_password", return_value="$2y$10$hash"):
        rendered = _render_filestash(no_s3, full_env)
    assert "CONFIG_JSON" not in rendered.env_vars


# ---------------------------------------------------------------------------
# Gitea workspace block — append + idempotency
# ---------------------------------------------------------------------------


def test_strip_gitea_block_on_clean_content_is_noop() -> None:
    content = "FOO=bar\nBAZ=qux\n"
    assert _strip_gitea_block(content) == content


def test_strip_gitea_block_removes_existing_block() -> None:
    content = (
        "FOO=bar\n"
        "# >>> Gitea workspace repo (auto-generated, do not edit)\n"
        "GITEA_URL=http://gitea:3000\n"
        "OLD=stale\n"
        "# <<< Gitea workspace repo\n"
        "BAZ=qux\n"
    )
    cleaned = _strip_gitea_block(content)
    assert "OLD=stale" not in cleaned
    assert ">>> Gitea workspace" not in cleaned
    assert "FOO=bar" in cleaned
    assert "BAZ=qux" in cleaned


def test_append_gitea_workspace_block_idempotent(tmp_path: Path) -> None:
    """R-idempotency: re-running adds the block once, doesn't pile."""
    stacks = tmp_path / "stacks"
    (stacks / "jupyter").mkdir(parents=True)
    (stacks / "jupyter" / ".env").write_text("EXISTING=value\n")

    cfg = GiteaWorkspaceConfig(
        gitea_repo_url="http://gitea:3000/admin/repo",
        gitea_username="admin",
        gitea_password="pw",
        git_author_name="admin",
        git_author_email="admin@example.com",
        repo_name="repo",
    )
    # First append
    appended1 = append_gitea_workspace_block(cfg, ["jupyter", "gitea"], stacks_dir=stacks)
    content1 = (stacks / "jupyter" / ".env").read_text()
    assert appended1 == ("jupyter",)
    assert content1.count("# >>> Gitea workspace") == 1

    # Second append with different password — should still have ONE block.
    cfg2 = GiteaWorkspaceConfig(
        gitea_repo_url="http://gitea:3000/admin/repo",
        gitea_username="admin",
        gitea_password="new-pw",
        git_author_name="admin",
        git_author_email="admin@example.com",
        repo_name="repo",
    )
    append_gitea_workspace_block(cfg2, ["jupyter", "gitea"], stacks_dir=stacks)
    content2 = (stacks / "jupyter" / ".env").read_text()
    assert content2.count("# >>> Gitea workspace") == 1
    assert "GITEA_PASSWORD=new-pw" in content2
    assert "GITEA_PASSWORD=pw\n" not in content2  # old password gone
    # Original content preserved
    assert "EXISTING=value" in content2


def test_append_gitea_skips_disabled_services(tmp_path: Path) -> None:
    stacks = tmp_path / "stacks"
    (stacks / "jupyter").mkdir(parents=True)
    (stacks / "jupyter" / ".env").write_text("X=1\n")

    cfg = GiteaWorkspaceConfig(
        gitea_repo_url="x",
        gitea_username="x",
        gitea_password="x",
        git_author_name="x",
        git_author_email="x",
        repo_name="x",
    )
    # marimo not enabled; jupyter is
    appended = append_gitea_workspace_block(cfg, ["jupyter"], stacks_dir=stacks)
    assert appended == ("jupyter",)


def test_append_gitea_skips_when_env_missing(tmp_path: Path) -> None:
    """A service in the enabled list but without .env yet (e.g.
    spec failed to render) — append silently skips it."""
    stacks = tmp_path / "stacks"
    (stacks / "jupyter").mkdir(parents=True)
    # NO .env file written
    cfg = GiteaWorkspaceConfig(
        gitea_repo_url="x",
        gitea_username="x",
        gitea_password="x",
        git_author_name="x",
        git_author_email="x",
        repo_name="x",
    )
    appended = append_gitea_workspace_block(cfg, ["jupyter"], stacks_dir=stacks)
    assert appended == ()


# ---------------------------------------------------------------------------
# render_all_env_files — orchestration
# ---------------------------------------------------------------------------


def test_render_prefect_emits_r2_credentials(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """R-prefect-r2-explicit (#531 R4 #9): the four R2_* keys MUST
    appear in stacks/prefect/.env. The seeded NYC Green-Taxi flow
    reads them at task entry; an accidentally-dropped key would crash
    the flow with a confusing boto/DuckDB error instead of a clear
    'configure R2 first' hint, so this test pins the contract
    explicitly rather than relying on the catch-all generic-render
    smoke test."""
    config = full_config.model_copy(
        update={
            "r2_data_endpoint": "https://r2.example.com",
            "r2_data_access_key": "ak-prefect",
            "r2_data_secret_key": "sk-prefect",
            "r2_data_bucket": "prefect-bucket",
        },
    )
    render_all_env_files(config, full_env, ["prefect"], stacks_dir=tmp_path)
    prefect_env = (tmp_path / "prefect" / ".env").read_text()
    assert "R2_ENDPOINT=https://r2.example.com" in prefect_env
    assert "R2_ACCESS_KEY=ak-prefect" in prefect_env
    assert "R2_SECRET_KEY=sk-prefect" in prefect_env
    assert "R2_BUCKET=prefect-bucket" in prefect_env


def test_render_prefect_emits_empty_r2_when_unconfigured(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """When the optional R2 datalake isn't configured (r2_data_*
    fields blank), the R2_* keys are still written but with empty
    values. The Prefect flow's upfront precondition check catches
    those and raises a clear error rather than letting boto crash
    at runtime."""
    config = full_config.model_copy(
        update={
            "r2_data_endpoint": "",
            "r2_data_access_key": "",
            "r2_data_secret_key": "",
            "r2_data_bucket": "",
        },
    )
    render_all_env_files(config, full_env, ["prefect"], stacks_dir=tmp_path)
    prefect_env = (tmp_path / "prefect" / ".env").read_text()
    # Keys present, values empty — the seed flow reads via os.environ.get
    # which returns "" (falsy) in the precondition check.
    assert "R2_ENDPOINT=\n" in prefect_env
    assert "R2_ACCESS_KEY=\n" in prefect_env
    assert "R2_SECRET_KEY=\n" in prefect_env
    assert "R2_BUCKET=\n" in prefect_env


def test_render_all_writes_only_enabled_services(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """Disabled services should NOT have a .env file written."""
    enabled = ["postgres", "kestra"]
    result = render_all_env_files(full_config, full_env, enabled, stacks_dir=tmp_path)

    assert (tmp_path / "postgres" / ".env").exists()
    assert (tmp_path / "kestra" / ".env").exists()
    # gitea is NOT in enabled
    assert not (tmp_path / "gitea" / ".env").exists()

    # Counts
    rendered = {s.service for s in result.services if s.status == "rendered"}
    assert "postgres" in rendered
    assert "kestra" in rendered
    skipped_not_enabled = {s.service for s in result.services if s.status == "skipped-not-enabled"}
    assert "gitea" in skipped_not_enabled


def test_render_all_marimo_creates_env_file_for_gitea_append(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """R-marimo-gitea (#531): Marimo MUST get a (possibly empty) ``.env``
    file from its EnvSpec render — without it,
    ``append_gitea_workspace_block`` sees ``not env_path.exists()``
    and silently skips, leaving Marimo with no GITEA_REPO_URL /
    GITEA_USERNAME / GITEA_PASSWORD / REPO_NAME plumbed through to
    the container, so the workspace repo never becomes visible in
    the Marimo UI. This was the bug observed during initial-setup
    testing.
    """
    result = render_all_env_files(full_config, full_env, ["marimo"], stacks_dir=tmp_path)
    marimo_env = tmp_path / "marimo" / ".env"
    assert marimo_env.exists(), "Marimo spec must produce stacks/marimo/.env"
    marimo_result = next(s for s in result.services if s.service == "marimo")
    assert marimo_result.status == "rendered"


def test_render_all_marimo_then_append_gitea_block_succeeds(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """End-to-end: render_all_env_files creates Marimo's .env, then
    append_gitea_workspace_block writes the Gitea coords into it."""
    render_all_env_files(full_config, full_env, ["marimo"], stacks_dir=tmp_path)
    cfg = GiteaWorkspaceConfig(
        gitea_repo_url="http://gitea:3000/owner/workspace.git",
        gitea_username="ops",
        gitea_password="pw",
        git_author_name="Operator",
        git_author_email="ops@example.com",
        repo_name="workspace",
    )
    appended = append_gitea_workspace_block(cfg, ["marimo"], stacks_dir=tmp_path)
    assert appended == ("marimo",)
    content = (tmp_path / "marimo" / ".env").read_text()
    # Assert ALL env-vars the Gitea-integrated stacks depend on. The
    # original bug was that ZERO of them landed in .env (file didn't
    # exist for the appender), but a future regression that drops
    # only one (e.g. GITEA_PASSWORD or WORKSPACE_BRANCH) would still
    # let the clone fail in production — Prefect's `pull:` step
    # explicitly references WORKSPACE_BRANCH in the seeded manifest,
    # and Marimo's clone step needs the four GITEA_* + REPO_NAME.
    # Each line is asserted explicitly.
    assert "GITEA_REPO_URL=http://gitea:3000/owner/workspace.git" in content
    assert "GITEA_USERNAME=ops" in content
    assert "GITEA_PASSWORD=pw" in content
    assert "REPO_NAME=workspace" in content
    # WORKSPACE_BRANCH defaults to "main" when not explicitly set on
    # the GiteaWorkspaceConfig — locks the back-compat default in.
    assert "WORKSPACE_BRANCH=main" in content


def test_render_all_code_server_creates_env_file_for_gitea_append(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """R-code-server-gitea (#580 follow-up): code-server MUST get a
    (possibly empty) ``.env`` file from its EnvSpec render — same bug
    class as the Marimo fix in commit fb586ab. Without it,
    ``append_gitea_workspace_block`` sees ``not env_path.exists()``
    and silently skips, leaving code-server with no GITEA_REPO_URL /
    GITEA_USERNAME / GITEA_PASSWORD / REPO_NAME plumbed through; the
    compose entrypoint's clone step then never fires and students see
    only the bare /home/coder/ instead of the workspace fork.
    """
    result = render_all_env_files(full_config, full_env, ["code-server"], stacks_dir=tmp_path)
    code_server_env = tmp_path / "code-server" / ".env"
    assert code_server_env.exists(), "code-server spec must produce stacks/code-server/.env"
    code_server_result = next(s for s in result.services if s.service == "code-server")
    assert code_server_result.status == "rendered"


def test_render_all_code_server_then_append_gitea_block_succeeds(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """End-to-end for code-server: render_all_env_files creates the
    .env, then append_gitea_workspace_block writes the Gitea coords
    into it. Mirrors the equivalent Marimo test (commit fb586ab) —
    these two tests together pin the invariant for every entry in
    _GITEA_APPEND_TARGETS: spec render must create the .env so the
    Gitea-append helper can populate it."""
    render_all_env_files(full_config, full_env, ["code-server"], stacks_dir=tmp_path)
    cfg = GiteaWorkspaceConfig(
        gitea_repo_url="http://gitea:3000/owner/workspace.git",
        gitea_username="ops",
        gitea_password="pw",
        git_author_name="Operator",
        git_author_email="ops@example.com",
        repo_name="workspace",
    )
    appended = append_gitea_workspace_block(cfg, ["code-server"], stacks_dir=tmp_path)
    assert appended == ("code-server",)
    content = (tmp_path / "code-server" / ".env").read_text()
    assert "GITEA_REPO_URL=http://gitea:3000/owner/workspace.git" in content
    assert "GITEA_USERNAME=ops" in content
    assert "GITEA_PASSWORD=pw" in content
    assert "REPO_NAME=workspace" in content
    assert "WORKSPACE_BRANCH=main" in content


def test_render_all_code_server_never_emits_nexus_postgres_enabled(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """Regression guard for #593 (SQLTools revert): NEXUS_POSTGRES_ENABLED
    must NEVER appear in code-server's .env, regardless of whether
    postgres is in the enabled list. The old wiring (added in #588,
    reverted in #593) used this flag to trigger a settings.json write
    that leaked the Postgres admin password in plaintext into the
    persistent volume. If a future PR re-introduces a postgres-aware
    branch in _render_code_server, this test fails — forcing a
    deliberate review of whether the new mechanism re-creates the
    password-leak class of bug."""
    # With postgres enabled
    render_all_env_files(full_config, full_env, ["code-server", "postgres"], stacks_dir=tmp_path)
    content = (tmp_path / "code-server" / ".env").read_text()
    assert "NEXUS_POSTGRES_ENABLED" not in content
    # With postgres NOT enabled (paranoid: ensure no accidental emit)
    render_all_env_files(full_config, full_env, ["code-server"], stacks_dir=tmp_path)
    content = (tmp_path / "code-server" / ".env").read_text()
    assert "NEXUS_POSTGRES_ENABLED" not in content


def test_render_all_prefect_then_append_gitea_block_writes_custom_branch(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """R-workspace-branch (#531 R8 #4): a non-default branch (e.g.
    'master' on a mirrored upstream) must propagate to .env so
    Prefect's `pull:` step and any Kestra/Meltano clone step uses
    the right ref. Without explicit coverage, a future regression
    that ignores the cfg.workspace_branch field would silently keep
    'main' and break mirrored Prefect workspaces."""
    render_all_env_files(full_config, full_env, ["prefect"], stacks_dir=tmp_path)
    cfg = GiteaWorkspaceConfig(
        gitea_repo_url="http://gitea:3000/owner/workspace.git",
        gitea_username="ops",
        gitea_password="pw",
        git_author_name="Operator",
        git_author_email="ops@example.com",
        repo_name="workspace",
        workspace_branch="master",
    )
    append_gitea_workspace_block(cfg, ["prefect"], stacks_dir=tmp_path)
    content = (tmp_path / "prefect" / ".env").read_text()
    assert "WORKSPACE_BRANCH=master" in content
    assert "WORKSPACE_BRANCH=main" not in content


def test_render_all_skipped_guard_does_not_write_file(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """A guard-failure (e.g. wikijs without DB password) should
    skip the file write entirely."""
    config = full_config.model_copy(update={"wikijs_db_password": ""})
    result = render_all_env_files(config, full_env, ["wikijs"], stacks_dir=tmp_path)
    assert not (tmp_path / "wikijs" / ".env").exists()
    wikijs_result = next(s for s in result.services if s.service == "wikijs")
    assert wikijs_result.status == "skipped-guard"
    assert "WIKIJS_DB_PASS" in wikijs_result.detail


def test_render_all_propagates_sftpgo_fail_fast(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """SFTPGo with empty password raises ServiceEnvError — that's
    a hard-abort signal for the CLI."""
    config = full_config.model_copy(update={"sftpgo_admin_password": ""})
    with pytest.raises(ServiceEnvError):
        render_all_env_files(config, full_env, ["sftpgo"], stacks_dir=tmp_path)


def test_render_all_jupyter_uses_local_master_when_no_spark(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """R-conditional: jupyter SPARK_MASTER depends on whether spark
    is in the enabled list."""
    render_all_env_files(full_config, full_env, ["jupyter"], stacks_dir=tmp_path)
    content = (tmp_path / "jupyter" / ".env").read_text()
    assert "SPARK_MASTER=local[*]" in content


def test_render_all_jupyter_uses_spark_master_when_spark_enabled(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    render_all_env_files(full_config, full_env, ["jupyter", "spark"], stacks_dir=tmp_path)
    content = (tmp_path / "jupyter" / ".env").read_text()
    assert "SPARK_MASTER=spark://spark-master:7077" in content


def test_render_all_writes_sidecars_for_seaweedfs(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    render_all_env_files(full_config, full_env, ["seaweedfs"], stacks_dir=tmp_path)
    assert (tmp_path / "seaweedfs" / ".env").exists()
    assert (tmp_path / "seaweedfs" / "s3.json").exists()


def test_render_all_writes_sidecars_for_garage(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    render_all_env_files(full_config, full_env, ["garage"], stacks_dir=tmp_path)
    assert (tmp_path / "garage" / ".env").exists()
    assert (tmp_path / "garage" / "garage.toml").exists()


def test_render_all_pg_ducklake_writes_init_sql(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    render_all_env_files(full_config, full_env, ["pg-ducklake"], stacks_dir=tmp_path)
    assert (tmp_path / "pg-ducklake" / ".env").exists()
    assert (tmp_path / "pg-ducklake" / "init" / "00-ducklake-bootstrap.sql").exists()


def test_render_all_sftpgo_writes_with_mode_600(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """R-security: SFTPGo .env mode is 0o600."""
    render_all_env_files(full_config, full_env, ["sftpgo"], stacks_dir=tmp_path)
    file_mode = stat.S_IMODE((tmp_path / "sftpgo" / ".env").stat().st_mode)
    assert file_mode == 0o600


# ---------------------------------------------------------------------------
# Atomic write — TOCTOU + permission tests (reused setup.py pattern)
# ---------------------------------------------------------------------------


def test_atomic_write_creates_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "subdir" / ".env"
    _atomic_write(target, "X=1\n")
    assert target.exists()
    assert target.read_text() == "X=1\n"


def test_atomic_write_default_mode_644(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    _atomic_write(target, "X=1\n")
    file_mode = stat.S_IMODE(target.stat().st_mode)
    assert file_mode == 0o644


def test_atomic_write_explicit_mode_600(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    _atomic_write(target, "X=1\n", mode=0o600)
    file_mode = stat.S_IMODE(target.stat().st_mode)
    assert file_mode == 0o600


def test_atomic_write_replaces_existing(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    target.write_text("OLD=1\n")
    _atomic_write(target, "NEW=2\n")
    assert target.read_text() == "NEW=2\n"


# ---------------------------------------------------------------------------
# Snapshot tests — pin per-service rendered content for selected stacks
# ---------------------------------------------------------------------------


def test_snapshot_postgres(
    full_config: NexusConfig, full_env: BootstrapEnv, snapshot: SnapshotAssertion
) -> None:
    from nexus_deploy.service_env import _render_postgres

    rendered = _render_postgres(full_config, full_env)
    assert _render_env_file_content(rendered.env_vars) == snapshot


def test_snapshot_kestra(
    full_config: NexusConfig, full_env: BootstrapEnv, snapshot: SnapshotAssertion
) -> None:
    from nexus_deploy.service_env import _render_kestra

    rendered = _render_kestra(full_config, full_env)
    assert _render_env_file_content(rendered.env_vars) == snapshot


def test_snapshot_hoppscotch_full(
    full_config: NexusConfig, full_env: BootstrapEnv, snapshot: SnapshotAssertion
) -> None:
    """Hoppscotch has 16 vars including derived URLs — snapshot pins
    the entire shape."""
    from nexus_deploy.service_env import _render_hoppscotch

    rendered = _render_hoppscotch(full_config, full_env)
    assert _render_env_file_content(rendered.env_vars) == snapshot


def test_snapshot_lakefs_s3(
    full_config: NexusConfig, full_env: BootstrapEnv, snapshot: SnapshotAssertion
) -> None:
    rendered = _render_lakefs(full_config, full_env)
    assert _render_env_file_content(rendered.env_vars) == snapshot


def test_snapshot_lakefs_local_fallback(
    full_config: NexusConfig, full_env: BootstrapEnv, snapshot: SnapshotAssertion
) -> None:
    config = full_config.model_copy(update={"hetzner_s3_server": ""})
    rendered = _render_lakefs(config, full_env)
    assert _render_env_file_content(rendered.env_vars) == snapshot


def test_snapshot_pg_ducklake_sql_with_s3(
    full_config: NexusConfig, full_env: BootstrapEnv, snapshot: SnapshotAssertion
) -> None:
    rendered = _render_pg_ducklake(full_config, full_env)
    assert rendered.sidecars[0].content == snapshot


def test_snapshot_pg_ducklake_sql_without_s3(
    full_config: NexusConfig, full_env: BootstrapEnv, snapshot: SnapshotAssertion
) -> None:
    config = full_config.model_copy(update={"hetzner_s3_server": ""})
    rendered = _render_pg_ducklake(config, full_env)
    assert rendered.sidecars[0].content == snapshot


def test_snapshot_garage_toml(
    full_config: NexusConfig, full_env: BootstrapEnv, snapshot: SnapshotAssertion
) -> None:
    from nexus_deploy.service_env import _render_garage

    rendered = _render_garage(full_config, full_env)
    assert rendered.sidecars[0].content == snapshot


def test_snapshot_seaweedfs_s3_json(
    full_config: NexusConfig, full_env: BootstrapEnv, snapshot: SnapshotAssertion
) -> None:
    rendered = _render_seaweedfs(full_config, full_env)
    assert rendered.sidecars[0].content == snapshot


def test_snapshot_dify_full(
    full_config: NexusConfig, full_env: BootstrapEnv, snapshot: SnapshotAssertion
) -> None:
    from nexus_deploy.service_env import _render_dify

    rendered = _render_dify(full_config, full_env)
    assert _render_env_file_content(rendered.env_vars) == snapshot


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_service_env_unknown_arg_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    from nexus_deploy.__main__ import _service_env

    rc = _service_env(["--bogus"])
    assert rc == 2
    assert "unknown arg" in capsys.readouterr().err


def test_cli_service_env_missing_enabled_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    from nexus_deploy.__main__ import _service_env

    rc = _service_env([])
    assert rc == 2
    assert "--enabled" in capsys.readouterr().err


def test_cli_service_env_bad_stacks_dir_returns_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _service_env

    bogus = tmp_path / "does-not-exist"
    rc = _service_env(["--enabled", "postgres", "--stacks-dir", str(bogus)])
    assert rc == 2
    assert "not a directory" in capsys.readouterr().err


def test_simple_render_functions_smoke(full_config: NexusConfig, full_env: BootstrapEnv) -> None:
    """Smoke-test every simple render function. Each should produce
    a non-empty env_vars dict for a fully-populated NexusConfig.
    Catches any field-rename drift between NexusConfig and the
    render functions."""
    from nexus_deploy.service_env import (
        _render_appsmith,
        _render_clickhouse,
        _render_cloudbeaver,
        _render_dagster,
        _render_dify,
        _render_dinky,
        _render_flink,
        _render_gitea,
        _render_grafana,
        _render_hoppscotch,
        _render_infisical,
        _render_kestra,
        _render_mage,
        _render_meilisearch,
        _render_meltano,
        _render_minio,
        _render_nocodb,
        _render_openmetadata,
        _render_pgadmin,
        _render_postgres,
        _render_prefect,
        _render_redpanda_console,
        _render_rustfs,
        _render_s3manager,
        _render_soda,
        _render_spark,
        _render_superset,
        _render_trino,
        _render_wikijs,
        _render_windmill,
        _render_woodpecker,
    )

    simple_renders = (
        _render_infisical,
        _render_grafana,
        _render_dagster,
        _render_kestra,
        _render_cloudbeaver,
        _render_mage,
        _render_meilisearch,
        _render_minio,
        _render_redpanda_console,
        _render_hoppscotch,
        _render_meltano,
        _render_soda,
        _render_postgres,
        _render_pgadmin,
        _render_prefect,
        _render_windmill,
        _render_superset,
        _render_openmetadata,
        _render_gitea,
        _render_clickhouse,
        _render_trino,
        _render_rustfs,
        _render_woodpecker,
        _render_spark,
        _render_flink,
        _render_dinky,
        _render_s3manager,
        _render_wikijs,
        _render_appsmith,
        _render_nocodb,
        _render_dify,
    )
    for render in simple_renders:
        result = render(full_config, full_env)
        # All simple renders should produce env_vars when fully populated
        # (no skip_reason for happy-path).
        assert result.skip_reason is None or render is _render_dinky
        assert result.env_vars  # non-empty
        # Defensive: no hidden None values leaked
        for v in result.env_vars.values():
            assert isinstance(v, str)


def test_render_pgadmin_emits_pgpass_sidecar(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    """pgAdmin's pre-configured 'Nexus PostgreSQL' server references
    PassFile=/pgpass in servers.json; this test pins that the sidecar
    is rendered with libpq's pgpass format (host:port:db:user:pass)
    and the nexus-postgres user (not 'postgres' — see CLAUDE.md
    naming convention). Regression guard: without this sidecar the
    pre-configured connection would prompt for a password on every
    click."""
    from nexus_deploy.service_env import _render_pgadmin

    result = _render_pgadmin(full_config, full_env)
    assert len(result.sidecars) == 1
    pgpass = result.sidecars[0]
    assert pgpass.relative_path == "pgpass"
    assert pgpass.content == "postgres:5432:postgres:nexus-postgres:pg-pw\n"
    # 0o644 so pgAdmin's uid 5050 can read it — libpq's 0o600 check
    # doesn't apply here, see render docstring.
    assert pgpass.mode == 0o644


def test_appsmith_skipped_when_salt_missing(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    from nexus_deploy.service_env import _render_appsmith

    config = full_config.model_copy(update={"appsmith_encryption_salt": ""})
    rendered = _render_appsmith(config, full_env)
    assert rendered.skip_reason is not None


def test_nocodb_skipped_when_jwt_missing(full_config: NexusConfig, full_env: BootstrapEnv) -> None:
    from nexus_deploy.service_env import _render_nocodb

    config = full_config.model_copy(update={"nocodb_jwt_secret": ""})
    rendered = _render_nocodb(config, full_env)
    assert rendered.skip_reason is not None


def test_dify_skipped_when_admin_pass_missing(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    from nexus_deploy.service_env import _render_dify

    config = full_config.model_copy(update={"dify_admin_password": ""})
    rendered = _render_dify(config, full_env)
    assert rendered.skip_reason is not None


def test_woodpecker_skipped_when_agent_secret_missing(
    full_config: NexusConfig, full_env: BootstrapEnv
) -> None:
    from nexus_deploy.service_env import _render_woodpecker

    config = full_config.model_copy(update={"woodpecker_agent_secret": ""})
    rendered = _render_woodpecker(config, full_env)
    assert rendered.skip_reason is not None


def test_render_all_renders_full_stack_combination(
    full_config: NexusConfig, full_env: BootstrapEnv, tmp_path: Path
) -> None:
    """Smoke: enable a representative full stack list (one of each
    quirk class) and confirm render-all completes without raise."""
    enabled = [
        "infisical",
        "postgres",
        "kestra",
        "gitea",
        "clickhouse",
        "spark",
        "jupyter",
        "pg-ducklake",
        "lakefs",
        "seaweedfs",
        "garage",
        "filestash",
        "trino",
        "appsmith",
        "dify",
    ]
    with patch("nexus_deploy.service_env._bcrypt_password", return_value="$2y$10$h"):
        result = render_all_env_files(full_config, full_env, enabled, stacks_dir=tmp_path)
    assert result.failed == 0
    assert result.rendered >= 10  # most should render


def test_servicerenderresult_status_is_success_property() -> None:
    from nexus_deploy.service_env import ServiceEnvResult, ServiceRenderResult

    ok = ServiceEnvResult(
        services=(ServiceRenderResult(service="a", status="rendered"),),
    )
    assert ok.is_success is True
    assert ok.failed == 0

    bad = ServiceEnvResult(
        services=(ServiceRenderResult(service="a", status="failed", detail="boom"),),
    )
    assert bad.is_success is False
    assert bad.failed == 1


def test_cli_service_env_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus_deploy.__main__ import _service_env

    secrets = "{}"
    monkeypatch.setattr("sys.stdin.read", lambda: secrets)
    monkeypatch.setenv("DOMAIN", "example.com")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    rc = _service_env(["--enabled", "postgres", "--stacks-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "rendered=1" in out
    assert (tmp_path / "postgres" / ".env").exists()


# ---------------------------------------------------------------------------
# SUBDOMAIN_SEPARATOR — Issue #540
#
# Multi-tenant forks (e.g. an education / classroom admin panel) provision
# tenants under a shared base domain via flat subdomains. With
# ``subdomain_separator='-'`` and ``DOMAIN='user1.example.com'``,
# the rendered service URLs must compose to ``kestra-user1.example.com``
# etc. so they match the DNS records Tofu provisions.
# ---------------------------------------------------------------------------


def _flat_env() -> BootstrapEnv:
    """A BootstrapEnv configured for a flat-subdomain tenant."""
    return BootstrapEnv(
        domain="user1.example.com",
        admin_email="user1@example.com",
        gitea_user_email="user1@example.com",
        gitea_user_username="user1",
        subdomain_separator="-",
    )


def test_separator_dash_kestra_url(full_config: NexusConfig) -> None:
    """KESTRA_URL composes to ``kestra-user1.example.com`` under
    flat-subdomain separator. Without the fix, OAuth callbacks /
    embedded iframe URLs would point at the wrong host."""
    from nexus_deploy.service_env import _render_kestra

    rendered = _render_kestra(full_config, _flat_env())
    assert rendered.env_vars["KESTRA_URL"] == "https://kestra-user1.example.com"


def test_separator_dash_cloudbeaver_url(full_config: NexusConfig) -> None:
    from nexus_deploy.service_env import _render_cloudbeaver

    rendered = _render_cloudbeaver(full_config, _flat_env())
    assert rendered.env_vars["CB_SERVER_URL"] == "https://cloudbeaver-user1.example.com"


def test_separator_dash_hoppscotch_urls(full_config: NexusConfig) -> None:
    """Hoppscotch derives multiple URL fields from a shared `host`;
    all of them must use the same flat-subdomain form."""
    from nexus_deploy.service_env import _render_hoppscotch

    rendered = _render_hoppscotch(full_config, _flat_env())
    expected_host = "hoppscotch-user1.example.com"
    assert rendered.env_vars["VITE_BASE_URL"] == f"https://{expected_host}"
    assert rendered.env_vars["REDIRECT_URL"] == f"https://{expected_host}"
    assert rendered.env_vars["VITE_BACKEND_WS_URL"] == f"wss://{expected_host}/backend/graphql"


def test_separator_dash_prefect_url(full_config: NexusConfig) -> None:
    from nexus_deploy.service_env import _render_prefect

    rendered = _render_prefect(full_config, _flat_env())
    assert rendered.env_vars["PREFECT_UI_API_URL"] == "https://prefect-user1.example.com/api"


def test_separator_dash_nocodb_url(full_config: NexusConfig) -> None:
    from nexus_deploy.service_env import _render_nocodb

    rendered = _render_nocodb(full_config, _flat_env())
    assert rendered.env_vars["NC_PUBLIC_URL"] == "https://nocodb-user1.example.com"


def test_separator_dash_lakefs_s3_domain(full_config: NexusConfig) -> None:
    """LakeFS's S3 gateway domain composes ``s3.<lakefs-host>``.
    With separator='-' the lakefs hostname itself becomes flat;
    the ``s3.`` sub-prefix stays as-is. Result:
    ``s3.lakefs-user1.example.com``."""
    rendered = _render_lakefs(full_config, _flat_env())
    assert rendered.env_vars["LAKEFS_GATEWAYS_S3_DOMAIN_NAME"] == "s3.lakefs-user1.example.com"
