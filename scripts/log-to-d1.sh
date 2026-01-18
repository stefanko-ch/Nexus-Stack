#!/bin/bash
# =============================================================================
# Log to Control Plane D1 Database
# =============================================================================
# Usage: log-to-d1.sh <source> <level> <message> [metadata_json]
#
# Environment variables required:
#   DOMAIN - Your domain (e.g., example.com)
#   GITHUB_RUN_ID - Correlation ID (auto-set in GitHub Actions)
#
# Sources:
#   github-action  - GitHub Actions workflows
#   worker         - Cloudflare Workers (scheduled teardown)
#   api            - Control Plane API
#   health-check   - Health monitoring
#   deploy         - Deployment scripts
#
# Examples:
#   ./log-to-d1.sh "github-action" "info" "Starting deployment"
#   ./log-to-d1.sh "worker" "error" "Teardown failed" '{"error_code": 500}'
# =============================================================================

set -e

SOURCE="${1:-unknown}"
LEVEL="${2:-info}"
MESSAGE="${3:-No message provided}"
METADATA="${4:-null}"

if [ -z "$DOMAIN" ]; then
    echo "Warning: DOMAIN not set, skipping log"
    exit 0
fi

# Build JSON payload
if [ "$METADATA" = "null" ] || [ -z "$METADATA" ]; then
    PAYLOAD=$(cat <<EOF
{
  "source": "$SOURCE",
  "run_id": "${GITHUB_RUN_ID:-}",
  "level": "$LEVEL",
  "message": "$MESSAGE"
}
EOF
)
else
    PAYLOAD=$(cat <<EOF
{
  "source": "$SOURCE",
  "run_id": "${GITHUB_RUN_ID:-}",
  "level": "$LEVEL",
  "message": "$MESSAGE",
  "metadata": $METADATA
}
EOF
)
fi

# Send to Control Plane API
# Note: This goes through Cloudflare Access, so it needs a valid session or service token
curl -s -X POST "https://control.${DOMAIN}/api/logs" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" >/dev/null 2>&1 || true

# Always succeed - logging should never break the workflow
exit 0
