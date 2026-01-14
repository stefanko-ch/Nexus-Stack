#!/bin/bash
# =============================================================================
# Test Cloudflare API Token Permissions
# =============================================================================
# This script tests if your Cloudflare API token has the required permissions
# for creating Workers KV namespaces.
#
# Usage:
#   source .env
#   ./scripts/test-cloudflare-permissions.sh
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 Testing Cloudflare API Token Permissions${NC}"
echo ""

# Check required environment variables
if [ -z "$TF_VAR_cloudflare_api_token" ] && [ -z "$CLOUDFLARE_API_TOKEN" ]; then
    echo -e "${RED}❌ Error: CLOUDFLARE_API_TOKEN or TF_VAR_cloudflare_api_token not set${NC}"
    echo "   Source your .env file: source .env"
    exit 1
fi

if [ -z "$TF_VAR_cloudflare_account_id" ] && [ -z "$CLOUDFLARE_ACCOUNT_ID" ]; then
    echo -e "${RED}❌ Error: CLOUDFLARE_ACCOUNT_ID or TF_VAR_cloudflare_account_id not set${NC}"
    echo "   Source your .env file: source .env"
    exit 1
fi

# Use TF_VAR_ prefix if available, otherwise use direct env vars
CF_TOKEN="${TF_VAR_cloudflare_api_token:-$CLOUDFLARE_API_TOKEN}"
CF_ACCOUNT_ID="${TF_VAR_cloudflare_account_id:-$CLOUDFLARE_ACCOUNT_ID}"

echo -e "${BLUE}Token Info:${NC}"
TOKEN_INFO=$(curl -s -X GET "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json")

if echo "$TOKEN_INFO" | jq -e '.success == true' > /dev/null 2>&1; then
    echo -e "${GREEN}  ✅ Token is valid${NC}"
    echo "$TOKEN_INFO" | jq -r '.result | "  ID: \(.id)\n  Status: \(.status)\n  Issued: \(.issued_on)"'
else
    echo -e "${RED}  ❌ Token is invalid${NC}"
    echo "$TOKEN_INFO" | jq -r '.errors[]? | "  Error: \(.message)"'
    exit 1
fi
echo ""

# Test 1: List KV namespaces (requires Workers KV Storage permission)
echo -e "${BLUE}Test 1: List KV Namespaces${NC}"
KV_LIST=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json")

if echo "$KV_LIST" | jq -e '.success == true' > /dev/null 2>&1; then
    echo -e "${GREEN}  ✅ KV Namespace list access: OK${NC}"
    COUNT=$(echo "$KV_LIST" | jq -r '.result | length')
    echo "  Found $COUNT existing namespace(s)"
    if [ "$COUNT" -gt 0 ]; then
        echo "$KV_LIST" | jq -r '.result[] | "    - \(.title) (ID: \(.id))"'
    fi
else
    echo -e "${RED}  ❌ KV Namespace list access: FAILED${NC}"
    echo "$KV_LIST" | jq -r '.errors[]? | "  Error: \(.message) (Code: \(.code))"'
    echo ""
    echo -e "${YELLOW}  ⚠️  This indicates missing 'Workers KV Storage' permission${NC}"
    echo "  Required: Account → Workers KV Storage → Edit"
fi
echo ""

# Test 2: Try to create a test KV namespace (requires Workers KV Storage permission)
echo -e "${BLUE}Test 2: Create KV Namespace (Test)${NC}"
TEST_NS_NAME="test-permission-check-$(date +%s)"
CREATE_TEST=$(curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\": \"$TEST_NS_NAME\"}")

if echo "$CREATE_TEST" | jq -e '.success == true' > /dev/null 2>&1; then
    echo -e "${GREEN}  ✅ KV Namespace creation: OK${NC}"
    NS_ID=$(echo "$CREATE_TEST" | jq -r '.result.id')
    echo "  Created test namespace ID: $NS_ID"
    
    # Clean up test namespace
    echo "  Cleaning up test namespace..."
    DELETE_RESULT=$(curl -s -X DELETE "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces/$NS_ID" \
      -H "Authorization: Bearer $CF_TOKEN")
    
    if echo "$DELETE_RESULT" | jq -e '.success == true' > /dev/null 2>&1; then
        echo -e "${GREEN}  ✅ Test namespace deleted${NC}"
    else
        echo -e "${YELLOW}  ⚠️  Failed to delete test namespace (ID: $NS_ID) - please delete manually${NC}"
    fi
else
    echo -e "${RED}  ❌ KV Namespace creation: FAILED${NC}"
    echo "$CREATE_TEST" | jq -r '.errors[]? | "  Error: \(.message) (Code: \(.code))"'
    echo ""
    echo -e "${YELLOW}  ⚠️  This indicates missing 'Workers KV Storage' permission${NC}"
    echo "  Required: Account → Workers KV Storage → Edit"
    echo ""
    echo -e "${YELLOW}  Steps to fix:${NC}"
    echo "  1. Go to Cloudflare Dashboard → My Profile → API Tokens"
    echo "  2. Edit your token"
    echo "  3. Add permission: Account → Workers KV Storage → Edit"
    echo "  4. Save the token"
    echo "  5. If token is in GitHub Secrets, update it there too"
fi
echo ""

# Test 3: List Worker scripts (requires Workers Scripts permission)
echo -e "${BLUE}Test 3: List Worker Scripts${NC}"
SCRIPTS_LIST=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json")

if echo "$SCRIPTS_LIST" | jq -e '.success == true' > /dev/null 2>&1; then
    echo -e "${GREEN}  ✅ Workers Scripts access: OK${NC}"
    COUNT=$(echo "$SCRIPTS_LIST" | jq -r '.result | length')
    echo "  Found $COUNT existing script(s)"
else
    echo -e "${RED}  ❌ Workers Scripts access: FAILED${NC}"
    echo "$SCRIPTS_LIST" | jq -r '.errors[]? | "  Error: \(.message) (Code: \(.code))"'
    echo ""
    echo -e "${YELLOW}  ⚠️  This indicates missing 'Workers Scripts' permission${NC}"
    echo "  Required: Account → Workers Scripts → Edit"
fi
echo ""

echo -e "${BLUE}Summary:${NC}"
if echo "$CREATE_TEST" | jq -e '.success == true' > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Workers KV Storage permissions are correct!${NC}"
    echo "  Your token can create KV namespaces."
else
    echo -e "${RED}❌ Missing required permissions${NC}"
    echo "  Please add 'Workers KV Storage: Edit' permission to your token."
fi
