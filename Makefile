.PHONY: up down status ssh logs init plan urls

# =============================================================================
# Nexus-Stack - Makefile
# =============================================================================
# Simple Docker deployment with Cloudflare Zero Trust
# =============================================================================

# First-time setup: copy config template and initialize OpenTofu
init:
	@echo "🚀 Nexus-Stack - First Time Setup"
	@echo "=================================="
	@if [ ! -f tofu/config.tfvars ]; then \
		cp tofu/config.tfvars.example tofu/config.tfvars; \
		echo "✅ Created tofu/config.tfvars from template"; \
		echo ""; \
		echo "📝 Next steps:"; \
		echo "  1. Edit tofu/config.tfvars with your:"; \
		echo "     - Hetzner Cloud API token"; \
		echo "     - Cloudflare API token, Account ID, Zone ID"; \
		echo "     - Your domain and email"; \
		echo ""; \
		echo "  2. Run: make up"; \
	else \
		echo "⚠️  tofu/config.tfvars already exists"; \
	fi
	@cd tofu && tofu init

# Full deployment: infrastructure + containers
up:
	@echo "🏗️  Creating infrastructure with OpenTofu..."
	cd tofu && tofu apply -var-file=config.tfvars -auto-approve
	@echo ""
	@chmod +x scripts/deploy.sh
	@./scripts/deploy.sh

# Destroy everything
down:
	@echo "💥 Destroying infrastructure..."
	@DOMAIN=$$(grep -E '^domain\s*=' tofu/config.tfvars 2>/dev/null | sed 's/.*"\(.*\)"/\1/'); \
	if [ -n "$$DOMAIN" ]; then \
		ssh-keygen -R "ssh.$$DOMAIN" 2>/dev/null || true; \
		echo "🔑 Removed SSH known_hosts entry for ssh.$$DOMAIN"; \
	fi
	cd tofu && tofu destroy -var-file=config.tfvars -auto-approve

# Show running containers
status:
	@ssh nexus 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'

# SSH into server
ssh:
	@ssh nexus

# View container logs (usage: make logs or make logs SERVICE=excalidraw)
SERVICE ?= it-tools
logs:
	@ssh nexus 'docker logs $(SERVICE) --tail 50'

# Plan changes without applying
plan:
	cd tofu && tofu plan -var-file=config.tfvars

# Show service URLs
urls:
	@cd tofu && tofu output -json service_urls | jq -r 'to_entries | .[] | "\(.key): \(.value)"'
