#!/bin/bash
set -e

# =============================================================================
# Setup Control Panel Secrets
# =============================================================================
# This script helps set up the required environment variables for the Control Panel
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
echo "║          Control Panel Secrets Setup                          ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if wrangler is available
if ! command -v npx &> /dev/null; then
    echo -e "${RED}Error: npx is required but not installed${NC}"
    exit 1
fi

# Get project name from Terraform output or config
if [ -f "$TOFU_DIR/config.tfvars" ]; then
    SERVER_NAME=$(grep -E '^server_name\s*=' "$TOFU_DIR/config.tfvars" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' || echo "nexus")
else
    SERVER_NAME="nexus"
fi

PROJECT_NAME="${SERVER_NAME}-control"

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

# Set GITHUB_TOKEN secret
echo -e "${YELLOW}Setting GITHUB_TOKEN secret...${NC}"
echo "$GITHUB_TOKEN" | npx wrangler@latest pages secret put GITHUB_TOKEN --project-name="$PROJECT_NAME"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ GITHUB_TOKEN secret set successfully${NC}"
else
    echo -e "${RED}✗ Failed to set GITHUB_TOKEN secret${NC}"
    exit 1
fi

echo ""
echo -e "${CYAN}Note: GITHUB_OWNER and GITHUB_REPO are set automatically by Terraform${NC}"
echo -e "${CYAN}      They should already be configured in Cloudflare Pages.${NC}"
echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo -e "${YELLOW}To verify, check Cloudflare Dashboard:${NC}"
echo "  Pages → $PROJECT_NAME → Settings → Environment Variables"
echo ""
