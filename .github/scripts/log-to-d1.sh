#!/bin/bash
# =============================================================================
# Log to D1 Database
# =============================================================================
# Usage: ./log-to-d1.sh <level> <message> [metadata_json]
#
# Environment variables required:
#   CLOUDFLARE_API_TOKEN  - Cloudflare API token with D1 access
#   CLOUDFLARE_ACCOUNT_ID - Cloudflare account ID
#   DOMAIN                - Domain for database name derivation
#   GITHUB_RUN_ID         - GitHub Actions run ID (auto-set in workflows)
#   GITHUB_WORKFLOW       - GitHub workflow name (auto-set in workflows)
#
# Examples:
#   ./log-to-d1.sh info "Workflow started"
#   ./log-to-d1.sh error "Container failed" '{"container":"grafana"}'
#   ./log-to-d1.sh warn "Skipping optional step"
# =============================================================================

# Don't exit on error for logging - it's non-critical
set +e

LEVEL="${1:-info}"
MESSAGE="${2:-}"
METADATA="${3:-}"

if [ -z "$MESSAGE" ]; then
  echo "Usage: $0 <level> <message> [metadata_json]"
  exit 0
fi

# Validate required environment variables
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ] || [ -z "${DOMAIN:-}" ]; then
  echo "⚠️ Missing required env vars for D1 logging (non-critical)"
  exit 0
fi

# Derive D1 database name from domain
D1_DATABASE_NAME="nexus-${DOMAIN//./-}-db"

# Build metadata with workflow context
# If metadata is empty or invalid JSON, start with empty object
if [ -z "$METADATA" ] || ! echo "$METADATA" | jq -e . >/dev/null 2>&1; then
  METADATA="{}"
fi

FULL_METADATA=$(echo "$METADATA" | jq -c \
  --arg workflow "${GITHUB_WORKFLOW:-unknown}" \
  --arg run_id "${GITHUB_RUN_ID:-unknown}" \
  --arg job "${GITHUB_JOB:-unknown}" \
  '. + {workflow: $workflow, run_id: $run_id, job: $job}' 2>/dev/null || echo '{}')

# Escape single quotes in message and metadata for SQL
# Note: wrangler d1 execute doesn't support parameterized queries via CLI
# Single-quote escaping is sufficient here as inputs come from GitHub Actions variables
ESCAPED_MESSAGE="${MESSAGE//\'/\'\'}"
ESCAPED_METADATA="${FULL_METADATA//\'/\'\'}"
ESCAPED_LEVEL="${LEVEL//\'/\'\'}"

# Insert log entry
SQL="INSERT INTO logs (source, level, message, metadata) VALUES ('github-action', '$ESCAPED_LEVEL', '$ESCAPED_MESSAGE', '$ESCAPED_METADATA')"

# Execute via wrangler (silent on success)
if npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$SQL" 2>/dev/null; then
  echo "📝 Logged: [$LEVEL] $MESSAGE"
else
  echo "⚠️ Failed to log to D1 (non-critical)"
fi

exit 0