#!/bin/bash
# =============================================================================
# Nexus-Stack - R2 Bootstrap
# =============================================================================
# Called by GitHub Actions setup-control-plane workflow.
# Creates R2 buckets (state + data) and a single unified API token.
# This runs before 'tofu init' to solve the chicken-and-egg problem.
#
# A single R2 token is used for both Terraform state and datalake access,
# reducing Cloudflare API token usage (important for Education deployments
# where the 50-token limit can be reached quickly).
#
# Required environment variables:
#   TF_VAR_cloudflare_api_token  - Cloudflare API token
#   TF_VAR_cloudflare_account_id - Cloudflare Account ID
#   TF_VAR_domain                - Domain name (used for bucket naming)
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Generate bucket name from domain: nexus-stack.ch -> nexus-stack-ch-terraform-state
DOMAIN="${TF_VAR_domain:-}"
if [ -z "$DOMAIN" ]; then
    echo -e "${RED}❌ TF_VAR_domain not set${NC}"
    echo ""
    echo "Set environment variables before running:"
    echo "  export TF_VAR_domain=\"your-domain.com\""
    echo ""
    echo "Or source your .env file:"
    echo "  source .env && make init"
    exit 1
fi

DOMAIN_SLUG=$(echo "$DOMAIN" | tr '.' '-')
BUCKET_NAME="${DOMAIN_SLUG}-terraform-state"
DATA_BUCKET_NAME="nexus-${DOMAIN_SLUG}-data"
# RFC 0001: persistence bucket for spinup-restore / teardown-snapshot
# of Gitea + Dify state (replaces the old Hetzner block volume).
PERSISTENCE_BUCKET_NAME="nexus-${DOMAIN_SLUG}-persistence"

R2_CREDENTIALS_FILE="tofu/.r2-credentials"

echo -e "${BLUE}🪣 Nexus-Stack - R2 Bootstrap${NC}"
echo "=============================="
echo ""

# Read from environment variables (TF_VAR_* format for OpenTofu compatibility)
CLOUDFLARE_API_TOKEN="${TF_VAR_cloudflare_api_token:-}"
CLOUDFLARE_ACCOUNT_ID="${TF_VAR_cloudflare_account_id:-}"

# Validate required values
if [ -z "$CLOUDFLARE_API_TOKEN" ]; then
    echo -e "${RED}❌ TF_VAR_cloudflare_api_token not set${NC}"
    echo ""
    echo "Set environment variables before running:"
    echo "  export TF_VAR_cloudflare_api_token=\"your-token\""
    echo "  export TF_VAR_cloudflare_account_id=\"your-account-id\""
    echo ""
    echo "Or source your .env file:"
    echo "  source .env && make init"
    exit 1
fi

if [ -z "$CLOUDFLARE_ACCOUNT_ID" ]; then
    echo -e "${RED}❌ TF_VAR_cloudflare_account_id not set${NC}"
    echo ""
    echo "Set environment variables before running:"
    echo "  export TF_VAR_cloudflare_api_token=\"your-token\""
    echo "  export TF_VAR_cloudflare_account_id=\"your-account-id\""
    echo ""
    echo "Or source your .env file:"
    echo "  source .env && make init"
    exit 1
fi

echo -e "📋 Account ID: ${YELLOW}${CLOUDFLARE_ACCOUNT_ID:0:8}...${NC}"

# =============================================================================
# Step 1: Check/Create R2 Buckets (state + data)
# =============================================================================
echo ""
echo -e "${BLUE}Step 1/4: Checking R2 buckets...${NC}"

# Check if bucket exists
BUCKET_CHECK=$(curl -s -w "\n%{http_code}" \
    "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/r2/buckets/${BUCKET_NAME}" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")

HTTP_CODE=$(echo "$BUCKET_CHECK" | tail -n1)
RESPONSE=$(echo "$BUCKET_CHECK" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "  ${GREEN}✓${NC} Bucket '${BUCKET_NAME}' already exists"
elif [ "$HTTP_CODE" = "404" ]; then
    echo -e "  ${YELLOW}→${NC} Creating bucket '${BUCKET_NAME}'..."

    CREATE_RESPONSE=$(curl -s -X POST \
        "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/r2/buckets" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${BUCKET_NAME}\"}")

    if echo "$CREATE_RESPONSE" | grep -q '"success":true'; then
        echo -e "  ${GREEN}✓${NC} Bucket created successfully"
    else
        ERROR_MSG=$(echo "$CREATE_RESPONSE" | grep -o '"message":"[^"]*"' | head -1 | sed 's/"message":"//;s/"$//')
        echo -e "  ${RED}❌ Failed to create bucket: ${ERROR_MSG}${NC}"
        echo "     Check Cloudflare dashboard for details"
        exit 1
    fi
else
    echo -e "  ${RED}❌ Failed to check state bucket (HTTP ${HTTP_CODE})${NC}"
    echo "     Response: ${RESPONSE}"
    exit 1
fi

# Check/Create data datalake bucket
echo ""
echo -e "  ${YELLOW}→${NC} Checking data bucket '${DATA_BUCKET_NAME}'..."

DATA_BUCKET_CHECK=$(curl -s -w "\n%{http_code}" \
    "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/r2/buckets/${DATA_BUCKET_NAME}" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")

DATA_HTTP_CODE=$(echo "$DATA_BUCKET_CHECK" | tail -n1)

if [ "$DATA_HTTP_CODE" = "200" ]; then
    echo -e "  ${GREEN}✓${NC} Data bucket '${DATA_BUCKET_NAME}' already exists"
elif [ "$DATA_HTTP_CODE" = "404" ]; then
    echo -e "  ${YELLOW}→${NC} Creating data bucket '${DATA_BUCKET_NAME}'..."

    DATA_CREATE_RESPONSE=$(curl -s -X POST \
        "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/r2/buckets" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${DATA_BUCKET_NAME}\"}")

    if echo "$DATA_CREATE_RESPONSE" | grep -q '"success":true'; then
        echo -e "  ${GREEN}✓${NC} Data bucket created successfully"
    else
        ERROR_MSG=$(echo "$DATA_CREATE_RESPONSE" | grep -o '"message":"[^"]*"' | head -1 | sed 's/"message":"//;s/"$//')
        echo -e "  ${RED}❌ Failed to create data bucket: ${ERROR_MSG}${NC}"
        echo "     Check Cloudflare dashboard for details"
        exit 1
    fi
else
    echo -e "  ${RED}❌ Failed to check data bucket (HTTP ${DATA_HTTP_CODE})${NC}"
    echo "     Response: $(echo "$DATA_BUCKET_CHECK" | sed '$d')"
    exit 1
fi

echo ""
echo -e "  ${YELLOW}→${NC} Checking persistence bucket '${PERSISTENCE_BUCKET_NAME}'..."

# RFC 0001: persistence bucket (idempotent). Same pattern as data
# bucket above. setup-control-plane.yaml ALSO ensures this on every
# run, so a user who skips this bootstrap and goes straight to
# initial-setup still gets the bucket created. Belt-and-suspenders.
PERSISTENCE_BUCKET_CHECK=$(curl -s -w "\n%{http_code}" \
    "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/r2/buckets/${PERSISTENCE_BUCKET_NAME}" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")

PERSISTENCE_HTTP_CODE=$(echo "$PERSISTENCE_BUCKET_CHECK" | tail -n1)

if [ "$PERSISTENCE_HTTP_CODE" = "200" ]; then
    echo -e "  ${GREEN}✓${NC} Persistence bucket '${PERSISTENCE_BUCKET_NAME}' already exists"
elif [ "$PERSISTENCE_HTTP_CODE" = "404" ]; then
    echo -e "  ${YELLOW}→${NC} Creating persistence bucket '${PERSISTENCE_BUCKET_NAME}'..."

    PERSISTENCE_CREATE_RESPONSE=$(curl -s -X POST \
        "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/r2/buckets" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${PERSISTENCE_BUCKET_NAME}\"}")

    if echo "$PERSISTENCE_CREATE_RESPONSE" | grep -q '"success":true'; then
        echo -e "  ${GREEN}✓${NC} Persistence bucket created successfully"
    else
        ERROR_MSG=$(echo "$PERSISTENCE_CREATE_RESPONSE" | grep -o '"message":"[^"]*"' | head -1 | sed 's/"message":"//;s/"$//')
        echo -e "  ${RED}❌ Failed to create persistence bucket: ${ERROR_MSG}${NC}"
        echo "     Check Cloudflare dashboard for details"
        exit 1
    fi
else
    echo -e "  ${RED}❌ Failed to check persistence bucket (HTTP ${PERSISTENCE_HTTP_CODE})${NC}"
    echo "     Response: $(echo "$PERSISTENCE_BUCKET_CHECK" | sed '$d')"
    exit 1
fi

# =============================================================================
# Step 2: Check/Create R2 API Token (unified for state + data)
# =============================================================================
echo ""
echo -e "${BLUE}Step 2/4: Checking R2 API credentials...${NC}"

# Check if credentials file already exists with valid credentials
if [ -f "$R2_CREDENTIALS_FILE" ]; then
    source "$R2_CREDENTIALS_FILE"
    if [ -n "$R2_ACCESS_KEY_ID" ] && [ -n "$R2_SECRET_ACCESS_KEY" ]; then
        echo -e "  ${GREEN}✓${NC} R2 credentials already configured"

        # Export for current session
        export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
        export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"

        # Generate backend.hcl with dynamic bucket name
        echo ""
        echo -e "${BLUE}Step 3/4: Generating backend configuration...${NC}"
        cat > tofu/backend.hcl << EOF
# Auto-generated by init-r2-state.sh
# R2 endpoint and bucket configuration for OpenTofu S3 backend
endpoints = {
  s3 = "https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com"
}
bucket = "${BUCKET_NAME}"
EOF
        echo -e "  ${GREEN}✓${NC} Generated tofu/backend.hcl (bucket: ${BUCKET_NAME})"

        echo ""
        echo -e "${GREEN}✅ R2 bootstrap complete!${NC}"
        echo ""
        echo "Credentials are stored in: $R2_CREDENTIALS_FILE"
        echo "Bucket name: $BUCKET_NAME"
        exit 0
    fi
fi

echo -e "  ${YELLOW}→${NC} Creating R2 API token..."

# Permission group ID for "Workers R2 Storage Write" (account-scoped)
# This allows full read/write access to R2 buckets and objects
# ID verified from Cloudflare docs: https://developers.cloudflare.com/r2/api/tokens/
R2_STORAGE_WRITE_PERMISSION_ID="bf7481a1826f439697cb59a20b22293e"

# Unified token name — one token for both state and data access
# Previously two tokens were created (nexus-r2-terraform-state-* and nexus-r2-data-*)
# Consolidated to reduce Cloudflare API token usage (50-token limit)
TOKEN_NAME="nexus-r2-${DOMAIN_SLUG}"

# Create User API token for R2 with account-level R2 permissions
# Using account resource instead of bucket-specific resource for broader access
# No expiration - token must remain valid for state access
# Retry logic for temporary Cloudflare API errors (500, rate limits, etc.)

# Helper function to extract error messages
extract_error() {
    echo "$1" | grep -o '"message":"[^"]*"' | head -1 | sed 's/"message":"//;s/"$//'
}

# Proactive cleanup: delete ANY existing token with our target name BEFORE
# trying to create a new one. Mirrors the bug-fix described in #530:
# the legacy "already exists" → delete-and-retry path was unpaginated
# (?per_page= unset → Cloudflare default of 25), so once an account
# carried >25 tokens the matching token might not appear in the response
# and the script would bail. Worse, if the API returned non-canonical
# error wording the delete-existing branch wouldn't trigger at all and
# orphans would leak. Doing this BEFORE create is idempotent and handles
# every edge case uniformly. Uses ?per_page=100 (Cloudflare's max) to
# tolerate accounts up to the 50-token hard cap.
#
# The listing used to be best-effort, on the reasoning that a create
# against a surviving token fails with "already exists" and the legacy
# delete-and-retry path recovers. That holds only while Cloudflare
# rejects a duplicate name — and the comment below acknowledges that
# tokens CAN share one. So a transient list failure plus an accepted
# duplicate meant the script created a second token, exited 0, and left
# the previous one live with R2 write access. Nothing downstream could
# notice, because from the caller's side the run had succeeded.
#
# The listing is therefore retried and, once the deletes are done,
# verified. If we cannot establish that no token with this name
# survives, we stop instead of minting another one.

# List every API token, retrying transient failures. Echoes the raw
# response on success; returns 1 when no attempt produced a usable one.
list_api_tokens() {
    local attempt response
    for attempt in 1 2 3; do
        response=$(curl -s "https://api.cloudflare.com/client/v4/user/tokens?per_page=100" \
            -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" 2>/dev/null || echo "")
        if echo "$response" | jq -e '.success == true and (.result | type == "array")' >/dev/null 2>&1; then
            printf '%s' "$response"
            return 0
        fi
        [ "$attempt" -lt 3 ] && sleep $((attempt * 2))
    done
    return 1
}

# IDs of every token named $TOKEN_NAME in a listing response. ALL of
# them, not just the first: the account can end up with several sharing
# a name (an earlier Cloudflare API behaviour change, or a race during a
# parallel re-setup), and leaving one behind is the case this guards.
stale_token_ids() {
    printf '%s' "$1" | jq -r --arg name "$TOKEN_NAME" '.result[] | select(.name == $name) | .id'
}

echo -e "  ${CYAN}→${NC} Pre-cleanup: looking for stale '${TOKEN_NAME}' tokens..."
if ! STALE_TOKEN_LIST=$(list_api_tokens); then
    echo -e "  ${RED}✗${NC} Could not list API tokens after 3 attempts."
    echo -e "     Aborting rather than creating another '${TOKEN_NAME}' token:"
    echo -e "     if a previous one is still live, a second would leave it"
    echo -e "     active with R2 write access and nothing would report it."
    echo -e "     Check the Cloudflare API status and re-run."
    exit 1
fi

STALE_IDS=$(stale_token_ids "$STALE_TOKEN_LIST")
if [ -n "$STALE_IDS" ]; then
    STALE_COUNT=$(printf '%s\n' "$STALE_IDS" | wc -l | tr -d ' ')
    echo -e "  ${YELLOW}⚠${NC}  Found ${STALE_COUNT} stale token(s) with name '${TOKEN_NAME}' — deleting before re-create..."
    while IFS= read -r STALE_ID; do
        [ -z "$STALE_ID" ] && continue
        STALE_DEL=$(curl -s -X DELETE \
            "https://api.cloudflare.com/client/v4/user/tokens/${STALE_ID}" \
            -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" 2>/dev/null || echo "")
        if echo "$STALE_DEL" | grep -q '"success":true'; then
            echo -e "  ${GREEN}✓${NC} Deleted stale token ${STALE_ID}"
        else
            STALE_ERR=$(extract_error "$STALE_DEL")
            echo -e "  ${YELLOW}⚠${NC}  Could not delete stale token ${STALE_ID}: ${STALE_ERR:-no error message}"
            # Not fatal on its own — the verification below decides. A
            # delete can report failure and still have taken effect, so
            # re-reading the truth beats trusting this response.
        fi
    done <<< "$STALE_IDS"

    # Verify. This is the assertion the whole block exists for: after
    # this point no token named $TOKEN_NAME may remain, because the very
    # next thing we do is create one.
    if ! VERIFY_LIST=$(list_api_tokens); then
        echo -e "  ${RED}✗${NC} Deleted stale token(s) but could not verify the result."
        echo -e "     Aborting rather than creating another '${TOKEN_NAME}' token."
        exit 1
    fi
    SURVIVORS=$(stale_token_ids "$VERIFY_LIST")
    if [ -n "$SURVIVORS" ]; then
        SURVIVOR_COUNT=$(printf '%s\n' "$SURVIVORS" | wc -l | tr -d ' ')
        echo -e "  ${RED}✗${NC} ${SURVIVOR_COUNT} token(s) named '${TOKEN_NAME}' could not be deleted:"
        printf '%s\n' "$SURVIVORS" | sed 's/^/     /'
        echo -e "     They still hold R2 write access. Creating another would"
        echo -e "     leave them live and unaccounted for, so this stops here."
        echo -e "     Delete them under Cloudflare dashboard → My Profile →"
        echo -e "     API Tokens, then re-run."
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Verified: no '${TOKEN_NAME}' tokens remain"
else
    echo -e "  ${GREEN}✓${NC} No stale tokens found"
fi

MAX_RETRIES=3
RETRY=0
TOKEN_RESPONSE=""

while [ $RETRY -lt $MAX_RETRIES ]; do
    TOKEN_RESPONSE=$(curl -s -X POST \
        "https://api.cloudflare.com/client/v4/user/tokens" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"${TOKEN_NAME}\",
            \"policies\": [
                {
                    \"effect\": \"allow\",
                    \"resources\": {
                        \"com.cloudflare.api.account.${CLOUDFLARE_ACCOUNT_ID}\": \"*\"
                    },
                    \"permission_groups\": [
                        {
                            \"id\": \"${R2_STORAGE_WRITE_PERMISSION_ID}\",
                            \"name\": \"Workers R2 Storage Write\"
                        }
                    ]
                }
            ]
        }")

    if echo "$TOKEN_RESPONSE" | grep -q '"success":true'; then
        break
    fi

    # Extract error message and code
    ERROR_MSG=$(extract_error "$TOKEN_RESPONSE")
    ERROR_CODE=$(echo "$TOKEN_RESPONSE" | grep -o '"code":[0-9]*' | head -1 | cut -d: -f2)

    # Token already exists — delete it and retry (credentials can't be retrieved after creation)
    if echo "$TOKEN_RESPONSE" | grep -q "already exists"; then
        RETRY=$((RETRY + 1))
        echo -e "  ${YELLOW}⚠${NC}  Token '${TOKEN_NAME}' already exists — deleting and recreating..."

        # Find the existing token by name (using jq for reliable JSON parsing).
        # Use ?per_page=100 (Cloudflare's max) so the matching token appears
        # in the response even when the account is near the 50-token cap.
        # Without this, the default per_page=25 missed tokens on later pages,
        # producing the "Token exists but could not find its ID" hard-fail
        # path observed in production accounts (see #530).
        EXISTING_TOKEN_ID=$(curl -s \
            "https://api.cloudflare.com/client/v4/user/tokens?per_page=100" \
            -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
            | jq -r --arg TOKEN_NAME "$TOKEN_NAME" \
                '.result[] | select(.name == $TOKEN_NAME) | .id' | head -n 1)

        if [ -n "$EXISTING_TOKEN_ID" ]; then
            # Delete the existing token
            DELETE_RESPONSE=$(curl -s -X DELETE \
                "https://api.cloudflare.com/client/v4/user/tokens/${EXISTING_TOKEN_ID}" \
                -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")

            if echo "$DELETE_RESPONSE" | grep -q '"success":true'; then
                echo -e "  ${GREEN}✓${NC} Old token deleted"
                sleep 2
                continue  # Retry token creation
            else
                echo -e "  ${RED}❌ Failed to delete existing token${NC}"
                echo "     Delete it manually: Cloudflare Dashboard → My Profile → API Tokens"
                exit 1
            fi
        else
            echo -e "  ${RED}❌ Token exists but could not find its ID${NC}"
            echo "     Delete it manually: Cloudflare Dashboard → My Profile → API Tokens"
            exit 1
        fi
    fi

    # Retry on 500 errors or rate limits (retryable)
    if [ "$ERROR_CODE" = "500" ] || [ "$ERROR_CODE" = "429" ] || [ -z "$ERROR_CODE" ]; then
        RETRY=$((RETRY + 1))
        if [ $RETRY -lt $MAX_RETRIES ]; then
            WAIT_TIME=$((RETRY * 5))
            echo -e "  ${YELLOW}⚠${NC}  API error (attempt $RETRY/$MAX_RETRIES): ${ERROR_MSG:-Unknown error}"
            echo -e "  ${YELLOW}→${NC} Retrying in ${WAIT_TIME}s..."
            sleep $WAIT_TIME
            continue
        fi
    fi

    # Non-retryable error or max retries reached
    ERROR_MSG=$(extract_error "$TOKEN_RESPONSE")
    echo -e "  ${RED}❌ Failed to create token: ${ERROR_MSG:-Unknown error}${NC}"
    echo "     Check Cloudflare dashboard for details"
    exit 1
done

if ! echo "$TOKEN_RESPONSE" | grep -q '"success":true'; then
    ERROR_MSG=$(extract_error "$TOKEN_RESPONSE")
    echo -e "  ${RED}❌ Failed to create token after $MAX_RETRIES attempts: ${ERROR_MSG:-Unknown error}${NC}"
    echo "     Check Cloudflare dashboard for details"
    exit 1
fi

# Extract token ID and value
TOKEN_ID=$(echo "$TOKEN_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | sed 's/"id":"//;s/"$//')
TOKEN_VALUE=$(echo "$TOKEN_RESPONSE" | grep -o '"value":"[^"]*"' | sed 's/"value":"//;s/"$//')

if [ -z "$TOKEN_ID" ] || [ -z "$TOKEN_VALUE" ]; then
    echo -e "  ${RED}❌ Failed to extract token credentials${NC}"
    echo "     Check Cloudflare dashboard for details"
    exit 1
fi

# Calculate Secret Access Key (SHA-256 of token value)
# Per Cloudflare docs: Access Key ID = token ID, Secret Access Key = SHA-256(token value)
# See: https://developers.cloudflare.com/r2/api/tokens/#get-s3-api-credentials-from-an-api-token
SECRET_KEY_SHA256=$(echo -n "$TOKEN_VALUE" | openssl dgst -sha256 | awk '{print $2}')

if [ -z "$SECRET_KEY_SHA256" ]; then
    echo -e "  ${YELLOW}⚠${NC}  SHA-256 derivation returned empty value"
    echo -e "     You may need to use the raw token value instead."
    echo -e "     See R2_SECRET_ACCESS_KEY_RAW in $R2_CREDENTIALS_FILE after setup."
fi

echo -e "  ${GREEN}✓${NC} R2 API token created"
echo -e "  ${YELLOW}→${NC} Waiting for token propagation..."
sleep 5

# Save credentials to file
# We save both the SHA-256 version and the raw token for debugging
cat > "$R2_CREDENTIALS_FILE" << EOF
# Nexus-Stack R2 Credentials
# Auto-generated by init-r2-state.sh - DO NOT COMMIT
# These credentials are used for both OpenTofu state and datalake access

# Access Key ID = Token ID
R2_ACCESS_KEY_ID="${TOKEN_ID}"

# Secret Access Key = SHA-256 hash of token value (per Cloudflare docs)
R2_SECRET_ACCESS_KEY="${SECRET_KEY_SHA256}"

# Data datalake bucket name
R2_DATA_BUCKET="${DATA_BUCKET_NAME}"

# Alternative: Raw token value (try this if SHA-256 doesn't work)
# R2_SECRET_ACCESS_KEY_RAW="${TOKEN_VALUE}"

# For S3-compatible tools, export these as:
# export AWS_ACCESS_KEY_ID="\$R2_ACCESS_KEY_ID"
# export AWS_SECRET_ACCESS_KEY="\$R2_SECRET_ACCESS_KEY"
EOF

chmod 600 "$R2_CREDENTIALS_FILE"
echo -e "  ${GREEN}✓${NC} Saved credentials to $R2_CREDENTIALS_FILE"

# Clean up old-format tokens now that the new unified token is persisted.
# Done AFTER credential persistence so that if token creation had failed,
# the old tokens would still be valid.
OLD_TOKEN_NAMES=("nexus-r2-terraform-state-${DOMAIN_SLUG}" "nexus-r2-data-${DOMAIN_SLUG}")
ALL_TOKENS=$(curl -s "https://api.cloudflare.com/client/v4/user/tokens?per_page=100" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")

if echo "$ALL_TOKENS" | jq -e '.success == true and (.result | type == "array")' >/dev/null 2>&1; then
    for OLD_NAME in "${OLD_TOKEN_NAMES[@]}"; do
        OLD_TOKEN_ID=$(echo "$ALL_TOKENS" | jq -r --arg name "$OLD_NAME" \
            '.result[] | select(.name == $name) | .id' 2>/dev/null | head -n 1 || true)
        if [ -n "${OLD_TOKEN_ID}" ] && [ "${OLD_TOKEN_ID}" != "null" ]; then
            echo -e "  ${YELLOW}→${NC} Cleaning up old token '${OLD_NAME}'..."
            DELETE_RESP=$(curl -s -X DELETE \
                "https://api.cloudflare.com/client/v4/user/tokens/${OLD_TOKEN_ID}" \
                -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")
            if echo "$DELETE_RESP" | grep -q '"success":true'; then
                echo -e "  ${GREEN}✓${NC} Deleted old token '${OLD_NAME}'"
            else
                echo -e "  ${YELLOW}⚠${NC}  Could not delete old token '${OLD_NAME}' (non-fatal)"
            fi
        fi
    done
else
    echo -e "  ${YELLOW}⚠${NC}  Skipping cleanup of old R2 tokens (could not parse token list response; non-fatal)"
fi

# =============================================================================
# Step 3: Generate backend.hcl
# =============================================================================
echo ""
echo -e "${BLUE}Step 3/4: Generating backend configuration...${NC}"

cat > tofu/backend.hcl << EOF
# Auto-generated by init-r2-state.sh
# R2 endpoint and bucket configuration for OpenTofu S3 backend
endpoints = {
  s3 = "https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com"
}
bucket = "${BUCKET_NAME}"
EOF

echo -e "  ${GREEN}✓${NC} Generated tofu/backend.hcl (bucket: ${BUCKET_NAME})"

# =============================================================================
# Step 4: Summary
# =============================================================================
echo ""
echo -e "${GREEN}✅ R2 bootstrap complete!${NC}"
echo ""
echo "Credentials saved to: $R2_CREDENTIALS_FILE"
echo "State bucket: $BUCKET_NAME"
echo "Data bucket:  $DATA_BUCKET_NAME"
echo ""
echo -e "${YELLOW}📝 To use with OpenTofu, run:${NC}"
echo "   source $R2_CREDENTIALS_FILE"
echo "   export AWS_ACCESS_KEY_ID=\"\$R2_ACCESS_KEY_ID\""
echo "   export AWS_SECRET_ACCESS_KEY=\"\$R2_SECRET_ACCESS_KEY\""
echo ""
