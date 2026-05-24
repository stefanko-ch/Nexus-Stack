"""Tests for nexus_deploy.services.

Eight round-tagged invariant tests (one per hardening round) plus
per-spec snapshots, exec'd-bash regression tests for the JSON
build + idempotent-skip dispatch, and CLI integration covering rc=0/1/2.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from nexus_deploy.config import NexusConfig
from nexus_deploy.infisical import BootstrapEnv
from nexus_deploy.services import (
    HookResult,
    SetupResult,
    _filestash_has_external,
    _filestash_has_hetzner,
    _filestash_has_r2,
    _filestash_mutate_config,
    _filestash_primary_backend,
    _filestash_s3_connections,
    _filestash_s3_params,
    _parse_filestash_pull_output,
    _render_filestash_pull_script,
    _render_filestash_push_script,
    configure_filestash,
    parse_results,
    render_dify_hook,
    render_garage_hook,
    render_hedgedoc_hook,
    render_lakefs_hook,
    render_metabase_hook,
    render_n8n_hook,
    render_openmetadata_hook,
    render_pg_ducklake_hook,
    render_portainer_hook,
    render_redpanda_hook,
    render_remote_script,
    render_sftpgo_hook,
    render_superset_hook,
    render_uptime_kuma_hook,
    render_wikijs_hook,
    render_windmill_hook,
    run_admin_setups,
    supported_hooks,
)


def _make_config(**overrides: Any) -> NexusConfig:
    """Build a NexusConfig with minimal credentials for every admin-setup
    hook that consumes them: REST hooks (Portainer, n8n, Metabase,
    LakeFS, OpenMetadata), docker-exec hooks (RedPanda, Superset),
    Filestash, plus Wiki.js / Dify / Windmill / SFTPGo (with R2 vfs).
    Uptime Kuma + Garage don't need credentials in this fixture
    (Uptime Kuma is warn-only; Garage's admin token comes via .env,
    not via the rendered hook)."""
    defaults: dict[str, Any] = {
        "admin_username": "admin",
        "portainer_admin_password": "p-pass",
        "n8n_admin_password": "n-pass",
        "metabase_admin_password": "m-pass",
        # Deliberately NOT shaped like an AWS access key (AKIA prefix)
        # to avoid false-positive secret-scanner alerts in CI/GitHub.
        "lakefs_admin_access_key": "FAKE-LAKEFS-ACCESS-KEY-1234",
        "lakefs_admin_secret_key": "secret-lakefs-key",
        "openmetadata_admin_password": "om-pass-Complex1!",
        "hetzner_s3_bucket_lakefs": "my-bucket",
        # docker-exec hooks
        "redpanda_admin_password": "rp-pass",
        "superset_admin_password": "su-pass",
        "hedgedoc_admin_password": "hd-admin-pass",
        # additional admin-setup hooks
        "wikijs_admin_password": "wiki-pass",
        "dify_admin_password": "dify-pass",
        "windmill_admin_password": "wm-admin-pass",
        "windmill_superadmin_secret": "wm-secret",
        "sftpgo_admin_password": "sftpgo-admin",
        "sftpgo_user_password": "sftpgo-user",
        "r2_data_bucket": "r2-bucket",
        "r2_data_endpoint": "https://r2.example.com",
        "r2_data_access_key": "r2-ak",
        "r2_data_secret_key": "r2-sk",
    }
    defaults.update(overrides)
    return NexusConfig.from_secrets_json(json.dumps(defaults))


def _make_env(admin_email: str = "ops@example.com") -> BootstrapEnv:
    return BootstrapEnv(domain="example.com", admin_email=admin_email)


# ---------------------------------------------------------------------------
# supported_hooks — registry contract
# ---------------------------------------------------------------------------


def test_supported_hooks_contains_all_specs() -> None:
    """5 REST hooks + 3 docker-exec hooks + Filestash (python) +
    6 additional admin-setups."""
    assert set(supported_hooks()) == {
        # REST first-init
        "portainer",
        "n8n",
        "metabase",
        "lakefs",
        "openmetadata",
        # docker-exec CLI
        "redpanda",
        "superset",
        "hedgedoc",
        # python-side mutation
        "filestash",
        # additional admin-setups
        "uptime-kuma",
        "garage",
        "wikijs",
        "dify",
        "windmill",
        "sftpgo",
        # pg-ducklake bootstrap-SQL re-apply
        "pg-ducklake",
    }


# ---------------------------------------------------------------------------
# Per-hook renderers — basic shape + skip-on-missing-credential
# ---------------------------------------------------------------------------


def test_render_portainer_hook_basic() -> None:
    script = render_portainer_hook(_make_config(), _make_env())
    assert "portainer_hook()" in script
    assert "/api/users/admin/init" in script
    assert "RESULT hook=portainer status=" in script


def test_render_portainer_hook_skips_when_password_empty() -> None:
    """Missing admin password → skipped-not-ready, not failed."""
    config = _make_config(portainer_admin_password="")
    script = render_portainer_hook(config, _make_env())
    assert script.strip() == 'echo "RESULT hook=portainer status=skipped-not-ready"'


def test_render_n8n_hook_uses_admin_email_from_env() -> None:
    """n8n needs admin_email — comes from BootstrapEnv, not NexusConfig."""
    script = render_n8n_hook(_make_config(), _make_env(admin_email="alice@example.com"))
    assert "alice@example.com" in script


def test_render_n8n_hook_skips_when_email_empty() -> None:
    """Missing admin_email → skipped (uniform with missing password)."""
    script = render_n8n_hook(_make_config(), _make_env(admin_email=""))
    assert script.strip() == 'echo "RESULT hook=n8n status=skipped-not-ready"'


def test_render_metabase_hook_skips_when_password_empty() -> None:
    script = render_metabase_hook(_make_config(metabase_admin_password=""), _make_env())
    assert script.strip() == 'echo "RESULT hook=metabase status=skipped-not-ready"'


def test_render_lakefs_hook_skips_when_keys_empty() -> None:
    script = render_lakefs_hook(
        _make_config(lakefs_admin_access_key="", lakefs_admin_secret_key=""),
        _make_env(),
    )
    assert script.strip() == 'echo "RESULT hook=lakefs status=skipped-not-ready"'


def test_render_lakefs_hook_pins_host_port_8000() -> None:
    """R-port: LakeFS compose maps 8000:8000. Hook MUST hit
    localhost:8000 from the SSH host. Pinned to catch port-mapping
    drift if the compose file changes (and to defend against a
    repeat of the cross-hook search-replace bug from PR #529 R1
    that incorrectly pushed LakeFS to 8200 alongside Windmill)."""
    script = render_lakefs_hook(_make_config(), _make_env())
    assert "localhost:8000" in script
    assert "localhost:8200" not in script


def test_render_openmetadata_hook_skips_when_password_empty() -> None:
    script = render_openmetadata_hook(_make_config(openmetadata_admin_password=""), _make_env())
    assert script.strip() == 'echo "RESULT hook=openmetadata status=skipped-not-ready"'


def test_render_metabase_hook_uses_admin_email() -> None:
    script = render_metabase_hook(_make_config(), _make_env())
    assert "ops@example.com" in script
    assert "/api/setup" in script


def test_render_lakefs_hook_picks_hetzner_when_both_bucket_and_server_set() -> None:
    """Storage namespace selection requires BOTH
    `hetzner_s3_bucket_lakefs` AND `hetzner_s3_server` to be set
    to land in the s3:// namespace.

    Test fixture intentionally uses a non-URL-shaped server value
    (``hetzner-s3-fake-host``) to avoid CodeQL's "Incomplete URL
    substring sanitization" false-positive — the rule fires on
    ``"foo.com" in some_url`` patterns intended for security
    decisions, but this assertion just checks rendered-bash content.
    """
    script = render_lakefs_hook(
        _make_config(
            hetzner_s3_bucket_lakefs="b1",
            hetzner_s3_server="hetzner-s3-fake-host",
        ),
        _make_env(),
    )
    assert "b1" in script
    assert "hetzner-s3-fake-host" in script
    # The if-condition tests both vars
    assert '[ -n "$HETZNER_BUCKET" ] && [ -n "$HETZNER_SERVER" ]' in script


def test_render_lakefs_hook_falls_back_to_local_when_no_hetzner() -> None:
    script = render_lakefs_hook(
        _make_config(hetzner_s3_bucket_lakefs="", hetzner_s3_server=""), _make_env()
    )
    assert "local://data/lakefs/" in script
    assert "local-storage" in script


def test_render_lakefs_hook_falls_back_when_only_bucket_set_no_server() -> None:
    """Round-7 finding: bucket alone is NOT enough — endpoint is also
    required. Without the server, lakefs has no way to read/write S3.
    Both inputs are required; we enforce that here."""
    config = _make_config(hetzner_s3_bucket_lakefs="b1", hetzner_s3_server="")
    script = render_lakefs_hook(config, _make_env())
    # Both fields are present in the rendered script (their values
    # get baked in), but at runtime the AND-check will land in the
    # local:// branch because HETZNER_SERVER is empty. We pin the
    # AND-check structure here.
    assert '[ -n "$HETZNER_BUCKET" ] && [ -n "$HETZNER_SERVER" ]' in script


def test_render_openmetadata_hook_3_step_flow() -> None:
    """Login (default-pwd) → changePassword → verify-login."""
    script = render_openmetadata_hook(_make_config(), _make_env())
    # All three POST endpoints appear
    assert script.count("/api/v1/users/login") == 2  # login + verify
    assert "/api/v1/users/changePassword" in script
    # System-version probe (custom wait, not _render_wait_healthy)
    assert "/api/v1/system/version" in script


# ---------------------------------------------------------------------------
# docker-exec hooks (RedPanda, Superset)
# ---------------------------------------------------------------------------


def test_render_redpanda_hook_basic() -> None:
    script = render_redpanda_hook(_make_config(), _make_env())
    assert "redpanda_hook()" in script
    # Wait via docker exec curl (admin API not exposed externally)
    assert "docker exec redpanda curl" in script
    # rpk SASL user create + cluster config
    assert "rpk acl user create nexus-redpanda" in script
    assert "rpk cluster config set superusers" in script
    # Verify via /v1/security/users
    assert "/v1/security/users" in script
    assert "RESULT hook=redpanda" in script


def test_render_redpanda_hook_skips_when_password_empty() -> None:
    script = render_redpanda_hook(_make_config(redpanda_admin_password=""), _make_env())
    assert script.strip() == 'echo "RESULT hook=redpanda status=skipped-not-ready"'


def test_render_redpanda_hook_password_via_stdin_not_argv() -> None:
    """R4 — RedPanda password reaches docker exec via stdin, NOT
    via ``-e RPK_PASS=value`` (which would put it in docker's argv
    on the host). The host-argv leak surface is closed; the password
    only ever reaches the redpanda container via stdin.
    """
    canary = "RP-CANARY-X1Y2Z3"
    script = render_redpanda_hook(_make_config(redpanda_admin_password=canary), _make_env())
    assert canary in script  # appears as bash var assignment
    # No `docker exec -e <var>=<canary>` form (would leak via host ps)
    for line in script.splitlines():
        if "docker exec -e" in line:
            assert canary not in line, f"Password leaked into docker exec -e argv: {line!r}"
    # Pipe-to-stdin form must be present
    assert "printf '%s' \"$REDPANDA_PASSWORD\" |" in script
    assert "docker exec -i redpanda" in script


def test_render_redpanda_hook_restart_with_firewall_override() -> None:
    """RedPanda restart honours docker-compose.firewall.yml when present."""
    script = render_redpanda_hook(_make_config(), _make_env())
    assert "docker-compose.firewall.yml" in script
    # Both branches: with-firewall and without-firewall
    assert "-f docker-compose.yml -f docker-compose.firewall.yml restart" in script


def test_render_redpanda_hook_uses_curl_dash_f_for_status_check() -> None:
    """Round-1 finding on PR #515: `curl -s` returns 0 even on 5xx, so
    the wait loop could break on a 503 response and run SASL setup
    too early. Switched to `curl -sf` which fails on 4xx/5xx —
    enforces a true 200-OK before proceeding.
    """
    script = render_redpanda_hook(_make_config(), _make_env())
    # No bare `curl -s` invocations against the readiness endpoint
    for line in script.splitlines():
        if "/v1/status/ready" in line and "curl -s " in line:
            raise AssertionError(
                f"Use 'curl -sf' for HTTP-status check on /v1/status/ready: {line!r}"
            )
    # Both wait loops use -sf
    assert script.count("curl -sf") >= 3  # initial wait + post-restart wait + verify


def test_render_redpanda_hook_password_rotation_via_create_first_then_delete() -> None:
    """Round-1 + round-2 findings: rotation must propagate. A previous
    naive implementation never synced the password on a second run, so
    Infisical rotation silently broke clients. The current pattern is
    try-create-first; only delete + recreate IF create reports "already
    exists" (the rotation case). The delete is gated on the broker
    proving it's responsive — a transient broker glitch on the first
    create returns failed without touching state. Round-2 specifically
    flagged delete-before-prove as a real bug — broker could be
    left with no SASL user if create failed transiently.
    """
    script = render_redpanda_hook(_make_config(), _make_env())
    # Try-create-first happens BEFORE any delete
    create_idx = script.find("rpk acl user create nexus-redpanda")
    delete_idx = script.find("rpk acl user delete nexus-redpanda")
    assert create_idx >= 0, "rpk acl user create must be in script"
    assert delete_idx >= 0, "rpk acl user delete must be in script"
    assert create_idx < delete_idx, (
        "create-attempt must come BEFORE delete (no delete-before-prove)"
    )
    # The delete is gated on "already exists" branch
    assert "already exists" in script
    # Tracked via USER_EXISTED so restart can be skipped on rotation
    assert "USER_EXISTED=true" in script
    assert "USER_EXISTED=false" in script


def test_render_redpanda_hook_cluster_config_set_failure_propagates() -> None:
    """Round-1 finding: an earlier implementation swallowed
    `rpk cluster config set superusers` failures — could mark the hook
    as `configured` while the user had no permissions. Now: capture the
    result, fail loudly.
    """
    script = render_redpanda_hook(_make_config(), _make_env())
    # The result is captured (NOT discarded via >/dev/null)
    assert "SUPER_RESULT=$(docker exec redpanda rpk cluster config set superusers" in script
    # And checked for success
    assert "if ! echo \"$SUPER_RESULT\" | grep -qi 'success\\|updated\\|set'" in script


def test_render_redpanda_hook_restart_only_on_first_setup() -> None:
    """Round-1 finding: legacy restarted unconditionally on every
    spin-up, briefly interrupting clients for no benefit on re-runs.
    Now: restart only when USER_EXISTED=false (= first setup).
    """
    script = render_redpanda_hook(_make_config(), _make_env())
    # The restart is gated on USER_EXISTED
    assert 'if [ "$USER_EXISTED" = "false" ]; then' in script
    # And the restart commands are inside that gate (one of them at least)
    restart_idx = script.find("docker compose restart")
    gate_idx = script.find('if [ "$USER_EXISTED" = "false" ]')
    assert gate_idx >= 0, "USER_EXISTED gate must be present"
    assert restart_idx > gate_idx, "Restart must be inside the USER_EXISTED=false branch"


def test_render_redpanda_hook_restart_failure_propagates_to_failed() -> None:
    """Round-2 finding: legacy `|| true` swallowed restart failures
    — if `docker compose restart` returned non-zero, the SASL
    listener config never picked up the change but the hook still
    reported success. Now: capture restart's exit code, mark hook
    as failed if restart returned non-zero.
    """
    script = render_redpanda_hook(_make_config(), _make_env())
    # Restart command captures exit code
    assert "RESTART_RC=0" in script
    assert "|| RESTART_RC=$?" in script
    # And checks for non-zero before continuing
    assert 'if [ "$RESTART_RC" -ne 0 ]; then' in script
    # No bare `|| true` after `docker compose restart` (would hide failures)
    for line in script.splitlines():
        if "docker compose" in line and "restart" in line and "|| true" in line:
            raise AssertionError(
                f"docker compose restart must capture exit code, not || true: {line!r}"
            )


def test_render_superset_hook_basic() -> None:
    script = render_superset_hook(_make_config(), _make_env())
    assert "superset_hook()" in script
    assert "/health" in script
    assert "fab create-admin" in script
    assert "fab reset-password" in script  # idempotent fallback
    assert "RESULT hook=superset" in script


def test_render_superset_hook_skips_when_password_empty() -> None:
    script = render_superset_hook(_make_config(superset_admin_password=""), _make_env())
    assert script.strip() == 'echo "RESULT hook=superset status=skipped-not-ready"'


def test_render_superset_hook_skips_when_email_empty() -> None:
    script = render_superset_hook(_make_config(), _make_env(admin_email=""))
    assert script.strip() == 'echo "RESULT hook=superset status=skipped-not-ready"'


def test_render_superset_hook_password_via_stdin_not_argv() -> None:
    """R4 — Superset password piped via stdin to ``docker exec -i``.

    Both ``fab create-admin`` and ``fab reset-password`` get the
    password via the in-container ``PASS`` shell var; the host-
    visible argv is just ``docker exec -i superset sh -c '...'``.
    """
    canary = "SU-CANARY-A1B2C3"
    script = render_superset_hook(_make_config(superset_admin_password=canary), _make_env())
    assert canary in script  # appears as bash var assignment
    # The literal canary must NOT appear after `docker exec` on any line
    for line in script.splitlines():
        idx_docker = line.find("docker exec")
        if idx_docker >= 0:
            idx_canary = line.find(canary)
            if idx_canary > idx_docker:
                raise AssertionError(f"Password leaked into docker exec argv: {line!r}")
    # Pipe-to-stdin form must be present (twice — create-admin + reset-password)
    assert script.count("printf '%s' \"$SUPERSET_PASSWORD\" |") == 2


def test_render_superset_hook_email_via_dash_e_not_argv() -> None:
    """admin_email is non-secret → ``-e ADMIN_EMAIL=`` (host argv
    visible but harmless). This pin documents the deliberate split:
    only secrets go via stdin; non-secrets stay readable in the
    rendered bash for debug-ability."""
    script = render_superset_hook(_make_config(), _make_env(admin_email="ops@example.com"))
    assert '-e ADMIN_EMAIL="$ADMIN_EMAIL"' in script


# ---------------------------------------------------------------------------
# HedgeDoc admin-seed (manage_users CLI via docker exec)
# ---------------------------------------------------------------------------


def test_render_hedgedoc_hook_basic() -> None:
    script = render_hedgedoc_hook(_make_config(), _make_env())
    assert "hedgedoc_hook()" in script
    assert "/status" in script  # readiness wait
    assert "manage_users --add" in script  # primary path
    assert "manage_users --reset" in script  # idempotent fallback
    assert "RESULT hook=hedgedoc" in script


def test_render_hedgedoc_hook_skips_when_password_empty() -> None:
    script = render_hedgedoc_hook(_make_config(hedgedoc_admin_password=""), _make_env())
    assert script.strip() == 'echo "RESULT hook=hedgedoc status=skipped-not-ready"'


def test_render_hedgedoc_hook_skips_when_email_empty() -> None:
    script = render_hedgedoc_hook(_make_config(), _make_env(admin_email=""))
    assert script.strip() == 'echo "RESULT hook=hedgedoc status=skipped-not-ready"'


def test_render_hedgedoc_hook_password_via_stdin_not_argv() -> None:
    """HedgeDoc password piped via stdin to ``docker exec -i``. Same
    secret-handling pattern as the Superset hook: the cleartext
    password reaches the in-container ``PASS`` shell var via
    stdin, the host-visible argv is just ``docker exec -i hedgedoc
    sh -c '...'``. Cleartext NEVER appears after `docker exec` on
    any line.
    """
    canary = "HD-CANARY-X9Y8Z7"
    script = render_hedgedoc_hook(_make_config(hedgedoc_admin_password=canary), _make_env())
    assert canary in script  # appears as bash var assignment
    for line in script.splitlines():
        idx_docker = line.find("docker exec")
        if idx_docker >= 0:
            idx_canary = line.find(canary)
            if idx_canary > idx_docker:
                raise AssertionError(f"Password leaked into docker exec argv: {line!r}")
    # Pipe-to-stdin form must appear twice (--add + --reset fallback)
    assert script.count("printf '%s' \"$HEDGEDOC_ADMIN_PASSWORD\" |") == 2


def test_render_hedgedoc_hook_email_via_dash_e_not_argv() -> None:
    """admin_email is non-secret → ``-e HEDGEDOC_ADMIN_EMAIL=`` (host
    argv visible but harmless). Same split as Superset."""
    script = render_hedgedoc_hook(_make_config(), _make_env(admin_email="ops@example.com"))
    assert '-e HEDGEDOC_ADMIN_EMAIL="$HEDGEDOC_ADMIN_EMAIL"' in script


# ---------------------------------------------------------------------------
# Uptime Kuma, Garage, Wiki.js, Dify, Windmill, SFTPGo
# ---------------------------------------------------------------------------


def test_render_uptime_kuma_hook_always_skipped() -> None:
    """Uptime Kuma is a manual-setup placeholder per issue #145."""
    script = render_uptime_kuma_hook(_make_config(), _make_env())
    assert "uptime_kuma_hook()" in script
    assert "RESULT hook=uptime-kuma status=skipped-not-ready" in script
    assert "issue #145" in script


def test_render_garage_hook_basic() -> None:
    script = render_garage_hook(_make_config(), _make_env())
    assert "garage_hook()" in script
    # Three-step layout setup
    assert "/garage layout show" in script
    assert "/garage layout assign -z dc1 -c 100G" in script
    assert "/garage layout apply --version 1" in script
    assert "/garage key create nexus-garage-key" in script


def test_render_garage_hook_idempotency_branches() -> None:
    """Already-configured (any node has a role) → already-configured;
    fresh layout → configured; node-id missing → failed."""
    script = render_garage_hook(_make_config(), _make_env())
    assert "RESULT hook=garage status=already-configured" in script
    assert "RESULT hook=garage status=configured" in script
    assert "RESULT hook=garage status=failed" in script


def test_render_garage_hook_layout_show_failure_reports_failed() -> None:
    """R-exit-status: layout-show exit status is captured separately
    so a Docker-daemon / container-missing failure reports `failed`,
    not false-positive `already-configured`. The naive `|| echo ""`
    pattern an earlier implementation used here silently swallowed
    real failures and is explicitly avoided."""
    script = render_garage_hook(_make_config(), _make_env())
    # LAYOUT_RC captured separately, gated before the grep
    assert "LAYOUT_RC=0" in script
    assert "|| LAYOUT_RC=$?" in script
    assert 'if [ "$LAYOUT_RC" -ne 0 ]' in script


def test_render_garage_hook_key_create_failure_reports_failed() -> None:
    """R-exit-status: key-create's exit status is also captured.
    Garage `key create` is idempotent (returns the existing key
    on re-run), so success doesn't prove fresh-create — but a
    non-zero exit DOES prove a real failure (daemon down /
    container missing) and must surface as `failed` rather than
    silent `configured`. Same class as the layout-show fix."""
    script = render_garage_hook(_make_config(), _make_env())
    assert "KEY_RC=0" in script
    assert "|| KEY_RC=$?" in script
    assert 'if [ "$KEY_RC" -ne 0 ]' in script


def test_render_garage_hook_validates_node_id_as_64_hex() -> None:
    """R-validate: node-id length and charset are checked before use."""
    script = render_garage_hook(_make_config(), _make_env())
    assert "${#FULL_NODE_ID} -ne 64" in script
    assert "[0-9a-fA-F]{64}" in script


def test_render_wikijs_hook_basic() -> None:
    script = render_wikijs_hook(_make_config(), _make_env())
    assert "wikijs_hook()" in script
    assert "/graphql" in script
    assert "mutation ($input: SetupInput!)" in script
    assert "siteUrl: env.NEXUS_U" in script


def test_render_wikijs_hook_skips_when_password_empty() -> None:
    config = _make_config(wikijs_admin_password="")
    script = render_wikijs_hook(config, _make_env())
    assert "wikijs_hook()" not in script
    assert "RESULT hook=wikijs status=skipped-not-ready" in script


def test_render_wikijs_hook_skips_when_email_empty() -> None:
    """Email comes from gitea_user_email or admin_email — both empty → skip."""
    env = BootstrapEnv(domain="example.com")  # no admin_email, no gitea_user_email
    script = render_wikijs_hook(_make_config(), env)
    assert "RESULT hook=wikijs status=skipped-not-ready" in script


def test_render_wikijs_hook_prefers_gitea_user_email_over_admin_email() -> None:
    """When both are set, gitea_user_email wins (single-address user
    identity). Use disjoint email values so the check is unambiguous —
    shlex.quote('admin@example.com') returns the bare string (no
    shell-special chars), so the previous assertion
    'NEXUS_E=...admin@example.com... not in script' would have passed
    even if the hook had buggily used admin_email (it would have been
    embedded as NEXUS_E=admin@example.com without quotes). Using a
    distinctive admin-only token here avoids that false-positive."""
    env = BootstrapEnv(
        domain="example.com",
        admin_email="admin-should-not-appear@example.org",
        gitea_user_email="user@example.com",
    )
    script = render_wikijs_hook(_make_config(), env)
    assert "user@example.com" in script
    # The admin email's distinctive prefix MUST NOT appear anywhere
    # in the rendered script — pins both the gitea-user-wins choice
    # AND defends against shlex.quote rendering ambiguities.
    assert "admin-should-not-appear" not in script


def test_render_wikijs_hook_password_via_env_var_not_argv() -> None:
    """R-secret: GraphQL body builds via NEXUS_P=… jq -n env, not --arg."""
    script = render_wikijs_hook(_make_config(), _make_env())
    assert "NEXUS_P=" in script
    # No --arg pass-through (would land password in jq's argv)
    assert "--arg pass" not in script


def test_render_dify_hook_basic() -> None:
    script = render_dify_hook(_make_config(), _make_env())
    assert "dify_hook()" in script
    assert "/console/api/init" in script
    assert "/console/api/setup" in script
    # Cookie jar tmpfile
    assert "DIFY_COOKIES=$(mktemp)" in script
    assert 'chmod 600 "$DIFY_COOKIES"' in script


def test_render_dify_hook_skips_when_password_empty() -> None:
    config = _make_config(dify_admin_password="")
    script = render_dify_hook(config, _make_env())
    assert "RESULT hook=dify status=skipped-not-ready" in script
    assert "dify_hook()" not in script


def test_render_dify_hook_already_configured_via_setup_check() -> None:
    """R-idempotent: pre-check `/setup` → already-configured if step finished."""
    script = render_dify_hook(_make_config(), _make_env())
    assert '"step":"finished"' in script
    assert "RESULT hook=dify status=already-configured" in script


def test_render_dify_hook_handles_307_redirect_in_readiness() -> None:
    """Dify's redirect-to-/install pattern (HTTP 307) counts as ready."""
    script = render_dify_hook(_make_config(), _make_env())
    assert "200|302|307)" in script


def test_render_dify_hook_password_via_env_var_not_argv() -> None:
    script = render_dify_hook(_make_config(), _make_env())
    # Init body and setup body both use NEXUS_P= env-var
    assert "NEXUS_P=" in script
    assert "--arg password" not in script


def test_render_dify_hook_cookie_trap_on_return() -> None:
    """R-tmpfile-cleanup: cookie jar removed on function-scoped RETURN
    trap, AND the trap is explicitly cleared via 'trap - RETURN'
    before EVERY function-return path (success AND init-failure
    early-exit) so it doesn't leak across hooks. Same pattern as
    LakeFS / OpenMetadata. The orchestrator runs all hooks in one
    shell with 'set -u'; a leaked RETURN trap referencing
    DIFY_COOKIES would trip set -u on a later hook."""
    script = render_dify_hook(_make_config(), _make_env())
    assert "trap 'rm -f \"$DIFY_COOKIES\"' RETURN" in script
    # Cleanup + trap-reset must appear at least TWICE: once on the
    # success path (after the setup POST) and once on the init-
    # failure early-exit path. R7 caught the missing one on the
    # init-failure path.
    assert script.count('rm -f "$DIFY_COOKIES"') >= 2
    assert script.count("trap - RETURN") >= 2


def test_render_windmill_hook_basic() -> None:
    script = render_windmill_hook(_make_config(), _make_env())
    assert "windmill_hook()" in script
    # All 4 legacy steps present
    assert "/api/users/create" in script
    assert "/api/workspaces/create" in script
    assert "/api/users/setpassword" in script
    # Workspace name must be "nexus" for stability across migration
    assert 'id: "nexus"' in script


def test_render_windmill_hook_pins_host_port_8200() -> None:
    """R-port: Windmill compose maps 8200:8000. Hook MUST hit
    localhost:8200 from the SSH host, not the in-container port 8000.
    Pinned to catch port-mapping drift if the compose file changes."""
    script = render_windmill_hook(_make_config(), _make_env())
    assert "localhost:8200" in script
    assert "localhost:8000" not in script


def test_render_windmill_hook_skips_when_any_required_field_empty() -> None:
    """Skip when any of secret/admin_password/admin_email is empty —
    the legacy gate required all 3."""
    for kw in (
        {"windmill_superadmin_secret": ""},
        {"windmill_admin_password": ""},
    ):
        config = _make_config(**kw)
        script = render_windmill_hook(config, _make_env())
        assert "RESULT hook=windmill status=skipped-not-ready" in script
        assert "windmill_hook()" not in script
    # admin_email empty
    env = BootstrapEnv(domain="example.com")
    script = render_windmill_hook(_make_config(), env)
    assert "RESULT hook=windmill status=skipped-not-ready" in script


def test_render_windmill_hook_creates_admin_user() -> None:
    """Step 1: legacy creates super_admin=true user for ADMIN_EMAIL."""
    script = render_windmill_hook(_make_config(), _make_env())
    assert "super_admin: true" in script
    # Email goes via env-var to jq, not --arg
    assert "NEXUS_E=" in script


def test_render_windmill_hook_creates_regular_user_when_gitea_user_email_differs() -> None:
    """Step 2: legacy conditionally creates super_admin=false user
    for GITEA_USER_EMAIL when it differs from ADMIN_EMAIL."""
    script = render_windmill_hook(_make_config(), _make_env())
    assert "super_admin: false" in script
    assert "GITEA_UE=" in script
    # Conditional gate
    assert '[ -n "$GITEA_UE" ]' in script


def test_render_windmill_hook_secures_default_admin_account() -> None:
    """R-security (Step 4): MUST rotate admin@windmill.dev password
    away from the long-lived WINDMILL_SUPERADMIN_SECRET. Without
    this, anyone with the secret could log in as the default admin.

    Plus: rotation HTTP status must be CHECKED, not silenced. A
    failed rotation (wrong secret, API error) must surface as
    'failed' with a stderr warning, not silently report 'configured'
    while the default admin stays usable."""
    script = render_windmill_hook(_make_config(), _make_env())
    assert "openssl rand -base64 32" in script
    assert "/api/users/setpassword" in script
    # Status capture (NOT silenced)
    assert "DEFPW_STATUS=" in script
    assert "200|204)" in script  # success branch
    # Failure path: warns AND aborts to 'failed'
    assert "default-admin password rotation returned HTTP" in script
    assert "may still be usable with the superadmin secret" in script


def test_render_windmill_hook_bearer_via_curl_config_not_argv() -> None:
    """R-secret-transport: WINDMILL_SUPERADMIN_SECRET reaches curl
    via mode-600 --config tmpfile (RETURN trap), NOT via -H argv.
    Plus: the RETURN trap is explicitly cleared before function-
    return so it doesn't leak across hooks (orchestrator runs all
    hooks in one shell with set -u)."""
    script = render_windmill_hook(_make_config(), _make_env())
    assert "WM_CFG=$(mktemp)" in script
    assert 'chmod 600 "$WM_CFG"' in script
    assert "trap 'rm -f \"$WM_CFG\"' RETURN" in script
    # Explicit cleanup + trap reset before exit
    assert 'rm -f "$WM_CFG"' in script
    assert "trap - RETURN" in script
    # No -H "Authorization: Bearer" argv
    assert '-H "Authorization' not in script
    assert "-H 'Authorization" not in script


def test_render_windmill_hook_secret_via_env_var_not_argv() -> None:
    """jq calls receive secrets via NEXUS_E / NEXUS_P / NEXUS_RP env vars."""
    script = render_windmill_hook(_make_config(), _make_env())
    assert "NEXUS_P=" in script
    assert "--arg password" not in script
    assert "--arg email" not in script


def test_render_windmill_hook_workspace_response_dispatch() -> None:
    """Workspace-create body \"nexus\" / 'created' → configured;
    'already exists' → already-configured; else → failed."""
    script = render_windmill_hook(_make_config(), _make_env())
    assert "RESULT hook=windmill status=configured" in script
    assert "RESULT hook=windmill status=already-configured" in script
    assert "RESULT hook=windmill status=failed" in script


def test_render_sftpgo_hook_basic() -> None:
    script = render_sftpgo_hook(_make_config(), _make_env())
    assert "sftpgo_hook()" in script
    # Two-stage readiness probe
    assert "/healthz" in script
    assert "/api/v2/token" in script
    assert "/api/v2/folders" in script
    assert "/api/v2/users" in script


def test_render_sftpgo_hook_skips_when_admin_or_user_pass_empty() -> None:
    for kw in ({"sftpgo_admin_password": ""}, {"sftpgo_user_password": ""}):
        config = _make_config(**kw)
        script = render_sftpgo_hook(config, _make_env())
        assert "RESULT hook=sftpgo status=skipped-not-ready" in script
        assert "sftpgo_hook()" not in script


def test_render_sftpgo_hook_skips_with_warning_when_r2_missing() -> None:
    """R2 creds drive the default-user vfs; missing → warn-and-skip."""
    config = _make_config(r2_data_bucket="")
    script = render_sftpgo_hook(config, _make_env())
    assert "RESULT hook=sftpgo status=skipped-not-ready" in script
    assert "R2 datalake credentials missing" in script


def test_render_sftpgo_hook_dir_prep_inside_container() -> None:
    """Pre-creates home_dir + folder mapped_path; chown 1000:1000."""
    script = render_sftpgo_hook(_make_config(), _make_env())
    assert "mkdir -p /var/lib/sftpgo/users/nexus-default" in script
    assert "chown -R 1000:1000 /var/lib/sftpgo/users /var/lib/sftpgo/folders" in script


def test_render_sftpgo_hook_hetzner_folder_gated_on_all_5_fields() -> None:
    """Hetzner virtual folder gated on all 5 HZ_* fields (bucket + server
    + region + access_key + secret_key). A 3-field gate would attempt
    the POST with empty creds and fail."""
    script = render_sftpgo_hook(_make_config(), _make_env())
    for var in (
        "SFTPGO_HZ_BUCKET",
        "SFTPGO_HZ_SERVER",
        "SFTPGO_HZ_REGION",
        "SFTPGO_HZ_AK_B64",
        "SFTPGO_HZ_SK_B64",
    ):
        assert f'[ -n "${var}" ]' in script, f"missing {var} guard"
    # Both vfolder JSON variants present (one with hetzner_s3, one without)
    assert '"name":"cloudflare_r2"' in script
    assert '"name":"hetzner_s3"' in script


def test_render_sftpgo_hook_status_dispatch() -> None:
    """201 → configured; 400/409 → already-configured; else → failed."""
    script = render_sftpgo_hook(_make_config(), _make_env())
    # Final user POST status-code case
    assert "201)" in script
    assert "400|409)" in script
    assert "RESULT hook=sftpgo status=failed" in script


def test_render_sftpgo_hook_secrets_via_base64_env_not_argv() -> None:
    """R-secret-transport: all 4 secrets (admin, user, R2 access/secret)
    flow through ``printf '%s' <quoted> | base64`` (printf is a bash
    builtin → no fork-exec → no `ps` exposure on the runner side),
    then are decoded remote-side from env vars. They MUST NOT reach
    jq via ``--arg`` or curl via ``-H`` argv.
    """
    config = _make_config(
        sftpgo_admin_password="ADM-SECRET-XYZ",
        sftpgo_user_password="USR-SECRET-XYZ",
        r2_data_secret_key="R2-SECRET-XYZ",
    )
    script = render_sftpgo_hook(config, _make_env())
    # Each secret reaches base64 via a printf-builtin pipe (printf
    # is a bash builtin → no fork-exec → no `ps` exposure on the
    # runner side). shlex.quote may render the value bare or
    # single-quoted depending on the chars; both forms reach printf.
    for secret in ("ADM-SECRET-XYZ", "USR-SECRET-XYZ", "R2-SECRET-XYZ"):
        # Match either bare or single-quoted form
        assert (
            f"printf '%s' {secret} | base64" in script
            or f"printf '%s' '{secret}' | base64" in script
        ), f"secret {secret!r} not piped to base64 via printf-builtin"
    # No --arg to jq (would land secrets in jq's argv)
    assert "--arg pass" not in script
    assert "--arg secret" not in script
    # No -H Authorization argv (we use mode-600 curl --config tmpfile instead)
    assert '-H "Authorization' not in script
    assert "-H 'Authorization" not in script


def test_render_pg_ducklake_hook_basic() -> None:
    """pg-ducklake re-apply hook: pg_isready probe + psql -f exec."""
    script = render_pg_ducklake_hook(_make_config(), _make_env())
    assert "pg_ducklake_hook()" in script
    # Two-stage: readiness probe then exec
    assert "pg_isready -U nexus-pgducklake -d ducklake" in script
    assert "/docker-entrypoint-initdb.d/00-ducklake-bootstrap.sql" in script
    assert "psql -U nexus-pgducklake -d ducklake" in script


def test_render_pg_ducklake_hook_status_dispatch() -> None:
    """Three branches: skipped-not-ready / configured / failed."""
    script = render_pg_ducklake_hook(_make_config(), _make_env())
    assert "RESULT hook=pg-ducklake status=skipped-not-ready" in script
    assert "RESULT hook=pg-ducklake status=configured" in script
    assert "RESULT hook=pg-ducklake status=failed" in script


def test_render_pg_ducklake_hook_uses_wall_clock_bound_for_readiness() -> None:
    """R-bounded-wait: 30s wall-clock cap (NOT iteration-counted), so a
    stalled pg_isready can't blow the wait past the documented timeout."""
    script = render_pg_ducklake_hook(_make_config(), _make_env())
    assert 'while [ "$SECONDS" -lt 30 ]' in script


# ---------------------------------------------------------------------------
# Round-tagged invariants on the rendered bash
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "renderer",
    [
        render_portainer_hook,
        render_n8n_hook,
        render_metabase_hook,
        render_lakefs_hook,
        render_openmetadata_hook,
    ],
)
def test_round_8_per_hook_emits_exactly_one_result_line(renderer: Any) -> None:
    """R8 — every hook function emits exactly one ``RESULT hook=…`` line per branch.

    Static check via grep: each renderer's output must contain at
    least one ``echo "RESULT hook=`` line. The exec'd version below
    pins the runtime invariant (exactly one per execution).
    """
    script = renderer(_make_config(), _make_env())
    assert "RESULT hook=" in script


def test_round_1_set_minus_u_at_top_no_set_e() -> None:
    """R1 — orchestrator script uses ``set -u`` (NOT ``set -e``).

    Subtle but critical: ``set -e`` would abort the orchestrator on
    the first hook that returns non-zero from a curl pipe, and we
    want hook failures to be reported via RESULT lines without
    cross-contaminating the rest. The per-hook bodies still use
    ``|| true`` and explicit branches to control flow.
    """
    script = render_remote_script(
        config=_make_config(), env=_make_env(), enabled_hooks=["portainer"]
    )
    assert script.startswith("set -u")
    # No `set -e` in the orchestrator (R6 corollary)
    assert "set -e" not in script.splitlines()[0]


def test_round_2_per_spec_healthcheck_timeouts() -> None:
    """R2 — each hook has its own healthcheck timeout, NOT a global default.

    Pin the timeouts so a future contributor doesn't accidentally
    unify them and break Metabase (Java app, 120s), OpenMetadata
    (180s, slow boot), or Superset (300s = 5min, db upgrade + init).
    """
    timeouts = {
        # 2.2b — REST hooks
        "portainer": 5,
        "n8n": 60,
        "metabase": 120,
        "lakefs": 60,
        "openmetadata": 180,
        # 2.2c — docker-exec hooks
        "redpanda": 60,
        "superset": 300,
    }
    renderers = {
        "portainer": render_portainer_hook,
        "n8n": render_n8n_hook,
        "metabase": render_metabase_hook,
        "lakefs": render_lakefs_hook,
        "openmetadata": render_openmetadata_hook,
        "redpanda": render_redpanda_hook,
        "superset": render_superset_hook,
    }
    for hook_name, expected_timeout in timeouts.items():
        script = renderers[hook_name](_make_config(), _make_env())
        # Look for the human-readable warning that names the timeout.
        # Superset's warning uses '5min' instead of '300s' for readability.
        if hook_name == "superset":
            assert "after 5min" in script, "Expected '5min' in superset script"
        else:
            assert f"after {expected_timeout}s" in script, (
                f"Expected '{expected_timeout}s' in {hook_name} script"
            )


@pytest.mark.parametrize(
    ("renderer", "canary_field", "canary_value"),
    [
        # Each hook is tested with a unique canary substituted for the
        # credential field that's most likely to land in argv.
        # 2.2b — REST hooks
        (render_portainer_hook, "portainer_admin_password", "PORTAINER-CANARY-X1Y2"),
        (render_n8n_hook, "n8n_admin_password", "N8N-CANARY-X1Y2"),
        (render_metabase_hook, "metabase_admin_password", "METABASE-CANARY-X1Y2"),
        (render_lakefs_hook, "lakefs_admin_secret_key", "LAKEFS-SECRET-CANARY-X1Y2"),
        (render_openmetadata_hook, "openmetadata_admin_password", "OM-CANARY-X1Y2"),
        # 2.2c — docker-exec hooks. Same R4 invariant via stdin pipe.
        (render_redpanda_hook, "redpanda_admin_password", "RP-CANARY-X1Y2"),
        (render_superset_hook, "superset_admin_password", "SU-CANARY-X1Y2"),
    ],
)
def test_no_credential_leaks_into_subprocess_argv_per_hook(
    renderer: Any, canary_field: str, canary_value: str
) -> None:
    """R4 (per-hook generalisation): no credential ever lands on a line
    that invokes a non-builtin subprocess (``curl``, ``jq``, ``docker``)
    — all leak via ``ps`` on the remote host.

    Round-2 PR #514: caught Portainer + n8n curl-argv leaks.
    Round-5 PR #514: caught the SAME class on jq's argv (``jq -n
    --arg pw <secret>`` puts secret in jq's argv).
    docker-exec hooks add a third leak surface (``docker exec -e
    VAR=value`` or ``docker exec ... cmd $secret``).

    Bash builtins (printf, env-var assignments via ``VAR=value cmd``)
    don't fork — values can safely appear on those lines without
    reaching ``ps``.

    Scope of THIS test: ``curl``, ``jq``, ``docker``. Other forking
    commands the rendered scripts use (``base64``, ``tr``, ``mktemp``,
    ``chmod``) all read from stdin or operate on tmpfile paths
    rather than taking secrets as positional args, so they're not
    on the leak-path here.
    """
    script = renderer(_make_config(**{canary_field: canary_value}), _make_env())
    assert canary_value in script, "Canary must appear somewhere in the script"
    for line in script.splitlines():
        # Skip lines that ONLY contain `VAR=value cmd ...` env-var
        # assignment for the next non-builtin (e.g. `NEXUS_P=secret jq -n`):
        # the value is set as an env var, NOT as positional argv.
        # We detect this pattern by checking whether the canary appears
        # before any forking-command token on the line.
        for forking_command in ("curl ", "curl\n", "jq ", "jq\n", "docker ", "docker\n"):
            if forking_command in line:
                idx_canary = line.find(canary_value)
                idx_cmd = line.find(forking_command)
                if idx_canary >= 0 and idx_canary > idx_cmd:
                    # Canary appears AFTER the command name → it's in
                    # positional argv → leak.
                    raise AssertionError(
                        f"Credential leaked into {forking_command.strip()!r} argv: {line!r}"
                    )


def test_round_4_setup_body_via_env_no_argv_leak() -> None:
    """R4 — admin password is injected to jq via env var (NOT --arg
    positional argv) and fed to curl via stdin (--data-binary @-),
    never via argv.

    Critical: a future bug that put the password into curl's OR
    jq's argv would leak it via `ps` on the remote host. We assert
    that:
      1. The password value appears in the rendered script (it's
         the value of an env-var assignment — that's expected and
         bash-safe; bash builtins / env-var-to-cmd assignments don't
         fork).
      2. The password value does NOT appear AFTER a forking-command
         token (curl, jq) on any line — meaning it's never in argv.

    The detailed cross-hook version of this check lives in
    ``test_no_credential_leaks_into_subprocess_argv_per_hook``;
    this test pins the Metabase-specific shape.
    """
    canary = "UNIQUE-METABASE-PWD-LEAK-CANARY"
    config = _make_config(metabase_admin_password=canary)
    script = render_metabase_hook(config, _make_env())
    assert canary in script, "Canary must appear (as env-var value)"
    # Canary must NOT appear AFTER curl/jq on any line (= not in argv)
    for line in script.splitlines():
        for cmd_token in ("curl ", "jq "):
            idx_cmd = line.find(cmd_token)
            idx_canary = line.find(canary)
            if idx_cmd >= 0 and idx_canary > idx_cmd:
                raise AssertionError(f"Password leaked into {cmd_token.strip()} argv: {line!r}")
    # And the rendered script uses --data-binary @- for the POST body
    assert "--data-binary @-" in script


def test_round_4_setup_body_built_correctly_against_rendered_script() -> None:
    """R4 exec — drive the ACTUAL rendered jq pipeline against a known
    config and assert the resulting JSON parses + has expected
    fields, even with shell-meta characters in the password.

    Earlier this test built a hand-coded jq snippet that was decoupled
    from the renderer — it could pass even if the real renderer drifted.
    Now we extract the BODY=$(...) line from the rendered script,
    execute it via bash -c, and parse the captured JSON. This pins
    the renderer's actual jq form against shell-meta-character
    payloads.
    """
    nasty_password = 'evil"$(date)`whoami`'
    config = _make_config(metabase_admin_password=nasty_password)
    full_script = render_metabase_hook(config, _make_env())
    # Extract the BODY=$(...) jq-build block from the rendered script.
    # It's a multi-line continuation: BODY=$(NEXUS_TOKEN=... NEXUS_E=...
    # NEXUS_P=... jq -n '{...}')
    lines = full_script.splitlines()
    body_start = next(i for i, line in enumerate(lines) if line.strip().startswith("BODY=$(NEXUS_"))
    body_end = body_start
    while not lines[body_end].rstrip().endswith(")"):
        body_end += 1
    body_lines = lines[body_start : body_end + 1]
    # The rendered version uses an implicit SETUP_TOKEN runtime-shell var
    # (captured from /api/session/properties); inject it explicitly.
    snippet = (
        "set -euo pipefail\nSETUP_TOKEN=tok123\n"
        + "\n".join(body_lines)
        + '\nprintf "%s" "$BODY"\n'
    )
    out = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True, check=True).stdout
    parsed = json.loads(out)
    assert parsed["user"]["password"] == nasty_password
    assert parsed["token"] == "tok123"
    assert parsed["user"]["email"] == "ops@example.com"


def test_round_5_idempotent_skip_via_substring_match() -> None:
    """R5 — idempotent-skip detection per hook.

    Each hook has a distinct "already configured" signal. Pin them
    so refactors don't accidentally drop the check.
    """
    portainer = render_portainer_hook(_make_config(), _make_env())
    assert "already initialized" in portainer  # Portainer's API response substring

    n8n = render_n8n_hook(_make_config(), _make_env())
    assert "showSetupOnFirstLoad" in n8n  # n8n's settings probe

    metabase = render_metabase_hook(_make_config(), _make_env())
    assert "setup-token" in metabase  # Metabase: token absent → already configured

    lakefs = render_lakefs_hook(_make_config(), _make_env())
    assert '"setup_complete":true' in lakefs

    om = render_openmetadata_hook(_make_config(), _make_env())
    # OpenMetadata: default login fails with invalid → already configured
    assert "invalid" in om
    assert "unauthorized" in om


def test_round_6_hook_failure_does_not_abort_orchestrator() -> None:
    """R6 — orchestrator does NOT use ``set -e``; one hook's failure
    cannot stop subsequent hooks. Pin via static check on the
    orchestrator preamble + by verifying every per-hook function
    uses ``return 0`` (NOT ``exit 1``) on bail-out paths.
    """
    script = render_remote_script(
        config=_make_config(),
        env=_make_env(),
        enabled_hooks=["portainer", "n8n", "metabase"],
    )
    # Orchestrator preamble: set -u only
    assert script.startswith("set -u")
    # No `exit 1` in any hook function (those would propagate)
    for line in script.splitlines():
        # Orchestrator-level exits are the issue; ignore subshell exits in jq etc.
        stripped = line.strip()
        assert "exit 1" not in stripped, (
            f"Hook bodies must use 'return 0' on bail-outs, not 'exit 1': {line!r}"
        )


def test_round_7_hook_execution_order_matches_enabled_arg() -> None:
    """R7 — orchestrator emits hooks in the caller-provided
    ``enabled_hooks`` argument order, NOT registry order.

    Operators rely on this for log debug + the integration with
    the caller's [7/7] sequence — the CLI passes the comma-list as
    typed, and the caller's $ENABLED_SERVICES is built from
    services.yaml in source order via tofu output.
    """
    script = render_remote_script(
        config=_make_config(),
        env=_make_env(),
        # Pass in reverse-registry order to verify caller-order wins
        enabled_hooks=["openmetadata", "portainer", "lakefs"],
    )
    # The order in which hook functions are called must follow the
    # `enabled_hooks` argument order (caller's responsibility to sort
    # if they want a different one). Verify by finding the *_hook
    # call lines and asserting they appear in the expected order.
    order = []
    for line in script.splitlines():
        m = re.match(r"^([a-z_]+)_hook$", line.strip())
        if m:
            order.append(m.group(1))
    assert order == ["openmetadata", "portainer", "lakefs"]


# ---------------------------------------------------------------------------
# render_remote_script — orchestrator behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "$(rm -rf /)",
        "x; rm -rf /",
        "x`whoami`",
        "x|cat /etc/passwd",
        "x with space",
        "x'single'",
        'x"double"',
        "../etc/passwd",
        "x\\backslash",
        "",
    ],
)
def test_render_remote_script_drops_unsafe_hook_names(
    unsafe_name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Round-4 finding: hook names with shell-meta chars must NOT be
    interpolated into the rendered bash. Each unsafe name is dropped
    with a stderr warning; the rendered script must NOT contain the
    unsafe substring at all (no echo, no comment, nothing).
    """
    script = render_remote_script(
        config=_make_config(),
        env=_make_env(),
        enabled_hooks=["portainer", unsafe_name],
    )
    # Unsafe name must NOT reach the rendered bash
    if unsafe_name:  # empty string isn't a substring of anything useful
        assert unsafe_name not in script
    # Portainer (the safe entry) still rendered
    assert "portainer_hook" in script
    # Stderr warning emitted
    captured = capsys.readouterr()
    assert "Dropped hook with unsafe name" in captured.err


def test_render_remote_script_unknown_hook_emits_skip() -> None:
    """An enabled service with no renderer → emit skip line so counts stay consistent."""
    script = render_remote_script(
        config=_make_config(),
        env=_make_env(),
        enabled_hooks=["portainer", "filestash"],  # filestash → 2.2c
    )
    assert "RESULT hook=filestash status=skipped-not-ready" in script
    # Portainer still runs
    assert "portainer_hook" in script


def test_render_remote_script_empty_list_yields_minimal_orchestrator() -> None:
    """Empty enabled list → just the orchestrator preamble, no hook calls."""
    script = render_remote_script(config=_make_config(), env=_make_env(), enabled_hooks=[])
    assert script.startswith("set -u")
    assert "_hook()" not in script


# ---------------------------------------------------------------------------
# parse_results
# ---------------------------------------------------------------------------


def test_parse_results_one_per_line() -> None:
    out = (
        "  ✓ portainer\n"
        "RESULT hook=portainer status=configured\n"
        "RESULT hook=n8n status=already-configured\n"
        "  ⚠ metabase not ready after 120s — skipping setup\n"
        "RESULT hook=metabase status=skipped-not-ready\n"
        "RESULT hook=openmetadata status=failed\n"
    )
    results = parse_results(out)
    assert results == (
        HookResult(name="portainer", status="configured"),
        HookResult(name="n8n", status="already-configured"),
        HookResult(name="metabase", status="skipped-not-ready"),
        HookResult(name="openmetadata", status="failed"),
    )


def test_parse_results_invalid_status_skipped() -> None:
    """Lines with invalid status values (typos, future statuses) are dropped."""
    out = "RESULT hook=foo status=configured\nRESULT hook=bar status=bogus-status"
    results = parse_results(out)
    assert results == (HookResult(name="foo", status="configured"),)


def test_parse_results_empty_input() -> None:
    assert parse_results("") == ()


# ---------------------------------------------------------------------------
# SetupResult counters
# ---------------------------------------------------------------------------


def test_setup_result_counters() -> None:
    r = SetupResult(
        hooks=(
            HookResult(name="a", status="configured"),
            HookResult(name="b", status="configured"),
            HookResult(name="c", status="already-configured"),
            HookResult(name="d", status="skipped-not-ready"),
            HookResult(name="e", status="failed"),
        )
    )
    assert r.configured == 2
    assert r.already_configured == 1
    assert r.skipped_not_ready == 1
    assert r.failed == 1
    assert r.is_success is False


def test_setup_result_empty_is_success() -> None:
    """Zero hooks = no failures = success."""
    assert SetupResult(hooks=()).is_success is True


# ---------------------------------------------------------------------------
# run_admin_setups — orchestration
# ---------------------------------------------------------------------------


def _ok_runner(stdout: str) -> Any:
    def runner(_script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=stdout, stderr="")

    return runner


def test_run_admin_setups_filters_unknown_services() -> None:
    """Services without a renderer don't reach the remote script."""
    captured: dict[str, str] = {}

    def capture(script: str) -> subprocess.CompletedProcess[str]:
        captured["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="RESULT hook=portainer status=configured",
            stderr="",
        )

    run_admin_setups(
        _make_config(),
        _make_env(),
        # gitea + jupyter are not in any admin-setup registry
        # (gitea uses its own dedicated module; jupyter has no admin hook)
        ["portainer", "gitea", "jupyter"],
        script_runner=capture,
    )
    # gitea + jupyter (not in any registry) must NOT reach the script
    assert "gitea_hook" not in captured["script"]
    assert "jupyter_hook" not in captured["script"]
    assert "portainer_hook" in captured["script"]


def test_run_admin_setups_all_unknown_returns_empty_result() -> None:
    """If no enabled service has a renderer, we don't even invoke ssh."""
    runner_invoked = []

    def runner(_script: str) -> subprocess.CompletedProcess[str]:
        runner_invoked.append(True)
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")

    result = run_admin_setups(
        _make_config(),
        _make_env(),
        # neither gitea nor jupyter are in any registry
        ["gitea", "jupyter"],
        script_runner=runner,
    )
    assert result == SetupResult(hooks=())
    assert runner_invoked == []


def test_run_admin_setups_missing_result_line_counts_as_failed() -> None:
    """A hook that did NOT emit a RESULT line counts as failed
    (server-side ssh hung up mid-script, etc.)."""
    out = "RESULT hook=portainer status=configured\n"  # n8n missing
    result = run_admin_setups(
        _make_config(),
        _make_env(),
        ["portainer", "n8n"],
        script_runner=_ok_runner(out),
    )
    by_name = {h.name: h.status for h in result.hooks}
    assert by_name["portainer"] == "configured"
    assert by_name["n8n"] == "failed"


def test_run_admin_setups_forwards_remote_warnings_to_local_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Modul-1.2 Round-4 lesson: ⚠ warnings reach local stderr."""
    out = (
        "  ⚠ metabase not ready after 120s — skipping setup\n"
        "RESULT hook=metabase status=skipped-not-ready\n"
    )
    run_admin_setups(_make_config(), _make_env(), ["metabase"], script_runner=_ok_runner(out))
    captured = capsys.readouterr()
    assert "metabase not ready after 120s" in captured.err
    # RESULT line is wire-format, must NOT pollute stderr
    assert "RESULT hook=metabase" not in captured.err


# ---------------------------------------------------------------------------
# CLI integration — direct _services_configure unit tests with monkeypatch
# (subprocess CLI tests covered via _run_cli below for arg-parsing cases)
# ---------------------------------------------------------------------------


def _run_cli(
    args: list[str],
    *,
    stdin: str = "{}",
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [sys.executable, "-m", "nexus_deploy", "services", *args],
        capture_output=True,
        text=True,
        env=full_env,
        input=stdin,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_cli_services_missing_subcommand_returns_2() -> None:
    rc, _, err = _run_cli([])
    assert rc == 2
    assert "only 'configure'" in err


def test_cli_services_configure_missing_enabled_returns_2() -> None:
    rc, _, err = _run_cli(["configure"])
    assert rc == 2
    assert "--enabled" in err


def test_cli_services_configure_empty_enabled_returns_zero() -> None:
    rc, out, _ = _run_cli(["configure", "--enabled", ""])
    assert rc == 0
    assert "nothing to do" in out


def test_cli_services_configure_unknown_arg_returns_2() -> None:
    rc, _, err = _run_cli(["configure", "--enabled", "portainer", "--bogus"])
    assert rc == 2
    assert "unknown arg" in err


def test_cli_services_configure_subcommand_typo_returns_2() -> None:
    """`services up`, `services down` etc. all rejected."""
    rc, _, err = _run_cli(["up", "--enabled", "x"])
    assert rc == 2
    assert "only 'configure'" in err


# CLI rc-mapping unit tests via monkeypatch (avoid spinning subprocesses for
# the rc=0/1/2 contract — same pattern as test_compose_runner.py).


@pytest.mark.parametrize(
    ("hooks", "expected_rc"),
    [
        # All success
        (
            (
                HookResult(name="portainer", status="configured"),
                HookResult(name="n8n", status="already-configured"),
            ),
            0,
        ),
        # Empty
        ((), 0),
        # Partial: some success, some failed → rc=1
        (
            (
                HookResult(name="portainer", status="configured"),
                HookResult(name="metabase", status="failed"),
            ),
            1,
        ),
        # All failed → rc=2 (orchestrator should abort)
        ((HookResult(name="portainer", status="failed"),), 2),
        # Skipped-not-ready alone is success (no failures)
        ((HookResult(name="portainer", status="skipped-not-ready"),), 0),
    ],
)
def test_services_configure_cli_rc_mapping(
    monkeypatch: pytest.MonkeyPatch,
    hooks: tuple[HookResult, ...],
    expected_rc: int,
) -> None:
    """Verify the rc=0/1/2 contract via direct `_services_configure` call."""
    from nexus_deploy.__main__ import _services_configure

    def fake_run(_config: Any, _env: Any, _enabled: list[str]) -> SetupResult:
        return SetupResult(hooks=hooks)

    monkeypatch.setattr("nexus_deploy.__main__.run_admin_setups", fake_run)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")
    rc = _services_configure(["configure", "--enabled", "portainer"])
    assert rc == expected_rc


def test_services_configure_cli_rc2_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Programming errors → rc=2; secret-bearing message NEVER printed."""
    from nexus_deploy.__main__ import _services_configure

    def boom(_c: Any, _e: Any, _en: list[str]) -> SetupResult:
        raise RuntimeError("secret-bearing-message-NEVER-print")

    monkeypatch.setattr("nexus_deploy.__main__.run_admin_setups", boom)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")
    rc = _services_configure(["configure", "--enabled", "portainer"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "RuntimeError" in captured.err
    assert "secret-bearing-message-NEVER-print" not in captured.err


def test_services_configure_cli_rc2_on_transport_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ssh/rsync failure → rc=2. exc.cmd must NOT leak to stderr."""
    from nexus_deploy.__main__ import _services_configure

    def boom(_c: Any, _e: Any, _en: list[str]) -> SetupResult:
        raise subprocess.CalledProcessError(255, ["ssh", "with-secret-arg"])

    monkeypatch.setattr("nexus_deploy.__main__.run_admin_setups", boom)
    monkeypatch.setattr("sys.stdin.read", lambda: "{}")
    rc = _services_configure(["configure", "--enabled", "portainer"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "transport failure" in captured.err
    assert "with-secret-arg" not in captured.err


# ---------------------------------------------------------------------------
# Filestash (Python-side JSON mutation)
# ---------------------------------------------------------------------------


def _config_no_s3() -> NexusConfig:
    return NexusConfig.from_secrets_json("{}")


def _config_with_r2() -> NexusConfig:
    return NexusConfig.from_secrets_json(
        json.dumps(
            {
                "r2_data_endpoint": "https://r2.example.com",
                "r2_data_access_key": "r2-fake-access",
                "r2_data_secret_key": "r2-fake-secret",
                "r2_data_bucket": "datalake",
            }
        )
    )


def _config_with_hetzner() -> NexusConfig:
    return NexusConfig.from_secrets_json(
        json.dumps(
            {
                "hetzner_s3_server": "hetzner-s3-fake-host",
                "hetzner_s3_region": "fsn1",
                "hetzner_s3_access_key": "hz-fake-access",
                "hetzner_s3_secret_key": "hz-fake-secret",
                "hetzner_s3_bucket_general": "general",
            }
        )
    )


def _config_with_external() -> NexusConfig:
    return NexusConfig.from_secrets_json(
        json.dumps(
            {
                "external_s3_endpoint": "https://external.example.com",
                "external_s3_region": "us-east-1",
                "external_s3_access_key": "ext-fake-access",
                "external_s3_secret_key": "ext-fake-secret",
                "external_s3_bucket": "ext-bucket",
                "external_s3_label": "Acme S3",
            }
        )
    )


def _config_all_three() -> NexusConfig:
    fields: dict[str, Any] = {}
    for cfg in (_config_with_r2(), _config_with_hetzner(), _config_with_external()):
        for k, v in cfg.model_dump().items():
            if v is not None and v != "":
                fields[k] = v
    return NexusConfig.from_secrets_json(json.dumps(fields))


# -- has_* predicates -----------------------------------------------


def test_filestash_has_r2_requires_all_four_fields() -> None:
    cfg = _config_with_r2()
    assert _filestash_has_r2(cfg) is True
    # Missing any one field → false. Mutate by setting one to empty.
    partial = NexusConfig.from_secrets_json(
        json.dumps({**cfg.model_dump(exclude_none=True), "r2_data_secret_key": ""})
    )
    assert _filestash_has_r2(partial) is False


def test_filestash_has_hetzner_requires_general_bucket() -> None:
    cfg = _config_with_hetzner()
    assert _filestash_has_hetzner(cfg) is True


def test_filestash_has_external_requires_all_fields() -> None:
    cfg = _config_with_external()
    assert _filestash_has_external(cfg) is True


def test_filestash_no_s3_returns_no_predicates() -> None:
    cfg = _config_no_s3()
    assert _filestash_has_r2(cfg) is False
    assert _filestash_has_hetzner(cfg) is False
    assert _filestash_has_external(cfg) is False
    assert _filestash_primary_backend(cfg) is None


# -- connections + params + primary_backend -------------------------


def test_filestash_connections_order_r2_then_hetzner_then_external() -> None:
    """the caller's iteration order: R2 first, Hetzner second, External third."""
    conns = _filestash_s3_connections(_config_all_three())
    labels = [c["label"] for c in conns]
    assert labels == ["R2 Datalake", "Hetzner Storage", "Acme S3"]


def test_filestash_connections_only_r2() -> None:
    conns = _filestash_s3_connections(_config_with_r2())
    assert conns == [{"type": "s3", "label": "R2 Datalake"}]


def test_filestash_external_label_default_when_unset() -> None:
    """external_s3_label defaults to 'External Storage' (the caller fallback)."""
    cfg = NexusConfig.from_secrets_json(
        json.dumps(
            {
                "external_s3_endpoint": "https://e.example.com",
                "external_s3_access_key": "x-fake",
                "external_s3_secret_key": "y-fake",
                "external_s3_bucket": "b",
                # external_s3_label omitted
            }
        )
    )
    conns = _filestash_s3_connections(cfg)
    assert conns == [{"type": "s3", "label": "External Storage"}]


def test_filestash_primary_backend_r2_wins() -> None:
    assert _filestash_primary_backend(_config_all_three()) == "R2 Datalake"


def test_filestash_primary_backend_hetzner_when_no_r2() -> None:
    cfg = _config_with_hetzner()
    assert _filestash_primary_backend(cfg) == "Hetzner Storage"


def test_filestash_primary_backend_external_with_label() -> None:
    cfg = _config_with_external()
    assert _filestash_primary_backend(cfg) == "Acme S3"


def test_filestash_params_external_only() -> None:
    """External-only config produces full params under its custom label."""
    params = _filestash_s3_params(_config_with_external())
    assert "Acme S3" in params
    assert params["Acme S3"]["endpoint"] == "https://external.example.com"
    assert params["Acme S3"]["region"] == "us-east-1"
    assert params["Acme S3"]["path"] == "/ext-bucket/"


def test_filestash_params_hetzner_endpoint_prefixed_with_https() -> None:
    """the caller stores HETZNER_S3_SERVER bare; Filestash needs full URL."""
    params = _filestash_s3_params(_config_with_hetzner())
    assert params["Hetzner Storage"]["endpoint"] == "https://hetzner-s3-fake-host"


def test_filestash_params_r2_path_uses_bucket() -> None:
    params = _filestash_s3_params(_config_with_r2())
    assert params["R2 Datalake"]["path"] == "/datalake/"
    assert params["R2 Datalake"]["region"] == "auto"


# -- _filestash_mutate_config ---------------------------------------


def test_filestash_mutate_strips_https_from_host() -> None:
    """A pre-existing https:// prefix on .general.host gets removed."""
    pre = {"general": {"host": "https://files.example.com"}}
    post = _filestash_mutate_config(pre, config=_config_no_s3())
    assert post["general"]["host"] == "files.example.com"


def test_filestash_mutate_does_not_double_strip() -> None:
    """A bare host (no scheme) is left alone — never accidentally truncated."""
    pre = {"general": {"host": "files.example.com"}}
    post = _filestash_mutate_config(pre, config=_config_no_s3())
    assert post["general"]["host"] == "files.example.com"


def test_filestash_mutate_force_ssl_set_to_true_when_null() -> None:
    """the caller: 'force_ssl': null → 'force_ssl': true."""
    pre = {"general": {"host": "x.example.com", "force_ssl": None}}
    post = _filestash_mutate_config(pre, config=_config_no_s3())
    assert post["general"]["force_ssl"] is True


def test_filestash_mutate_force_ssl_set_to_true_when_false() -> None:
    pre = {"general": {"host": "x.example.com", "force_ssl": False}}
    post = _filestash_mutate_config(pre, config=_config_no_s3())
    assert post["general"]["force_ssl"] is True


def test_filestash_mutate_no_s3_leaves_connections_untouched() -> None:
    """If no backend is configured, .connections must NOT be overwritten."""
    pre = {"general": {"host": "x"}, "connections": [{"label": "manual"}]}
    post = _filestash_mutate_config(pre, config=_config_no_s3())
    assert post["connections"] == [{"label": "manual"}]
    assert "middleware" not in post or "attribute_mapping" not in post.get("middleware", {})


def test_filestash_mutate_with_r2_overwrites_connections_and_middleware() -> None:
    pre = {"general": {"host": "x"}, "connections": []}
    post = _filestash_mutate_config(pre, config=_config_with_r2())
    assert len(post["connections"]) == 1
    assert post["connections"][0]["label"] == "R2 Datalake"

    # Middleware params are JSON STRINGS (Filestash quirk — not nested dicts)
    assert isinstance(post["middleware"]["identity_provider"]["params"], str)
    assert isinstance(post["middleware"]["attribute_mapping"]["params"], str)
    assert post["middleware"]["attribute_mapping"]["related_backend"] == "R2 Datalake"
    decoded = json.loads(post["middleware"]["attribute_mapping"]["params"])
    assert "R2 Datalake" in decoded


def test_filestash_mutate_does_not_modify_input() -> None:
    """Pure function — input dict must remain unchanged."""
    pre = {"general": {"host": "https://x.example.com"}, "connections": []}
    pre_copy = json.loads(json.dumps(pre))
    _filestash_mutate_config(pre, config=_config_with_r2())
    assert pre == pre_copy


# -- _render_filestash_pull_script ----------------------------------


def test_render_filestash_pull_script_starts_with_set_u() -> None:
    """R1: rendered bash must begin with `set -u` (set -e omitted by design)."""
    script = _render_filestash_pull_script()
    assert script.lstrip().startswith("set -u")


def test_render_filestash_pull_script_uses_curl_dash_f() -> None:
    """R2.2c lesson: -sf, not bare -s — bare -s accepts any HTTP code."""
    script = _render_filestash_pull_script()
    assert "curl -sf" in script


def test_render_filestash_pull_script_emits_three_distinct_markers() -> None:
    script = _render_filestash_pull_script()
    assert "RESULT_PULL_NOT_READY" in script
    assert "RESULT_PULL_NO_CONFIG" in script
    assert "RESULT_PULL_OK" in script


def test_render_filestash_pull_script_base64_no_dash_w() -> None:
    """`base64 -w0` is GNU-only; we use `base64 | tr -d '\\n'` for BSD/Alpine."""
    script = _render_filestash_pull_script()
    assert "base64 -w0" not in script
    assert "tr -d" in script


def test_render_filestash_pull_script_executable_via_bash_n(tmp_path: Path) -> None:
    """`bash -n` parses the rendered script — catches shell-syntax errors."""
    script = _render_filestash_pull_script()
    f = tmp_path / "pull.sh"
    f.write_text(script)
    rc = subprocess.run(
        ["bash", "-n", str(f)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 0, rc.stderr


# -- _render_filestash_push_script ----------------------------------


def test_render_filestash_push_script_uses_heredoc_not_argv_for_b64() -> None:
    """R4: base64 (encoding S3 secrets) must NOT appear in argv on the
    remote host. Even encoded the b64 is recoverable; ``ps -ef`` on
    nexus during the brief command window would expose it. The b64
    travels via heredoc on stdin to ``base64 -d``, NOT as a positional
    arg to ``printf`` / ``echo``."""
    fake_b64 = base64.b64encode(b'{"x":"secret-do-not-leak"}').decode()
    script = _render_filestash_push_script(new_config_b64=fake_b64)
    # The b64 string IS in the rendered script body (it's the only way
    # to get the bytes onto the server) — but the DECODED secret is not.
    assert "secret-do-not-leak" not in script
    # Heredoc form: cat <<'NEXUS_FS_PUSH_EOF' | base64 -d | docker exec -i ...
    assert "<<'NEXUS_FS_PUSH_EOF'" in script
    # The b64 must NOT appear after `printf` / `echo` / argv-style invocations
    # — that would leak it to remote `ps`.
    for line in script.splitlines():
        if fake_b64 in line:
            # Only allowed: the heredoc body line (just the b64, nothing else)
            assert line.strip() == fake_b64, f"b64 leaked into argv-bearing line: {line!r}"
    assert "base64 -d" in script
    assert "docker exec -i filestash" in script


def test_render_filestash_push_script_pipefail_enabled() -> None:
    """Without `set -o pipefail`, a base64 -d failure would be masked
    by docker exec's exit status. Pin the option in the rendered script."""
    fake_b64 = base64.b64encode(b"{}").decode()
    script = _render_filestash_push_script(new_config_b64=fake_b64)
    assert "set -o pipefail" in script


def test_render_filestash_push_script_rejects_non_b64_input() -> None:
    """Defensive guard: non-base64 alphabet → ValueError immediately."""
    with pytest.raises(ValueError, match="base64 alphabet"):
        _render_filestash_push_script(new_config_b64="not!base64!")


def test_render_filestash_push_script_emits_result_lines() -> None:
    script = _render_filestash_push_script(new_config_b64=base64.b64encode(b"{}").decode())
    assert "RESULT hook=filestash status=configured" in script
    assert "RESULT hook=filestash status=failed" in script


def test_render_filestash_push_script_executable_via_bash_n(tmp_path: Path) -> None:
    fake_b64 = base64.b64encode(b'{"general":{"host":"x"}}').decode()
    script = _render_filestash_push_script(new_config_b64=fake_b64)
    f = tmp_path / "push.sh"
    f.write_text(script)
    rc = subprocess.run(
        ["bash", "-n", str(f)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 0, rc.stderr


# -- _parse_filestash_pull_output -----------------------------------


def test_parse_pull_output_not_ready() -> None:
    assert _parse_filestash_pull_output("RESULT_PULL_NOT_READY\n") == "not-ready"


def test_parse_pull_output_no_config() -> None:
    assert _parse_filestash_pull_output("RESULT_PULL_NO_CONFIG\n") == "not-ready"


def test_parse_pull_output_valid_b64_returns_dict() -> None:
    b64 = base64.b64encode(b'{"general": {"host": "files.example.com"}}').decode()
    out = _parse_filestash_pull_output(f"RESULT_PULL_OK {b64}\n")
    assert isinstance(out, dict)
    assert out["general"]["host"] == "files.example.com"


def test_parse_pull_output_invalid_b64_returns_none() -> None:
    """Marker present but base64 bad → parse-fail signal, callers treat as failed."""
    out = _parse_filestash_pull_output("RESULT_PULL_OK !!!not-base64!!!\n")
    assert out is None


def test_parse_pull_output_valid_b64_but_not_json() -> None:
    b64 = base64.b64encode(b"not json").decode()
    out = _parse_filestash_pull_output(f"RESULT_PULL_OK {b64}\n")
    assert out is None


def test_parse_pull_output_valid_json_but_not_dict() -> None:
    """A JSON list at top level isn't a config — reject."""
    b64 = base64.b64encode(b"[1, 2, 3]").decode()
    out = _parse_filestash_pull_output(f"RESULT_PULL_OK {b64}\n")
    assert out is None


def test_parse_pull_output_no_marker_returns_none() -> None:
    assert _parse_filestash_pull_output("random unrelated stdout\n") is None


# -- configure_filestash end-to-end ---------------------------------


def _runner_returning(
    stdouts: list[str],
) -> Callable[[str], subprocess.CompletedProcess[str]]:
    """Stateful runner: returns each stdout in order on successive calls."""
    state = {"i": 0}

    def runner(_script: str) -> subprocess.CompletedProcess[str]:
        out = stdouts[state["i"]]
        state["i"] += 1
        return subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout=out, stderr="")

    return runner


def test_configure_filestash_happy_path_writes_configured() -> None:
    initial = {"general": {"host": "https://files.example.com", "force_ssl": None}}
    pull_b64 = base64.b64encode(json.dumps(initial).encode()).decode()
    runner = _runner_returning(
        [
            f"RESULT_PULL_OK {pull_b64}\n",
            "RESULT hook=filestash status=configured\n",
        ]
    )
    result = configure_filestash(_config_with_r2(), script_runner=runner)
    assert result == HookResult(name="filestash", status="configured")


def test_configure_filestash_skipped_not_ready_short_circuits() -> None:
    """When stage 1 reports not-ready we don't even render stage 2."""
    runner_call_count = {"n": 0}

    def runner(_script: str) -> subprocess.CompletedProcess[str]:
        runner_call_count["n"] += 1
        return subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="RESULT_PULL_NOT_READY\n",
            stderr="",
        )

    result = configure_filestash(_config_no_s3(), script_runner=runner)
    assert result == HookResult(name="filestash", status="skipped-not-ready")
    assert runner_call_count["n"] == 1  # No stage 2 invocation


def test_configure_filestash_no_config_marker_short_circuits() -> None:
    runner_call_count = {"n": 0}

    def runner(_script: str) -> subprocess.CompletedProcess[str]:
        runner_call_count["n"] += 1
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="RESULT_PULL_NO_CONFIG\n", stderr=""
        )

    result = configure_filestash(_config_no_s3(), script_runner=runner)
    assert result == HookResult(name="filestash", status="skipped-not-ready")
    assert runner_call_count["n"] == 1


def test_configure_filestash_pull_unparseable_returns_failed() -> None:
    """Marker line malformed → failed, not skipped (we couldn't read state)."""
    runner = _runner_returning(["nothing useful here\n"])
    result = configure_filestash(_config_no_s3(), script_runner=runner)
    assert result == HookResult(name="filestash", status="failed")


def test_configure_filestash_forwards_remote_diagnostics_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Remote ``  ⚠ …`` / ``  ✗ …`` lines must reach local stderr so
    operators can debug failures from the deploy log, not just see
    ``status=failed``. Mirrors the bash-hook orchestrator's pattern.
    """
    initial = {"general": {"host": "x"}}
    pull_b64 = base64.b64encode(json.dumps(initial).encode()).decode()
    # Pull stage emits a warning + the OK marker; push stage emits a
    # warning + the failed RESULT.
    runner = _runner_returning(
        [
            f"  ⚠ pull-stage diagnostic warning\nRESULT_PULL_OK {pull_b64}\n",
            "  ✗ push-stage diagnostic\nRESULT hook=filestash status=failed\n",
        ]
    )
    configure_filestash(_config_no_s3(), script_runner=runner)
    captured = capsys.readouterr()
    assert "pull-stage diagnostic warning" in captured.err
    assert "push-stage diagnostic" in captured.err
    # Marker lines must NOT be forwarded (those are wire-format only)
    assert "RESULT_PULL_OK" not in captured.err
    assert "RESULT hook=filestash" not in captured.err


def test_configure_filestash_push_failed_returns_failed() -> None:
    initial = {"general": {"host": "x.example.com"}}
    pull_b64 = base64.b64encode(json.dumps(initial).encode()).decode()
    runner = _runner_returning(
        [
            f"RESULT_PULL_OK {pull_b64}\n",
            "RESULT hook=filestash status=failed\n",
        ]
    )
    result = configure_filestash(_config_no_s3(), script_runner=runner)
    assert result == HookResult(name="filestash", status="failed")


def test_configure_filestash_push_no_result_line_counts_as_failed() -> None:
    """Stage 2 returns stdout but no parseable RESULT line → failed."""
    initial = {"general": {"host": "x"}}
    pull_b64 = base64.b64encode(json.dumps(initial).encode()).decode()
    runner = _runner_returning([f"RESULT_PULL_OK {pull_b64}\n", "ssh died mid-restart\n"])
    result = configure_filestash(_config_no_s3(), script_runner=runner)
    assert result == HookResult(name="filestash", status="failed")


def test_configure_filestash_secrets_not_in_rendered_push_script() -> None:
    """End-to-end R4: S3 secret key should never reach a rendered argv.

    The mutated config contains the R2 secret key. We capture stage 2's
    rendered script and assert the secret string is NOT present in
    plaintext (it's base64-encoded inside the rendered script, which
    is on stdin to ssh, NOT argv).
    """
    initial = {"general": {"host": "x"}}
    pull_b64 = base64.b64encode(json.dumps(initial).encode()).decode()
    captured: list[str] = []

    def runner(script: str) -> subprocess.CompletedProcess[str]:
        captured.append(script)
        if len(captured) == 1:
            return subprocess.CompletedProcess(
                args=["ssh"], returncode=0, stdout=f"RESULT_PULL_OK {pull_b64}\n", stderr=""
            )
        return subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="RESULT hook=filestash status=configured\n",
            stderr="",
        )

    configure_filestash(_config_with_r2(), script_runner=runner)
    # Stage 2 script — assert plaintext secret absent
    assert len(captured) == 2
    assert "r2-fake-secret" not in captured[1]
    assert "r2-fake-access" not in captured[1]


def test_run_admin_setups_dispatches_filestash_via_python_path() -> None:
    """run_admin_setups routes 'filestash' through configure_filestash."""
    initial = {"general": {"host": "x"}}
    pull_b64 = base64.b64encode(json.dumps(initial).encode()).decode()
    runner = _runner_returning(
        [
            f"RESULT_PULL_OK {pull_b64}\n",
            "RESULT hook=filestash status=configured\n",
        ]
    )
    result = run_admin_setups(_make_config(), _make_env(), ["filestash"], script_runner=runner)
    assert result.hooks == (HookResult(name="filestash", status="configured"),)


def test_run_admin_setups_dispatches_bash_and_python_hooks_together() -> None:
    """Both registries dispatched in one call. Bash runs first, then Python."""
    initial = {"general": {"host": "x"}}
    pull_b64 = base64.b64encode(json.dumps(initial).encode()).decode()
    runner = _runner_returning(
        [
            "RESULT hook=portainer status=configured\n",
            f"RESULT_PULL_OK {pull_b64}\n",
            "RESULT hook=filestash status=configured\n",
        ]
    )
    result = run_admin_setups(
        _make_config(), _make_env(), ["portainer", "filestash"], script_runner=runner
    )
    names = {h.name for h in result.hooks}
    assert names == {"portainer", "filestash"}
    assert result.is_success


# ---------------------------------------------------------------------------
# SUBDOMAIN_SEPARATOR — Issue #540 (wiki site_url)
# ---------------------------------------------------------------------------


def test_render_wikijs_hook_uses_separator_in_site_url() -> None:
    """siteUrl in the rendered GraphQL mutation honors
    BootstrapEnv.subdomain_separator. With separator='-' the
    rendered URL is ``wiki-user1.example.com``, not
    ``wiki.user1.example.com``. Without this fix, Wiki.js would
    redirect users to a host that doesn't resolve under
    flat-subdomain tenants."""
    env = BootstrapEnv(
        domain="user1.example.com",
        admin_email="user1@example.com",
        gitea_user_email="user1@example.com",
        subdomain_separator="-",
    )
    config = _make_config(wikijs_admin_password="pw")
    script = render_wikijs_hook(config, env)
    # The site URL is shlex-quoted into the rendered bash. Pinning
    # the SHELL-QUOTED form (``'…'``) rather than the bare URL makes
    # the assertion more specific AND dodges CodeQL's
    # py/incomplete-url-substring-sanitization rule, which heuristically
    # flags ``<bare-domain> in container`` patterns in tests.
    assert shlex.quote("https://wiki-user1.example.com") in script
    # And the dot form's shlex-quoted shape must NOT appear (would
    # be a regression).
    assert shlex.quote("https://wiki.user1.example.com") not in script


def test_render_wikijs_hook_default_separator_is_dot_form_unchanged() -> None:
    """Default-tenant render is byte-identical to pre-#540."""
    env = BootstrapEnv(
        domain="example.com",
        admin_email="admin@example.com",
        gitea_user_email="user@example.com",
    )
    config = _make_config(wikijs_admin_password="pw")
    script = render_wikijs_hook(config, env)
    assert shlex.quote("https://wiki.example.com") in script
