#!/bin/bash
# =============================================================================
# Sync Services to D1
# =============================================================================
# After a successful spin-up:
# 1. Initialize services from services.tfvars to D1 (metadata sync)
# 2. Set deployed = enabled for all services (mark as deployed)
#
# Environment variables required:
#   DOMAIN - Domain for Control Plane URL
# =============================================================================

set -e

# Validate required environment variables
if [ -z "${DOMAIN:-}" ]; then
  echo "⚠️ Missing DOMAIN env var - skipping D1 sync"
  exit 0
fi

CONTROL_PLANE_URL="https://control.${DOMAIN}"

echo "📊 Syncing services to D1..."

# Step 1: Initialize services from services.tfvars
echo "  Initializing services from services.tfvars..."
INIT_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${CONTROL_PLANE_URL}/api/services/init" \
  -H "Content-Type: application/json" || echo -e "\n000")
INIT_HTTP_CODE=$(echo "$INIT_RESPONSE" | tail -n1)
INIT_BODY=$(echo "$INIT_RESPONSE" | sed '$d')

if [ "$INIT_HTTP_CODE" -ge 200 ] && [ "$INIT_HTTP_CODE" -lt 300 ]; then
  echo "  ✅ Services initialized from services.tfvars"
  echo "$INIT_BODY" | jq -r '.message // empty' 2>/dev/null || true
else
  echo "  ⚠️ Failed to initialize services (HTTP $INIT_HTTP_CODE) - continuing"
fi

# Step 2: Sync deployed state
echo "  Syncing deployed state..."
SYNC_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${CONTROL_PLANE_URL}/api/services/sync-deployed" \
  -H "Content-Type: application/json" || echo -e "\n000")
SYNC_HTTP_CODE=$(echo "$SYNC_RESPONSE" | tail -n1)
SYNC_BODY=$(echo "$SYNC_RESPONSE" | sed '$d')

if [ "$SYNC_HTTP_CODE" -ge 200 ] && [ "$SYNC_HTTP_CODE" -lt 300 ]; then
  echo "  ✅ Deployed state synced"
else
  echo "  ⚠️ Failed to sync deployed state (HTTP $SYNC_HTTP_CODE)"
fi

echo "✅ D1 sync complete"
exit 0
