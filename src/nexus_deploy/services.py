"""Per-service admin-setup hooks for the auto-configure phase.

Three hook families cover the supported services:

**REST first-init** (Portainer, n8n, Metabase, LakeFS, OpenMetadata):

  1. Waits for the service container to be HTTP-ready
  2. Optionally checks "already configured" (idempotent skip)
  3. POSTs the admin-init / first-setup payload
  4. Yellow-warns on failure, never aborts

**docker-exec CLI** (RedPanda, Superset):

  1. Waits for the service container to be HTTP-ready
  2. Runs an in-container CLI (``rpk`` for RedPanda, ``superset
     fab`` for Superset) via ``docker exec -i``, with passwords
     piped via stdin to keep them out of docker's argv on the
     remote host
  3. Idempotent re-runs: RedPanda's ``rpk acl user create`` errors
     harmlessly if user exists; Superset falls back to ``fab
     reset-password`` if ``fab create-admin`` reports user-exists

**Python-side file mutation** (Filestash):

  1. Stage 1: rendered bash pulls the container's config.json via
     ``docker exec cat``, base64-encoded over the wire
  2. Python locally mutates the JSON (Pydantic-typed config →
     dict transformations: strip protocol from host, force_ssl=true,
     inject S3 backend connections + middleware)
  3. Stage 2: rendered bash pipes the new config via base64 →
     ``docker exec -i sh -c 'cat > …'`` → ``docker restart`` →
     wait for /healthz again
  This pattern uses TWO ssh round-trips (vs. one for the bash-render
  family). The win: JSON mutation is pure-Python testable, replacing
  a 100-line jq chain with a typed dict transform.

Additional hooks (Wikijs, Dify, Windmill, Garage, SFTPGo) live
alongside these in the same file using whichever family fits the
service.

Why one ssh round-trip with rendered bash (consistent with
:mod:`infisical` / :mod:`secret_sync` / :mod:`seeder` /
:mod:`compose_runner`): the curl loop is proven, one SSH connection
vs N, and the rendered script is testable as a string.

Eight rounds of hardening preserved (one regression test per round
in ``tests/unit/test_services.py``):

R1. Orchestrator script begins with ``set -u`` (unset-var detection)
    but **NOT** ``set -e`` — a failed hook MUST not abort the rest
    (see R6). Per-hook bodies stay safe via explicit branches +
    ``|| echo ""`` capture patterns; no ``set -e`` reliance inside
    hooks either. R3 below is the corollary on tmpfile cleanup.
R2. Per-spec healthcheck timeout (Metabase 120s, OpenMetadata 180s,
    LakeFS 60s, Portainer 5s, n8n 60s — NOT a global default).
R3. Per-hook tmpfile cleanup. LakeFS + OpenMetadata create mode-600
    `mktemp` curl-config files (R4 — auth via --config, NOT argv)
    and clean them up via per-hook ``trap ... RETURN`` + explicit
    ``rm -f`` after the curl call. No shared cross-hook tmpfiles
    or EXIT trap; each hook is self-contained. (Portainer + n8n +
    Metabase don't need a tmpfile — their POST endpoints are
    auth-free, only the body is sensitive, and that travels via
    --data-binary @- stdin.)
R4. JSON setup-body built via jq with secrets injected as env vars
    (``NEXUS_P=value jq -n 'env.NEXUS_P'``), NOT positional
    ``--arg`` values that would land in jq's argv (visible via
    ``ps``). The body is then fed to curl via stdin
    (``--data-binary @-``) so neither jq nor curl carry secrets in
    argv. Auth headers / basic-auth go via ``curl --config <tmpfile>``
    (mode 600, RETURN-trap cleanup) — never via ``-H`` / ``-u``
    argv either. Together: no fork visible via ``ps -ef`` carries
    a credential value.
R5. Idempotent skip when ``already_configured_substring`` appears in
    the pre-setup probe response (e.g. ``"setup_complete":true``).
R6. error_strategy=continue: a failed hook NEVER aborts the orchestrator;
    the next hook still runs (yellow-warn-and-continue).
R7. Hook execution order matches the caller-provided ``enabled_hooks``
    argument (NOT registry insertion order). Operators get the order
    they typed.
R8. RESULT-line-per-hook: ``RESULT hook=<name> status=<configured|
    already-configured|failed|skipped-not-ready>``. The orchestrator
    parses one line per hook, never grepping for emoji.
"""

from __future__ import annotations

import base64
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

from nexus_deploy import _remote
from nexus_deploy.config import NexusConfig, service_host
from nexus_deploy.infisical import BootstrapEnv

_RESULT_LINE_RE = re.compile(
    r"^RESULT hook=(?P<name>[A-Za-z0-9_-]+) "
    r"status=(?P<status>configured|already-configured|failed|skipped-not-ready)$",
    re.MULTILINE,
)

# Same alphabet as the RESULT line's `name` group. Used to validate
# hook names from the caller-provided `enabled_hooks` list before
# interpolating into the rendered bash — prevents shell injection
# via $(), backticks, semicolons, etc. if a buggy or adversarial
# caller ever passes a name with shell metacharacters. In production
# `enabled_hooks` comes from the orchestrator's $ENABLED_SERVICES
# list (sourced from `tofu output -json` keys — all alphanumeric +
# dash), so this is defence in depth.
_VALID_HOOK_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

HookStatus = Literal["configured", "already-configured", "failed", "skipped-not-ready"]


@dataclass(frozen=True)
class HookResult:
    """Outcome of one admin-setup hook."""

    name: str
    status: HookStatus


@dataclass(frozen=True)
class SetupResult:
    """Aggregate of all hook outcomes for one orchestrator call."""

    hooks: tuple[HookResult, ...]

    @property
    def configured(self) -> int:
        return sum(1 for h in self.hooks if h.status == "configured")

    @property
    def already_configured(self) -> int:
        return sum(1 for h in self.hooks if h.status == "already-configured")

    @property
    def skipped_not_ready(self) -> int:
        return sum(1 for h in self.hooks if h.status == "skipped-not-ready")

    @property
    def failed(self) -> int:
        return sum(1 for h in self.hooks if h.status == "failed")

    @property
    def is_success(self) -> bool:
        """All hooks ended in a non-failed terminal state."""
        return self.failed == 0


# ---------------------------------------------------------------------------
# Per-hook bash renderers. Each takes NexusConfig and returns a bash
# fragment that, when executed server-side, emits exactly one
# `RESULT hook=<name> status=<...>` line.
# ---------------------------------------------------------------------------


def _render_wait_healthy(
    *,
    name: str,
    url: str,
    timeout_seconds: int,
    interval_seconds: int = 2,
    predicate: str = '[ "$STATUS" = "200" ]',
) -> str:
    """Render a polling-wait loop; sets ``$READY`` to ``true``/``false``.

    Bounded by **wall-clock** (``$SECONDS``), not iteration count.
    Earlier versions used ``for _ in $(seq 1 N)`` with N derived
    from ``timeout_seconds // interval_seconds``, but each iteration
    could spend up to curl's ``--max-time`` waiting for a stalled
    response PLUS ``sleep interval_seconds`` between probes — so a
    "60s" timeout could blow out to ~200s in the worst case while
    still printing the misleading "after 60s" warning. Using
    ``$SECONDS`` keeps the upper bound close to ``timeout_seconds``:
    the worst case is ~``timeout_seconds + curl_max_time +
    interval_seconds`` (the loop can enter at SECONDS=N-1, then
    spend one more probe + sleep before the while-check fires
    again). For the typical Portainer/n8n/Metabase configs that's
    ~+7s; not exact, but bounded and accurate enough for the
    "after Ns — skipping" warning.

    The predicate runs against ``$STATUS`` (HTTP code from curl
    ``-w '%{http_code}'``). Specs that need a body-substring check
    (OpenMetadata's ``grep 'version'``) build a custom inner block
    instead of using this helper.
    """
    return f"""
READY=false
SECONDS=0
while [ "$SECONDS" -lt {timeout_seconds} ]; do
    STATUS=$(curl -s -o /dev/null -w '%{{http_code}}' --connect-timeout 3 --max-time 5 {shlex.quote(url)} 2>/dev/null || echo "000")
    if {predicate}; then READY=true; break; fi
    sleep {interval_seconds}
done
if [ "$READY" != "true" ]; then
    echo "  ⚠ {name} not ready after {timeout_seconds}s — skipping setup" >&2
    echo "RESULT hook={name} status=skipped-not-ready"
    return 0 2>/dev/null || exit 0
fi
"""


def render_portainer_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """Portainer first-init: ``POST /api/users/admin/init`` (no auth).

    Secrets reach jq via env vars (``NEXUS_U`` / ``NEXUS_P``) and are
    referenced in the filter as ``env.NEXUS_U`` / ``env.NEXUS_P`` —
    NEVER as positional ``--arg`` values, which would put them in
    jq's argv (visible via ``ps``). The body is then piped to curl
    via stdin (``--data-binary @-``) so neither jq nor curl carry
    secrets in argv (R4).
    """
    del env  # not used; signature uniform across hooks
    username = config.admin_username or "admin"
    password = config.portainer_admin_password or ""
    if not password:
        return 'echo "RESULT hook=portainer status=skipped-not-ready"\n'
    username_q = shlex.quote(username)
    password_q = shlex.quote(password)
    wait = _render_wait_healthy(
        name="portainer",
        url="http://localhost:9090/api/system/status",
        timeout_seconds=5,
        interval_seconds=1,
    )
    return f"""
portainer_hook() {{
    {wait}
    BODY=$(NEXUS_U={username_q} NEXUS_P={password_q} jq -n \\
        '{{Username: env.NEXUS_U, Password: env.NEXUS_P}}')
    RESP=$(printf '%s' "$BODY" | curl -s -X POST 'http://localhost:9090/api/users/admin/init' \\
        --max-time 30 \\
        -H 'Content-Type: application/json' \\
        --data-binary @- 2>/dev/null || echo "")
    if echo "$RESP" | grep -q '"Id"'; then
        echo "RESULT hook=portainer status=configured"
    elif echo "$RESP" | grep -q 'already initialized'; then
        echo "RESULT hook=portainer status=already-configured"
    else
        echo "RESULT hook=portainer status=failed"
    fi
}}
portainer_hook
"""


def render_n8n_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """n8n owner-setup: ``POST /rest/owner/setup`` (no auth, idempotent via /rest/settings).

    Body built with secrets injected via env vars (``NEXUS_E`` /
    ``NEXUS_P``), referenced in jq's filter as ``env.NEXUS_E`` /
    ``env.NEXUS_P``. The body is then piped to curl via stdin
    (``--data-binary @-``). Neither jq nor curl carry the password
    in argv (R4).
    """
    email = env.admin_email or ""
    password = config.n8n_admin_password or ""
    if not password or not email:
        return 'echo "RESULT hook=n8n status=skipped-not-ready"\n'
    email_q = shlex.quote(email)
    password_q = shlex.quote(password)
    wait = _render_wait_healthy(
        name="n8n",
        url="http://localhost:5678/healthz",
        timeout_seconds=60,
    )
    return f"""
n8n_hook() {{
    {wait}
    SETTINGS=$(curl -s --max-time 10 'http://localhost:5678/rest/settings' 2>/dev/null || echo "{{}}")
    NEEDS_SETUP=$(printf '%s' "$SETTINGS" | jq -r '.data.userManagement.showSetupOnFirstLoad // true | if . then "true" else "false" end' 2>/dev/null || echo "true")
    if [ "$NEEDS_SETUP" = "false" ]; then
        echo "RESULT hook=n8n status=already-configured"
        return 0
    fi
    BODY=$(NEXUS_E={email_q} NEXUS_P={password_q} jq -n \\
        '{{email: env.NEXUS_E, firstName: "Admin", lastName: "User", password: env.NEXUS_P}}')
    RESP=$(printf '%s' "$BODY" | curl -s -X POST 'http://localhost:5678/rest/owner/setup' \\
        --max-time 30 \\
        -H 'Content-Type: application/json' \\
        --data-binary @- 2>/dev/null || echo "")
    if echo "$RESP" | grep -q '"id"'; then
        echo "RESULT hook=n8n status=configured"
    else
        echo "RESULT hook=n8n status=failed"
    fi
}}
n8n_hook
"""


def render_metabase_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """Metabase first-setup: ``POST /api/setup`` with one-time setup token."""
    email = env.admin_email or ""
    password = config.metabase_admin_password or ""
    if not password or not email:
        return 'echo "RESULT hook=metabase status=skipped-not-ready"\n'
    email_q = shlex.quote(email)
    password_q = shlex.quote(password)
    wait = _render_wait_healthy(
        name="metabase",
        url="http://localhost:3000/api/health",
        timeout_seconds=120,
    )
    return f"""
metabase_hook() {{
    {wait}
    SETUP_TOKEN=$(curl -s --max-time 10 'http://localhost:3000/api/session/properties' 2>/dev/null \\
        | jq -r '."setup-token" // empty' 2>/dev/null || echo "")
    if [ -z "$SETUP_TOKEN" ]; then
        echo "RESULT hook=metabase status=already-configured"
        return 0
    fi
    BODY=$(NEXUS_TOKEN="$SETUP_TOKEN" NEXUS_E={email_q} NEXUS_P={password_q} jq -n \\
        '{{token: env.NEXUS_TOKEN, user: {{email: env.NEXUS_E, first_name: "Admin", last_name: "User", password: env.NEXUS_P}}, prefs: {{site_name: "Nexus Stack Analytics", allow_tracking: false}}}}')
    RESP=$(printf '%s' "$BODY" | curl -s -X POST 'http://localhost:3000/api/setup' \\
        --max-time 30 \\
        -H 'Content-Type: application/json' \\
        --data-binary @- 2>/dev/null || echo "")
    if echo "$RESP" | grep -q '"id"'; then
        echo "RESULT hook=metabase status=configured"
    else
        echo "RESULT hook=metabase status=failed"
    fi
}}
metabase_hook
"""


def render_lakefs_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """LakeFS: ``POST /api/v1/setup_lakefs`` then ``POST /api/v1/repositories``.

    Two-step: setup admin user (no auth, idempotent via ``/api/v1/config``
    ``setup_complete`` flag) THEN create the default repo (basic-auth
    using the just-created credentials, idempotent via "already exists"
    response substring). Both reported as one ``RESULT`` line; the
    repo step's status is folded into the overall hook outcome.
    """
    del env  # not used; signature uniform across hooks
    access_key = config.lakefs_admin_access_key or ""
    secret_key = config.lakefs_admin_secret_key or ""
    if not access_key or not secret_key:
        return 'echo "RESULT hook=lakefs status=skipped-not-ready"\n'
    access_q = shlex.quote(access_key)
    secret_q = shlex.quote(secret_key)
    # Storage namespace selection: BOTH HETZNER_S3_SERVER AND
    # HETZNER_S3_BUCKET must be set. Bucket alone isn't enough because LakeFS
    # also needs the endpoint URL to read/write S3, and a partially
    # configured tofu state (bucket without server) would land us in
    # the s3:// branch with broken connectivity. Both NexusConfig
    # fields are shlex-quoted into the rendered bash as literals, NOT
    # read from a remote env var — keeps the renderer pure.
    hetzner_bucket = config.hetzner_s3_bucket_lakefs or ""
    hetzner_server = config.hetzner_s3_server or ""
    hetzner_bucket_q = shlex.quote(hetzner_bucket)
    hetzner_server_q = shlex.quote(hetzner_server)
    wait = _render_wait_healthy(
        name="lakefs",
        url="http://localhost:8000/api/v1/healthcheck",
        timeout_seconds=60,
    )
    return f"""
lakefs_hook() {{
    {wait}
    CFG=$(curl -s --max-time 10 'http://localhost:8000/api/v1/config' 2>/dev/null || echo "")
    SETUP_DONE=false
    if echo "$CFG" | grep -q '"setup_complete":true'; then
        SETUP_DONE=true
    fi
    if [ "$SETUP_DONE" = "false" ]; then
        SETUP_BODY=$(NEXUS_AK={access_q} NEXUS_SK={secret_q} jq -n \\
            '{{username: "nexus-lakefs", key: {{access_key_id: env.NEXUS_AK, secret_access_key: env.NEXUS_SK}}}}')
        SETUP_RESP=$(printf '%s' "$SETUP_BODY" | curl -s -X POST 'http://localhost:8000/api/v1/setup_lakefs' \\
            --max-time 30 \\
            -H 'Content-Type: application/json' \\
            --data-binary @- 2>/dev/null || echo "")
        if ! echo "$SETUP_RESP" | grep -q 'access_key_id'; then
            if ! echo "$SETUP_RESP" | grep -qi 'already'; then
                echo "RESULT hook=lakefs status=failed"
                return 0
            fi
        fi
    fi
    HETZNER_BUCKET={hetzner_bucket_q}
    HETZNER_SERVER={hetzner_server_q}
    # BOTH must be set to pick the s3:// namespace (bucket alone
    # without endpoint would break read/write).
    if [ -n "$HETZNER_BUCKET" ] && [ -n "$HETZNER_SERVER" ]; then
        STORAGE_NS="s3://${{HETZNER_BUCKET}}/lakefs/"
        REPO_NAME="hetzner-object-storage"
    else
        STORAGE_NS="local://data/lakefs/"
        REPO_NAME="local-storage"
    fi
    REPO_BODY=$(jq -n \\
        --arg name "$REPO_NAME" \\
        --arg ns "$STORAGE_NS" \\
        '{{name: $name, storage_namespace: $ns, default_branch: "main", sample_data: false}}')
    # R4: basic-auth via curl --config tmpfile, NOT -u user:secret
    # in argv. The tmpfile is mode 600 + cleaned up by a function-
    # scoped RETURN trap (fires when lakefs_hook returns) plus an
    # explicit `rm -f` after the curl call.
    LFS_CFG=$(mktemp)
    chmod 600 "$LFS_CFG"
    trap 'rm -f "$LFS_CFG"' RETURN
    printf 'user = "%s:%s"\\n' {access_q} {secret_q} > "$LFS_CFG"
    REPO_RESP=$(printf '%s' "$REPO_BODY" | curl -s -X POST 'http://localhost:8000/api/v1/repositories' \\
        --config "$LFS_CFG" \\
        --max-time 30 \\
        -H 'Content-Type: application/json' \\
        --data-binary @- 2>/dev/null || echo "")
    rm -f "$LFS_CFG"
    trap - RETURN
    if echo "$REPO_RESP" | grep -q '"id"'; then
        echo "RESULT hook=lakefs status=configured"
    elif echo "$REPO_RESP" | grep -q 'already exists'; then
        if [ "$SETUP_DONE" = "true" ]; then
            echo "RESULT hook=lakefs status=already-configured"
        else
            echo "RESULT hook=lakefs status=configured"
        fi
    else
        echo "RESULT hook=lakefs status=failed"
    fi
}}
lakefs_hook
"""


def render_openmetadata_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """OpenMetadata: 3-step (default-pwd login → change-password → verify).

    Login API takes base64-encoded passwords; changePassword takes
    plain text. The orchestrator detects "already configured" via
    the default-login failing with ``invalid|unauthorized``.
    """
    new_password = config.openmetadata_admin_password or ""
    email = env.admin_email or ""
    if not new_password or not email:
        return 'echo "RESULT hook=openmetadata status=skipped-not-ready"\n'
    new_pw_q = shlex.quote(new_password)
    email_q = shlex.quote(email)
    # OpenMetadata's wait check is a body-substring grep, not an HTTP
    # status check — we render a custom wait loop here instead of using
    # _render_wait_healthy.
    return f"""
openmetadata_hook() {{
    EMAIL={email_q}
    DOMAIN=$(printf '%s' "$EMAIL" | cut -d'@' -f2)
    # Wall-clock-bounded wait (matches _render_wait_healthy's pattern):
    # each iteration spends up to ~5s in curl + 3s sleep, so an
    # iteration-counted loop would blow well past 180s in the
    # worst case. ``$SECONDS`` caps the real wall-time at 180.
    READY=false
    SECONDS=0
    while [ "$SECONDS" -lt 180 ]; do
        if curl -s --connect-timeout 3 --max-time 5 'http://localhost:8585/api/v1/system/version' 2>/dev/null | grep -q 'version'; then
            READY=true; break
        fi
        sleep 3
    done
    if [ "$READY" != "true" ]; then
        echo "  ⚠ openmetadata not ready after 180s — skipping setup" >&2
        echo "RESULT hook=openmetadata status=skipped-not-ready"
        return 0
    fi
    DEFAULT_PW_B64=$(printf 'admin' | base64 | tr -d '\\n')
    # NEXUS_PW carries the base64 of "admin" (default OpenMetadata
    # password) — public knowledge, but keep it out of jq's argv
    # uniformly with the other hooks. NEXUS_E is the email address.
    LOGIN_BODY=$(NEXUS_E="admin@${{DOMAIN}}" NEXUS_PW="$DEFAULT_PW_B64" jq -n \\
        '{{email: env.NEXUS_E, password: env.NEXUS_PW}}')
    LOGIN_RESP=$(printf '%s' "$LOGIN_BODY" | curl -s -X POST 'http://localhost:8585/api/v1/users/login' \\
        --max-time 30 \\
        -H 'Content-Type: application/json' \\
        --data-binary @- 2>/dev/null || echo "")
    TOKEN=$(printf '%s' "$LOGIN_RESP" | jq -r '.accessToken // empty' 2>/dev/null)
    if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
        if echo "$LOGIN_RESP" | grep -qi 'invalid\\|unauthorized\\|credentials'; then
            echo "RESULT hook=openmetadata status=already-configured"
        else
            echo "RESULT hook=openmetadata status=failed"
        fi
        return 0
    fi
    PW_BODY=$(NEXUS_NEW={new_pw_q} jq -n \\
        '{{username: "admin", oldPassword: "admin", newPassword: env.NEXUS_NEW, confirmPassword: env.NEXUS_NEW, requestType: "SELF"}}')
    # R4: Bearer token via curl --config tmpfile, NOT -H argv. The
    # tmpfile is mode 600 + cleaned up by a function-scoped RETURN
    # trap (fires when openmetadata_hook returns) plus an explicit
    # `rm -f` after the curl call.
    OM_CFG=$(mktemp)
    chmod 600 "$OM_CFG"
    trap 'rm -f "$OM_CFG"' RETURN
    printf 'header = "Authorization: Bearer %s"\\n' "$TOKEN" > "$OM_CFG"
    printf '%s' "$PW_BODY" | curl -s -X PUT 'http://localhost:8585/api/v1/users/changePassword' \\
        --config "$OM_CFG" \\
        --max-time 30 \\
        -H 'Content-Type: application/json' \\
        --data-binary @- >/dev/null 2>&1 || true
    rm -f "$OM_CFG"
    trap - RETURN
    # base64 reads the new password from stdin (printf is a bash
    # builtin → no fork → no `ps` exposure for the printf).
    NEW_PW_B64=$(printf '%s' {new_pw_q} | base64 | tr -d '\\n')
    # NEXUS_PW carries the base64-of-new-password — even base64 of
    # the password is sensitive (trivially reversible), so we route
    # via env var to keep it out of jq's argv.
    VERIFY_BODY=$(NEXUS_E="admin@${{DOMAIN}}" NEXUS_PW="$NEW_PW_B64" jq -n \\
        '{{email: env.NEXUS_E, password: env.NEXUS_PW}}')
    VERIFY_RESP=$(printf '%s' "$VERIFY_BODY" | curl -s -X POST 'http://localhost:8585/api/v1/users/login' \\
        --max-time 30 \\
        -H 'Content-Type: application/json' \\
        --data-binary @- 2>/dev/null || echo "")
    if printf '%s' "$VERIFY_RESP" | jq -r '.accessToken // empty' 2>/dev/null | grep -q '.'; then
        echo "RESULT hook=openmetadata status=configured"
    else
        echo "RESULT hook=openmetadata status=failed"
    fi
}}
openmetadata_hook
"""


# ---------------------------------------------------------------------------
# docker-exec hooks: RedPanda, Superset.
#
# Different family from the 5 REST hooks above. Pattern:
#   1. Wait for HTTP healthcheck (mostly via ``docker exec curl`` from
#      inside the container, since some endpoints aren't exposed
#      externally).
#   2. Run an in-container CLI (``rpk`` / ``superset fab``) via
#      ``docker exec -i``, with passwords piped via stdin so they
#      never reach docker's argv on the remote host.
#   3. Idempotent re-runs handled per-hook (RedPanda: rpk's "user
#      exists" error is treated as already-configured; Superset:
#      fab create-admin → fab reset-password fallback).
#
# Why argv-vs-stdin matters for docker exec: passing a password via
# ``docker exec -e RPK_PASS='$pass'`` lands the env-var literal in
# docker's argv on the host. The strictly-more-correct path is
# ``printf '%s' "$pass" | docker exec -i <container> sh -c 'PASS=$(cat); ...'``,
# which keeps the password on stdin only. The inner CLI ``rpk acl
# user create --password "$PASS"`` still has the password in its
# argv inside the container (visible to other processes in the same
# container), but the OUTER host-level ``ps -ef`` shows just the
# benign sh -c invocation.
# ---------------------------------------------------------------------------


def render_redpanda_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """RedPanda SASL: ``rpk acl user create`` + ``rpk cluster config set superusers``.

    Wait via ``docker exec redpanda curl -sf /v1/status/ready`` (the
    admin API isn't exposed outside the container; ``-sf`` requires
    a true 2xx status, not just a transport-level success). Password
    reaches the container via stdin → in-container shell var → rpk's
    ``--password`` argv (visible only inside the container, not via
    host ``ps``).

    Idempotency contract — always converges to ``configured``
    (or ``failed`` / ``skipped-not-ready``); NO ``already-configured``
    path. Reasoning:
    - First run: create user → cluster config → restart → verify ✓
    - Re-run with same Infisical password: rpk reports "already exists"
      → delete + recreate (no broker restart, since SASL listener is
      already on) → verify ✓ — ends in ``configured``, not
      ``already-configured``, because we DID re-write state (the
      password was rotated to its current value, even if that
      happens to equal the previous value).
    - Re-run with rotated password: same path as above, password
      now genuinely differs → external clients pick up new credential
      via Infisical sync.

    The delete is gated on the first create-attempt returning
    "already exists" — we never delete a user we haven't proven the
    broker can recreate. A transient broker glitch on the first
    create returns ``failed`` without touching existing state.

    Restart of the broker happens ONLY on first setup
    (``USER_EXISTED=false``). Subsequent rotations don't need it
    because the SASL listener config is a one-time broker-side
    setting; only the credentials change. Restart failure is
    surfaced as ``failed`` (legacy ``|| true`` hid this — listener
    not picking up the SASL change is broken-but-silent).
    """
    del env  # not used; signature uniform across hooks
    password = config.redpanda_admin_password or ""
    if not password:
        return 'echo "RESULT hook=redpanda status=skipped-not-ready"\n'
    password_q = shlex.quote(password)
    return f"""
redpanda_hook() {{
    # Wall-clock-bounded readiness wait (matches the per-spec
    # healthcheck-timeout convention from R2).
    # `curl -sf` returns non-zero on 4xx/5xx responses (NOT just on
    # transport failures), so the loop only breaks on a true 200 OK
    # — earlier `curl -s` would have broken on a 503 too, letting the
    # SASL setup run while RedPanda was still "not ready".
    READY=false
    SECONDS=0
    while [ "$SECONDS" -lt 60 ]; do
        if docker exec redpanda curl -sf --connect-timeout 2 --max-time 5 'http://localhost:9644/v1/status/ready' >/dev/null 2>&1; then
            READY=true; break
        fi
        sleep 2
    done
    if [ "$READY" != "true" ]; then
        echo "  ⚠ redpanda admin API not ready after 60s — skipping SASL setup" >&2
        echo "RESULT hook=redpanda status=skipped-not-ready"
        return 0
    fi
    # Try create-first. Three outcomes:
    #   1. SUCCESS → fresh install, USER_EXISTED stays false (→ restart needed below)
    #   2. "already exists" → rotation case: delete the current user
    #      and recreate with the current Infisical password. We only
    #      open the no-user window AFTER the first create proved the
    #      broker accepts our request, so a transient broker glitch
    #      can't leave us userless mid-flight.
    #   3. Other error → bail with failed.
    # Pipe password via stdin so it never reaches docker exec's argv
    # on the host. Inside the container, `cat` consumes the full
    # stdin into RPK_PASS; rpk then receives it via shell var
    # expansion (still in argv inside the container — different
    # threat model).
    REDPANDA_PASSWORD={password_q}
    USER_EXISTED=false
    USER_RESULT=$(printf '%s' "$REDPANDA_PASSWORD" | \\
        docker exec -i redpanda sh -c 'RPK_PASS=$(cat); rpk acl user create nexus-redpanda --password "$RPK_PASS" --mechanism SCRAM-SHA-256' 2>&1 || echo "")
    if echo "$USER_RESULT" | grep -qi 'already exists\\|user already\\|already in use'; then
        # Rotation path: delete + recreate. Brief no-user window —
        # acceptable because we just proved the broker is responsive.
        # Without this branch, an Infisical password rotation would
        # silently leave the broker out of sync.
        USER_EXISTED=true
        docker exec redpanda rpk acl user delete nexus-redpanda >/dev/null 2>&1 || true
        USER_RESULT=$(printf '%s' "$REDPANDA_PASSWORD" | \\
            docker exec -i redpanda sh -c 'RPK_PASS=$(cat); rpk acl user create nexus-redpanda --password "$RPK_PASS" --mechanism SCRAM-SHA-256' 2>&1 || echo "")
        if ! echo "$USER_RESULT" | grep -qi 'created\\|added\\|success'; then
            echo "  ⚠ rpk acl user create failed after delete (no SASL user — broker is now in a broken state): $USER_RESULT" >&2
            echo "RESULT hook=redpanda status=failed"
            return 0
        fi
    elif ! echo "$USER_RESULT" | grep -qi 'created\\|added\\|success'; then
        echo "  ⚠ rpk acl user create failed: $USER_RESULT" >&2
        echo "RESULT hook=redpanda status=failed"
        return 0
    fi
    # rpk cluster config set: superusers list. Capture the result so
    # we can fail loudly — without this check, the user would have
    # no permissions and the broker would reject every ACL-protected
    # operation while the hook reported `configured`.
    SUPER_RESULT=$(docker exec redpanda rpk cluster config set superusers '["nexus-redpanda"]' 2>&1 || echo "")
    if ! echo "$SUPER_RESULT" | grep -qi 'success\\|updated\\|set'; then
        echo "  ⚠ rpk cluster config set superusers failed: $SUPER_RESULT" >&2
        echo "RESULT hook=redpanda status=failed"
        return 0
    fi
    # Restart only on FIRST setup. SASL listener config is set on the
    # broker side once and stays applied across rotations, so a
    # password-only change doesn't need a restart. An unconditional
    # restart would be harmless when the broker has no traffic but
    # introduces a multi-second window where producers/consumers
    # reconnect for no reason.
    if [ "$USER_EXISTED" = "false" ]; then
        # First-setup restart: the SASL listener config takes effect
        # only after a broker restart. Capture the exit code — if the
        # restart fails (network/disk/compose issue), the listener
        # never picks up the SASL change and external clients can't
        # authenticate, even though the user exists. Legacy `|| true`
        # would have hidden this.
        RESTART_RC=0
        if [ -f /opt/docker-server/stacks/redpanda/docker-compose.firewall.yml ]; then
            ( cd /opt/docker-server/stacks/redpanda && docker compose -f docker-compose.yml -f docker-compose.firewall.yml restart >/dev/null 2>&1 ) || RESTART_RC=$?
        else
            ( cd /opt/docker-server/stacks/redpanda && docker compose restart >/dev/null 2>&1 ) || RESTART_RC=$?
        fi
        if [ "$RESTART_RC" -ne 0 ]; then
            echo "  ⚠ docker compose restart redpanda failed (rc=$RESTART_RC) — SASL listener config not applied" >&2
            echo "RESULT hook=redpanda status=failed"
            return 0
        fi
        sleep 5
        # Wait for restart-readiness. `curl -sf` for proper status check.
        SECONDS=0
        while [ "$SECONDS" -lt 30 ]; do
            if docker exec redpanda curl -sf --connect-timeout 2 --max-time 5 'http://localhost:9644/v1/status/ready' >/dev/null 2>&1; then break; fi
            sleep 2
        done
    fi
    # Verify the user is in place after all state changes. `curl -sf`
    # → if the admin API is still not-ready, the verify probe fails
    # and we report `failed` (NOT a false-positive `configured`).
    USERS=$(docker exec redpanda curl -sf --max-time 10 'http://localhost:9644/v1/security/users' 2>/dev/null || echo "[]")
    if echo "$USERS" | grep -q 'nexus-redpanda'; then
        echo "RESULT hook=redpanda status=configured"
    else
        echo "RESULT hook=redpanda status=failed"
    fi
}}
redpanda_hook
"""


def render_superset_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """Superset admin setup: ``superset fab create-admin`` (with reset-password fallback).

    Wait via ``/health`` substring grep ('OK'). Both ``fab create-admin``
    and ``fab reset-password`` accept ``--password "$VAR"`` — the
    password reaches the in-container shell via stdin, then is
    expanded as the inner argv (visible inside the container only,
    not via host ``ps``). Idempotent re-run: if create-admin reports
    user-exists, fall back to reset-password.
    """
    password = config.superset_admin_password or ""
    email = env.admin_email or ""
    if not password or not email:
        return 'echo "RESULT hook=superset status=skipped-not-ready"\n'
    password_q = shlex.quote(password)
    email_q = shlex.quote(email)
    return f"""
superset_hook() {{
    # Wall-clock-bounded readiness wait. Superset is slow on first
    # boot (db upgrade + init) — generous 5min timeout.
    READY=false
    SECONDS=0
    while [ "$SECONDS" -lt 300 ]; do
        if curl -s --connect-timeout 2 --max-time 5 'http://localhost:8089/health' 2>/dev/null | grep -q 'OK'; then
            READY=true; break
        fi
        sleep 5
    done
    if [ "$READY" != "true" ]; then
        echo "  ⚠ superset not ready after 5min — skipping admin setup" >&2
        echo "RESULT hook=superset status=skipped-not-ready"
        return 0
    fi
    # Pass password via stdin → in-container PASS var → fab argv. The
    # email is non-secret, so it goes via -e (host argv, but harmless).
    SUPERSET_PASSWORD={password_q}
    ADMIN_EMAIL={email_q}
    CREATE_RESULT=$(printf '%s' "$SUPERSET_PASSWORD" | \\
        docker exec -i -e ADMIN_EMAIL="$ADMIN_EMAIL" superset \\
        sh -c 'PASS=$(cat); superset fab create-admin --username admin --email "$ADMIN_EMAIL" --firstname Superset --lastname Admin --password "$PASS"' 2>&1 || echo "")
    if echo "$CREATE_RESULT" | grep -qi 'created\\|added'; then
        echo "RESULT hook=superset status=configured"
        return 0
    fi
    # Fallback: fab reset-password for the existing admin user.
    RESET_RESULT=$(printf '%s' "$SUPERSET_PASSWORD" | \\
        docker exec -i superset \\
        sh -c 'PASS=$(cat); superset fab reset-password --username admin --password "$PASS"' 2>&1 || echo "")
    if echo "$RESET_RESULT" | grep -qi 'reset\\|changed\\|success'; then
        echo "RESULT hook=superset status=already-configured"
    else
        echo "RESULT hook=superset status=failed"
    fi
}}
superset_hook
"""


def render_hedgedoc_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """HedgeDoc admin seed: ``node /hedgedoc/bin/manage_users --add EMAIL``.

    With CMD_ALLOW_EMAIL_REGISTER=false (the post-#618 default), no
    one can sign up through the web UI — the CLI is the only path
    to create the single admin account.

    Idempotent pattern mirrors Superset's: try ``--add`` first,
    if the user already exists fall back to ``--reset`` so a
    rotated random_password.hedgedoc_admin (or a re-seed after an
    R2 snapshot restore from a stack with a different password)
    converges the in-DB hash with the Infisical-stored secret.

    Secrets handling: the password is piped via stdin into ``docker
    exec -i`` and read by an in-container ``sh -c 'PASS=$(cat); ...'``
    wrapper, so the cleartext password reaches the ``node`` argv
    only INSIDE the container (visible to a hypothetical
    other-uid-attached process in that container, of which there is
    none) and NEVER appears in host-side ``ps`` output. Same threat
    model as Superset's hook.

    The /status endpoint returns 200 once the Node process bound
    its port; that's a sufficient readiness signal for the CLI
    sub-process to find a valid sequelize connection. We give the
    container 90s before bailing — first-init runs migrations, and
    the Postgres-DB-restore path adds another beat.
    """
    password = config.hedgedoc_admin_password or ""
    email = env.admin_email or ""
    if not password or not email:
        return 'echo "RESULT hook=hedgedoc status=skipped-not-ready"\n'
    password_q = shlex.quote(password)
    email_q = shlex.quote(email)
    wait = _render_wait_healthy(
        name="hedgedoc",
        url="http://localhost:3110/status",
        timeout_seconds=90,
    )
    return f"""
hedgedoc_hook() {{
    {wait}
    HEDGEDOC_ADMIN_EMAIL={email_q}
    HEDGEDOC_ADMIN_PASSWORD={password_q}
    # Try add first — stdin-pipe the password so the cleartext is
    # never in host argv. The inner sh reads stdin into PASS, then
    # invokes manage_users with --pass "$PASS" so the password is
    # in the CONTAINER's node argv only (host-side argv shows only
    # `sh -c '...'`). 2>&1 captures both manage_users's "already
    # exists" message (stdout) and any sequelize errors (stderr).
    CREATE_RESULT=$(printf '%s' "$HEDGEDOC_ADMIN_PASSWORD" | \\
        docker exec -i -e HEDGEDOC_ADMIN_EMAIL="$HEDGEDOC_ADMIN_EMAIL" hedgedoc \\
        sh -c 'PASS=$(cat); node /hedgedoc/bin/manage_users --add "$HEDGEDOC_ADMIN_EMAIL" --pass "$PASS"' 2>&1 || echo "")
    if echo "$CREATE_RESULT" | grep -q 'Created user'; then
        echo "RESULT hook=hedgedoc status=configured"
        return 0
    fi
    if ! echo "$CREATE_RESULT" | grep -q 'already exists'; then
        echo "  ⚠ hedgedoc admin create unexpected output: $CREATE_RESULT" >&2
        echo "RESULT hook=hedgedoc status=failed"
        return 0
    fi
    # Fallback: reset password so the in-DB hash matches the
    # Infisical-stored secret (re-converges after snapshot restore
    # with a rotated random_password, or operator-side `tofu taint`).
    RESET_RESULT=$(printf '%s' "$HEDGEDOC_ADMIN_PASSWORD" | \\
        docker exec -i -e HEDGEDOC_ADMIN_EMAIL="$HEDGEDOC_ADMIN_EMAIL" hedgedoc \\
        sh -c 'PASS=$(cat); node /hedgedoc/bin/manage_users --reset "$HEDGEDOC_ADMIN_EMAIL" --pass "$PASS"' 2>&1 || echo "")
    if echo "$RESET_RESULT" | grep -qi 'reset\\|changed\\|success'; then
        echo "RESULT hook=hedgedoc status=already-configured"
    else
        echo "  ⚠ hedgedoc admin reset unexpected output: $RESET_RESULT" >&2
        echo "RESULT hook=hedgedoc status=failed"
    fi
}}
hedgedoc_hook
"""


# ---------------------------------------------------------------------------
# Admin-setup hooks for the bash-render family: Uptime Kuma, Garage,
# Wiki.js, Dify, Windmill, SFTPGo. SFTPGo was originally a candidate
# for the filestash-style Python hook (two SSH round-trips), but its
# JSON construction is built remote-side via ``jq -n env``, so no
# Python-side mutation is needed and the bash-render pattern is
# uniform across all six.
# ---------------------------------------------------------------------------


def render_uptime_kuma_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """Uptime Kuma: manual-setup placeholder (issue #145).

    The Socket.io-based admin bootstrap fails from inside the
    container — see issue #145. Until that's fixed, this hook emits
    a stderr warning pointing operators at Infisical for credentials
    and reports ``skipped-not-ready``. Registering the hook
    explicitly gives operators a hook line in the workflow log and
    makes it trivial to swap in the real auto-setup the moment
    Socket.io / container networking constraints are resolved.
    """
    del config, env  # signature uniform across hooks
    return """
uptime_kuma_hook() {
    echo "  ⚠ Uptime Kuma requires manual setup on first login (issue #145)" >&2
    echo "    Credentials available in Infisical" >&2
    echo "RESULT hook=uptime-kuma status=skipped-not-ready"
}
uptime_kuma_hook
"""


def render_garage_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """Garage: layout assign + apply + key create (one-time, idempotent).

    Three docker-exec calls on the ``garage`` container:
    1. ``/garage layout show`` — detect already-configured (legacy
       check ``"No nodes currently have"`` substring); skip with
       ``already-configured`` if configured.
    2. ``/garage node id`` — fetch node ID, validate as 64-hex,
       slice to first-16 short form (Garage's layout commands use
       the short form).
    3. ``/garage layout assign -z dc1 -c 100G $NODE_ID`` +
       ``/garage layout apply --version 1`` + ``/garage key create
       nexus-garage-key``.

    Wait via ``/health`` HTTP probe on the admin API (port 3903)
    bounded to 30s wall-clock.

    Idempotency contract:
    - Already-configured (any node has a role) → ``already-configured``
    - Layout missing nodes / new install → assign + apply + key →
      ``configured``
    - Node-id fetch fails / non-hex / wrong length → ``failed``
      (operator must investigate; auto-retry on next spin-up)
    """
    del config, env  # admin token comes via .env, not into the hook
    wait = _render_wait_healthy(
        name="garage",
        url="http://localhost:3903/health",
        timeout_seconds=30,
        interval_seconds=2,
    )
    return f"""
garage_hook() {{
{wait}
    # Capture the layout-show exit status separately. ``|| echo ""``
    # would silently treat ANY failure (Docker daemon unhealthy,
    # container missing, RPC timeout) as "already-configured"
    # because the grep then doesn't match. Surfacing the exit status
    # makes genuine container failures report `failed` instead of
    # false-positive `already-configured`.
    LAYOUT_RC=0
    LAYOUT_CHECK=$(docker exec garage /garage layout show 2>&1) || LAYOUT_RC=$?
    if [ "$LAYOUT_RC" -ne 0 ]; then
        echo "  ⚠ garage layout show failed (rc=$LAYOUT_RC) — container or daemon unhealthy" >&2
        echo "RESULT hook=garage status=failed"
        return 0
    fi
    if ! echo "$LAYOUT_CHECK" | grep -q "No nodes currently have"; then
        echo "RESULT hook=garage status=already-configured"
        return 0
    fi
    # Node id is the first line of `/garage node id`. Validate as
    # 64-char hex before using to avoid running layout commands
    # with garbage if Garage wasn't fully ready (the earlier wait
    # probe already gates this, but belt-and-braces).
    FULL_NODE_ID=$(docker exec garage /garage node id 2>&1 | head -1 || echo "")
    if [ -z "$FULL_NODE_ID" ] || [ ${{#FULL_NODE_ID}} -ne 64 ] \\
       || ! echo "$FULL_NODE_ID" | grep -qE '^[0-9a-fA-F]{{64}}$'; then
        echo "  ⚠ Garage node id missing or malformed — layout setup skipped" >&2
        echo "RESULT hook=garage status=failed"
        return 0
    fi
    NODE_ID="${{FULL_NODE_ID:0:16}}"
    if ! docker exec garage /garage layout assign -z dc1 -c 100G "$NODE_ID" >/dev/null 2>&1; then
        echo "RESULT hook=garage status=failed"
        return 0
    fi
    if ! docker exec garage /garage layout apply --version 1 >/dev/null 2>&1; then
        echo "RESULT hook=garage status=failed"
        return 0
    fi
    # `key create` is idempotent on the Garage side (returns the
    # existing key if it already exists), so we don't distinguish
    # already-exists from fresh-create. But we DO need to
    # distinguish 'idempotent no-op' from 'docker daemon unhealthy /
    # container missing' — the latter must surface as `failed`,
    # not silently report `configured`. Same class as the
    # layout-show R1 fix.
    KEY_RC=0
    docker exec garage /garage key create nexus-garage-key >/dev/null 2>&1 || KEY_RC=$?
    if [ "$KEY_RC" -ne 0 ]; then
        echo "  ⚠ garage key create failed (rc=$KEY_RC) — container or daemon unhealthy" >&2
        echo "RESULT hook=garage status=failed"
        return 0
    fi
    echo "RESULT hook=garage status=configured"
}}
garage_hook
"""


def render_wikijs_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """Wiki.js: GraphQL ``setup`` mutation (creates admin + finalises install).

    Two-step:
    1. Wait for ``/healthz`` to return HTTP 200. Bounded to 90s.
       (Wiki.js returns plain ``OK`` only when status is 200, so a
       status-only check is equivalent to a body-grep.)
    2. POST GraphQL mutation ``setup($input: SetupInput!)`` with
       admin email + password (twice, "confirm" field) + site URL.
       Wiki.js returns ``{succeeded: true}`` on first run,
       ``{...message: "...already...}`` on re-run.

    Idempotency contract:
    - First run: setup succeeds → ``configured``
    - Re-run: response message contains "already" → ``already-configured``
    - Other: ``failed``

    Email source: ``env.gitea_user_email`` if non-empty, else
    ``env.admin_email`` (single-address user identity for the Wiki).
    """
    password = config.wikijs_admin_password or ""
    email = env.gitea_user_email or env.admin_email or ""
    domain = env.domain or ""
    if not password or not email or not domain:
        return 'echo "RESULT hook=wikijs status=skipped-not-ready"\n'
    password_q = shlex.quote(password)
    email_q = shlex.quote(email)
    site_url_q = shlex.quote(f"https://{service_host('wiki', domain, env.subdomain_separator)}")
    wait = _render_wait_healthy(
        name="wikijs",
        url="http://localhost:3005/healthz",
        timeout_seconds=90,
        interval_seconds=3,
        # Wiki.js's /healthz returns plain text "OK" with 200; a
        # STATUS check is sufficient (a body-grep for "ok" is the
        # same signal).
    )
    return f"""
wikijs_hook() {{
{wait}
    # Build the GraphQL setup mutation body via jq -n with env-var
    # inputs (NOT --arg, which would put values into jq's argv).
    SETUP_BODY=$(NEXUS_E={email_q} NEXUS_P={password_q} NEXUS_U={site_url_q} jq -n \\
        '{{query: "mutation ($input: SetupInput!) {{ setup(input: $input) {{ responseResult {{ succeeded message }} }} }}",
           variables: {{input: {{adminEmail: env.NEXUS_E, adminPassword: env.NEXUS_P, adminPasswordConfirm: env.NEXUS_P, siteUrl: env.NEXUS_U, telemetry: false}}}}}}')
    SETUP_RESP=$(printf '%s' "$SETUP_BODY" | curl -s -X POST 'http://localhost:3005/graphql' \\
        --max-time 30 \\
        -H 'Content-Type: application/json' \\
        --data-binary @- 2>/dev/null || echo "")
    if echo "$SETUP_RESP" | grep -q '"succeeded":true'; then
        echo "RESULT hook=wikijs status=configured"
    elif echo "$SETUP_RESP" | grep -qi 'already'; then
        echo "RESULT hook=wikijs status=already-configured"
    else
        echo "RESULT hook=wikijs status=failed"
    fi
}}
wikijs_hook
"""


def render_dify_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """Dify: 2-step admin bootstrap (``/console/api/init`` → ``/console/api/setup``).

    Three stages:
    1. Wait for the API to return 200/302/307 on ``/`` (Dify's
       redirect-to-/install pattern indicates the API is alive).
       Bounded to 120s — Dify cold-starts slowly.
    2. Pre-check ``/console/api/setup`` GET — if step ``finished``,
       skip with ``already-configured``.
    3. POST ``/console/api/init`` with the init password (cookie-jar
       captures the session). Then POST ``/console/api/setup`` with
       admin email + name + password (using the cookie). Dify
       responds ``{result:"success"}`` on success.

    Idempotency contract:
    - ``/setup`` reports ``"step":"finished"`` → ``already-configured``
    - Init+setup both succeed → ``configured``
    - Init validation fails → ``failed`` (init password is the same
      as admin password — if init rejects it, setup will too)
    - Other → ``failed``

    Cookie-jar is a mode-600 tmpfile cleaned via RETURN trap.
    """
    password = config.dify_admin_password or ""
    email = env.admin_email or ""
    if not password or not email:
        return 'echo "RESULT hook=dify status=skipped-not-ready"\n'
    password_q = shlex.quote(password)
    email_q = shlex.quote(email)
    # Dify's wait predicate is "200 OR 302 OR 307" — uniform 200-only
    # check would skip-not-ready while Dify is doing its install
    # redirect dance. Render a custom wait loop instead of using
    # _render_wait_healthy.
    return f"""
dify_hook() {{
    # Two-stage readiness: wait for HTTP 200/302/307 on /.
    READY=false
    SECONDS=0
    while [ "$SECONDS" -lt 120 ]; do
        STATUS=$(curl -s -o /dev/null -w '%{{http_code}}' --connect-timeout 3 --max-time 5 'http://localhost:8501/' 2>/dev/null || echo "000")
        case "$STATUS" in
            200|302|307) READY=true; break ;;
        esac
        sleep 3
    done
    if [ "$READY" != "true" ]; then
        echo "  ⚠ dify not ready after 120s — skipping setup" >&2
        echo "RESULT hook=dify status=skipped-not-ready"
        return 0
    fi
    # Brief settling delay for Dify's API container — mirrors the
    # legacy 5s sleep after readiness probes returned.
    sleep 5
    SETUP_CHECK=$(curl -s --max-time 10 'http://localhost:8501/console/api/setup' 2>/dev/null || echo "")
    if echo "$SETUP_CHECK" | grep -q '"step":"finished"'; then
        echo "RESULT hook=dify status=already-configured"
        return 0
    fi
    # Cookie jar tmpfile — mode-600, cleaned on RETURN.
    DIFY_COOKIES=$(mktemp)
    chmod 600 "$DIFY_COOKIES"
    trap 'rm -f "$DIFY_COOKIES"' RETURN
    # Step 1: validate init password.
    INIT_BODY=$(NEXUS_P={password_q} jq -n '{{password: env.NEXUS_P}}')
    INIT_RESP=$(printf '%s' "$INIT_BODY" | curl -s -c "$DIFY_COOKIES" \\
        -X POST 'http://localhost:8501/console/api/init' \\
        --max-time 30 \\
        -H 'Content-Type: application/json' \\
        --data-binary @- 2>/dev/null || echo "")
    if ! echo "$INIT_RESP" | grep -q '"result":"success"'; then
        # Cleanup + trap reset on early-exit too — same set-u-leak
        # concern as the success-path cleanup below. R6 fixed only
        # the success path; R7 caught this matching failure path.
        rm -f "$DIFY_COOKIES"
        trap - RETURN
        echo "  ⚠ Dify init validation failed — configure manually at /install" >&2
        echo "RESULT hook=dify status=failed"
        return 0
    fi
    # Step 2: create admin account using the session cookie.
    SETUP_BODY=$(NEXUS_E={email_q} NEXUS_P={password_q} jq -n \\
        '{{email: env.NEXUS_E, name: "Admin", password: env.NEXUS_P}}')
    SETUP_RESP=$(printf '%s' "$SETUP_BODY" | curl -s -b "$DIFY_COOKIES" \\
        -X POST 'http://localhost:8501/console/api/setup' \\
        --max-time 30 \\
        -H 'Content-Type: application/json' \\
        --data-binary @- 2>/dev/null || echo "")
    # Explicit cleanup + trap reset before exit. The orchestrator
    # runs all hooks in one shell with `set -u`; a lingering RETURN
    # trap referencing $DIFY_COOKIES would fire on a later hook's
    # function-return and could trip set -u if the var is unset.
    # Same pattern as LakeFS / OpenMetadata.
    rm -f "$DIFY_COOKIES"
    trap - RETURN
    if echo "$SETUP_RESP" | grep -q '"result":"success"'; then
        echo "RESULT hook=dify status=configured"
    elif echo "$SETUP_RESP" | grep -qi 'already'; then
        echo "RESULT hook=dify status=already-configured"
    else
        echo "RESULT hook=dify status=failed"
    fi
}}
dify_hook
"""


def render_windmill_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """Windmill: 5-stage bootstrap (readiness wait, admin user,
    optional regular user, workspace, secure default account).

    All API stages use ``WINDMILL_SUPERADMIN_SECRET`` as the Bearer
    token (NOT a session cookie — Windmill's superadmin secret
    authenticates the Admin API directly).

    Stages:
    1. Wait for ``/api/version`` to return 200 (Windmill is up).
    2. POST ``/users/create`` for ``$ADMIN_EMAIL`` with
       ``super_admin: true`` and ``$WINDMILL_ADMIN_PASS`` —
       gives operators the documented login.
    3. POST ``/users/create`` for ``$GITEA_USER_EMAIL`` (only if it
       differs from $ADMIN_EMAIL) with ``super_admin: false`` and
       the same password — non-admin user identity for workflow
       authorship.
    4. POST ``/workspaces/create`` with ``{id: "nexus", name: "Nexus
       Stack"}`` — creates the working namespace.
    5. POST ``/users/setpassword`` with a newly-generated random
       password to rotate the bootstrapped ``admin@windmill.dev``
       account away from ``$WINDMILL_SUPERADMIN_SECRET``. **Critical
       security step** — without this, anyone with the secret could
       log in as the default admin.

    Idempotency contract:
    - Step 2/3 see "already exists" → continue (legacy did the same)
    - Step 4 returns ``"nexus"`` body or "created" → configured;
      "already exists" → already-configured
    - Step 5 always re-rotates (cheap and ensures the default
      account stays sealed across re-runs)
    - Final hook status is driven by Step 4's outcome:
      - 200/201 / "nexus" body → ``configured``
      - 409 / "already exists" → ``already-configured``
      - else → ``failed``

    Bearer-token transport: ``WINDMILL_SUPERADMIN_SECRET`` is written
    to a mode-600 ``curl --config`` tmpfile (RETURN-trap cleanup) so
    it never reaches curl's argv via ``-H``. Same pattern as LakeFS /
    OpenMetadata.
    """
    superadmin_secret = config.windmill_superadmin_secret or ""
    admin_password = config.windmill_admin_password or ""
    admin_email = env.admin_email or ""
    if not superadmin_secret or not admin_password or not admin_email:
        return 'echo "RESULT hook=windmill status=skipped-not-ready"\n'
    secret_q = shlex.quote(superadmin_secret)
    pw_q = shlex.quote(admin_password)
    admin_q = shlex.quote(admin_email)
    user_email_q = shlex.quote(env.gitea_user_email or "")
    wait = _render_wait_healthy(
        name="windmill",
        url="http://localhost:8200/api/version",
        timeout_seconds=120,
        interval_seconds=3,
    )
    return f"""
windmill_hook() {{
{wait}
    # Bearer-token tmpfile — mode-600, cleaned via RETURN trap.
    WM_CFG=$(mktemp)
    chmod 600 "$WM_CFG"
    trap 'rm -f "$WM_CFG"' RETURN
    NEXUS_S={secret_q} sh -c 'printf "header = \\"Authorization: Bearer %s\\"\\nheader = \\"Content-Type: application/json\\"\\n" "$NEXUS_S"' > "$WM_CFG"
    # Step 1: create the admin user (super_admin=true) for ADMIN_EMAIL.
    # NEXUS_E / NEXUS_P route email + password through env vars to jq —
    # NEVER `--arg`, which would land them in jq's argv.
    ADMIN_CREATE_BODY=$(NEXUS_E={admin_q} NEXUS_P={pw_q} jq -n \\
        '{{email: env.NEXUS_E, password: env.NEXUS_P, super_admin: true, name: "Admin"}}')
    printf '%s' "$ADMIN_CREATE_BODY" | curl -s --config "$WM_CFG" \\
        -X POST 'http://localhost:8200/api/users/create' \\
        --max-time 30 --data-binary @- >/dev/null 2>&1 || true
    # Step 2: optional regular user for GITEA_USER_EMAIL (if set and
    # differs from ADMIN_EMAIL). Single-address: USER_EMAIL may be a
    # comma-list, GITEA_USER_EMAIL is the single resolved address.
    GITEA_UE={user_email_q}
    if [ -n "$GITEA_UE" ] && [ "$GITEA_UE" != {admin_q} ]; then
        USER_CREATE_BODY=$(NEXUS_E="$GITEA_UE" NEXUS_P={pw_q} jq -n \\
            '{{email: env.NEXUS_E, password: env.NEXUS_P, super_admin: false, name: "User"}}')
        printf '%s' "$USER_CREATE_BODY" | curl -s --config "$WM_CFG" \\
            -X POST 'http://localhost:8200/api/users/create' \\
            --max-time 30 --data-binary @- >/dev/null 2>&1 || true
    fi
    # Step 3: create the `nexus` workspace. Capture HTTP body (rather
    # than just status code) because Windmill returns the workspace id
    # as a JSON-encoded string on success (e.g. \"nexus\").
    WS_BODY=$(jq -n '{{id: "nexus", name: "Nexus Stack"}}')
    WS_RESP=$(printf '%s' "$WS_BODY" | curl -s --config "$WM_CFG" \\
        -X POST 'http://localhost:8200/api/workspaces/create' \\
        --max-time 30 --data-binary @- 2>/dev/null || echo "")
    # Step 4 (always): rotate `admin@windmill.dev` away from
    # WINDMILL_SUPERADMIN_SECRET. Critical security step — without
    # this, anyone with the (long-lived) secret could log in as the
    # default admin. Generate a fresh random password every spin-up.
    # Capture the HTTP status — if the rotation fails (wrong secret,
    # API error), emit a stderr warning AND override the final hook
    # status to `failed`. Silencing this with `|| true` would have
    # left the default admin usable while the hook reported success.
    RANDOM_PW=$(openssl rand -base64 32)
    DEFPW_BODY=$(NEXUS_RP="$RANDOM_PW" jq -n '{{password: env.NEXUS_RP}}')
    DEFPW_STATUS=$(printf '%s' "$DEFPW_BODY" | curl -s --config "$WM_CFG" \\
        -o /dev/null -w '%{{http_code}}' \\
        -X POST 'http://localhost:8200/api/users/setpassword' \\
        --max-time 30 --data-binary @- 2>/dev/null || echo "000")
    unset RANDOM_PW
    # Explicit cleanup + trap reset. Orchestrator runs all hooks
    # in one shell with `set -u`; a lingering RETURN trap referencing
    # $WM_CFG would fire on a later hook's function-return and trip
    # set -u once the var is unset. Same pattern as LakeFS / OpenMetadata.
    rm -f "$WM_CFG"
    trap - RETURN
    # Final status combines workspace-create outcome AND the
    # security-critical default-admin rotation. Either failing →
    # hook reports failed.
    case "$DEFPW_STATUS" in
        200|204) ;;  # rotation succeeded
        *)
            echo "  ⚠ Windmill default-admin password rotation returned HTTP $DEFPW_STATUS — admin@windmill.dev may still be usable with the superadmin secret" >&2
            echo "RESULT hook=windmill status=failed"
            return 0
            ;;
    esac
    if [ "$WS_RESP" = '"nexus"' ] || echo "$WS_RESP" | grep -qi 'created'; then
        echo "RESULT hook=windmill status=configured"
    elif echo "$WS_RESP" | grep -qi 'already exists'; then
        echo "RESULT hook=windmill status=already-configured"
    else
        echo "  ⚠ Windmill workspace create response: ${{WS_RESP:-no response}}" >&2
        echo "RESULT hook=windmill status=failed"
    fi
}}
windmill_hook
"""


def render_sftpgo_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """SFTPGo: 6-stage admin bootstrap + R2 default-user creation.

    The biggest hook in the file (~250 LoC of rendered bash). Kept
    as a single rendered bash function rather than a Python hook
    because all the JSON construction happens remote-side via
    ``jq -n`` env-vars (no Python-side typed mutation needed, unlike
    Filestash). Single SSH round-trip.

    Stages:
    1. Two-stage readiness: ``/healthz`` 200 AND ``/api/v2/token``
       basic-auth login succeeds (admin SQLite row written). Bounded
       to 60 iterations of 2s = 120s. Without the second check we'd
       hit the token endpoint before admin-init finished writing.
    2. R2 credentials guard: SFTPGo runs but no default user is
       created if R2 creds are missing (operator must configure
       manually); reports ``skipped-not-ready`` with that detail.
    3. Mint admin JWT via ``/api/v2/token`` (basic-auth).
    4. Pre-create local FS scratch dirs inside the container
       (``/var/lib/sftpgo/users/nexus-default``,
       ``/var/lib/sftpgo/folders/cloudflare_r2``,
       ``/var/lib/sftpgo/folders/hetzner_s3``) with chown 1000:1000.
       Without this, first SFTP listing fails ``lstat: no such file``.
    5. POST ``/api/v2/folders`` for R2 (always) and Hetzner Object
       Storage (only if all 5 HZ_* fields present).
    6. POST ``/api/v2/users`` with the local-FS scratch home + the
       registered virtual folders attached.

    Idempotency contract (status mapping is driven by the FINAL
    user-POST HTTP code; folder POSTs run unconditionally before
    that and only emit a stderr warning on non-{201,409} responses):
    - User POST 201 → ``configured`` (fresh install, or wiped volume)
    - User POST 400 / 409 → ``already-configured`` (named-volume
      preserves the user row across in-place spin-ups)
    - User POST any other code → ``failed``
    - Healthz/token probe times out → ``skipped-not-ready``
    - R2 missing → ``skipped-not-ready`` (operator configures
      manually in admin UI)
    - JWT mint fails (admin login 401) → ``failed``

    Argv-safety: admin password / user password / R2-secret-key /
    Hetzner-secret-key all pass through base64 env-var → remote
    bash → ``printf builtin → base64 -d → env-var → jq -n env``.
    No secret bytes ever land in argv on the runner OR remote shell.
    """
    admin_password = config.sftpgo_admin_password or ""
    user_password = config.sftpgo_user_password or ""
    r2_bucket = config.r2_data_bucket or ""
    r2_endpoint = config.r2_data_endpoint or ""
    r2_access_key = config.r2_data_access_key or ""
    r2_secret_key = config.r2_data_secret_key or ""
    if not admin_password or not user_password:
        return 'echo "RESULT hook=sftpgo status=skipped-not-ready"\n'
    if not (r2_bucket and r2_endpoint and r2_access_key and r2_secret_key):
        # R2-missing case: log a stderr diagnostic so operators see
        # why no default user was created. SFTPGo admin still up via
        # SFTPGO_DEFAULT_ADMIN_* env vars; user-creation is the
        # part that needs R2 to map to a virtual folder.
        return (
            'echo "  ⚠ sftpgo: R2 datalake credentials missing — '
            'default user not created (configure manually in admin UI)" >&2\n'
            'echo "RESULT hook=sftpgo status=skipped-not-ready"\n'
        )
    # All four R2 fields populated → render the full bootstrap.
    # Hetzner is optional; rendered per-spin-up based on which fields
    # are populated. We embed *all* four base64'd values unconditionally
    # — the inner `[ -n ... ]` guards on the remote side decide whether
    # to actually call sftpgo_post_folder for the Hetzner backend.
    hz_bucket = config.hetzner_s3_bucket_general or ""
    hz_server = config.hetzner_s3_server or ""
    hz_region = config.hetzner_s3_region or ""
    hz_access_key = config.hetzner_s3_access_key or ""
    hz_secret_key = config.hetzner_s3_secret_key or ""
    return f"""
sftpgo_hook() {{
    # Two-stage readiness: /healthz must answer 200 (process is up,
    # HTTP server bound), THEN /api/v2/token basic-auth must succeed
    # (admin SQLite row written). Without the second check, we hit
    # /api/v2/token while admin-init is still in flight and get 401
    # → "admin login failed", and the run looks green.
    SFTPGO_ADMIN_B64=$(printf '%s' {shlex.quote(admin_password)} | base64 | tr -d '\\n')
    SFTPGO_USER_B64=$(printf '%s' {shlex.quote(user_password)} | base64 | tr -d '\\n')
    SFTPGO_R2_BUCKET_B64=$(printf '%s' {shlex.quote(r2_bucket)} | base64 | tr -d '\\n')
    SFTPGO_R2_ENDPOINT_B64=$(printf '%s' {shlex.quote(r2_endpoint)} | base64 | tr -d '\\n')
    SFTPGO_R2_AK_B64=$(printf '%s' {shlex.quote(r2_access_key)} | base64 | tr -d '\\n')
    SFTPGO_R2_SK_B64=$(printf '%s' {shlex.quote(r2_secret_key)} | base64 | tr -d '\\n')
    SFTPGO_HZ_BUCKET={shlex.quote(hz_bucket)}
    SFTPGO_HZ_SERVER={shlex.quote(hz_server)}
    SFTPGO_HZ_REGION={shlex.quote(hz_region)}
    SFTPGO_HZ_AK_B64=$(printf '%s' {shlex.quote(hz_access_key)} | base64 | tr -d '\\n')
    SFTPGO_HZ_SK_B64=$(printf '%s' {shlex.quote(hz_secret_key)} | base64 | tr -d '\\n')
    SFTPGO_HZ_BUCKET_B64=$(printf '%s' {shlex.quote(hz_bucket)} | base64 | tr -d '\\n')
    SFTPGO_HZ_ENDPOINT_B64=$(printf '%s' {shlex.quote(hz_server)} | base64 | tr -d '\\n')
    READY=false
    SECONDS=0
    while [ "$SECONDS" -lt 120 ]; do
        STATUS=$(curl -s -o /dev/null -w '%{{http_code}}' --connect-timeout 3 --max-time 5 'http://localhost:8090/healthz' 2>/dev/null || echo "000")
        if [ "$STATUS" = "200" ]; then
            # /healthz is up; now verify admin login (admin row exists in SQLite).
            ADMIN_PW=$(printf '%s' "$SFTPGO_ADMIN_B64" | base64 -d)
            CFG=$(mktemp); chmod 600 "$CFG"
            printf 'user = "nexus-sftpgo:%s"\\n' "$ADMIN_PW" > "$CFG"
            TOKEN_STATUS=$(curl -s -o /dev/null -w '%{{http_code}}' --config "$CFG" --connect-timeout 3 --max-time 5 'http://localhost:8090/api/v2/token' 2>/dev/null || echo "000")
            rm -f "$CFG"
            unset ADMIN_PW
            if [ "$TOKEN_STATUS" = "200" ]; then READY=true; break; fi
        fi
        sleep 2
    done
    if [ "$READY" != "true" ]; then
        echo "  ⚠ sftpgo not ready after 120s — skipping default-user creation" >&2
        echo "RESULT hook=sftpgo status=skipped-not-ready"
        return 0
    fi
    # Mint the admin JWT. Same argv-safety pattern as the readiness
    # probe (mode-600 curl --config tmpfile).
    ADMIN_PW=$(printf '%s' "$SFTPGO_ADMIN_B64" | base64 -d)
    LOGIN_CFG=$(mktemp); chmod 600 "$LOGIN_CFG"
    trap 'rm -f "$LOGIN_CFG"' RETURN
    printf 'user = "nexus-sftpgo:%s"\\n' "$ADMIN_PW" > "$LOGIN_CFG"
    TOKEN_RESP=$(curl -s --config "$LOGIN_CFG" --max-time 10 'http://localhost:8090/api/v2/token' 2>/dev/null || echo "")
    rm -f "$LOGIN_CFG"
    trap - RETURN
    unset ADMIN_PW
    SFTPGO_TOKEN=$(printf '%s' "$TOKEN_RESP" | jq -r '.access_token // empty' 2>/dev/null)
    if [ -z "$SFTPGO_TOKEN" ]; then
        echo "  ⚠ sftpgo admin login failed — default user not created" >&2
        echo "RESULT hook=sftpgo status=failed"
        return 0
    fi
    SFTPGO_TOKEN_B64=$(printf '%s' "$SFTPGO_TOKEN" | base64 | tr -d '\\n')
    unset SFTPGO_TOKEN
    # Pre-create the local-FS scratch dirs that home_dir + each
    # folder's mapped_path expect. Without these, the first SFTP
    # listing returns "Failed to get directory listing" with no hint
    # that the dirs are missing. uid 1000 is SFTPGo's runtime user.
    if ! docker exec --user 0 sftpgo sh -c \\
        'mkdir -p /var/lib/sftpgo/users/nexus-default /var/lib/sftpgo/folders/cloudflare_r2 /var/lib/sftpgo/folders/hetzner_s3 \\
         && chown -R 1000:1000 /var/lib/sftpgo/users /var/lib/sftpgo/folders' >/dev/null 2>&1; then
        echo "  ⚠ sftpgo dir-prep (mkdir/chown) failed — first login may report 'Failed to get directory listing'" >&2
    fi
    # Helper: POST a virtual folder. Returns the HTTP status code
    # via stdout (caller captures with $()). All secret values reach
    # the remote env via base64 → printf builtin → base64 -d → env
    # var. jq -n reads the env vars (NOT --arg argv).
    sftpgo_post_folder() {{
        local _name="$1" _bucket_b64="$2" _endpoint_b64="$3" _region="$4" _ak_b64="$5" _sk_b64="$6"
        TOKEN_LOCAL=$(printf '%s' "$SFTPGO_TOKEN_B64" | base64 -d)
        BUCKET_LOCAL=$(printf '%s' "$_bucket_b64" | base64 -d)
        ENDPOINT_LOCAL=$(printf '%s' "$_endpoint_b64" | base64 -d)
        AK_LOCAL=$(printf '%s' "$_ak_b64" | base64 -d)
        SK_LOCAL=$(printf '%s' "$_sk_b64" | base64 -d)
        FCFG=$(mktemp); chmod 600 "$FCFG"
        printf 'header = "Authorization: Bearer %s"\\nheader = "Content-Type: application/json"\\n' "$TOKEN_LOCAL" > "$FCFG"
        FOLDER_STATUS=$(NAME="$_name" BUCKET="$BUCKET_LOCAL" ENDPOINT="$ENDPOINT_LOCAL" REGION="$_region" AK="$AK_LOCAL" SK="$SK_LOCAL" jq -n \\
            '{{name: env.NAME,
              mapped_path: ("/var/lib/sftpgo/folders/" + env.NAME),
              filesystem: {{provider: 1, s3config: {{bucket: env.BUCKET, endpoint: env.ENDPOINT, region: env.REGION, access_key: env.AK, access_secret: {{payload: env.SK, status: "Plain"}}, key_prefix: "", force_path_style: true}}}}}}' \\
            | curl -s -o /dev/null -w '%{{http_code}}' \\
              -X POST 'http://localhost:8090/api/v2/folders' \\
              --config "$FCFG" \\
              --data-binary @- 2>/dev/null || echo "000")
        rm -f "$FCFG"
        unset TOKEN_LOCAL BUCKET_LOCAL ENDPOINT_LOCAL AK_LOCAL SK_LOCAL
        printf '%s' "$FOLDER_STATUS"
    }}
    # R2 folder is always registered (we already validated R2 creds above).
    R2_STATUS=$(sftpgo_post_folder \\
        "cloudflare_r2" "$SFTPGO_R2_BUCKET_B64" "$SFTPGO_R2_ENDPOINT_B64" "auto" "$SFTPGO_R2_AK_B64" "$SFTPGO_R2_SK_B64")
    case "$R2_STATUS" in
        201|409) ;;  # created or already-exists are both fine
        *) echo "  ⚠ sftpgo R2 folder POST returned HTTP $R2_STATUS" >&2 ;;
    esac
    # Hetzner folder is optional — only if all 5 HZ fields are present
    # (bucket + server + region + access_key + secret_key). We check
    # the base64'd-form lengths because that's what's available in
    # this scope; the access/secret base64 strings are non-empty iff
    # their plaintext is non-empty.
    VFOLDERS_JSON='[{{"name":"cloudflare_r2","virtual_path":"/cloudflare_r2","quota_size":-1,"quota_files":-1}}]'
    if [ -n "$SFTPGO_HZ_BUCKET" ] && [ -n "$SFTPGO_HZ_SERVER" ] && [ -n "$SFTPGO_HZ_REGION" ] \\
       && [ -n "$SFTPGO_HZ_AK_B64" ] && [ -n "$SFTPGO_HZ_SK_B64" ]; then
        HZ_STATUS=$(sftpgo_post_folder \\
            "hetzner_s3" "$SFTPGO_HZ_BUCKET_B64" "$SFTPGO_HZ_ENDPOINT_B64" "$SFTPGO_HZ_REGION" "$SFTPGO_HZ_AK_B64" "$SFTPGO_HZ_SK_B64")
        case "$HZ_STATUS" in
            201|409)
                VFOLDERS_JSON='[{{"name":"cloudflare_r2","virtual_path":"/cloudflare_r2","quota_size":-1,"quota_files":-1}},{{"name":"hetzner_s3","virtual_path":"/hetzner_s3","quota_size":-1,"quota_files":-1}}]'
                ;;
            *) echo "  ⚠ sftpgo Hetzner folder POST returned HTTP $HZ_STATUS" >&2 ;;
        esac
    fi
    # Helper: POST the user with home_dir + virtual folders.
    TOKEN_LOCAL=$(printf '%s' "$SFTPGO_TOKEN_B64" | base64 -d)
    USER_PW=$(printf '%s' "$SFTPGO_USER_B64" | base64 -d)
    UCFG=$(mktemp); chmod 600 "$UCFG"
    trap 'rm -f "$UCFG"' RETURN
    printf 'header = "Authorization: Bearer %s"\\nheader = "Content-Type: application/json"\\n' "$TOKEN_LOCAL" > "$UCFG"
    USER_STATUS=$(VFOLDERS="$VFOLDERS_JSON" PASSWORD="$USER_PW" jq -n \\
        '{{username: "nexus-default",
          password: env.PASSWORD,
          home_dir: "/var/lib/sftpgo/users/nexus-default",
          permissions: {{"/": ["*"], "/cloudflare_r2": ["*"], "/hetzner_s3": ["*"]}},
          status: 1,
          filesystem: {{provider: 0}},
          virtual_folders: (env.VFOLDERS | fromjson)}}' \\
        | curl -s -o /dev/null -w '%{{http_code}}' \\
          -X POST 'http://localhost:8090/api/v2/users' \\
          --config "$UCFG" \\
          --data-binary @- 2>/dev/null || echo "000")
    rm -f "$UCFG"
    trap - RETURN
    unset TOKEN_LOCAL USER_PW SFTPGO_TOKEN_B64 SFTPGO_ADMIN_B64 SFTPGO_USER_B64
    case "$USER_STATUS" in
        201)     echo "RESULT hook=sftpgo status=configured" ;;
        400|409) echo "RESULT hook=sftpgo status=already-configured" ;;
        *)       echo "  ⚠ sftpgo user POST returned HTTP $USER_STATUS — configure manually" >&2
                 echo "RESULT hook=sftpgo status=failed" ;;
    esac
}}
sftpgo_hook
"""


def render_pg_ducklake_hook(config: NexusConfig, env: BootstrapEnv) -> str:
    """pg-ducklake: re-apply ``00-ducklake-bootstrap.sql`` on every
    spin-up to handle credential rotation.

    The bootstrap SQL is written to ``stacks/pg-ducklake/init/`` by
    service-env (PR #527), and Postgres'
    docker-entrypoint-initdb.d only executes scripts on an EMPTY data
    dir — so on persistent-volume deploys (named volume preserved
    across spin-ups), the freshly-rotated credentials in the SQL
    never make it into the running Postgres without this re-apply.

    Two stages:
    1. Wait for ``pg_isready`` — 30s wall-clock bound (``$SECONDS``-gated
       loop, ``sleep 2`` per iteration, so up to ~15 probes plus the
       partial second the loop entered on).
    2. Exec ``psql -f /docker-entrypoint-initdb.d/00-ducklake-bootstrap.sql``
       inside the container. Idempotent — the SQL itself uses
       ``DO $$ ... drop_secret EXCEPTION WHEN OTHERS THEN NULL ... $$``
       so re-runs against an already-bootstrapped DB are safe.

    Idempotency contract:
    - pg_isready times out → ``skipped-not-ready``
    - psql exec succeeds → ``configured``
    - psql exec fails → ``failed`` (legacy bash treated this as a
      yellow warning ``may already be applied``; we surface as failed
      so the operator can inspect, since a real psql failure means
      either the SQL has a syntax error OR the credentials in the
      SQL file don't match what Postgres expects)
    """
    del config, env
    return """
pg_ducklake_hook() {
    READY=false
    SECONDS=0
    while [ "$SECONDS" -lt 30 ]; do
        if docker exec pg-ducklake pg_isready -U nexus-pgducklake -d ducklake \\
                >/dev/null 2>&1; then
            READY=true
            break
        fi
        sleep 2
    done
    if [ "$READY" != "true" ]; then
        echo "  ⚠ pg_ducklake not ready after 30s — skipping bootstrap re-apply" >&2
        echo "RESULT hook=pg-ducklake status=skipped-not-ready"
        return 0
    fi
    if docker exec pg-ducklake psql -U nexus-pgducklake -d ducklake \\
            -f /docker-entrypoint-initdb.d/00-ducklake-bootstrap.sql \\
            >/dev/null 2>&1; then
        echo "RESULT hook=pg-ducklake status=configured"
    else
        echo "  ⚠ pg_ducklake bootstrap SQL re-apply failed — re-run manually to see the actual psql error:" >&2
        echo "    ssh nexus 'docker exec pg-ducklake psql -U nexus-pgducklake -d ducklake -f /docker-entrypoint-initdb.d/00-ducklake-bootstrap.sql'" >&2
        echo "RESULT hook=pg-ducklake status=failed"
    fi
}
pg_ducklake_hook
"""


# ---------------------------------------------------------------------------
# Filestash (Python-side file mutation).
#
# Filestash stores its admin-side state in a JSON file inside the
# container at ``/app/data/state/config/config.json``. Three things
# need fixing post-startup:
# 1. ``general.host`` defaults to the public URL with ``https://``
#    prefix — but Filestash treats that as a literal protocol marker
#    and breaks signed URLs unless we strip the prefix.
# 2. ``general.force_ssl`` defaults to ``null``/``false`` — must be
#    ``true`` to honour the Cloudflare-Access-only access pattern.
# 3. S3 backends (R2 / Hetzner / external) need to be injected as
#    pre-configured connections so admins don't need to re-enter
#    credentials in Filestash's web UI on first login.
#
# The hook pulls the JSON, mutates with typed Python dict transforms,
# and pushes back. Two ssh round-trips, pure mutation logic, fully
# testable without any I/O.
# ---------------------------------------------------------------------------


_FILESTASH_CONFIG_PATH = "/app/data/state/config/config.json"

# Marker tokens emitted by the pull-stage script. Both are
# distinct prefixes so no JSON content can collide with them
# (JSON can't start with whitespace-followed-by-uppercase-RESULT).
_FILESTASH_PULL_OK = "RESULT_PULL_OK"
_FILESTASH_PULL_NOT_READY = "RESULT_PULL_NOT_READY"
_FILESTASH_PULL_NO_CONFIG = "RESULT_PULL_NO_CONFIG"


def _filestash_has_r2(config: NexusConfig) -> bool:
    """All four R2 fields populated."""
    return bool(
        config.r2_data_endpoint
        and config.r2_data_access_key
        and config.r2_data_secret_key
        and config.r2_data_bucket,
    )


def _filestash_has_hetzner(config: NexusConfig) -> bool:
    return bool(
        config.hetzner_s3_server
        and config.hetzner_s3_access_key
        and config.hetzner_s3_secret_key
        and config.hetzner_s3_bucket_general,
    )


def _filestash_has_external(config: NexusConfig) -> bool:
    return bool(
        config.external_s3_endpoint
        and config.external_s3_access_key
        and config.external_s3_secret_key
        and config.external_s3_bucket,
    )


def _filestash_s3_connections(config: NexusConfig) -> list[dict[str, str]]:
    """Build the ``connections`` array.

    Order: R2 → Hetzner → External. The first one becomes the
    primary backend (see :func:`_filestash_primary_backend`).
    """
    out: list[dict[str, str]] = []
    if _filestash_has_r2(config):
        out.append({"type": "s3", "label": "R2 Datalake"})
    if _filestash_has_hetzner(config):
        out.append({"type": "s3", "label": "Hetzner Storage"})
    if _filestash_has_external(config):
        out.append({"type": "s3", "label": config.external_s3_label or "External Storage"})
    return out


def _filestash_s3_params(config: NexusConfig) -> dict[str, dict[str, str]]:
    """Build the per-backend params map keyed by label.

    Endpoints are normalised: ``HETZNER_S3_SERVER`` is stored without
    a scheme but Filestash needs a full URL, so we prefix
    ``https://``. R2 + external endpoints already include scheme.
    """
    out: dict[str, dict[str, str]] = {}
    if _filestash_has_r2(config):
        out["R2 Datalake"] = {
            "type": "s3",
            "access_key_id": config.r2_data_access_key or "",
            "secret_access_key": config.r2_data_secret_key or "",
            "endpoint": config.r2_data_endpoint or "",
            "region": "auto",
            "path": f"/{config.r2_data_bucket}/",
        }
    if _filestash_has_hetzner(config):
        out["Hetzner Storage"] = {
            "type": "s3",
            "access_key_id": config.hetzner_s3_access_key or "",
            "secret_access_key": config.hetzner_s3_secret_key or "",
            "endpoint": f"https://{config.hetzner_s3_server}",
            "region": config.hetzner_s3_region or "",
            "path": f"/{config.hetzner_s3_bucket_general}/",
        }
    if _filestash_has_external(config):
        label = config.external_s3_label or "External Storage"
        out[label] = {
            "type": "s3",
            "access_key_id": config.external_s3_access_key or "",
            "secret_access_key": config.external_s3_secret_key or "",
            "endpoint": config.external_s3_endpoint or "",
            "region": config.external_s3_region or "auto",
            "path": f"/{config.external_s3_bucket}/",
        }
    return out


def _filestash_primary_backend(config: NexusConfig) -> str | None:
    """First populated backend label, or None if no S3 backend is set up."""
    if _filestash_has_r2(config):
        return "R2 Datalake"
    if _filestash_has_hetzner(config):
        return "Hetzner Storage"
    if _filestash_has_external(config):
        return config.external_s3_label or "External Storage"
    return None


def _filestash_mutate_config(
    existing: dict[str, Any],
    *,
    config: NexusConfig,
) -> dict[str, Any]:
    """Apply the three transforms to a parsed config.json dict.

    Returns a NEW dict (does not mutate ``existing``) so callers can
    snapshot pre/post for diffing. The all-or-nothing transform is
    stricter than an in-place sed/jq chain, which could leave
    half-written state on a partial failure.
    """
    out: dict[str, Any] = json.loads(json.dumps(existing))  # deep copy

    general = out.setdefault("general", {})
    if isinstance(general, dict):
        host = general.get("host")
        if isinstance(host, str) and host.startswith("https://"):
            general["host"] = host[len("https://") :]
        general["force_ssl"] = True

    primary = _filestash_primary_backend(config)
    if primary is not None:
        out["connections"] = _filestash_s3_connections(config)
        params = _filestash_s3_params(config)
        # Filestash wants the middleware param values as JSON STRINGS,
        # not nested objects. This is the source of one of the original
        # PR's bug-classes — a missing tojson would parse but break the
        # admin UI on render. Pin via test snapshots.
        middleware = out.setdefault("middleware", {})
        if isinstance(middleware, dict):
            middleware["identity_provider"] = {
                "type": "passthrough",
                "params": json.dumps({"strategy": "direct"}),
            }
            middleware["attribute_mapping"] = {
                "related_backend": primary,
                "params": json.dumps(params),
            }

    return out


def _render_filestash_pull_script() -> str:
    """Stage 1: wait for filestash → wait for config.json → pull as base64.

    Emits exactly one of three marker lines so the Python-side parser
    knows what happened:
    - ``RESULT_PULL_NOT_READY`` — service never came up in 45s
    - ``RESULT_PULL_NO_CONFIG`` — service up but config.json absent
    - ``RESULT_PULL_OK <base64>`` — config.json captured

    The base64-encoding step keeps any binary bytes / newlines /
    quotes in config.json from breaking the line-based wire format
    on stdout.
    """
    return f"""
set -u
READY=false
SECONDS=0
while [ "$SECONDS" -lt 45 ]; do
    if curl -sf --connect-timeout 2 --max-time 5 \\
        'http://localhost:8334/healthz' >/dev/null 2>&1; then
        READY=true; break
    fi
    sleep 3
done
if [ "$READY" != "true" ]; then
    echo "  ⚠ filestash not ready after 45s — skipping setup" >&2
    echo "{_FILESTASH_PULL_NOT_READY}"
    exit 0
fi

CONFIG_PRESENT=false
SECONDS=0
while [ "$SECONDS" -lt 30 ]; do
    if docker exec filestash test -f {shlex.quote(_FILESTASH_CONFIG_PATH)} \\
        >/dev/null 2>&1; then
        CONFIG_PRESENT=true; break
    fi
    sleep 3
done
if [ "$CONFIG_PRESENT" != "true" ]; then
    echo "  ⚠ filestash config.json absent after 30s — skipping" >&2
    echo "{_FILESTASH_PULL_NO_CONFIG}"
    exit 0
fi

# base64 with -w0 (no-wrap) isn't on macOS / Alpine; pipe through `tr` instead.
CONFIG_B64=$(docker exec filestash cat {shlex.quote(_FILESTASH_CONFIG_PATH)} \\
    2>/dev/null | base64 | tr -d '\\n' || echo "")
if [ -z "$CONFIG_B64" ]; then
    echo "  ⚠ filestash config.json empty / unreadable" >&2
    echo "{_FILESTASH_PULL_NO_CONFIG}"
    exit 0
fi
echo "{_FILESTASH_PULL_OK} $CONFIG_B64"
"""


def _render_filestash_push_script(*, new_config_b64: str) -> str:
    """Stage 2: push base64'd config → restart → wait for /healthz.

    R4 — keep the base64 (and therefore the encoded S3 secret material)
    OUT of argv on the remote host. We feed the base64 string into
    ``base64 -d`` via heredoc on stdin (``cat << 'NEXUS_FS_PUSH_EOF'
    | base64 -d | docker exec -i …``), NOT as a positional argument to
    ``printf``. Heredoc bodies are written to the child's stdin by the
    bash shell directly; no fork in the pipeline carries the secret in
    argv visible to ``ps -ef`` on the nexus host.

    The single-quoted heredoc delimiter (``'NEXUS_FS_PUSH_EOF'``)
    disables variable expansion inside, so any ``$``-shaped bytes that
    coincidentally appear in base64 are not interpreted. The base64
    alphabet is ``[A-Za-z0-9+/=]`` — no underscores, no E-O-F sequence
    on its own line is reachable from a continuous (newline-stripped)
    base64 string — but we still defensively assert the delimiter
    doesn't appear inside the payload as a defence-in-depth check.

    pipefail is ON: a failure anywhere in the pipeline (missing
    ``base64`` binary, corrupt input, ``docker exec -i`` rejecting
    stdin) propagates to the if-branch's exit status. Without it the
    pipeline's status is just the last command's, which would mask a
    silent empty-write into config.json.

    Emits ``RESULT hook=filestash status=configured`` on success or
    ``status=failed`` if either the write or the post-restart
    healthcheck fails.
    """
    # Defensive guard: base64 alphabet check. If a future caller
    # supplies non-base64 content we want to fail loudly here, not
    # ship a broken script that the operator has to debug remotely.
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", new_config_b64):
        raise ValueError("new_config_b64 contains characters outside the base64 alphabet")
    # Defence in depth — unreachable as long as the base64 alphabet
    # check above stands (b64 alphabet excludes underscores, the
    # delimiter contains them). Kept as a tripwire for any future
    # widening of the accepted alphabet that would invalidate the
    # collision-impossibility argument.
    delimiter = "NEXUS_FS_PUSH_EOF"
    if delimiter in new_config_b64:  # pragma: no cover
        raise ValueError(f"heredoc delimiter {delimiter!r} appears inside the payload")

    return f"""
set -u
set -o pipefail  # ANY pipeline-stage failure → non-zero exit, NOT just the last
cat <<'{delimiter}' 2>/dev/null | base64 -d 2>/dev/null | \\
    docker exec -i filestash sh -c 'cat > {shlex.quote(_FILESTASH_CONFIG_PATH)}' \\
    2>/dev/null
{new_config_b64}
{delimiter}
WRITE_RC=$?
if [ "$WRITE_RC" -ne 0 ]; then
    echo "  ✗ filestash config write failed (rc=$WRITE_RC)" >&2
    echo "RESULT hook=filestash status=failed"
    exit 0
fi

if ! docker restart filestash >/dev/null 2>&1; then
    echo "  ✗ filestash restart failed" >&2
    echo "RESULT hook=filestash status=failed"
    exit 0
fi

# Wait for /healthz after restart. Bounded at 30s — restart is
# typically <10s on cax31; longer than that means something is wrong.
RESTARTED=false
SECONDS=0
while [ "$SECONDS" -lt 30 ]; do
    if curl -sf --connect-timeout 2 --max-time 5 \\
        'http://localhost:8334/healthz' >/dev/null 2>&1; then
        RESTARTED=true; break
    fi
    sleep 2
done
if [ "$RESTARTED" != "true" ]; then
    echo "  ✗ filestash not ready 30s after restart" >&2
    echo "RESULT hook=filestash status=failed"
    exit 0
fi
echo "RESULT hook=filestash status=configured"
"""


def _parse_filestash_pull_output(stdout: str) -> dict[str, Any] | None | Literal["not-ready"]:
    """Decode the pull-stage marker line into one of three states.

    Return value:
    - ``"not-ready"`` — readiness probe didn't pass in time, OR
      config.json is absent (treated identically as ``skipped-not-ready``).
    - ``None`` — pull marker line malformed (parse error, treat as failure).
    - ``dict`` — successfully decoded config.json content.
    """
    for line in stdout.splitlines():
        if line in (_FILESTASH_PULL_NOT_READY, _FILESTASH_PULL_NO_CONFIG):
            return "not-ready"
        if line.startswith(_FILESTASH_PULL_OK + " "):
            b64 = line[len(_FILESTASH_PULL_OK) + 1 :].strip()
            try:
                raw = base64.b64decode(b64, validate=True)
                parsed = json.loads(raw.decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                return None
            if not isinstance(parsed, dict):
                return None
            return parsed
    return None


_FILESTASH_MARKER_PREFIXES = (
    _FILESTASH_PULL_OK,
    _FILESTASH_PULL_NOT_READY,
    _FILESTASH_PULL_NO_CONFIG,
    "RESULT hook=filestash",
)


def _forward_non_marker_stderr(stdout: str) -> None:
    """Forward remote diagnostic lines (``  ⚠ …``, ``  ✗ …``) to local stderr.

    Mirrors the bash-hook orchestrator's pattern (Modul-1.2 Round-4):
    the rendered script writes warnings to its stderr, ``merge_stderr=True``
    folds them into stdout, we strip the wire-format marker lines and
    forward the rest so operators see WHY a setup failed instead of
    just ``status=failed``.
    """
    for line in stdout.splitlines():
        if any(line.startswith(p) for p in _FILESTASH_MARKER_PREFIXES):
            continue
        sys.stderr.write(line + "\n")


def configure_filestash(
    config: NexusConfig,
    *,
    script_runner: ScriptRunner | None = None,
) -> HookResult:
    """End-to-end Filestash admin setup.

    Two SSH round-trips, with Python-side JSON mutation between them.
    Failure at any stage maps to ``status=failed`` (NOT ``not-ready``)
    EXCEPT for the explicit "not ready" / "no config" markers from
    stage 1 which are pre-setup states, not failures.

    Remote diagnostic lines (``  ⚠ …``, ``  ✗ …``) from both stages
    are forwarded to local stderr so failures are debuggable from the
    deploy log, not just visible as ``status=failed``.

    ``script_runner`` defaults to :func:`_remote.ssh_run_script` so
    tests can substitute a mock; the production caller
    (``run_admin_setups``) passes the same callable through.
    """
    runner = script_runner or _remote.ssh_run_script

    # Stage 1: pull
    out1 = runner(_render_filestash_pull_script())
    _forward_non_marker_stderr(out1.stdout)
    pulled = _parse_filestash_pull_output(out1.stdout)
    if pulled == "not-ready":
        return HookResult(name="filestash", status="skipped-not-ready")
    if pulled is None:
        sys.stderr.write("  ✗ filestash pull stage produced no parseable result\n")
        return HookResult(name="filestash", status="failed")

    # Stage 2: mutate locally
    new_config = _filestash_mutate_config(pulled, config=config)
    new_b64 = base64.b64encode(json.dumps(new_config).encode("utf-8")).decode("ascii")

    # Stage 3: push + restart + wait
    out2 = runner(_render_filestash_push_script(new_config_b64=new_b64))
    _forward_non_marker_stderr(out2.stdout)
    if "RESULT hook=filestash status=configured" in out2.stdout:
        return HookResult(name="filestash", status="configured")
    return HookResult(name="filestash", status="failed")


# ScriptRunner forward reference for type hints above (defined in
# the orchestration section below; the runtime alias is set there).
ScriptRunner = Callable[[str], "subprocess.CompletedProcess[str]"]


# ---------------------------------------------------------------------------
# Hook registry — maps service name → renderer function. NOT the
# execution-order source of truth — render_remote_script iterates the
# caller-provided ``enabled_hooks`` list, so the operator (or the CLI
# parser) controls the order. The dict insertion order here is only a
# debugging convenience (``supported_hooks()`` returns it).
# ---------------------------------------------------------------------------

HookRenderer = Callable[[NexusConfig, BootstrapEnv], str]

_HOOK_REGISTRY: dict[str, HookRenderer] = {
    # REST first-init hooks
    "portainer": render_portainer_hook,
    "n8n": render_n8n_hook,
    "metabase": render_metabase_hook,
    "lakefs": render_lakefs_hook,
    "openmetadata": render_openmetadata_hook,
    # docker-exec CLI hooks
    "redpanda": render_redpanda_hook,
    "superset": render_superset_hook,
    # Remaining REST + docker-exec admin-setups
    "uptime-kuma": render_uptime_kuma_hook,
    "garage": render_garage_hook,
    "wikijs": render_wikijs_hook,
    "dify": render_dify_hook,
    "windmill": render_windmill_hook,
    "sftpgo": render_sftpgo_hook,
    "hedgedoc": render_hedgedoc_hook,
    # pg-ducklake bootstrap re-apply (handles cred rotation on
    # persistent-volume deploys where the entrypoint-initdb scripts
    # only ran on first init).
    "pg-ducklake": render_pg_ducklake_hook,
}


# Python-side hooks — separate registry because their orchestration
# shape differs from bash renderers: they need to issue multiple SSH
# round-trips with Python-side mutation in between.
PythonHookFn = Callable[[NexusConfig, ScriptRunner], HookResult]


def _filestash_python_hook(config: NexusConfig, runner: ScriptRunner) -> HookResult:
    """Adapter: pin the (config, runner) signature for the registry."""
    return configure_filestash(config, script_runner=runner)


_PYTHON_HOOK_REGISTRY: dict[str, PythonHookFn] = {
    "filestash": _filestash_python_hook,
}

# Single-source-of-truth invariant: a name lives in exactly one registry.
# A name in both would silently double-dispatch in run_admin_setups (one
# bash run + one python run). Checked at import time so any future
# refactor that violates the invariant fails the test suite, not
# production. If you genuinely need cross-registry routing, route via a
# wrapper function that lives in only one registry.
if _overlap := set(_HOOK_REGISTRY) & set(_PYTHON_HOOK_REGISTRY):
    raise RuntimeError(f"hook names in both registries: {sorted(_overlap)}")


def supported_hooks() -> tuple[str, ...]:
    """All service names with admin-setup hooks (bash + python families).

    Order: bash-registry insertion order, then python-registry insertion
    order. ``dict.fromkeys`` preserves order while de-duplicating —
    redundant given the import-time invariant above, but defence in depth
    if a future refactor weakens that assertion.
    """
    return tuple(dict.fromkeys((*_HOOK_REGISTRY, *_PYTHON_HOOK_REGISTRY)))


# ---------------------------------------------------------------------------
# Bash rendering: combine per-hook renderers into one server-side script.
# ---------------------------------------------------------------------------


def render_remote_script(
    *,
    config: NexusConfig,
    env: BootstrapEnv,
    enabled_hooks: list[str],
) -> str:
    """Render the combined bash script for all enabled admin-setup hooks.

    Each hook is rendered as a self-contained bash function that emits
    exactly one ``RESULT hook=<name> status=<...>`` line. A failure in
    one hook does NOT propagate (each hook function uses ``return 0``
    on its bail-out paths and the orchestrator script has no
    ``set -e`` in the outer scope).

    Hook execution is sequential (NOT parallel). **Order matches the
    caller-provided ``enabled_hooks`` argument** — NOT
    ``_HOOK_REGISTRY`` insertion order. Callers (the CLI in
    ``__main__._services_configure``) determine the order; the
    registry is only a name → renderer map.

    KNOWN-LIMITATION: hooks run sequentially. Several of them
    (Portainer, LakeFS, OpenMetadata) are independent and could run
    in parallel; sequential wall-time can reach ~``sum(per-hook
    timeouts)`` — about 7 minutes worst case for the currently-shipped
    hooks. A future paramiko + asyncio refactor would naturally
    restore parallelism via ``asyncio.gather``. Until then we accept
    the increased wall-time in exchange for predictable, easy-to-grep
    linear logs.
    """
    parts: list[str] = ["set -u  # -e omitted: hook failures must not abort the orchestrator\n"]
    for name in enabled_hooks:
        # Defence in depth: drop any hook name with shell-meta chars
        # before interpolating into the rendered bash. Logged to local
        # stderr (NOT into the rendered script — we cannot trust the
        # value enough to embed it). Production callers should never
        # hit this path; the orchestrator's $ENABLED_SERVICES is
        # alphanumeric + dash by tofu-output construction.
        if not _VALID_HOOK_NAME_RE.fullmatch(name):
            sys.stderr.write(f"  ⚠ Dropped hook with unsafe name: {name!r}\n")
            continue
        renderer = _HOOK_REGISTRY.get(name)
        if renderer is None:
            # Unknown but well-formed hook → emit a skip line so the
            # operator can see the name in the workflow log.
            parts.append(f'echo "RESULT hook={name} status=skipped-not-ready"\n')
            continue
        parts.append(renderer(config, env))
    return "".join(parts)


def parse_results(stdout: str) -> tuple[HookResult, ...]:
    """Extract one HookResult per ``RESULT hook=…`` line in remote stdout.

    Both regex groups (``name``, ``status``) are required by
    ``_RESULT_LINE_RE`` — ``finditer`` only yields matches where
    every group captured something — so ``m.group(name)`` is
    statically guaranteed non-None. The ``cast`` pins the status
    string to its Literal-typed alias for the typed dataclass
    constructor (replaces the previous ``# type: ignore[arg-type]``
    suppression).
    """
    return tuple(
        HookResult(name=m.group("name"), status=cast("HookStatus", m.group("status")))
        for m in _RESULT_LINE_RE.finditer(stdout)
    )


# ---------------------------------------------------------------------------
# End-to-end orchestration
# ---------------------------------------------------------------------------


def run_admin_setups(
    config: NexusConfig,
    env: BootstrapEnv,
    enabled: list[str],
    *,
    script_runner: ScriptRunner | None = None,
) -> SetupResult:
    """Render → exec → parse, dispatching to bash or python hook family.

    ``enabled`` is the full enabled-services list (the same shape
    used everywhere else in the package). Hooks are filtered to those
    that have an entry in either ``_HOOK_REGISTRY`` (bash-rendered)
    or ``_PYTHON_HOOK_REGISTRY`` (Python-side, e.g. Filestash);
    unknown services are dropped silently (they belong to other
    modules: seeder, compose_runner, future hooks).

    Returns :class:`SetupResult` with one :class:`HookResult` per
    enabled+supported hook. Bash hooks that report no RESULT line
    (e.g. a server-side ssh failure mid-script) are reflected as
    ``status=failed`` for accountability.
    """
    bash_hooks = [s for s in enabled if s in _HOOK_REGISTRY]
    py_hooks = [s for s in enabled if s in _PYTHON_HOOK_REGISTRY]
    if not bash_hooks and not py_hooks:
        return SetupResult(hooks=())

    runner = script_runner or (lambda s: _remote.ssh_run_script(s))

    bash_results: tuple[HookResult, ...] = ()
    if bash_hooks:
        script = render_remote_script(config=config, env=env, enabled_hooks=bash_hooks)
        completed = runner(script)
        # Forward remote ⚠ warnings + "  ✓/✗" lines to local stderr
        # (Modul-1.2 Round-4 pattern); strip the RESULT wire-format lines.
        for line in completed.stdout.splitlines():
            if not line.startswith("RESULT hook="):
                sys.stderr.write(line + "\n")
        parsed = parse_results(completed.stdout)
        parsed_names = {r.name for r in parsed}
        # Any enabled bash-hook with no RESULT line counts as failed.
        missing = tuple(
            HookResult(name=h, status="failed") for h in bash_hooks if h not in parsed_names
        )
        bash_results = tuple(parsed) + missing

    py_results: list[HookResult] = []
    for name in py_hooks:
        hook_fn = _PYTHON_HOOK_REGISTRY[name]
        py_results.append(hook_fn(config, runner))

    return SetupResult(hooks=bash_results + tuple(py_results))


# Re-export the keys for tests that want to discover them programmatically.
__all__ = [
    "HookResult",
    "HookStatus",
    "SetupResult",
    "configure_filestash",
    "parse_results",
    "render_lakefs_hook",
    "render_metabase_hook",
    "render_n8n_hook",
    "render_openmetadata_hook",
    "render_portainer_hook",
    "render_redpanda_hook",
    "render_remote_script",
    "render_superset_hook",
    "run_admin_setups",
    "supported_hooks",
]
