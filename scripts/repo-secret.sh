#!/bin/bash
# =============================================================================
# Nexus-Stack - Repository secret helper (GitHub or Forgejo)
# =============================================================================
# Writes or deletes an Actions repository secret on whichever forge the
# workflow is running on.
#
#   GitHub  -> `gh secret set` / `gh secret delete` (unchanged behaviour)
#   Forgejo -> the Actions secrets API: PUT /repos/{owner}/{repo}/actions/
#              secrets/{name} with {"data": "<value>"}; the forge encrypts
#              server-side. DELETE on the same path removes it.
#
# Usage:
#   printf '%s' "$VALUE" | scripts/repo-secret.sh set NAME
#   scripts/repo-secret.sh delete NAME
#
# Environment (all provided by GitHub Actions and by Forgejo Actions):
#   GH_TOKEN            token allowed to write this repository's secrets
#   GITHUB_SERVER_URL   https://github.com, or the forge's base URL
#   GITHUB_API_URL      https://api.github.com, or <forge>/api/v1
#   GITHUB_REPOSITORY   owner/repo
#
# The secret value travels on stdin end to end and GH_TOKEN goes in a
# curl config file, so neither appears in argv -- process arguments are
# world-readable through /proc on a shared runner. Neither is echoed, so
# neither reaches the workflow log. Diagnostics go to stderr and name the
# status and the endpoint, never the response body.
# =============================================================================

set -euo pipefail

ACTION="${1:-}"
NAME="${2:-}"
if [ -z "$ACTION" ] || [ -z "$NAME" ]; then
  echo "usage: repo-secret.sh set|delete NAME   (value on stdin for set)" >&2
  exit 2
fi
case "$NAME" in
  *[!A-Za-z0-9_]*) echo "repo-secret.sh: invalid secret name: $NAME" >&2; exit 2 ;;
esac
case "$ACTION" in
  set|delete) ;;
  *) echo "repo-secret.sh: unknown action: $ACTION (expected set|delete)" >&2; exit 2 ;;
esac
if [ -z "${GH_TOKEN:-}" ]; then
  echo "repo-secret.sh: GH_TOKEN is not set" >&2
  exit 2
fi

# github.com takes the `gh` path; anything else is assumed to be Forgejo.
# That assumption is deliberate but not universal: GitHub Enterprise Server
# also has a server URL that is not github.com, and would land in the
# branch below, which PUTs a plaintext {"data": ...}. GitHub's own secrets
# API wants a libsodium-encrypted value, so it would fail — loudly, with
# the forge's own status code, but the message would blame the wrong
# thing. Nexus-Stack targets github.com and Forgejo; add an explicit GHES
# branch here rather than widening this condition if that ever changes.
if [ "${GITHUB_SERVER_URL:-https://github.com}" = "https://github.com" ]; then
  if [ "$ACTION" = "set" ]; then
    exec gh secret set "$NAME"
  fi
  exec gh secret delete "$NAME"
fi

: "${GITHUB_API_URL:?repo-secret.sh: GITHUB_API_URL is not set}"
: "${GITHUB_REPOSITORY:?repo-secret.sh: GITHUB_REPOSITORY is not set}"

# Refuse to put a write-capable token on the wire in cleartext.
#
# The exception is loopback, where there is no wire to listen on. That is
# not a hypothetical shape here: whether a Forgejo job container can reach
# its own forge at all is #679, and one plausible answer is an http URL on
# the same host.
case "$GITHUB_API_URL" in
  https://*) ;;
  http://localhost|http://localhost[:/]*) ;;
  http://127.0.0.1|http://127.0.0.1[:/]*) ;;
  'http://[::1]'|'http://[::1]'[:/]*) ;;
  *)
    echo "repo-secret.sh: refusing to send GH_TOKEN in cleartext to ${GITHUB_API_URL}" >&2
    echo "repo-secret.sh: use https, or point GITHUB_API_URL at loopback if the forge runs on this host" >&2
    exit 2
    ;;
esac

URL="${GITHUB_API_URL%/}/repos/${GITHUB_REPOSITORY}/actions/secrets/${NAME}"

RESPONSE=$(mktemp)

# The token travels in a curl config file, not in `-H` on the command
# line. Process arguments are readable through /proc by any user on a
# shared runner, and this token can write every repository secret --
# the same reason the secret VALUE already goes on stdin rather than argv.
CURL_CFG=$(mktemp)
chmod 600 "$CURL_CFG"
printf 'header = "Authorization: token %s"\n' "$GH_TOKEN" > "$CURL_CFG"

trap 'rm -f "$RESPONSE" "$CURL_CFG"' EXIT

TRANSPORT=0
if [ "$ACTION" = "set" ]; then
  # JSON-encode stdin with node rather than jq. On GitHub the workflows
  # already run actions/setup-node, so node is present.
  #
  # On Forgejo this is a requirement on the runner rather than an observed
  # fact: no Forgejo runner exists in this repository yet -- it arrives with
  # the migration, whose job images must therefore carry node. Stated as a
  # constraint on purpose, because the alternative reading ("the runner
  # image happens to have node") is something nobody can check today.
  # jq is the weaker bet either way: it is absent from more base images
  # than node is.
  CODE=$(node -e 'process.stdout.write(JSON.stringify({ data: require("fs").readFileSync(0, "utf8") }))' \
    | curl -sS --config "$CURL_CFG" -o "$RESPONSE" -w '%{http_code}' -X PUT \
        -H "Content-Type: application/json" \
        --data-binary @- "$URL") || TRANSPORT=$?
else
  CODE=$(curl -sS --config "$CURL_CFG" -o "$RESPONSE" -w '%{http_code}' -X DELETE "$URL") || TRANSPORT=$?
fi

# No HTTP status was ever produced -- DNS, connect timeout, TLS, or node
# failing to encode. Without this branch `set -e` would abort right here on
# curl's exit code, and the operator would get curl's bare one-liner with
# no action, name or endpoint attached. That is the "forge unreachable"
# case this script exists to make legible, so it gets the same two-line
# shape as an HTTP failure.
if [ "$TRANSPORT" -ne 0 ]; then
  echo "repo-secret.sh: ${ACTION} ${NAME} failed before any HTTP status (exit ${TRANSPORT})" >&2
  echo "repo-secret.sh: endpoint was ${URL} -- the forge may be unreachable" >&2
  exit 1
fi

case "$CODE" in
  200|201|204) exit 0 ;;
esac

# The status code is the diagnosis and is safe to print: 404 wrong API
# path, 403 token cannot write secrets, 422 payload rejected. So is the
# endpoint, which carries the secret's NAME but never its value.
echo "repo-secret.sh: ${ACTION} ${NAME} failed — ${GITHUB_SERVER_URL} returned HTTP ${CODE}" >&2
echo "repo-secret.sh: endpoint was ${URL}" >&2

# The response body is never printed. This request's payload IS the
# secret, and callers in setup-control-plane.yaml capture this stream with
# `OUTPUT=$(... 2>&1)` and print it as SAVE_ERROR into the workflow log —
# world-readable for this repository. Whether a forge or an intermediate
# proxy echoes the rejected request back is not knowable from here and may
# differ per version.
#
# Truncating instead of dropping was tried and does not work, which is
# recorded here so it is not reintroduced as a compromise: every secret
# this workflow stores is short. An ed25519 private key is 387 bytes, an
# R2 access key 32, its secret 64 — all of them fit inside any cap large
# enough to still show a `{"message": ...}`. A bound that admits the
# useful case admits these too.
#
# Per CLAUDE.md: never print API responses that may contain credentials.
# `curl -o` still writes the body to a temp file, so the two branches above
# keep one shape; the trap removes it.
exit 1
