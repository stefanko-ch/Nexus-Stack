.PHONY: status ssh logs urls secrets ssh-setup

# =============================================================================
# Nexus-Stack - Development/Debugging Tools
# =============================================================================
# ⚠️  WARNING: This Makefile is for debugging/management ONLY.
# 
# Production deployments use GitHub Actions exclusively.
# Local deployment is NOT supported as it bypasses the Control Plane architecture.
#
# For production deployment, see: docs/setup-guide.md
# =============================================================================

# Domain for SSH setup (extracted from GitHub secrets or manual input)
DOMAIN ?= your-domain.com

# Check if SSH to nexus is configured
check-ssh:
	@if ! ssh -o ConnectTimeout=2 -o BatchMode=yes nexus exit 2>/dev/null; then \
		echo "⚠️  SSH to 'nexus' not configured. Run 'make ssh-setup' first."; \
		echo ""; \
		echo "SSH setup is only needed for debugging. Production uses GitHub Actions."; \
		exit 1; \
	fi

# Show running containers (requires SSH)
status: check-ssh
	@ssh nexus 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'

# SSH into server (requires SSH config)
ssh: check-ssh
	@ssh nexus

# View container logs (usage: make logs SERVICE=excalidraw)
SERVICE ?= it-tools
logs: check-ssh
	@ssh nexus 'docker logs $(SERVICE) --tail 50'

# Show service URLs
urls:
	@echo "⚠️  Service URLs are available in the Control Plane UI:"
	@echo "   https://control.$(DOMAIN)"
	@echo ""
	@echo "Or check the info page:"
	@echo "   https://info.$(DOMAIN)"

# Show service credentials
secrets:
	@echo "⚠️  Service credentials are available in the Control Plane UI."
	@echo ""
	@echo "Use the 'Email Credentials' button in the Control Plane:"
	@echo "   https://control.$(DOMAIN)"
	@echo ""
	@echo "Or check Infisical for stored credentials:"
	@echo "   https://infisical.$(DOMAIN)"

# Setup SSH config (one-time, for debugging)
ssh-setup:
	@echo "🔧 SSH Setup for Debugging"
	@echo "=========================="
	@echo ""
	@echo "This is optional and only needed for debugging tools (status, logs, ssh)."
	@echo "Production uses GitHub Actions - no SSH needed."
	@echo ""
	@echo "Add the following to ~/.ssh/config:"
	@echo ""
	@echo "Host nexus"
	@echo "  HostName ssh.$(DOMAIN)"
	@echo "  User root"
	@echo "  ProxyCommand cloudflared access ssh --hostname %h"
	@echo ""
	@echo "Requirements:"
	@echo "  - cloudflared installed (brew install cloudflared)"
	@echo "  - Cloudflare Access configured for ssh.$(DOMAIN)"
	@echo ""
	@echo "Test with: ssh nexus"
