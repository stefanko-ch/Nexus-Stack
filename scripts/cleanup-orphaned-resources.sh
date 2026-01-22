#!/bin/bash
set -e

# =============================================================================
# Cleanup Orphaned Cloudflare Resources
# =============================================================================
# This script deletes orphaned Cloudflare resources that may have been
# left behind after manual cleanup:
# - D1 Databases
# - Access Applications
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TOFU_DIR="$PROJECT_ROOT/tofu"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}Cleaning up orphaned Cloudflare resources...${NC}"
echo ""

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Try to load from GitHub Secrets if not set
if [ -z "$TF_VAR_cloudflare_api_token" ] && command -v gh >/dev/null 2>&1; then
    echo -e "${CYAN}Loading CLOUDFLARE_API_TOKEN from GitHub Secrets...${NC}"
    GITHUB_TOKEN=$(gh secret get CLOUDFLARE_API_TOKEN 2>/dev/null || echo "")
    if [ -n "$GITHUB_TOKEN" ]; then
        export TF_VAR_cloudflare_api_token="$GITHUB_TOKEN"
        echo -e "${GREEN}  ✓ Token loaded${NC}"
    fi
fi

if [ -z "$TF_VAR_cloudflare_account_id" ] && command -v gh >/dev/null 2>&1; then
    echo -e "${CYAN}Loading CLOUDFLARE_ACCOUNT_ID from GitHub Secrets...${NC}"
    GITHUB_ACCOUNT_ID=$(gh secret get CLOUDFLARE_ACCOUNT_ID 2>/dev/null || echo "")
    if [ -n "$GITHUB_ACCOUNT_ID" ]; then
        export TF_VAR_cloudflare_account_id="$GITHUB_ACCOUNT_ID"
        echo -e "${GREEN}  ✓ Account ID loaded${NC}"
    fi
fi

if [ -z "$TF_VAR_cloudflare_zone_id" ] && command -v gh >/dev/null 2>&1; then
    echo -e "${CYAN}Loading CLOUDFLARE_ZONE_ID from GitHub Secrets...${NC}"
    GITHUB_ZONE_ID=$(gh secret get CLOUDFLARE_ZONE_ID 2>/dev/null || echo "")
    if [ -n "$GITHUB_ZONE_ID" ]; then
        export TF_VAR_cloudflare_zone_id="$GITHUB_ZONE_ID"
        echo -e "${GREEN}  ✓ Zone ID loaded${NC}"
    fi
fi

if [ -z "$TF_VAR_cloudflare_api_token" ] || [ -z "$TF_VAR_cloudflare_account_id" ] || [ -z "$TF_VAR_cloudflare_zone_id" ]; then
    echo -e "${RED}Error: Required environment variables not set!${NC}"
    echo ""
    echo "Please set:"
    echo "  export TF_VAR_cloudflare_api_token='your-token'"
    echo "  export TF_VAR_cloudflare_account_id='your-account-id'"
    echo "  export TF_VAR_cloudflare_zone_id='your-zone-id'"
    echo ""
    echo "Or ensure you're authenticated with GitHub CLI:"
    echo "  gh auth login"
    exit 1
fi

# Get resource prefix from domain in config
if [ -f "$TOFU_DIR/config.tfvars" ]; then
    DOMAIN=$(grep -E '^domain\s*=' "$TOFU_DIR/config.tfvars" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' || echo "")
    if [ -n "$DOMAIN" ]; then
        RESOURCE_PREFIX="nexus-${DOMAIN//./-}"
    else
        RESOURCE_PREFIX="nexus"
    fi
else
    RESOURCE_PREFIX="nexus"
fi

D1_DATABASE_NAME="${RESOURCE_PREFIX}-db"
ACCESS_APP_DOMAIN="control.${TF_VAR_domain:-unknown}"

# =============================================================================
# Step 1: Delete D1 Database
# =============================================================================

echo -e "${CYAN}Step 1: Deleting D1 Database '${D1_DATABASE_NAME}'...${NC}"

# Get all D1 databases
D1_DATABASES_RESPONSE=$(curl -s \
    "https://api.cloudflare.com/client/v4/accounts/$TF_VAR_cloudflare_account_id/d1/database" \
    -H "Authorization: Bearer $TF_VAR_cloudflare_api_token" \
    -H "Content-Type: application/json")

D1_DATABASE_ID=$(echo "$D1_DATABASES_RESPONSE" | jq -r ".result[] | select(.name == \"$D1_DATABASE_NAME\") | .uuid" 2>/dev/null || echo "")

if [ -n "$D1_DATABASE_ID" ] && [ "$D1_DATABASE_ID" != "null" ]; then
    echo "  Found D1 Database ID: $D1_DATABASE_ID"
    
    # Delete the database
    D1_DELETE_RESPONSE=$(curl -s -X DELETE \
        "https://api.cloudflare.com/client/v4/accounts/$TF_VAR_cloudflare_account_id/d1/database/$D1_DATABASE_ID" \
        -H "Authorization: Bearer $TF_VAR_cloudflare_api_token" \
        -H "Content-Type: application/json")
    
    if echo "$D1_DELETE_RESPONSE" | grep -q '"success":true'; then
        echo -e "${GREEN}  ✓ D1 Database deleted${NC}"
    else
        echo -e "${YELLOW}  ⚠️  Could not delete D1 Database${NC}"
        echo "    Response: $(echo "$D1_DELETE_RESPONSE" | jq -r '.errors[0].message // "Unknown error"' 2>/dev/null || echo "Parse error")"
    fi
else
    echo -e "${YELLOW}  ⚠️  D1 Database not found (may already be deleted)${NC}"
fi

# =============================================================================
# Step 2: Delete Access Application
# =============================================================================

echo ""
echo -e "${CYAN}Step 2: Deleting Access Application for '${ACCESS_APP_DOMAIN}'...${NC}"

# Get all Access applications for the zone
ACCESS_APPS_RESPONSE=$(curl -s \
    "https://api.cloudflare.com/client/v4/zones/$TF_VAR_cloudflare_zone_id/access/apps" \
    -H "Authorization: Bearer $TF_VAR_cloudflare_api_token" \
    -H "Content-Type: application/json")

ACCESS_APP_ID=$(echo "$ACCESS_APPS_RESPONSE" | jq -r ".result[] | select(.domain == \"$ACCESS_APP_DOMAIN\") | .id" 2>/dev/null || echo "")

if [ -n "$ACCESS_APP_ID" ] && [ "$ACCESS_APP_ID" != "null" ]; then
    echo "  Found Access Application ID: $ACCESS_APP_ID"
    
    # Delete the Access Application
    ACCESS_DELETE_RESPONSE=$(curl -s -X DELETE \
        "https://api.cloudflare.com/client/v4/zones/$TF_VAR_cloudflare_zone_id/access/apps/$ACCESS_APP_ID" \
        -H "Authorization: Bearer $TF_VAR_cloudflare_api_token" \
        -H "Content-Type: application/json")
    
    if echo "$ACCESS_DELETE_RESPONSE" | grep -q '"success":true'; then
        echo -e "${GREEN}  ✓ Access Application deleted${NC}"
    else
        echo -e "${YELLOW}  ⚠️  Could not delete Access Application${NC}"
        echo "    Response: $(echo "$ACCESS_DELETE_RESPONSE" | jq -r '.errors[0].message // "Unknown error"' 2>/dev/null || echo "Parse error")"
    fi
else
    echo -e "${YELLOW}  ⚠️  Access Application not found (may already be deleted)${NC}"
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
echo -e "${GREEN}Cleanup complete!${NC}"
echo ""
echo "You can now deploy via GitHub Actions again."
