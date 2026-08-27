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
CYAN='\033[0;36m'
NC='\033[0m'

# Failure accumulator, kept separate from any message variable: a step that
# fails while writing nothing to either stream must still be distinguishable
# from a step that worked. The script continues past a failure so a broken
# D1 delete does not hide an orphaned Access application, then exits non-zero
# at the end.
FAILED=0

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

# Get all D1 databases. per_page is explicit because the endpoint paginates
# with a documented default of 20 — an orphan on page 2 would otherwise look
# like no orphan at all.
if ! D1_DATABASES_RESPONSE=$(curl -sS --fail-with-body --max-time 30 --retry 3 \
    "https://api.cloudflare.com/client/v4/accounts/$TF_VAR_cloudflare_account_id/d1/database?per_page=1000" \
    -H "Authorization: Bearer $TF_VAR_cloudflare_api_token" \
    -H "Content-Type: application/json"); then
    echo -e "${RED}  ✗ Could not list D1 databases — the API call itself failed.${NC}"
    echo "    Not treating that as 'nothing to clean up': an orphan may still"
    echo "    exist. Check the token's D1 permission and re-run."
    FAILED=1
elif ! echo "$D1_DATABASES_RESPONSE" | jq -e '.success == true' >/dev/null 2>&1; then
    # --fail-with-body catches an HTTP error status, but Cloudflare also
    # reports failures as HTTP 200 with "success": false. Without this the
    # next line would read a null .result as zero databases and the script
    # would say "nothing to clean up" — the false all-clear this file exists
    # to stop producing.
    echo -e "${RED}  ✗ Cloudflare rejected the D1 listing:${NC}"
    echo "    $(echo "$D1_DATABASES_RESPONSE" | jq -r '.errors[]?.message // "no error message"' 2>/dev/null || echo "(response was not JSON)")"
    FAILED=1
else
    D1_SEEN=$(echo "$D1_DATABASES_RESPONSE" | jq -r '.result | length')
    D1_TOTAL=$(echo "$D1_DATABASES_RESPONSE" | jq -r '.result_info.total_count // empty')
    D1_MATCHES=$(echo "$D1_DATABASES_RESPONSE" \
        | jq -c --arg name "$D1_DATABASE_NAME" '[.result[]? | select(.name == $name) | .uuid]')
    D1_MATCH_COUNT=$(echo "$D1_MATCHES" | jq -r 'length')
    D1_DATABASE_ID=$(echo "$D1_MATCHES" | jq -r '.[0] // ""')

    if [ -n "$D1_TOTAL" ] && [ "$D1_TOTAL" -gt "$D1_SEEN" ]; then
        echo -e "${RED}  ✗ The listing returned $D1_SEEN of $D1_TOTAL D1 databases.${NC}"
        echo "    An orphan beyond the first page cannot be ruled out."
        FAILED=1
    elif [ "$D1_MATCH_COUNT" -gt 1 ]; then
        echo -e "${RED}  ✗ $D1_MATCH_COUNT D1 databases are named '$D1_DATABASE_NAME'.${NC}"
        echo "    Deleting by name is ambiguous, so this step stops rather than guessing."
        FAILED=1
    elif [ -z "$D1_DATABASE_ID" ]; then
        echo -e "${GREEN}  ✓ No D1 database named '$D1_DATABASE_NAME' — nothing to clean up.${NC}"
    else
        echo "  Found D1 Database ID: $D1_DATABASE_ID"

        # --max-time but no --retry: a DELETE that timed out may already have
        # succeeded, and a blind retry would report the resulting 404 as failure.
        if ! D1_DELETE_RESPONSE=$(curl -sS --fail-with-body --max-time 30 -X DELETE \
            "https://api.cloudflare.com/client/v4/accounts/$TF_VAR_cloudflare_account_id/d1/database/$D1_DATABASE_ID" \
            -H "Authorization: Bearer $TF_VAR_cloudflare_api_token" \
            -H "Content-Type: application/json"); then
            echo -e "${RED}  ✗ Delete request for D1 database $D1_DATABASE_ID failed.${NC}"
            echo "    $D1_DELETE_RESPONSE"
            FAILED=1
        elif echo "$D1_DELETE_RESPONSE" | jq -e '.success == true' >/dev/null 2>&1; then
            echo -e "${GREEN}  ✓ D1 Database deleted${NC}"
        else
            echo -e "${RED}  ✗ Cloudflare refused to delete D1 database $D1_DATABASE_ID:${NC}"
            echo "    $(echo "$D1_DELETE_RESPONSE" | jq -r '.errors[]?.message // "no error message"' 2>/dev/null || echo "(response was not JSON)")"
            FAILED=1
        fi
    fi
fi

# =============================================================================
# Step 2: Delete Access Application
# =============================================================================

echo ""
echo -e "${CYAN}Step 2: Deleting Access Application for '${ACCESS_APP_DOMAIN}'...${NC}"

# Get all Access applications for the zone. Paginated like the D1 listing.
if ! ACCESS_APPS_RESPONSE=$(curl -sS --fail-with-body --max-time 30 --retry 3 \
    "https://api.cloudflare.com/client/v4/zones/$TF_VAR_cloudflare_zone_id/access/apps?per_page=1000" \
    -H "Authorization: Bearer $TF_VAR_cloudflare_api_token" \
    -H "Content-Type: application/json"); then
    echo -e "${RED}  ✗ Could not list Access applications — the API call itself failed.${NC}"
    echo "    An orphaned app would keep gating $ACCESS_APP_DOMAIN. Check the"
    echo "    token's Access permission and re-run."
    FAILED=1
elif ! echo "$ACCESS_APPS_RESPONSE" | jq -e '.success == true' >/dev/null 2>&1; then
    echo -e "${RED}  ✗ Cloudflare rejected the Access listing:${NC}"
    echo "    $(echo "$ACCESS_APPS_RESPONSE" | jq -r '.errors[]?.message // "no error message"' 2>/dev/null || echo "(response was not JSON)")"
    FAILED=1
else
    AC_SEEN=$(echo "$ACCESS_APPS_RESPONSE" | jq -r '.result | length')
    AC_TOTAL=$(echo "$ACCESS_APPS_RESPONSE" | jq -r '.result_info.total_count // empty')
    AC_MATCHES=$(echo "$ACCESS_APPS_RESPONSE" \
        | jq -c --arg d "$ACCESS_APP_DOMAIN" '[.result[]? | select(.domain == $d) | .id]')
    AC_MATCH_COUNT=$(echo "$AC_MATCHES" | jq -r 'length')
    ACCESS_APP_ID=$(echo "$AC_MATCHES" | jq -r '.[0] // ""')

    if [ -n "$AC_TOTAL" ] && [ "$AC_TOTAL" -gt "$AC_SEEN" ]; then
        echo -e "${RED}  ✗ The listing returned $AC_SEEN of $AC_TOTAL Access applications.${NC}"
        echo "    An orphan beyond the first page cannot be ruled out."
        FAILED=1
    elif [ "$AC_MATCH_COUNT" -gt 1 ]; then
        echo -e "${RED}  ✗ $AC_MATCH_COUNT Access applications claim '$ACCESS_APP_DOMAIN'.${NC}"
        echo "    Deleting by domain is ambiguous, so this step stops rather than guessing."
        FAILED=1
    elif [ -z "$ACCESS_APP_ID" ]; then
        echo -e "${GREEN}  ✓ No Access application for '$ACCESS_APP_DOMAIN' — nothing to clean up.${NC}"
    else
        echo "  Found Access Application ID: $ACCESS_APP_ID"

        if ! ACCESS_DELETE_RESPONSE=$(curl -sS --fail-with-body --max-time 30 -X DELETE \
            "https://api.cloudflare.com/client/v4/zones/$TF_VAR_cloudflare_zone_id/access/apps/$ACCESS_APP_ID" \
            -H "Authorization: Bearer $TF_VAR_cloudflare_api_token" \
            -H "Content-Type: application/json"); then
            echo -e "${RED}  ✗ Delete request for Access application $ACCESS_APP_ID failed.${NC}"
            echo "    $ACCESS_DELETE_RESPONSE"
            FAILED=1
        elif echo "$ACCESS_DELETE_RESPONSE" | jq -e '.success == true' >/dev/null 2>&1; then
            echo -e "${GREEN}  ✓ Access Application deleted${NC}"
        else
            echo -e "${RED}  ✗ Cloudflare refused to delete Access application $ACCESS_APP_ID:${NC}"
            echo "    $(echo "$ACCESS_DELETE_RESPONSE" | jq -r '.errors[]?.message // "no error message"' 2>/dev/null || echo "(response was not JSON)")"
            FAILED=1
        fi
    fi
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
# The success line lives inside the success branch. Previously it printed
# unconditionally, so a run that failed to delete anything still ended on
# "Cleanup complete!" with status 0 — the exact shape CLAUDE.md warns about.
if [ "$FAILED" -ne 0 ]; then
    echo -e "${RED}Cleanup did NOT complete — see the errors above.${NC}"
    echo "Resources may still exist and will hold their names against the next setup."
    exit 1
fi
echo -e "${GREEN}Cleanup complete — every step above verified its own result.${NC}"
echo ""
echo "You can now deploy via GitHub Actions again."
