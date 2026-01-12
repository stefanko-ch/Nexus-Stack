.PHONY: up down status ssh logs init plan urls secrets

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
	@echo ""
	@echo "🔐 Revoking Cloudflare Zero Trust sessions..."
	@CLOUDFLARE_API_TOKEN=$$(grep -E '^cloudflare_api_token\s*=' tofu/config.tfvars 2>/dev/null | sed 's/.*"\(.*\)"/\1/'); \
	CLOUDFLARE_ACCOUNT_ID=$$(grep -E '^cloudflare_account_id\s*=' tofu/config.tfvars 2>/dev/null | sed 's/.*"\(.*\)"/\1/'); \
	ADMIN_EMAIL=$$(grep -E '^admin_email\s*=' tofu/config.tfvars 2>/dev/null | sed 's/.*"\(.*\)"/\1/'); \
	if [ -n "$$CLOUDFLARE_API_TOKEN" ] && [ -n "$$CLOUDFLARE_ACCOUNT_ID" ] && [ -n "$$ADMIN_EMAIL" ]; then \
		RESPONSE=$$(curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$$CLOUDFLARE_ACCOUNT_ID/access/organizations/revoke_user" \
			-H "Authorization: Bearer $$CLOUDFLARE_API_TOKEN" \
			-H "Content-Type: application/json" \
			-d "{\"email\": \"$$ADMIN_EMAIL\"}"); \
		if echo "$$RESPONSE" | tr -d '\n' | grep -q '"success"[[:space:]]*:[[:space:]]*true'; then \
			echo "  ✓ Revoked Zero Trust sessions for $$ADMIN_EMAIL"; \
		else \
			echo "  ⚠️  Could not revoke sessions (may require additional API permissions)"; \
		fi; \
	else \
		echo "  ⚠️  Could not read config, skipping session revocation"; \
	fi
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

# Show service credentials
secrets:
	@echo "🔐 Service Credentials"
	@echo "======================"
	@if [ -f tofu/terraform.tfstate ]; then \
		SECRETS_JSON=$$(cd tofu && tofu output -json secrets 2>/dev/null || echo "{}"); \
		ADMIN_EMAIL=$$(echo "$$SECRETS_JSON" | jq -r '.admin_email // empty'); \
		ADMIN_USER=$$(echo "$$SECRETS_JSON" | jq -r '.admin_username // "admin"'); \
		DOMAIN=$$(grep -E '^domain\s*=' tofu/config.tfvars 2>/dev/null | sed 's/.*"\(.*\)"/\1/'); \
		echo ""; \
		echo "Infisical:"; \
		SUBDOMAIN=$$(grep -A5 'infisical.*=' tofu/config.tfvars | grep 'subdomain' | sed 's/.*"\(.*\)"/\1/'); \
		echo "  URL:      https://$$SUBDOMAIN.$$DOMAIN"; \
		echo "  User:     $$ADMIN_EMAIL"; \
		echo "  Password: $$(echo "$$SECRETS_JSON" | jq -r '.infisical_admin_password')"; \
		echo ""; \
		echo "Portainer:"; \
		SUBDOMAIN=$$(grep -A5 'portainer.*=' tofu/config.tfvars | grep 'subdomain' | sed 's/.*"\(.*\)"/\1/'); \
		echo "  URL:      https://$$SUBDOMAIN.$$DOMAIN"; \
		echo "  User:     $$ADMIN_USER"; \
		echo "  Password: $$(echo "$$SECRETS_JSON" | jq -r '.portainer_admin_password')"; \
		echo ""; \
		echo "Uptime Kuma:"; \
		SUBDOMAIN=$$(grep -A5 'uptime-kuma.*=' tofu/config.tfvars | grep 'subdomain' | sed 's/.*"\(.*\)"/\1/'); \
		echo "  URL:      https://$$SUBDOMAIN.$$DOMAIN"; \
		echo "  User:     $$ADMIN_USER"; \
		echo "  Password: $$(echo "$$SECRETS_JSON" | jq -r '.kuma_admin_password')"; \
	else \
		echo "⚠️  No OpenTofu state found. Run 'make up' first."; \
	fi
