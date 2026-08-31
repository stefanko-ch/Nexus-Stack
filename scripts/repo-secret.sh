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
URL="${GITHUB_API_URL%/}/repos/${GITHUB_REPOSITORY}/actions/secrets/${NAME}"

RESPONSE=$(mktemp)
trap 'rm -f "$RESPONSE"' EXIT

if [ "$ACTION" = "set" ]; then
  # JSON-encode stdin with node rather than jq. On GitHub the workflows
  # already run actions/setup-node, so node is present.
  #
  # On Forgejo this is a requirement on the runner rather than an observed
  # fact: no Forgejo runner exists in this repository yet — it arrives with
  # the migration, whose job images must therefore carry node. Stated as a
  # constraint on purpose, because the alternative reading ("the runner
  # image happens to have node") is something nobody can check today.
  # jq is the weaker bet either way: it is absent from more base images
  # than node is.
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

# The status code is the diagnosis and is always safe to print: 404 wrong
# API path, 403 token cannot write secrets, 422 payload rejected.
echo "repo-secret.sh: ${ACTION} ${NAME} failed — ${GITHUB_SERVER_URL} returned HTTP ${CODE}" >&2

# The body is a different matter. This request's payload IS the secret,
# and callers in setup-control-plane.yaml capture this stream with
# `OUTPUT=$(... 2>&1)` and print it into the workflow log — which for this
# repository is world-readable. Whether a forge echoes the request back in
# an error response is not something this script can know, and the answer
# may differ per forge and per version, so the body is bounded rather than
# trusted: 500 bytes is enough for a `{"message": "..."}` and short enough
# that a mirrored payload cannot leave in full. Per CLAUDE.md — never
# print API responses that may contain credentials.
if [ -s "$RESPONSE" ]; then
  echo "repo-secret.sh: first 500 bytes of the response follow" >&2
  head -c 500 "$RESPONSE" >&2
  echo >&2
fi
exit 1
