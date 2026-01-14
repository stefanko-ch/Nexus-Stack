.PHONY: up down status ssh logs init plan urls secrets destroy deploy-control-panel

# =============================================================================
# Nexus-Stack - Makefile
# =============================================================================
# Simple Docker deployment with Cloudflare Zero Trust
#
# Secrets are read from .env file (auto-loaded) or environment variables.
# For CI/CD: Set secrets as GitHub Actions repository secrets (TF_VAR_*)
# =============================================================================

# Auto-load .env file if it exists (handles 'export VAR="value"' format)
# Note: Simple format only - values must not contain '=' or unescaped quotes
ifneq (,$(wildcard ./.env))
    # Parse .env: strip 'export ', quotes, comments, and empty lines
    $(foreach line, $(shell grep -v '^\#' .env | grep '=' | sed 's/^export //; s/"\([^"]*\)"/\1/g' 2>/dev/null), \
        $(eval $(line)))
    export
endif

# Check if required environment variables are set
check-env:
	@if [ -z "$$TF_VAR_cloudflare_api_token" ] || [ -z "$$TF_VAR_cloudflare_account_id" ] || [ -z "$$TF_VAR_hcloud_token" ]; then \
		echo "❌ Required environment variables not set!"; \
		echo ""; \
		echo "Please create .env file with your secrets:"; \
		echo "  cp .env.example .env"; \
		echo "  nano .env"; \
		exit 1; \
	fi

# First-time setup: copy config template, create R2 bucket, and initialize OpenTofu
init:
	@echo "🚀 Nexus-Stack - First Time Setup"
	@echo "=================================="
	@if [ ! -f tofu/config.tfvars ]; then \
		cp tofu/config.tfvars.example tofu/config.tfvars; \
		echo "✅ Created tofu/config.tfvars from template"; \
		echo ""; \
		echo "📝 Next steps:"; \
		echo "   1. Edit tofu/config.tfvars (domain, zone_id, admin_email)"; \
		echo "   2. Copy .env.example to .env and add your secrets"; \
		echo "   3. Run: source .env && make init"; \
		exit 0; \
	fi
	@if [ -z "$$TF_VAR_cloudflare_api_token" ] || [ -z "$$TF_VAR_cloudflare_account_id" ]; then \
		echo "❌ Environment variables not set!"; \
		echo ""; \
		echo "Run: source .env && make init"; \
		exit 1; \
	fi
	@echo ""
	@chmod +x scripts/init-r2-state.sh
	@./scripts/init-r2-state.sh
	@echo ""
	@echo "🔧 Initializing OpenTofu..."
	@# Check for existing local state (should not exist for fresh setups)
	@if [ -f tofu/terraform.tfstate ]; then \
		echo "⚠️  Local state file found (tofu/terraform.tfstate)"; \
		echo "   This project uses R2 remote state. If you have existing infrastructure,"; \
		echo "   you need to migrate it manually. Otherwise, delete the local state:"; \
		echo "   rm -f tofu/terraform.tfstate tofu/terraform.tfstate.backup"; \
		exit 1; \
	fi
	@# Clean up terraform cache for fresh init
	@rm -rf tofu/.terraform tofu/.terraform.lock.hcl
	@if [ -f tofu/.r2-credentials ]; then \
		. tofu/.r2-credentials && \
		export AWS_ACCESS_KEY_ID="$$R2_ACCESS_KEY_ID" && \
		export AWS_SECRET_ACCESS_KEY="$$R2_SECRET_ACCESS_KEY" && \
		cd tofu && tofu init -backend-config=backend.hcl; \
	else \
		echo "❌ R2 credentials not found. Bootstrap may have failed."; \
		exit 1; \
	fi
	@echo ""
	@echo "✅ Initialization complete! Run 'source .env && make up' to deploy."

# Full deployment: infrastructure + containers
up: check-env
	@if [ ! -f tofu/.r2-credentials ]; then \
		echo "❌ R2 credentials not found. Run 'make init' first."; \
		exit 1; \
	fi
	@echo "🏗️  Creating infrastructure with OpenTofu..."
	@. tofu/.r2-credentials && \
		export AWS_ACCESS_KEY_ID="$$R2_ACCESS_KEY_ID" && \
		export AWS_SECRET_ACCESS_KEY="$$R2_SECRET_ACCESS_KEY" && \
		cd tofu && tofu init -backend-config=backend.hcl -reconfigure >/dev/null 2>&1 || true && \
		tofu apply -var-file=config.tfvars -auto-approve
	@echo ""
	@chmod +x scripts/deploy.sh
	@./scripts/deploy.sh
	@echo ""
	@echo "📦 Deploying Control Panel..."
	@$(MAKE) deploy-control-panel || echo "⚠️  Control Panel deployment skipped (set CLOUDFLARE_API_TOKEN to enable)"

# Teardown infrastructure (keeps R2 state for re-deploy)
teardown: check-env
	@echo "💥 Tearing down infrastructure..."
	@echo ""
	@echo "🔐 Revoking Cloudflare Zero Trust sessions..."
	@ADMIN_EMAIL=$$(grep -E '^admin_email\s*=' tofu/config.tfvars 2>/dev/null | sed 's/.*"\(.*\)"/\1/'); \
	if [ -n "$$TF_VAR_cloudflare_api_token" ] && [ -n "$$TF_VAR_cloudflare_account_id" ] && [ -n "$$ADMIN_EMAIL" ]; then \
		RESPONSE=$$(curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$$TF_VAR_cloudflare_account_id/access/organizations/revoke_user" \
			-H "Authorization: Bearer $$TF_VAR_cloudflare_api_token" \
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
	@if [ -f tofu/.r2-credentials ]; then \
		. tofu/.r2-credentials && \
		export AWS_ACCESS_KEY_ID="$$R2_ACCESS_KEY_ID" && \
		export AWS_SECRET_ACCESS_KEY="$$R2_SECRET_ACCESS_KEY" && \
		cd tofu && tofu destroy -var-file=config.tfvars -auto-approve; \
	else \
		cd tofu && tofu destroy -var-file=config.tfvars -auto-approve; \
	fi

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
plan: check-env
	@if [ -f tofu/.r2-credentials ]; then \
		. tofu/.r2-credentials && \
		export AWS_ACCESS_KEY_ID="$$R2_ACCESS_KEY_ID" && \
		export AWS_SECRET_ACCESS_KEY="$$R2_SECRET_ACCESS_KEY" && \
		cd tofu && tofu plan -var-file=config.tfvars; \
	else \
		echo "❌ R2 credentials not found. Run 'make init' first."; \
		exit 1; \
	fi

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
		echo ""; \
		echo "Grafana:"; \
		SUBDOMAIN=$$(grep -A5 'grafana.*=' tofu/config.tfvars | grep 'subdomain' | sed 's/.*"\(.*\)"/\1/'); \
		echo "  URL:      https://$$SUBDOMAIN.$$DOMAIN"; \
		echo "  User:     $$ADMIN_USER"; \
		echo "  Password: $$(echo "$$SECRETS_JSON" | jq -r '.grafana_admin_password')"; \
		echo ""; \
		echo "Kestra:"; \
		SUBDOMAIN=$$(grep -A5 'kestra.*=' tofu/config.tfvars | grep 'subdomain' | sed 's/.*"\(.*\)"/\1/'); \
		echo "  URL:      https://$$SUBDOMAIN.$$DOMAIN"; \
		echo "  User:     $$ADMIN_EMAIL"; \
		echo "  Password: $$(echo "$$SECRETS_JSON" | jq -r '.kestra_admin_password')"; \
		echo ""; \
		echo "n8n:"; \
		SUBDOMAIN=$$(grep -A5 'n8n.*=' tofu/config.tfvars | grep 'subdomain' | sed 's/.*"\(.*\)"/\1/'); \
		echo "  URL:      https://$$SUBDOMAIN.$$DOMAIN"; \
		echo "  User:     $$ADMIN_USER"; \
		echo "  Password: $$(echo "$$SECRETS_JSON" | jq -r '.n8n_admin_password')"; \
	else \
		echo "⚠️  No OpenTofu state found. Run 'make up' first."; \
	fi

# Full cleanup: teardown infrastructure AND remove R2 bucket/credentials
destroy-all: teardown
	@echo ""
	@echo "🧹 Cleaning up R2 state backend..."
	@if [ -z "$$TF_VAR_cloudflare_api_token" ] || [ -z "$$TF_VAR_cloudflare_account_id" ]; then \
		echo "  ⚠️  Environment variables not set, skipping R2 cleanup"; \
	else \
		if [ -f tofu/.r2-credentials ]; then \
			echo "  Deleting state files from R2 bucket..."; \
			. tofu/.r2-credentials && \
			export AWS_ACCESS_KEY_ID="$$R2_ACCESS_KEY_ID" && \
			export AWS_SECRET_ACCESS_KEY="$$R2_SECRET_ACCESS_KEY" && \
			curl -s -X DELETE \
				"https://$$TF_VAR_cloudflare_account_id.r2.cloudflarestorage.com/nexus-terraform-state/terraform.tfstate" \
				--aws-sigv4 "aws:amz:auto:s3" \
				--user "$$AWS_ACCESS_KEY_ID:$$AWS_SECRET_ACCESS_KEY" > /dev/null 2>&1 && \
			curl -s -X DELETE \
				"https://$$TF_VAR_cloudflare_account_id.r2.cloudflarestorage.com/nexus-terraform-state/.terraform.lock.hcl" \
				--aws-sigv4 "aws:amz:auto:s3" \
				--user "$$AWS_ACCESS_KEY_ID:$$AWS_SECRET_ACCESS_KEY" > /dev/null 2>&1 && \
			echo "  ✓ State files deleted"; \
		fi; \
		echo "  Deleting R2 bucket 'nexus-terraform-state'..."; \
		RESPONSE=$$(curl -s -X DELETE \
			"https://api.cloudflare.com/client/v4/accounts/$$TF_VAR_cloudflare_account_id/r2/buckets/nexus-terraform-state" \
			-H "Authorization: Bearer $$TF_VAR_cloudflare_api_token"); \
		if echo "$$RESPONSE" | grep -q '"success":true'; then \
			echo "  ✓ R2 bucket deleted"; \
		else \
			echo "  ⚠️  Could not delete R2 bucket (may already be deleted or not empty)"; \
		fi; \
		echo "  Deleting R2 API token 'nexus-r2-terraform-state'..."; \
		TOKEN_ID=$$(curl -s "https://api.cloudflare.com/client/v4/user/tokens" \
			-H "Authorization: Bearer $$TF_VAR_cloudflare_api_token" | \
			grep -o '"id":"[^"]*","name":"nexus-r2-terraform-state"' | \
			sed 's/"id":"//;s/","name":"nexus-r2-terraform-state"//'); \
		if [ -n "$$TOKEN_ID" ]; then \
			curl -s -X DELETE "https://api.cloudflare.com/client/v4/user/tokens/$$TOKEN_ID" \
				-H "Authorization: Bearer $$TF_VAR_cloudflare_api_token" > /dev/null; \
			echo "  ✓ R2 API token deleted"; \
		else \
			echo "  ⚠️  R2 API token not found (may already be deleted)"; \
		fi; \
	fi
	@echo ""
	@echo "🗑️  Removing local files..."
	@rm -f tofu/.r2-credentials tofu/backend.hcl
	@echo "  ✓ Removed .r2-credentials and backend.hcl"
	@echo ""
	@echo "✅ Full cleanup complete!"
	@echo ""
	@echo "To start fresh, run:"
	@echo "  source .env && make init"

# Deploy Control Panel to Cloudflare Pages
deploy-control-panel:
	@if [ -z "$$TF_VAR_cloudflare_api_token" ]; then \
		echo "⚠️  CLOUDFLARE_API_TOKEN not set - skipping Control Panel deployment"; \
		echo "   Set TF_VAR_cloudflare_api_token in .env to enable auto-deployment"; \
		exit 0; \
	fi
	@echo "📦 Deploying Control Panel to Cloudflare Pages..."
	@if [ ! -d "control-panel/pages/functions" ]; then \
		echo "❌ Error: control-panel/pages/functions/ not found!"; \
		exit 1; \
	fi
	@cd control-panel/pages && \
		npx wrangler@latest pages deploy . \
			--project-name=nexus-control \
			--branch=main \
			--commit-message="Auto-deploy via Makefile"
	@echo "✅ Control Panel deployed!"
