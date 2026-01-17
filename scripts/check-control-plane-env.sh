#!/bin/bash
# Quick check script to verify Control Plane environment variables

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

echo "Checking Cloudflare Pages environment variables for: $PROJECT_NAME"
echo ""
echo "Go to: https://dash.cloudflare.com"
echo "Pages → $PROJECT_NAME → Settings → Environment Variables"
echo ""
echo "Required variables:"
echo "  ✓ GITHUB_TOKEN (Secret) - Set via: make setup-control-plane-secrets"
echo "  ✓ GITHUB_OWNER (Variable) - Should be set by Terraform"
echo "  ✓ GITHUB_REPO (Variable) - Should be set by Terraform"
echo ""
echo "If GITHUB_OWNER/GITHUB_REPO are missing, run:"
echo "  cd tofu && tofu apply -var-file=config.tfvars"
echo ""
