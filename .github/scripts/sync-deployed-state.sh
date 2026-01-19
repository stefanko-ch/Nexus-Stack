#!/bin/bash
# =============================================================================
# Sync Deployed State to D1
# =============================================================================
# After a successful spin-up, set deployed = enabled for all services.
# This marks staged changes as deployed.
#
# Environment variables required:
#   CLOUDFLARE_API_TOKEN  - Cloudflare API token with D1 access
#   CLOUDFLARE_ACCOUNT_ID - Cloudflare account ID
#   DOMAIN                - Domain for database name derivation
# =============================================================================

set -e

# Validate required environment variables
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ] || [ -z "${DOMAIN:-}" ]; then
  echo "⚠️ Missing required env vars for D1 sync - skipping"
  exit 0
fi

# Derive D1 database name from domain
D1_DATABASE_NAME="nexus-${DOMAIN//./-}-db"

echo "📊 Syncing deployed state to D1..."

# Update all services: set deployed = enabled
SQL="UPDATE services SET deployed = enabled, updated_at = datetime('now') WHERE deployed != enabled"

if npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$SQL" 2>/dev/null; then
  echo "✅ Deployed state synced to D1"
else
  echo "⚠️ Failed to sync deployed state (non-critical)"
fi

exit 0
