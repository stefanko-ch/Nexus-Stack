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
# The value travels on stdin end to end (never argv, never echoed), so it
# does not show up in `ps` or in the workflow log. Exit status is the
# forge call's; diagnostics go to stderr.
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

if [ "${GITHUB_SERVER_URL:-https://github.com}" = "https://github.com" ]; then
  if [ "$ACTION" = "set" ]; then
    exec gh secret set "$NAME"
  fi
  exec gh secret delete "$NAME"
fi

: "${GITHUB_API_URL:?repo-secret.sh: GITHUB_API_URL is not set}"
: "${GITHUB_REPOSITORY:?repo-secret.sh: GITHUB_REPOSITORY is not set}"
URL="${GITHUB_API_URL%/}/repos/${GITHUB_REPOSITORY}/actions/secrets/${NAME}"

RESPONSE=$(mktemp)
trap 'rm -f "$RESPONSE"' EXIT

if [ "$ACTION" = "set" ]; then
  # JSON-encode stdin. node is on every runner this repo targets
  # (actions/setup-node in the workflows; the Forgejo runner image is
  # node:22-bookworm) — jq is not guaranteed on the latter.
  CODE=$(node -e 'process.stdout.write(JSON.stringify({ data: require("fs").readFileSync(0, "utf8") }))' \
    | curl -sS -o "$RESPONSE" -w '%{http_code}' -X PUT \
        -H "Authorization: token ${GH_TOKEN}" \
        -H "Content-Type: application/json" \
        --data-binary @- "$URL")
else
  CODE=$(curl -sS -o "$RESPONSE" -w '%{http_code}' -X DELETE \
        -H "Authorization: token ${GH_TOKEN}" "$URL")
fi

case "$CODE" in
  200|201|204) exit 0 ;;
esac
echo "repo-secret.sh: ${ACTION} ${NAME} failed — ${GITHUB_SERVER_URL} returned HTTP ${CODE}" >&2
cat "$RESPONSE" >&2
echo >&2
exit 1
