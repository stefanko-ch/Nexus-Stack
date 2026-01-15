#!/bin/bash
# Quick check script to verify Control Plane environment variables

PROJECT_NAME="nexus-control-plane"

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
