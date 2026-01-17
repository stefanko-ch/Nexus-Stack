#!/bin/bash
set -e

# =============================================================================
# Setup Control Plane Secrets
# =============================================================================
# This script helps set up the required environment variables for the Control Plane
# in Cloudflare Pages.
#
# Required variables:
#   - GITHUB_TOKEN: GitHub Personal Access Token with 'workflow' scope
#   - GITHUB_OWNER: Set automatically by Terraform
#   - GITHUB_REPO: Set automatically by Terraform
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TOFU_DIR="$PROJECT_ROOT/tofu"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║          Control Plane Secrets Setup                           ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if wrangler is available
if ! command -v npx &> /dev/null; then
    echo -e "${RED}Error: npx is required but not installed${NC}"
    exit 1
fi

# Get project name from domain in config
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

PROJECT_NAME="${RESOURCE_PREFIX}-control"

echo -e "${CYAN}Project name: ${PROJECT_NAME}${NC}"
echo ""

# Check if GITHUB_TOKEN is provided
if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${YELLOW}GITHUB_TOKEN not found in environment${NC}"
    echo ""
    echo "Please provide your GitHub Personal Access Token:"
    echo "  1. Go to https://github.com/settings/tokens"
    echo "  2. Generate new token (classic)"
    echo "  3. Select scope: 'workflow'"
    echo ""
    read -sp "Enter GitHub Token: " GITHUB_TOKEN
    echo ""
    echo ""
fi

if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${RED}Error: GITHUB_TOKEN is required${NC}"
    exit 1
fi

# Check if CLOUDFLARE_API_TOKEN is set (required for wrangler)
if [ -z "$CLOUDFLARE_API_TOKEN" ] && [ -n "$TF_VAR_cloudflare_api_token" ]; then
    export CLOUDFLARE_API_TOKEN="$TF_VAR_cloudflare_api_token"
fi

if [ -z "$CLOUDFLARE_API_TOKEN" ]; then
    echo -e "${YELLOW}CLOUDFLARE_API_TOKEN not found in environment${NC}"
    echo ""
    echo "Please provide your Cloudflare API Token:"
    echo "  1. Go to https://dash.cloudflare.com/profile/api-tokens"
    echo "  2. Create token with 'Cloudflare Pages:Edit' permission"
    echo ""
    read -sp "Enter Cloudflare API Token: " CLOUDFLARE_API_TOKEN
    echo ""
    echo ""
    export CLOUDFLARE_API_TOKEN
fi

if [ -z "$CLOUDFLARE_API_TOKEN" ]; then
    echo -e "${RED}Error: CLOUDFLARE_API_TOKEN is required for wrangler${NC}"
    exit 1
fi

# Set GITHUB_TOKEN secret
echo -e "${YELLOW}Setting GITHUB_TOKEN secret...${NC}"
echo "$GITHUB_TOKEN" | CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN" npx wrangler@latest pages secret put GITHUB_TOKEN --project-name="$PROJECT_NAME"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ GITHUB_TOKEN secret set successfully${NC}"
else
    echo -e "${RED}✗ Failed to set GITHUB_TOKEN secret${NC}"
    exit 1
fi

# Get GITHUB_OWNER and GITHUB_REPO from Terraform or config
if [ -f "$TOFU_DIR/config.tfvars" ]; then
    GITHUB_OWNER=$(grep -E '^github_owner\s*=' "$TOFU_DIR/config.tfvars" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' | tr -d ' ' || echo "")
    GITHUB_REPO=$(grep -E '^github_repo\s*=' "$TOFU_DIR/config.tfvars" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' | tr -d ' ' || echo "")
fi

# Fallback: try to get from git remote
if [ -z "$GITHUB_OWNER" ] || [ -z "$GITHUB_REPO" ]; then
    cd "$PROJECT_ROOT"
    REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
    if [[ "$REMOTE_URL" =~ github.com[:/]([^/]+)/([^/]+) ]]; then
        GITHUB_OWNER="${BASH_REMATCH[1]}"
        GITHUB_REPO="${BASH_REMATCH[2]%.git}"
    fi
fi

# Set GITHUB_OWNER and GITHUB_REPO as environment variables
if [ -n "$GITHUB_OWNER" ] && [ -n "$GITHUB_REPO" ]; then
    echo ""
    echo -e "${YELLOW}Setting GITHUB_OWNER and GITHUB_REPO environment variables...${NC}"
    echo -e "${CYAN}  GITHUB_OWNER: $GITHUB_OWNER${NC}"
    echo -e "${CYAN}  GITHUB_REPO: $GITHUB_REPO${NC}"
    echo ""
    echo -e "${YELLOW}Note: These need to be set via Cloudflare Dashboard:${NC}"
    echo "  1. Go to: https://dash.cloudflare.com"
    echo "  2. Pages → $PROJECT_NAME → Settings → Environment Variables"
    echo "  3. Add variable: GITHUB_OWNER = $GITHUB_OWNER"
    echo "  4. Add variable: GITHUB_REPO = $GITHUB_REPO"
    echo ""
    echo -e "${YELLOW}Or run Terraform apply again to set them automatically:${NC}"
    echo "  cd tofu && tofu apply -var-file=config.tfvars"
else
    echo ""
    echo -e "${YELLOW}⚠ Could not determine GITHUB_OWNER/GITHUB_REPO automatically${NC}"
    echo -e "${YELLOW}  Please set them manually in Cloudflare Dashboard${NC}"
fi

echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo -e "${YELLOW}To verify, check Cloudflare Dashboard:${NC}"
echo "  Pages → $PROJECT_NAME → Settings → Environment Variables"
echo ""
echo -e "${CYAN}Required variables:${NC}"
echo "  - GITHUB_TOKEN (Secret) ✓"
if [ -n "$GITHUB_OWNER" ] && [ -n "$GITHUB_REPO" ]; then
    echo "  - GITHUB_OWNER = $GITHUB_OWNER ✓"
    echo "  - GITHUB_REPO = $GITHUB_REPO ✓"
else
    echo "  - GITHUB_OWNER (set manually)"
    echo "  - GITHUB_REPO (set manually)"
fi
echo ""
