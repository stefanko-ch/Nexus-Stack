#!/bin/sh
# =============================================================================
# openbao-init: initialise OpenBao once, then give it a named admin login
# =============================================================================
# On the first start the server is uninitialised. This script initialises it
# (the static seal unseals it automatically), and with the one-time root
# token:
#   - enables userpass auth and creates nexus-admin with OPENBAO_ADMIN_PASSWORD
#     and a policy granting everything,
#   - mounts a KV v2 engine at secret/,
#   - revokes the root token, so no all-powerful token outlives this script.
# The recovery key from the init is discarded; nexus-admin is the way in.
#
# On later starts the server is already initialised, and the script only
# checks that nexus-admin still logs in.
#
# Secrets never reach an argument list: `bao write ... password=-` reads the
# value from stdin, and printf is a shell builtin.
# =============================================================================
set -eu
export BAO_ADDR=http://openbao:8200

fail() { echo "openbao-init: ERROR: $*" >&2; exit 1; }

# `bao status` exits 0 when unsealed, 2 when sealed or uninitialised, 1 on error.
i=0
until bao status >/dev/null 2>&1 || [ $? -eq 2 ]; do
  i=$((i + 1)); [ "$i" -ge 60 ] && fail "OpenBao did not answer within 120 s."
  sleep 2
done

# Logs in as nexus-admin and revokes the token again: the login is only a
# check, and a token left behind would stay valid for its whole TTL.
admin_login_works() {
  t=$(printf '%s' "$OPENBAO_ADMIN_PASSWORD" \
    | bao write -field=token auth/userpass/login/nexus-admin password=- 2>/dev/null) || return 1
  [ -n "$t" ] || return 1
  BAO_TOKEN=$t bao token revoke -self >/dev/null 2>&1 || true
  return 0
}

if bao status -format=json 2>/dev/null | grep -q '"initialized": true'; then
  if admin_login_works; then
    echo "openbao-init: already initialised; nexus-admin logs in."
  else
    # This step cannot tell which: the admin changed the password in
    # OpenBao, or an earlier run stopped between init and creating the
    # user, which only a fresh openbao-data volume repairs.
    echo "openbao-init: WARNING: already initialised, but the generated nexus-admin password does not log in. Either the password was changed in OpenBao, or an earlier initialisation stopped before creating nexus-admin (then only an empty openbao-data volume recovers it). Nothing changed." >&2
  fi
  exit 0
fi

echo "openbao-init: initialising"
init_json=$(bao operator init -format=json -recovery-shares=1 -recovery-threshold=1) \
  || fail "bao operator init failed."
BAO_TOKEN=$(printf '%s' "$init_json" | sed -n 's/.*"root_token": *"\([^"]*\)".*/\1/p' | head -n 1)
unset init_json
[ -n "$BAO_TOKEN" ] || fail "no root token in the init response."
export BAO_TOKEN

# The static seal unseals right after init, but a Raft node can be unsealed
# and still standby for a moment, and writes fail until it is active. The
# root token exists only in this process, so a failed write here would leave
# OpenBao initialised with no way in. /v1/sys/health answers 200 only when
# the node is initialised, unsealed and active.
i=0
until wget -q -O /dev/null "$BAO_ADDR/v1/sys/health" 2>/dev/null; do
  i=$((i + 1)); [ "$i" -ge 60 ] && fail "OpenBao did not become active within 120 s after init."
  sleep 2
done

bao auth enable userpass >/dev/null
printf '%s\n' 'path "*" { capabilities = ["create", "read", "update", "patch", "delete", "list", "sudo"] }' \
  | bao policy write nexus-admin - >/dev/null
printf '%s' "$OPENBAO_ADMIN_PASSWORD" \
  | bao write auth/userpass/users/nexus-admin password=- token_policies=nexus-admin >/dev/null
bao secrets enable -path=secret -version=2 kv >/dev/null

admin_login_works || fail "nexus-admin does not log in right after it was created."

bao token revoke -self >/dev/null || fail "could not revoke the root token."
unset BAO_TOKEN
echo "openbao-init: initialised; nexus-admin created, KV v2 at secret/, root token revoked."
