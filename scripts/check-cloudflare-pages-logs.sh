#!/bin/bash
# Check Cloudflare Pages logs and environment variables

set -e

# Derive project name from domain
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/../tofu/config.tfvars" ]; then
  DOMAIN=$(grep -E '^domain\s*=' "$SCRIPT_DIR/../tofu/config.tfvars" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' || echo "")
  if [ -n "$DOMAIN" ]; then
    RESOURCE_PREFIX="nexus-${DOMAIN//./-}"
  else
    RESOURCE_PREFIX="nexus"
  fi
else
  RESOURCE_PREFIX="nexus"
fi
PROJECT_NAME="${RESOURCE_PREFIX}-control"

echo "🔍 Cloudflare Pages Diagnostics"
echo "=================================="
echo ""

# Check if .env exists
if [ -f .env ]; then
  source .env
fi

if [ -z "$CLOUDFLARE_API_TOKEN" ] || [ -z "$CLOUDFLARE_ACCOUNT_ID" ]; then
  echo "❌ Missing CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID"
  echo "   Load from .env or set manually"
  echo ""
  echo "To check logs manually:"
  echo "1. Go to: https://dash.cloudflare.com"
  echo "2. Pages → $PROJECT_NAME → Deployments"
  echo "3. Click latest deployment → View Logs"
  exit 1
fi

echo "📋 Checking environment variables..."
RESPONSE=$(curl -s -X GET \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/$PROJECT_NAME" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json")

SUCCESS=$(echo "$RESPONSE" | jq -r '.success // false')
if [ "$SUCCESS" != "true" ]; then
  echo "❌ Failed to fetch project info"
  echo "$RESPONSE" | jq -r '.errors // .messages // "Unknown error"'
  exit 1
fi

echo ""
echo "Production Environment Variables:"
PROD_VARS=$(echo "$RESPONSE" | jq -r '.result.deployment_configs.production.env_vars // {}')
if [ "$PROD_VARS" = "{}" ]; then
  echo "  ⚠️  No variables set"
else
  echo "$PROD_VARS" | jq -r 'to_entries[] | "  \(.key) = \(.value.value // "***")"'
fi

echo ""
echo "Preview Environment Variables:"
PREVIEW_VARS=$(echo "$RESPONSE" | jq -r '.result.deployment_configs.preview.env_vars // {}')
if [ "$PREVIEW_VARS" = "{}" ]; then
  echo "  ⚠️  No variables set"
else
  echo "$PREVIEW_VARS" | jq -r 'to_entries[] | "  \(.key) = \(.value.value // "***")"'
fi

echo ""
echo "Required Variables:"
GITHUB_OWNER_PROD=$(echo "$PROD_VARS" | jq -r '.GITHUB_OWNER.value // empty')
GITHUB_REPO_PROD=$(echo "$PROD_VARS" | jq -r '.GITHUB_REPO.value // empty')
GITHUB_OWNER_PREVIEW=$(echo "$PREVIEW_VARS" | jq -r '.GITHUB_OWNER.value // empty')
GITHUB_REPO_PREVIEW=$(echo "$PREVIEW_VARS" | jq -r '.GITHUB_REPO.value // empty')

if [ -n "$GITHUB_OWNER_PROD" ]; then
  echo "  ✅ GITHUB_OWNER (production) = $GITHUB_OWNER_PROD"
else
  echo "  ❌ GITHUB_OWNER (production) = MISSING"
fi

if [ -n "$GITHUB_REPO_PROD" ]; then
  echo "  ✅ GITHUB_REPO (production) = $GITHUB_REPO_PROD"
else
  echo "  ❌ GITHUB_REPO (production) = MISSING"
fi

if [ -n "$GITHUB_OWNER_PREVIEW" ]; then
  echo "  ✅ GITHUB_OWNER (preview) = $GITHUB_OWNER_PREVIEW"
else
  echo "  ⚠️  GITHUB_OWNER (preview) = MISSING (may be OK if only using production)"
fi

if [ -n "$GITHUB_REPO_PREVIEW" ]; then
  echo "  ✅ GITHUB_REPO (preview) = $GITHUB_REPO_PREVIEW"
else
  echo "  ⚠️  GITHUB_REPO (preview) = MISSING (may be OK if only using production)"
fi

echo ""
echo "📝 Note: GITHUB_TOKEN is a secret and cannot be checked via API"
echo "   Check in Cloudflare Dashboard: Pages → $PROJECT_NAME → Settings → Environment Variables"
echo ""
echo "📊 To view logs:"
echo "   1. Cloudflare Dashboard: Pages → $PROJECT_NAME → Deployments → Latest → View Logs"
echo "   2. Wrangler CLI (production):"
echo "      npx wrangler@4.129.0 pages deployment tail --project-name=$PROJECT_NAME --environment=production --format=pretty"
echo "   3. Wrangler CLI (preview):"
echo "      npx wrangler@4.129.0 pages deployment tail --project-name=$PROJECT_NAME --environment=preview --format=pretty"
echo ""
echo "   Filter options:"
echo "     --status=error    (only show errors)"
echo "     --method=GET      (filter by HTTP method)"
echo "     --search='text'   (search in console.log messages)"
