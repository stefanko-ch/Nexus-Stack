#!/bin/bash
set -euo pipefail

# =============================================================================
# Nexus-Stack Deployment Script
# =============================================================================
# Called by GitHub Actions spin-up workflow after infrastructure is provisioned.
# Syncs Docker stacks to server and starts enabled containers.
# =============================================================================

# =============================================================================
# Nexus-Stack Deploy Script
# Runs after tofu apply to start containers
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TOFU_DIR="$PROJECT_ROOT/tofu/stack"
STACKS_DIR="$PROJECT_ROOT/stacks"
REMOTE_STACKS_DIR="/opt/docker-server/stacks"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
DIM='\033[2m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                   🚀 Nexus-Stack Deploy                       ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# -----------------------------------------------------------------------------
# Check OpenTofu state and load R2 credentials
# -----------------------------------------------------------------------------

# Load R2 credentials for remote state access
if [ -f "$PROJECT_ROOT/tofu/.r2-credentials" ]; then
    source "$PROJECT_ROOT/tofu/.r2-credentials"
    export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
    export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
fi

# Check if we can access state
cd "$TOFU_DIR"
if ! tofu state list >/dev/null 2>&1; then
    echo -e "${RED}Error: No OpenTofu state found. Infrastructure must be provisioned first.${NC}"
    exit 1
fi
cd "$PROJECT_ROOT"

# Get domain and admin email from config
DOMAIN=$(grep -E '^domain\s*=' "$TOFU_DIR/config.tfvars" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' || echo "")
ADMIN_EMAIL=$(grep -E '^admin_email\s*=' "$TOFU_DIR/config.tfvars" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' || echo "admin@$DOMAIN")
OM_PRINCIPAL_DOMAIN=$(echo "$ADMIN_EMAIL" | cut -d'@' -f2)
USER_EMAIL=$(grep -E '^user_email\s*=' "$TOFU_DIR/config.tfvars" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' || echo "")
# Fallback to ADMIN_EMAIL if USER_EMAIL is not set
USER_EMAIL=${USER_EMAIL:-$ADMIN_EMAIL}
# Gitea user username derived from user_email (part before @)
GITEA_USER_USERNAME="${USER_EMAIL%%@*}"
SSH_HOST="ssh.${DOMAIN}"

if [ -z "$DOMAIN" ]; then
    echo -e "${RED}Error: Could not read domain from config.tfvars${NC}"
    exit 1
fi

# Get secrets from OpenTofu
echo -e "${YELLOW}[0/7] Loading secrets from OpenTofu...${NC}"
SECRETS_JSON=$(cd "$TOFU_DIR" && tofu output -json secrets 2>/dev/null || echo "{}")

if [ "$SECRETS_JSON" = "{}" ]; then
    echo -e "${RED}Error: Could not read secrets from OpenTofu state${NC}"
    exit 1
fi

# Extract secrets
ADMIN_USERNAME=$(echo "$SECRETS_JSON" | jq -r '.admin_username // "admin"')
INFISICAL_PASS=$(echo "$SECRETS_JSON" | jq -r '.infisical_admin_password // empty')
INFISICAL_ENCRYPTION_KEY=$(echo "$SECRETS_JSON" | jq -r '.infisical_encryption_key // empty')
INFISICAL_AUTH_SECRET=$(echo "$SECRETS_JSON" | jq -r '.infisical_auth_secret // empty')
INFISICAL_DB_PASSWORD=$(echo "$SECRETS_JSON" | jq -r '.infisical_db_password // empty')
PORTAINER_PASS=$(echo "$SECRETS_JSON" | jq -r '.portainer_admin_password // empty')
KUMA_PASS=$(echo "$SECRETS_JSON" | jq -r '.kuma_admin_password // empty')
GRAFANA_PASS=$(echo "$SECRETS_JSON" | jq -r '.grafana_admin_password // empty')
KESTRA_PASS=$(echo "$SECRETS_JSON" | jq -r '.kestra_admin_password // empty')
KESTRA_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.kestra_db_password // empty')
N8N_PASS=$(echo "$SECRETS_JSON" | jq -r '.n8n_admin_password // empty')
METABASE_PASS=$(echo "$SECRETS_JSON" | jq -r '.metabase_admin_password // empty')
CLOUDBEAVER_PASS=$(echo "$SECRETS_JSON" | jq -r '.cloudbeaver_admin_password // empty')
MAGE_PASS=$(echo "$SECRETS_JSON" | jq -r '.mage_admin_password // empty')
MINIO_ROOT_PASS=$(echo "$SECRETS_JSON" | jq -r '.minio_root_password // empty')
HOPPSCOTCH_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.hoppscotch_db_password // empty')
HOPPSCOTCH_JWT=$(echo "$SECRETS_JSON" | jq -r '.hoppscotch_jwt_secret // empty')
HOPPSCOTCH_SESSION=$(echo "$SECRETS_JSON" | jq -r '.hoppscotch_session_secret // empty')
HOPPSCOTCH_ENCRYPTION=$(echo "$SECRETS_JSON" | jq -r '.hoppscotch_encryption_key // empty')
MELTANO_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.meltano_db_password // empty')
SODA_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.soda_db_password // empty')
REDPANDA_ADMIN_PASS=$(echo "$SECRETS_JSON" | jq -r '.redpanda_admin_password // empty')
POSTGRES_PASS=$(echo "$SECRETS_JSON" | jq -r '.postgres_password // empty')
PGADMIN_PASS=$(echo "$SECRETS_JSON" | jq -r '.pgadmin_password // empty')
PREFECT_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.prefect_db_password // empty')
RUSTFS_ROOT_PASS=$(echo "$SECRETS_JSON" | jq -r '.rustfs_root_password // empty')
SEAWEEDFS_ADMIN_PASS=$(echo "$SECRETS_JSON" | jq -r '.seaweedfs_admin_password // empty')
GARAGE_ADMIN_TOKEN=$(echo "$SECRETS_JSON" | jq -r '.garage_admin_token // empty')
GARAGE_RPC_SECRET=$(echo "$SECRETS_JSON" | jq -r '.garage_rpc_secret // empty')
LAKEFS_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.lakefs_db_password // empty')
LAKEFS_ENCRYPT_SECRET=$(echo "$SECRETS_JSON" | jq -r '.lakefs_encrypt_secret // empty')
LAKEFS_ADMIN_ACCESS_KEY=$(echo "$SECRETS_JSON" | jq -r '.lakefs_admin_access_key // empty')
LAKEFS_ADMIN_SECRET_KEY=$(echo "$SECRETS_JSON" | jq -r '.lakefs_admin_secret_key // empty')
HETZNER_S3_SERVER=$(echo "$SECRETS_JSON" | jq -r '.hetzner_s3_server // empty')
HETZNER_S3_REGION=$(echo "$SECRETS_JSON" | jq -r '.hetzner_s3_region // empty')
HETZNER_S3_ACCESS_KEY=$(echo "$SECRETS_JSON" | jq -r '.hetzner_s3_access_key // empty')
HETZNER_S3_SECRET_KEY=$(echo "$SECRETS_JSON" | jq -r '.hetzner_s3_secret_key // empty')
HETZNER_S3_BUCKET=$(echo "$SECRETS_JSON" | jq -r '.hetzner_s3_bucket // empty')
HETZNER_S3_BUCKET_GENERAL=$(echo "$SECRETS_JSON" | jq -r '.hetzner_s3_bucket_general // empty')
FILESTASH_ADMIN_PASSWORD=$(echo "$SECRETS_JSON" | jq -r '.filestash_admin_password // empty')
WINDMILL_ADMIN_PASS=$(echo "$SECRETS_JSON" | jq -r '.windmill_admin_password // empty')
WINDMILL_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.windmill_db_password // empty')
WINDMILL_SUPERADMIN_SECRET=$(echo "$SECRETS_JSON" | jq -r '.windmill_superadmin_secret // empty')
OPENMETADATA_ADMIN_PASS=$(echo "$SECRETS_JSON" | jq -r '.openmetadata_admin_password // empty')
OPENMETADATA_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.openmetadata_db_password // empty')
OPENMETADATA_AIRFLOW_PASS=$(echo "$SECRETS_JSON" | jq -r '.openmetadata_airflow_password // empty')
OPENMETADATA_FERNET_KEY=$(echo "$SECRETS_JSON" | jq -r '.openmetadata_fernet_key // empty')
GITEA_ADMIN_PASS=$(echo "$SECRETS_JSON" | jq -r '.gitea_admin_password // empty')
GITEA_USER_PASS=$(echo "$SECRETS_JSON" | jq -r '.gitea_user_password // empty')
GITEA_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.gitea_db_password // empty')
CLICKHOUSE_ADMIN_PASS=$(echo "$SECRETS_JSON" | jq -r '.clickhouse_admin_password // empty')
WIKIJS_ADMIN_PASS=$(echo "$SECRETS_JSON" | jq -r '.wikijs_admin_password // empty')
WIKIJS_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.wikijs_db_password // empty')
WOODPECKER_AGENT_SECRET=$(echo "$SECRETS_JSON" | jq -r '.woodpecker_agent_secret // empty')
NOCODB_ADMIN_PASS=$(echo "$SECRETS_JSON" | jq -r '.nocodb_admin_password // empty')
NOCODB_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.nocodb_db_password // empty')
NOCODB_JWT_SECRET=$(echo "$SECRETS_JSON" | jq -r '.nocodb_jwt_secret // empty')
DIFY_ADMIN_PASS=$(echo "$SECRETS_JSON" | jq -r '.dify_admin_password // empty')
DIFY_DB_PASS=$(echo "$SECRETS_JSON" | jq -r '.dify_db_password // empty')
DIFY_REDIS_PASS=$(echo "$SECRETS_JSON" | jq -r '.dify_redis_password // empty')
DIFY_SECRET_KEY=$(echo "$SECRETS_JSON" | jq -r '.dify_secret_key // empty')
DIFY_WEAVIATE_API_KEY=$(echo "$SECRETS_JSON" | jq -r '.dify_weaviate_api_key // empty')
DIFY_SANDBOX_API_KEY=$(echo "$SECRETS_JSON" | jq -r '.dify_sandbox_api_key // empty')
DIFY_PLUGIN_DAEMON_KEY=$(echo "$SECRETS_JSON" | jq -r '.dify_plugin_daemon_key // empty')
DIFY_PLUGIN_INNER_API_KEY=$(echo "$SECRETS_JSON" | jq -r '.dify_plugin_inner_api_key // empty')
DOCKERHUB_USER=$(echo "$SECRETS_JSON" | jq -r '.dockerhub_username // empty')
DOCKERHUB_TOKEN=$(echo "$SECRETS_JSON" | jq -r '.dockerhub_token // empty')

# Get SSH Service Token for headless authentication
SSH_TOKEN_JSON=$(cd "$TOFU_DIR" && tofu output -json ssh_service_token 2>/dev/null || echo "{}")
CF_ACCESS_CLIENT_ID=$(echo "$SSH_TOKEN_JSON" | jq -r '.client_id // empty')
CF_ACCESS_CLIENT_SECRET=$(echo "$SSH_TOKEN_JSON" | jq -r '.client_secret // empty')

echo -e "${GREEN}  ✓ Secrets loaded (admin user: $ADMIN_USERNAME)${NC}"

# Get image versions from OpenTofu
echo ""
echo -e "${YELLOW}Loading image versions...${NC}"
IMAGE_VERSIONS_JSON=$(cd "$TOFU_DIR" && tofu output -json image_versions 2>/dev/null || echo "{}")
echo -e "${GREEN}  ✓ Image versions loaded${NC}"

# Clean old SSH known_hosts entries
SERVER_IP=$(cd "$TOFU_DIR" && tofu output -raw server_ip 2>/dev/null || echo "")
[ -n "$SSH_HOST" ] && ssh-keygen -R "$SSH_HOST" 2>/dev/null || true
[ -n "$SERVER_IP" ] && ssh-keygen -R "$SERVER_IP" 2>/dev/null || true

# -----------------------------------------------------------------------------
# Setup SSH Config with Service Token (replaces existing config)
# -----------------------------------------------------------------------------
SSH_CONFIG="$HOME/.ssh/config"

echo -e "${YELLOW}[1/7] Configuring SSH access...${NC}"
mkdir -p "$HOME/.ssh"

# Remove old nexus config if exists (to update with token)
if grep -q "^Host nexus$" "$SSH_CONFIG" 2>/dev/null; then
    # Create temp file without the nexus block
    # This approach handles blocks correctly regardless of position
    awk '
        /^Host nexus$/ { skip=1; next }
        /^Host / && skip { skip=0 }
        !skip { print }
    ' "$SSH_CONFIG" > "$SSH_CONFIG.tmp" && mv "$SSH_CONFIG.tmp" "$SSH_CONFIG"
fi

# Add new config with Service Token support
if [ -n "$CF_ACCESS_CLIENT_ID" ] && [ -n "$CF_ACCESS_CLIENT_SECRET" ]; then
    cat >> "$SSH_CONFIG" << EOF

Host nexus
  HostName ${SSH_HOST}
  User root
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  ProxyCommand bash -c 'TUNNEL_SERVICE_TOKEN_ID=${CF_ACCESS_CLIENT_ID} TUNNEL_SERVICE_TOKEN_SECRET=${CF_ACCESS_CLIENT_SECRET} cloudflared access ssh --hostname %h'
EOF
    echo -e "${GREEN}  ✓ SSH config with Service Token added (no browser login required)${NC}"
    USE_SERVICE_TOKEN=true
else
    cat >> "$SSH_CONFIG" << EOF

Host nexus
  HostName ${SSH_HOST}
  User root
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  ProxyCommand cloudflared access ssh --hostname %h
EOF
    echo -e "${GREEN}  ✓ SSH config added (browser login required)${NC}"
    USE_SERVICE_TOKEN=false
fi
chmod 600 "$SSH_CONFIG"

# -----------------------------------------------------------------------------
# Cloudflare Zero Trust Authentication (Service Token required)
# -----------------------------------------------------------------------------
if [ "$USE_SERVICE_TOKEN" = "false" ]; then
    echo ""
    echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ${YELLOW}❌ Service Token Required for GitHub Actions Deployment${RED}     ║${NC}"
    echo -e "${RED}╠═══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${RED}║${NC}  Browser login is not supported in GitHub Actions.              ${RED}║${NC}"
    echo -e "${RED}║${NC}  Service Token must be configured in Terraform outputs.        ${RED}║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    exit 1
else
    echo -e "${GREEN}  ✓ Using Service Token for authentication${NC}"
fi
echo ""

# -----------------------------------------------------------------------------
# Wait for SSH connection
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[2/7] Waiting for SSH via Cloudflare Tunnel...${NC}"

# If using Service Token, test it first with retry and exponential backoff
if [ "$USE_SERVICE_TOKEN" = "true" ]; then
    echo "  Testing Service Token authentication..."
    MAX_TOKEN_RETRIES=6
    echo "  Note: Service Token may need a few seconds to propagate in Cloudflare..."
    
    # Initial wait for Service Token propagation (Cloudflare needs time to activate)
    INITIAL_WAIT=10
    echo "  Waiting ${INITIAL_WAIT}s for initial propagation..."
    sleep $INITIAL_WAIT

    TOKEN_RETRY=0
    BACKOFF=5
    SSH_ERR=$(mktemp)
    trap 'rm -f "$SSH_ERR"' EXIT

    while [ $TOKEN_RETRY -lt $MAX_TOKEN_RETRIES ]; do
        if [ $TOKEN_RETRY -eq $((MAX_TOKEN_RETRIES - 1)) ]; then
            # Last attempt: verbose SSH for full diagnostics
            echo "  Last attempt - running with verbose SSH output..."
            if ssh -v -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o BatchMode=yes nexus 'echo ok' >"$SSH_ERR" 2>&1; then
                echo -e "${GREEN}  ✓ Service Token authentication successful${NC}"
                cat "$SSH_ERR"
                rm -f "$SSH_ERR"
                trap - EXIT
                break
            fi
            # Print verbose output for diagnostics
            cat "$SSH_ERR"
        else
            if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o BatchMode=yes nexus 'echo ok' 2>"$SSH_ERR"; then
                echo -e "${GREEN}  ✓ Service Token authentication successful${NC}"
                rm -f "$SSH_ERR"
                trap - EXIT
                break
            fi
        fi
        TOKEN_RETRY=$((TOKEN_RETRY + 1))
        if [ $TOKEN_RETRY -lt $MAX_TOKEN_RETRIES ]; then
            echo "  Retry $TOKEN_RETRY/$MAX_TOKEN_RETRIES - waiting ${BACKOFF}s for propagation..."
            echo -e "  ${DIM}Last error (last 3 lines):${NC}"
            tail -n 3 "$SSH_ERR" | sed 's/^/    /'
            sleep $BACKOFF
            BACKOFF=$((BACKOFF + 5))  # Linear increase: 5s, 10s, 15s, 20s, 25s
        fi
    done

    if [ $TOKEN_RETRY -eq $MAX_TOKEN_RETRIES ]; then
        echo ""
        echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║  ${YELLOW}❌ Service Token Authentication Failed${RED}                            ║${NC}"
        echo -e "${RED}╠═══════════════════════════════════════════════════════════════╣${NC}"
        echo -e "${RED}║${NC}  Service Token authentication failed after $MAX_TOKEN_RETRIES attempts.  ${RED}║${NC}"
        echo -e "${RED}║${NC}  Browser login fallback is not supported in GitHub Actions.      ${RED}║${NC}"
        echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${YELLOW}  Diagnostics:${NC}"
        echo "  SSH Host: $SSH_HOST"
        echo "  Service Token Client ID: [redacted]"
        echo "  cloudflared version: $(cloudflared --version 2>&1 || echo 'not found')"
        if command -v nslookup >/dev/null 2>&1; then
            echo "  DNS lookup for $SSH_HOST:"
            nslookup "$SSH_HOST" 2>&1 | head -6
        else
            echo "  DNS lookup: nslookup not available"
        fi
        echo ""
        echo -e "${YELLOW}  Last SSH error output:${NC}"
        cat "$SSH_ERR" 2>/dev/null || echo "    (no error output captured)"
        rm -f "$SSH_ERR"
        trap - EXIT
        echo ""
        exit 1
    fi
fi

MAX_RETRIES=15
RETRY=0
TIMEOUT=5
SSH_ERR=$(mktemp)
trap 'rm -f "$SSH_ERR"' EXIT
while [ $RETRY -lt $MAX_RETRIES ]; do
    if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=$TIMEOUT -o BatchMode=yes nexus 'echo ok' 2>"$SSH_ERR"; then
        echo -e "${GREEN}  ✓ SSH connection established${NC}"
        rm -f "$SSH_ERR"
        trap - EXIT
        break
    fi
    RETRY=$((RETRY + 1))
    if [ $RETRY -lt $MAX_RETRIES ]; then
        echo "  Attempt $RETRY/$MAX_RETRIES - waiting for tunnel..."
        echo -e "  ${DIM}Last error:${NC}"
        tail -n 1 "$SSH_ERR" | sed 's/^/    /'
        # Increase timeout gradually: 5s, 5s, 10s, 10s, 15s...
        if [ $RETRY -lt 3 ]; then
            TIMEOUT=5
            sleep 5
        elif [ $RETRY -lt 7 ]; then
            TIMEOUT=10
            sleep 10
        else
            TIMEOUT=15
            sleep 15
        fi
    fi
done

if [ $RETRY -eq $MAX_RETRIES ]; then
    echo -e "${RED}Timeout waiting for SSH. Check Cloudflare Tunnel status.${NC}"
    echo -e "${YELLOW}  Last SSH error:${NC}"
    cat "$SSH_ERR" 2>/dev/null || echo "    (no error output captured)"
    rm -f "$SSH_ERR"
    trap - EXIT
    exit 1
fi

# -----------------------------------------------------------------------------
# Mount persistent volume (if configured)
# -----------------------------------------------------------------------------
PERSISTENT_VOLUME_ID=$(cd "$TOFU_DIR" && tofu output -raw persistent_volume_id 2>/dev/null || echo "0")

if [ "$PERSISTENT_VOLUME_ID" != "0" ] && [ -n "$PERSISTENT_VOLUME_ID" ]; then
    echo ""
    echo -e "${YELLOW}  Mounting persistent volume (ID: $PERSISTENT_VOLUME_ID)...${NC}"
    ssh nexus "
        MOUNT_POINT=/mnt/nexus-data

        # Check if already mounted
        if mountpoint -q \$MOUNT_POINT 2>/dev/null; then
            echo '  Volume already mounted at /mnt/nexus-data'
        else
            mkdir -p \$MOUNT_POINT

            # Find the volume device (Hetzner volumes appear as /dev/disk/by-id/scsi-0HC_Volume_*)
            VOLUME_DEVICE=\$(ls /dev/disk/by-id/scsi-0HC_Volume_${PERSISTENT_VOLUME_ID} 2>/dev/null || echo '')
            if [ -n \"\$VOLUME_DEVICE\" ]; then
                mount \$VOLUME_DEVICE \$MOUNT_POINT
                echo '  Volume mounted at /mnt/nexus-data'
            else
                echo '  Volume device not found via scsi ID, checking automount...'
                if mount | grep -q \$MOUNT_POINT; then
                    echo '  Volume auto-mounted at /mnt/nexus-data'
                else
                    echo '  Warning: Could not mount volume - checking /dev/sdb...'
                    if [ -b /dev/sdb ]; then
                        mount /dev/sdb \$MOUNT_POINT
                        echo '  Volume mounted via /dev/sdb'
                    fi
                fi
            fi
        fi

        # Add fstab entry for persistence across reboots (if not already present)
        if ! grep -q '/mnt/nexus-data' /etc/fstab; then
            VOLUME_DEVICE=\$(ls /dev/disk/by-id/scsi-0HC_Volume_${PERSISTENT_VOLUME_ID} 2>/dev/null || echo '/dev/sdb')
            echo \"\$VOLUME_DEVICE /mnt/nexus-data ext4 defaults,nofail 0 2\" >> /etc/fstab
            echo '  fstab entry added'
        fi

        # Create service subdirectories
        mkdir -p \$MOUNT_POINT/gitea/repos
        mkdir -p \$MOUNT_POINT/gitea/lfs
        mkdir -p \$MOUNT_POINT/gitea/db

        # Gitea runs as UID 1000 (git user)
        chown -R 1000:1000 \$MOUNT_POINT/gitea/repos
        chown -R 1000:1000 \$MOUNT_POINT/gitea/lfs

        # PostgreSQL runs as UID 70 in alpine images
        chown -R 70:70 \$MOUNT_POINT/gitea/db
    "
    echo -e "${GREEN}  ✓ Persistent volume mounted${NC}"
else
    echo ""
    echo -e "${DIM}  Persistent volume not configured (persistent_volume_id=0)${NC}"
fi

# -----------------------------------------------------------------------------
# Prepare stacks with secrets
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[3/7] Preparing stacks...${NC}"

# Get enabled services from tofu output
ENABLED_SERVICES=$(cd "$TOFU_DIR" && tofu output -json enabled_services 2>/dev/null | jq -r '.[]')

# Debug logging
LOG_FILE="/tmp/debug.log"
echo "{\"location\":\"deploy.sh:264\",\"message\":\"Reading enabled services from OpenTofu output\",\"data\":{\"enabled_services\":\"$ENABLED_SERVICES\"},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true

if [ -z "$ENABLED_SERVICES" ]; then
    echo -e "${YELLOW}  Warning: No enabled services in config.tfvars${NC}"
    echo "{\"location\":\"deploy.sh:268\",\"message\":\"No enabled services found\",\"data\":{},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true
    ENABLED_SERVICES=""
fi

# Create remote stacks directory
ssh nexus "mkdir -p $REMOTE_STACKS_DIR"

# Generate global .env file with image versions and DOMAIN
echo "  Creating global .env config..."
ENV_CONTENT="# Auto-generated global config - DO NOT EDIT
# Managed by OpenTofu via image-versions.tfvars

# Domain for service URLs
DOMAIN=$DOMAIN

# Admin credentials
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_USERNAME=$ADMIN_USERNAME
USER_EMAIL=$USER_EMAIL

# Docker image versions
# Keys are transformed to environment variables by:
#   - replacing '-' with '_'
#   - converting to upper-case
#   - prefixing with 'IMAGE_'
# Example: 'node-exporter' -> 'IMAGE_NODE_EXPORTER'
"
# Parse JSON and create IMAGE_XXX=value lines
if [ "$IMAGE_VERSIONS_JSON" != "{}" ]; then
    ENV_CONTENT+=$(echo "$IMAGE_VERSIONS_JSON" | jq -r 'to_entries | .[] | "IMAGE_\(.key | gsub("-"; "_") | ascii_upcase)=\(.value)"')
fi
# Write to server
echo "$ENV_CONTENT" | ssh nexus "cat > $REMOTE_STACKS_DIR/.env"
echo -e "${GREEN}  ✓ Global .env config created (DOMAIN + image versions)${NC}"

# Generate info page if info stack is enabled
echo "{\"location\":\"deploy.sh:303\",\"message\":\"Checking if info should be generated\",\"data\":{\"enabled_services\":\"$ENABLED_SERVICES\",\"info_in_list\":$(echo "$ENABLED_SERVICES" | grep -qw "info" && echo "true" || echo "false")},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true

if echo "$ENABLED_SERVICES" | grep -qw "info"; then
    echo "  Generating info page..."
    echo "{\"location\":\"deploy.sh:305\",\"message\":\"Generating info page\",\"data\":{},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true
    "$SCRIPT_DIR/generate-info-page.sh"
    echo "{\"location\":\"deploy.sh:306\",\"message\":\"Info page generation completed\",\"data\":{\"exit_code\":$?},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true
else
    echo "{\"location\":\"deploy.sh:303\",\"message\":\"Info page NOT generated - not in enabled services\",\"data\":{},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true
fi

# Generate Infisical .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "infisical"; then
    echo "  Generating Infisical config from OpenTofu secrets..."
    cat > "$STACKS_DIR/infisical/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
ENCRYPTION_KEY=$INFISICAL_ENCRYPTION_KEY
AUTH_SECRET=$INFISICAL_AUTH_SECRET
POSTGRES_PASSWORD=$INFISICAL_DB_PASSWORD
EOF
    echo -e "${GREEN}  ✓ Infisical .env generated${NC}"
fi

# Generate Grafana .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "grafana"; then
    echo "  Generating Grafana config from OpenTofu secrets..."
    cat > "$STACKS_DIR/grafana/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
GRAFANA_ADMIN_USER=$ADMIN_USERNAME
GRAFANA_ADMIN_PASSWORD=$GRAFANA_PASS
EOF
    echo -e "${GREEN}  ✓ Grafana .env generated${NC}"
fi

# Generate Kestra .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "kestra"; then
    echo "  Generating Kestra config from OpenTofu secrets..."
    cat > "$STACKS_DIR/kestra/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
KESTRA_ADMIN_USER=$ADMIN_EMAIL
KESTRA_ADMIN_PASSWORD=$KESTRA_PASS
KESTRA_DB_PASSWORD=$KESTRA_DB_PASS
KESTRA_URL=https://kestra.${DOMAIN}
EOF
    echo -e "${GREEN}  ✓ Kestra .env generated${NC}"
fi

# Generate CloudBeaver .env from OpenTofu secrets (auto-config on first boot)
if echo "$ENABLED_SERVICES" | grep -qw "cloudbeaver"; then
    echo "  Generating CloudBeaver config from OpenTofu secrets..."
    cat > "$STACKS_DIR/cloudbeaver/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
CB_SERVER_NAME=Nexus CloudBeaver
CB_SERVER_URL=https://cloudbeaver.${DOMAIN}
CB_ADMIN_NAME=$ADMIN_USERNAME
CB_ADMIN_PASSWORD=$CLOUDBEAVER_PASS
EOF
    echo -e "${GREEN}  ✓ CloudBeaver .env generated${NC}"
fi

# Generate Mage AI .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "mage"; then
    echo "  Generating Mage AI config from OpenTofu secrets..."
    cat > "$STACKS_DIR/mage/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
MAGE_ADMIN_PASSWORD=$MAGE_PASS
EOF
    echo -e "${GREEN}  ✓ Mage AI .env generated${NC}"
fi

# Generate MinIO .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "minio"; then
    echo "  Generating MinIO config from OpenTofu secrets..."
    cat > "$STACKS_DIR/minio/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
MINIO_ROOT_USER=nexus-minio
MINIO_ROOT_PASSWORD=$MINIO_ROOT_PASS
EOF
    echo -e "${GREEN}  ✓ MinIO .env generated${NC}"
fi

# Generate RedPanda Console .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "redpanda-console"; then
    echo "  Generating RedPanda Console config from OpenTofu secrets..."
    cat > "$STACKS_DIR/redpanda-console/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
REDPANDA_ADMIN_PASS=$REDPANDA_ADMIN_PASS
EOF
    echo -e "${GREEN}  ✓ RedPanda Console .env generated${NC}"
fi

# Generate Hoppscotch .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "hoppscotch"; then
    echo "  Generating Hoppscotch config from OpenTofu secrets..."
    cat > "$STACKS_DIR/hoppscotch/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
DATABASE_URL=postgres://nexus-hoppscotch:${HOPPSCOTCH_DB_PASS}@hoppscotch-db:5432/hoppscotch
POSTGRES_PASSWORD=${HOPPSCOTCH_DB_PASS}
JWT_SECRET=${HOPPSCOTCH_JWT}
SESSION_SECRET=${HOPPSCOTCH_SESSION}
DATA_ENCRYPTION_KEY=${HOPPSCOTCH_ENCRYPTION}
REDIRECT_URL=https://hoppscotch.${DOMAIN}
WHITELISTED_ORIGINS=https://hoppscotch.${DOMAIN}
VITE_BASE_URL=https://hoppscotch.${DOMAIN}
VITE_SHORTCODE_BASE_URL=https://hoppscotch.${DOMAIN}
VITE_ADMIN_URL=https://hoppscotch.${DOMAIN}/admin
VITE_BACKEND_GQL_URL=https://hoppscotch.${DOMAIN}/backend/graphql
VITE_BACKEND_WS_URL=wss://hoppscotch.${DOMAIN}/backend/graphql
VITE_BACKEND_API_URL=https://hoppscotch.${DOMAIN}/backend/v1
VITE_ALLOWED_AUTH_PROVIDERS=EMAIL
MAILER_USE_CUSTOM_CONFIGS=true
MAILER_SMTP_ENABLE=false
TOKEN_SALT_COMPLEXITY=10
MAGIC_LINK_TOKEN_VALIDITY=3
REFRESH_TOKEN_VALIDITY=604800000
ACCESS_TOKEN_VALIDITY=86400000
ENABLE_SUBPATH_BASED_ACCESS=false
EOF
    echo -e "${GREEN}  ✓ Hoppscotch .env generated${NC}"
fi

# Generate Meltano .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "meltano"; then
    echo "  Generating Meltano config from OpenTofu secrets..."
    cat > "$STACKS_DIR/meltano/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
MELTANO_DB_PASSWORD=${MELTANO_DB_PASS}
EOF
    echo -e "${GREEN}  ✓ Meltano .env generated${NC}"
fi

# Generate Soda .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "soda"; then
    echo "  Generating Soda config from OpenTofu secrets..."
    cat > "$STACKS_DIR/soda/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
SODA_DB_PASSWORD=${SODA_DB_PASS}
EOF
    echo -e "${GREEN}  ✓ Soda .env generated${NC}"
fi

# Generate PostgreSQL .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "postgres"; then
    echo "  Generating PostgreSQL config from OpenTofu secrets..."
    cat > "$STACKS_DIR/postgres/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
POSTGRES_PASSWORD=${POSTGRES_PASS}
EOF
    echo -e "${GREEN}  ✓ PostgreSQL .env generated${NC}"
fi

# Generate pgAdmin .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "pgadmin"; then
    echo "  Generating pgAdmin config from OpenTofu secrets..."
    cat > "$STACKS_DIR/pgadmin/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
ADMIN_EMAIL=${ADMIN_EMAIL}
PGADMIN_PASSWORD=${PGADMIN_PASS}
EOF
    echo -e "${GREEN}  ✓ pgAdmin .env generated${NC}"
fi

# Generate Prefect .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "prefect"; then
    echo "  Generating Prefect config from OpenTofu secrets..."
    cat > "$STACKS_DIR/prefect/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
PREFECT_DB_PASSWORD=${PREFECT_DB_PASS}
PREFECT_UI_API_URL=https://prefect.${DOMAIN}/api
EOF
    echo -e "${GREEN}  ✓ Prefect .env generated${NC}"
fi

# Generate Windmill .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "windmill"; then
    echo "  Generating Windmill config from OpenTofu secrets..."
    cat > "$STACKS_DIR/windmill/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
WINDMILL_DB_PASSWORD=${WINDMILL_DB_PASS}
WINDMILL_SUPERADMIN_SECRET=${WINDMILL_SUPERADMIN_SECRET}
DOMAIN=${DOMAIN}
EOF
    echo -e "${GREEN}  ✓ Windmill .env generated${NC}"
fi

# Generate OpenMetadata .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "openmetadata"; then
    echo "  Generating OpenMetadata config from OpenTofu secrets..."
    cat > "$STACKS_DIR/openmetadata/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
OPENMETADATA_DB_PASSWORD=${OPENMETADATA_DB_PASS}
OPENMETADATA_AIRFLOW_PASSWORD=${OPENMETADATA_AIRFLOW_PASS}
OPENMETADATA_FERNET_KEY=${OPENMETADATA_FERNET_KEY}
OPENMETADATA_PRINCIPAL_DOMAIN=${OM_PRINCIPAL_DOMAIN}
DOMAIN=${DOMAIN}
EOF
    echo -e "${GREEN}  ✓ OpenMetadata .env generated${NC}"
fi

# Generate Gitea .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "gitea"; then
    echo "  Generating Gitea config from OpenTofu secrets..."
    cat > "$STACKS_DIR/gitea/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
GITEA_DB_PASSWORD=${GITEA_DB_PASS}
DOMAIN=${DOMAIN}
EOF
    echo -e "${GREEN}  ✓ Gitea .env generated${NC}"
fi

# Generate ClickHouse .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "clickhouse"; then
    echo "  Generating ClickHouse config from OpenTofu secrets..."
    cat > "$STACKS_DIR/clickhouse/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
CLICKHOUSE_ADMIN_PASSWORD=${CLICKHOUSE_ADMIN_PASS}
EOF
    echo -e "${GREEN}  ✓ ClickHouse .env generated${NC}"
fi

# Generate Trino .env from OpenTofu secrets (catalog connector passwords)
if echo "$ENABLED_SERVICES" | grep -qw "trino"; then
    echo "  Generating Trino .env from OpenTofu secrets..."
    cat > "$STACKS_DIR/trino/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
CLICKHOUSE_ADMIN_PASSWORD=${CLICKHOUSE_ADMIN_PASS}
POSTGRES_PASSWORD=${POSTGRES_PASS}
EOF
    echo -e "${GREEN}  ✓ Trino .env generated${NC}"
fi

# Generate RustFS .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "rustfs"; then
    echo "  Generating RustFS config from OpenTofu secrets..."
    cat > "$STACKS_DIR/rustfs/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
RUSTFS_ACCESS_KEY=nexus-rustfs
RUSTFS_SECRET_KEY=$RUSTFS_ROOT_PASS
EOF
    echo -e "${GREEN}  ✓ RustFS .env generated${NC}"
fi

# Generate SeaweedFS .env and s3.json from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "seaweedfs"; then
    echo "  Generating SeaweedFS config from OpenTofu secrets..."
    cat > "$STACKS_DIR/seaweedfs/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
SEAWEEDFS_ACCESS_KEY=nexus-seaweedfs
SEAWEEDFS_SECRET_KEY=$SEAWEEDFS_ADMIN_PASS
EOF
    # Generate S3 auth config with actual credentials
    cat > "$STACKS_DIR/seaweedfs/s3.json" << EOF
{
  "identities": [
    {
      "name": "admin",
      "credentials": [
        {
          "accessKey": "nexus-seaweedfs",
          "secretKey": "$SEAWEEDFS_ADMIN_PASS"
        }
      ],
      "actions": ["Admin", "Read", "Write", "List", "Tagging"]
    }
  ]
}
EOF
    echo -e "${GREEN}  ✓ SeaweedFS .env and s3.json generated${NC}"
fi

# Generate Garage .env and garage.toml from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "garage"; then
    echo "  Generating Garage config from OpenTofu secrets..."
    cat > "$STACKS_DIR/garage/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
GARAGE_ADMIN_TOKEN=$GARAGE_ADMIN_TOKEN
EOF
    # Generate garage.toml with admin token
    cat > "$STACKS_DIR/garage/garage.toml" << EOF
metadata_dir = "/var/lib/garage/meta"
data_dir = "/var/lib/garage/data"
db_engine = "lmdb"
replication_factor = 1

rpc_bind_addr = "[::]:3901"
rpc_secret = "$GARAGE_RPC_SECRET"

[s3_api]
s3_region = "garage"
api_bind_addr = "[::]:3900"
root_domain = ".s3.garage.localhost"

[s3_web]
bind_addr = "[::]:3902"
root_domain = ".web.garage.localhost"

[admin]
api_bind_addr = "[::]:3903"
admin_token = "$GARAGE_ADMIN_TOKEN"
EOF
    echo -e "${GREEN}  ✓ Garage .env and garage.toml generated${NC}"
fi

# Generate LakeFS .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "lakefs"; then
    echo "  Generating LakeFS config from OpenTofu secrets..."

    # Check if Hetzner Object Storage is configured
    if [ -n "$HETZNER_S3_SERVER" ] && [ -n "$HETZNER_S3_ACCESS_KEY" ] && [ -n "$HETZNER_S3_SECRET_KEY" ] && [ -n "$HETZNER_S3_BUCKET" ]; then
        echo "  Using Hetzner Object Storage as blockstore..."
        cat > "$STACKS_DIR/lakefs/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
LAKEFS_DATABASE_TYPE=postgres
LAKEFS_DATABASE_POSTGRES_CONNECTION_STRING=postgres://nexus-lakefs:${LAKEFS_DB_PASS}@lakefs-db:5432/lakefs?sslmode=disable
LAKEFS_AUTH_ENCRYPT_SECRET_KEY=${LAKEFS_ENCRYPT_SECRET}
LAKEFS_BLOCKSTORE_TYPE=s3
LAKEFS_BLOCKSTORE_S3_ENDPOINT=https://${HETZNER_S3_SERVER}
LAKEFS_BLOCKSTORE_S3_FORCE_PATH_STYLE=true
LAKEFS_BLOCKSTORE_S3_DISCOVER_BUCKET_REGION=false
LAKEFS_BLOCKSTORE_S3_REGION=${HETZNER_S3_REGION}
LAKEFS_BLOCKSTORE_S3_CREDENTIALS_ACCESS_KEY_ID=${HETZNER_S3_ACCESS_KEY}
LAKEFS_BLOCKSTORE_S3_CREDENTIALS_SECRET_ACCESS_KEY=${HETZNER_S3_SECRET_KEY}
LAKEFS_GATEWAYS_S3_DOMAIN_NAME=s3.lakefs.${DOMAIN}
# Note: LAKEFS_INSTALLATION_* vars only work with database.type=local
# Admin user is created via API in Step 7/7
POSTGRES_PASSWORD=${LAKEFS_DB_PASS}
EOF
        echo -e "${GREEN}  ✓ LakeFS .env generated (Hetzner Object Storage backend)${NC}"
    else
        echo -e "${YELLOW}  ⚠ Hetzner Object Storage not configured, using local storage${NC}"
        cat > "$STACKS_DIR/lakefs/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
LAKEFS_DATABASE_TYPE=postgres
LAKEFS_DATABASE_POSTGRES_CONNECTION_STRING=postgres://nexus-lakefs:${LAKEFS_DB_PASS}@lakefs-db:5432/lakefs?sslmode=disable
LAKEFS_AUTH_ENCRYPT_SECRET_KEY=${LAKEFS_ENCRYPT_SECRET}
LAKEFS_BLOCKSTORE_TYPE=local
LAKEFS_BLOCKSTORE_LOCAL_PATH=/data
LAKEFS_GATEWAYS_S3_DOMAIN_NAME=s3.lakefs.${DOMAIN}
# Note: LAKEFS_INSTALLATION_* vars only work with database.type=local
# Admin user is created via API in Step 7/7
POSTGRES_PASSWORD=${LAKEFS_DB_PASS}
EOF
        echo -e "${GREEN}  ✓ LakeFS .env generated (local storage backend)${NC}"
    fi
fi

# Generate Filestash .env from OpenTofu secrets
if echo "$ENABLED_SERVICES" | grep -qw "filestash"; then
    echo "  Generating Filestash config from OpenTofu secrets..."

    # Generate bcrypt hash for admin password
    if [ -n "$FILESTASH_ADMIN_PASSWORD" ]; then
        if ! command -v htpasswd >/dev/null 2>&1; then
            echo "❌ ERROR: 'htpasswd' command not found but FILESTASH_ADMIN_PASSWORD is set."
            echo "   Please install 'apache2-utils' (Debian/Ubuntu) or 'httpd-tools' (RHEL/CentOS) on the target host."
            exit 1
        fi

        FILESTASH_ADMIN_HASH=$(htpasswd -nbBC 10 admin "$FILESTASH_ADMIN_PASSWORD" 2>/dev/null | cut -d: -f2)
        if [ -z "$FILESTASH_ADMIN_HASH" ]; then
            echo "❌ ERROR: Failed to generate Filestash admin password hash with 'htpasswd'."
            exit 1
        fi
    else
        FILESTASH_ADMIN_HASH=""
    fi

    # Check if Hetzner Object Storage is configured
    if [ -n "$HETZNER_S3_SERVER" ] && [ -n "$HETZNER_S3_ACCESS_KEY" ] && [ -n "$HETZNER_S3_SECRET_KEY" ] && [ -n "$HETZNER_S3_BUCKET_GENERAL" ]; then
        echo "  Pre-configuring Filestash with Hetzner Object Storage backend..."

        # Create CONFIG_JSON with passthrough middleware for auto-connect (base64 encoded)
        # This skips the login form - users connect directly to S3
        # Authentication is handled by Cloudflare Access upstream
        # IMPORTANT: middleware params MUST be JSON strings (not objects) because
        # Filestash encrypts/decrypts these fields, and Config.Get().String()
        # returns empty for object values in the form tree
        CONFIG_JSON=$(jq -n \
          --arg access_key "${HETZNER_S3_ACCESS_KEY}" \
          --arg secret_key "${HETZNER_S3_SECRET_KEY}" \
          --arg endpoint "https://${HETZNER_S3_SERVER}" \
          --arg region "${HETZNER_S3_REGION}" \
          --arg bucket "${HETZNER_S3_BUCKET_GENERAL}" \
          '{
            connections: [{"type":"s3","label":"Hetzner Storage"}],
            middleware: {
              identity_provider: {
                type: "passthrough",
                params: ({"strategy":"direct"} | tojson)
              },
              attribute_mapping: {
                related_backend: "Hetzner Storage",
                params: ({"Hetzner Storage":{"type":"s3","access_key_id":$access_key,"secret_access_key":$secret_key,"endpoint":$endpoint,"region":$region,"path":("/"+$bucket+"/")}} | tojson)
              }
            }
          }')
        CONFIG_BASE64=$(echo "$CONFIG_JSON" | base64 | tr -d '\n')

        cat > "$STACKS_DIR/filestash/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
CONFIG_JSON=${CONFIG_BASE64}
ADMIN_PASSWORD=${FILESTASH_ADMIN_HASH}
DOMAIN=${DOMAIN}
EOF
        echo -e "${GREEN}  ✓ Filestash .env generated (S3 + admin password pre-configured)${NC}"
    else
        # Create minimal .env without S3 pre-configuration
        cat > "$STACKS_DIR/filestash/.env" << EOF
# Auto-generated - DO NOT COMMIT
# Note: S3 backend must be configured manually at /admin
ADMIN_PASSWORD=${FILESTASH_ADMIN_HASH}
DOMAIN=${DOMAIN}
EOF
        echo -e "${YELLOW}  ⚠ Filestash .env generated (admin password set, configure S3 at /admin)${NC}"
    fi
fi

# Wiki.js
if echo "$ENABLED_SERVICES" | grep -qw "wikijs" && [ -n "$WIKIJS_DB_PASS" ]; then
    cat > "$STACKS_DIR/wikijs/.env" << EOF
# Auto-generated - DO NOT COMMIT
WIKIJS_DB_PASSWORD=${WIKIJS_DB_PASS}
EOF
    echo -e "${GREEN}  ✓ Wiki.js .env generated${NC}"
fi

# Woodpecker CI
if echo "$ENABLED_SERVICES" | grep -qw "woodpecker" && [ -n "$WOODPECKER_AGENT_SECRET" ]; then
    cat > "$STACKS_DIR/woodpecker/.env" << EOF
# Auto-generated - DO NOT COMMIT
DOMAIN=${DOMAIN}
WOODPECKER_AGENT_SECRET=${WOODPECKER_AGENT_SECRET}
WOODPECKER_ADMIN=${ADMIN_USERNAME:-}
WOODPECKER_GITEA_CLIENT=${WOODPECKER_GITEA_CLIENT:-}
WOODPECKER_GITEA_SECRET=${WOODPECKER_GITEA_SECRET:-}
EOF
    echo -e "${GREEN}  ✓ Woodpecker CI .env generated${NC}"
fi

# Apache Spark
if echo "$ENABLED_SERVICES" | grep -qw "spark"; then
    cat > "$STACKS_DIR/spark/.env" << EOF
# Auto-generated - DO NOT COMMIT
HETZNER_S3_ENDPOINT=${HETZNER_S3_SERVER:+https://${HETZNER_S3_SERVER}}
HETZNER_S3_ACCESS_KEY=${HETZNER_S3_ACCESS_KEY:-}
HETZNER_S3_SECRET_KEY=${HETZNER_S3_SECRET_KEY:-}
HETZNER_S3_BUCKET=${HETZNER_S3_BUCKET_GENERAL:-}
SPARK_WORKER_CORES=${SPARK_WORKER_CORES:-2}
SPARK_WORKER_MEMORY=${SPARK_WORKER_MEMORY:-3g}
EOF
    echo -e "${GREEN}  ✓ Spark .env generated${NC}"
fi

# Jupyter PySpark
if echo "$ENABLED_SERVICES" | grep -qw "jupyter"; then
    # Set SPARK_MASTER based on whether Spark stack is enabled
    if echo "$ENABLED_SERVICES" | grep -qw "spark"; then
        JUPYTER_SPARK_MASTER="spark://spark-master:7077"
    else
        JUPYTER_SPARK_MASTER="local[*]"
    fi
    cat > "$STACKS_DIR/jupyter/.env" << EOF
# Auto-generated - DO NOT COMMIT
SPARK_MASTER=${JUPYTER_SPARK_MASTER}
HETZNER_S3_ENDPOINT=${HETZNER_S3_SERVER:+https://${HETZNER_S3_SERVER}}
HETZNER_S3_ACCESS_KEY=${HETZNER_S3_ACCESS_KEY:-}
HETZNER_S3_SECRET_KEY=${HETZNER_S3_SECRET_KEY:-}
HETZNER_S3_BUCKET=${HETZNER_S3_BUCKET_GENERAL:-}
EOF
    echo -e "${GREEN}  ✓ Jupyter PySpark .env generated${NC}"
fi

# S3 Manager
if echo "$ENABLED_SERVICES" | grep -qw "s3manager"; then
    cat > "$STACKS_DIR/s3manager/.env" << EOF
# Auto-generated - DO NOT COMMIT
ACCESS_KEY_ID=${HETZNER_S3_ACCESS_KEY:-}
SECRET_ACCESS_KEY=${HETZNER_S3_SECRET_KEY:-}
REGION=${HETZNER_S3_REGION:-}
ENDPOINT=${HETZNER_S3_SERVER:-}
USE_SSL=true
EOF
    echo -e "${GREEN}  ✓ S3 Manager .env generated${NC}"
fi

# NocoDB
if echo "$ENABLED_SERVICES" | grep -qw "nocodb" && [ -n "$NOCODB_DB_PASS" ] && [ -n "$NOCODB_ADMIN_PASS" ] && [ -n "$NOCODB_JWT_SECRET" ]; then
    echo "  Generating NocoDB config from OpenTofu secrets..."
    cat > "$STACKS_DIR/nocodb/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
NC_DB=pg://nocodb-db:5432?u=nexus-nocodb&p=${NOCODB_DB_PASS}&d=nocodb
NC_AUTH_JWT_SECRET=${NOCODB_JWT_SECRET}
NC_ADMIN_EMAIL=${ADMIN_EMAIL}
NC_ADMIN_PASSWORD=${NOCODB_ADMIN_PASS}
NC_PUBLIC_URL=https://nocodb.${DOMAIN}
NOCODB_DB_PASSWORD=${NOCODB_DB_PASS}
EOF
    echo -e "${GREEN}  ✓ NocoDB .env generated${NC}"
fi

# Dify
if echo "$ENABLED_SERVICES" | grep -qw "dify" && [ -n "$DIFY_DB_PASS" ] && [ -n "$DIFY_ADMIN_PASS" ]; then
    echo "  Generating Dify config from OpenTofu secrets..."
    cat > "$STACKS_DIR/dify/.env" << EOF
# Auto-generated from OpenTofu secrets - DO NOT COMMIT
DIFY_DB_PASSWORD=${DIFY_DB_PASS}
DIFY_REDIS_PASSWORD=${DIFY_REDIS_PASS}
DIFY_SECRET_KEY=${DIFY_SECRET_KEY}
DIFY_ADMIN_PASSWORD=${DIFY_ADMIN_PASS}
DIFY_WEAVIATE_API_KEY=${DIFY_WEAVIATE_API_KEY}
DIFY_SANDBOX_API_KEY=${DIFY_SANDBOX_API_KEY}
DIFY_PLUGIN_DAEMON_KEY=${DIFY_PLUGIN_DAEMON_KEY}
DIFY_PLUGIN_INNER_API_KEY=${DIFY_PLUGIN_INNER_API_KEY}
EOF
    echo -e "${GREEN}  ✓ Dify .env generated${NC}"
fi

# Generate Git workspace .env vars for services that integrate with Gitea
# These vars enable auto-clone of the shared workspace repo at container startup.
# The clone may fail on first deployment (Gitea starts in parallel), but succeeds
# on subsequent spin-ups. Services are restarted in Step 7 after repo creation.
# Security: Credentials are passed via GITEA_USERNAME/GITEA_PASSWORD env vars and
# injected into containers via .netrc at startup (not embedded in the repo URL).
if echo "$ENABLED_SERVICES" | grep -qw "gitea" && [ -n "$GITEA_ADMIN_PASS" ]; then
    REPO_NAME="nexus-${DOMAIN//./-}-gitea"
    # Use user credentials for service Git integration (not admin)
    GITEA_USER_USERNAME="${USER_EMAIL%%@*}"
    # Repo URL without credentials (auth via .netrc inside containers)
    GITEA_REPO_URL="http://gitea:3000/${ADMIN_USERNAME}/${REPO_NAME}.git"
    if [ -n "$GITEA_USER_PASS" ]; then
        GITEA_GIT_USER="${GITEA_USER_USERNAME}"
        GITEA_GIT_PASS="${GITEA_USER_PASS}"
        GIT_AUTHOR="${GITEA_USER_USERNAME}"
        GIT_EMAIL="${USER_EMAIL}"
    else
        # Fallback to admin if no user password available
        GITEA_GIT_USER="${ADMIN_USERNAME}"
        GITEA_GIT_PASS="${GITEA_ADMIN_PASS}"
        GIT_AUTHOR="${ADMIN_USERNAME}"
        GIT_EMAIL="${ADMIN_EMAIL}"
    fi

    for SERVICE in jupyter marimo code-server meltano prefect; do
        if echo "$ENABLED_SERVICES" | grep -qw "$SERVICE"; then
            echo "  Adding Git workspace config to $SERVICE .env..."
            ENV_FILE="$STACKS_DIR/$SERVICE/.env"
            # Idempotent: remove existing Gitea block before writing
            if [ -f "$ENV_FILE" ]; then
                sed -i '/^# >>> Gitea workspace repo/,/^# <<< Gitea workspace repo/d' "$ENV_FILE"
            fi
            cat >> "$ENV_FILE" << EOF
# >>> Gitea workspace repo (auto-generated, do not edit)
GITEA_URL=http://gitea:3000
GITEA_REPO_URL=${GITEA_REPO_URL}
GITEA_USERNAME=${GITEA_GIT_USER}
GITEA_PASSWORD=${GITEA_GIT_PASS}
GIT_AUTHOR_NAME=${GIT_AUTHOR}
GIT_AUTHOR_EMAIL=${GIT_EMAIL}
GIT_COMMITTER_NAME=${GIT_AUTHOR}
GIT_COMMITTER_EMAIL=${GIT_EMAIL}
REPO_NAME=${REPO_NAME}
# <<< Gitea workspace repo
EOF
            echo -e "${GREEN}  ✓ $SERVICE Git config added${NC}"
        fi
    done
fi

# Sync only enabled stacks
echo "{\"location\":\"deploy.sh:378\",\"message\":\"Starting stack sync\",\"data\":{\"enabled_services\":\"$ENABLED_SERVICES\"},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true

for service in $ENABLED_SERVICES; do
    echo "{\"location\":\"deploy.sh:379\",\"message\":\"Processing service for sync\",\"data\":{\"service\":\"$service\",\"stack_dir_exists\":$([ -d "$STACKS_DIR/$service" ] && echo "true" || echo "false")},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true
    if [ -d "$STACKS_DIR/$service" ]; then
        echo "  Syncing $service..."
        rsync -av "$STACKS_DIR/$service/" "nexus:$REMOTE_STACKS_DIR/$service/"
        echo "{\"location\":\"deploy.sh:382\",\"message\":\"Service synced\",\"data\":{\"service\":\"$service\",\"exit_code\":$?},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true
    else
        echo -e "${YELLOW}  Warning: Stack folder 'stacks/$service' not found - skipping${NC}"
        echo "{\"location\":\"deploy.sh:384\",\"message\":\"Stack folder not found\",\"data\":{\"service\":\"$service\"},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true
    fi
done
echo -e "${GREEN}  ✓ Stacks synced${NC}"

# -----------------------------------------------------------------------------
# Stop disabled services
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[4/7] Cleaning up disabled services...${NC}"

ENABLED_LIST=$(echo $ENABLED_SERVICES | tr '\n' ' ')

ssh nexus "
# Find all stack directories on server
for stack_dir in $REMOTE_STACKS_DIR/*/; do
    [ -d \"\$stack_dir\" ] || continue
    stack_name=\$(basename \"\$stack_dir\")
    
    # Check if this stack is in the enabled list
    if ! echo '$ENABLED_LIST' | grep -qw \"\$stack_name\"; then
        # Stack is disabled - stop and remove
        if [ -f \"\${stack_dir}docker-compose.yml\" ]; then
            echo \"  Stopping \$stack_name (disabled)...\"
            cd \"\$stack_dir\"
            docker compose down 2>/dev/null || true
        fi
        echo \"  Removing \$stack_name stack folder...\"
        rm -rf \"\$stack_dir\"
    fi
done
echo '  ✓ Cleanup complete'
"

# -----------------------------------------------------------------------------
# Docker Hub Login (optional - for increased pull rate limits)
# -----------------------------------------------------------------------------
if [ -n "$DOCKERHUB_USER" ] && [ -n "$DOCKERHUB_TOKEN" ]; then
    echo ""
    echo -e "${YELLOW}[5/7] Logging into Docker Hub...${NC}"
    ssh nexus "echo '$DOCKERHUB_TOKEN' | docker login -u '$DOCKERHUB_USER' --password-stdin" 2>/dev/null
    echo -e "${GREEN}  ✓ Docker Hub login successful (200 pulls/6h)${NC}"
else
    echo ""
    echo -e "${CYAN}[5/7] Skipping Docker Hub login (anonymous: 100 pulls/6h)${NC}"
fi

# -----------------------------------------------------------------------------
# Setup SSH-Agent for Wetty (if enabled)
# -----------------------------------------------------------------------------
if echo "$ENABLED_SERVICES" | grep -qw "wetty"; then
    echo ""
    echo -e "${YELLOW}[5.5/7] Setting up SSH-Agent for Wetty...${NC}"
    ssh nexus "
        # Create SSH directory if it doesn't exist
        mkdir -p /root/.ssh
        chmod 700 /root/.ssh
        
        # Generate SSH key pair for Wetty if it doesn't exist
        WETTY_KEY_PATH=\"/root/.ssh/id_ed25519_wetty\"
        if [ ! -f \"\$WETTY_KEY_PATH\" ]; then
            echo '  Generating SSH key pair for Wetty...'
            ssh-keygen -t ed25519 -f \"\$WETTY_KEY_PATH\" -N '' -C 'wetty-auto-generated' >/dev/null 2>&1
            chmod 600 \"\$WETTY_KEY_PATH\"
            chmod 644 \"\$WETTY_KEY_PATH.pub\"
            echo '  ✓ SSH key pair generated for Wetty'
        else
            echo '  ✓ SSH key pair already exists for Wetty'
        fi
        
        # Add public key to authorized_keys if not already present
        WETTY_PUBKEY=\$(cat \"\$WETTY_KEY_PATH.pub\")
        if ! grep -q \"\$WETTY_PUBKEY\" /root/.ssh/authorized_keys 2>/dev/null; then
            echo \"\$WETTY_PUBKEY\" >> /root/.ssh/authorized_keys
            chmod 600 /root/.ssh/authorized_keys
            echo '  ✓ Public key added to authorized_keys'
        else
            echo '  ✓ Public key already in authorized_keys'
        fi
        
        # Create SSH-Agent socket directory if it doesn't exist
        SSH_AGENT_DIR=\"/tmp/ssh-agent\"
        mkdir -p \"\$SSH_AGENT_DIR\"
        
        # Helper function to check if SSH-Agent is responsive
        check_ssh_agent() {
            if ssh-add -l >/dev/null 2>&1; then
                return 0
            else
                return 1
            fi
        }
        
        # Check if SSH-Agent is already running (check for existing socket)
        SSH_AUTH_SOCK_FILE=\"\$SSH_AGENT_DIR/agent.sock\"
        if [ -S \"\$SSH_AUTH_SOCK_FILE\" ]; then
            export SSH_AUTH_SOCK=\"\$SSH_AUTH_SOCK_FILE\"
            # Test if agent is still responsive
            if check_ssh_agent; then
                echo '  ✓ SSH-Agent already running'
            else
                # Socket exists but agent is dead, remove it
                rm -f \"\$SSH_AUTH_SOCK_FILE\"
                unset SSH_AUTH_SOCK
            fi
        fi
        
        # Start SSH-Agent if not running
        if [ -z \"\${SSH_AUTH_SOCK:-}\" ] || [ ! -S \"\$SSH_AUTH_SOCK\" ]; then
            # Start SSH-Agent with socket in known location
            eval \$(ssh-agent -a \"\$SSH_AUTH_SOCK_FILE\" -s) >/dev/null 2>&1
            export SSH_AUTH_SOCK=\"\$SSH_AUTH_SOCK_FILE\"
            echo '  ✓ SSH-Agent started'
        fi
        
        # Add SSH key to agent if not already added
        if [ -f \"\$WETTY_KEY_PATH\" ]; then
            # Get key fingerprint for comparison
            KEY_FINGERPRINT=\$(ssh-keygen -lf \"\$WETTY_KEY_PATH\" 2>/dev/null | awk '{print \$2}' || echo \"\")
            
            # Check if key is already in agent by comparing fingerprints
            KEY_IN_AGENT=false
            if [ -n \"\$KEY_FINGERPRINT\" ] && check_ssh_agent && ssh-add -l 2>/dev/null | grep -q \"\$KEY_FINGERPRINT\"; then
                KEY_IN_AGENT=true
            fi
            
            if [ \"\$KEY_IN_AGENT\" = \"false\" ]; then
                # Add key to agent
                if ssh-add \"\$WETTY_KEY_PATH\" 2>&1; then
                    echo '  ✓ SSH key added to agent'
                else
                    echo -e \"  ${YELLOW}⚠ Failed to add SSH key to agent${NC}\"
                fi
            else
                echo '  ✓ SSH key already in agent'
            fi
        else
            echo -e \"  ${YELLOW}⚠ SSH key not found at \$WETTY_KEY_PATH${NC}\"
        fi
        
        # Export SSH_AUTH_SOCK path in wetty .env file for docker-compose
        WETTY_ENV=\"/opt/docker-server/stacks/wetty/.env\"
        if [ -f \"\$WETTY_ENV\" ]; then
            # Remove existing SSH_AUTH_SOCK line if present
            sed -i '/^SSH_AUTH_SOCK=/d' \"\$WETTY_ENV\"
        fi
        echo \"SSH_AUTH_SOCK=\$SSH_AUTH_SOCK\" >> \"\$WETTY_ENV\"
        echo '  ✓ SSH_AUTH_SOCK exported to wetty .env'
    "
    echo -e "${GREEN}  ✓ SSH-Agent configured for Wetty${NC}"
fi

# -----------------------------------------------------------------------------
# Generate Docker Compose override files for firewall TCP port exposure
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}  Generating firewall port overrides...${NC}"

# Read firewall rules from tofu output
if ! FIREWALL_JSON=$(cd "$TOFU_DIR" && tofu output -json firewall_rules 2>/dev/null); then
    echo -e "${YELLOW}  Warning: Unable to load firewall_rules from OpenTofu. No firewall overrides will be generated.${NC}" >&2
    FIREWALL_JSON="{}"
fi

if [ "$FIREWALL_JSON" != "{}" ] && [ -n "$FIREWALL_JSON" ]; then
    echo "  Firewall rules found, generating Docker Compose overrides..."

    # Parse firewall rules and generate override files per service
    while read -r service port; do
        [ -z "$service" ] && continue

        # Build override content - expose the port to the host
        # Find the main service container name from the docker-compose.yml
        OVERRIDE_PATH="stacks/$service/docker-compose.firewall.yml"

        if [ -f "stacks/$service/docker-compose.yml" ]; then
            # Get the first service name from the docker-compose file
            FIRST_SERVICE=$(python3 -c "
import yaml, sys
try:
    with open('stacks/$service/docker-compose.yml') as f:
        data = yaml.safe_load(f)
    services = list(data.get('services', {}).keys())
    print(services[0] if services else '')
except Exception as e:
    print(f'Error reading stacks/$service/docker-compose.yml: {e}', file=sys.stderr)
    print('')
" 2>/dev/null)

            if [ -n "$FIRST_SERVICE" ]; then
                # Skip creating generic port override for redpanda - handled separately below
                if [ "$service" != "redpanda" ]; then
                    # Check if override file exists, if so append the port
                    if [ -f "$OVERRIDE_PATH" ]; then
                        # Add port to existing override (under the same service)
                        if ! python3 -c "
import yaml, sys
try:
    with open('$OVERRIDE_PATH') as f:
        data = yaml.safe_load(f)
    svc = data.get('services', {}).get('$FIRST_SERVICE', {})
    ports = svc.get('ports', [])
    port_entry = '$port:$port'
    if port_entry not in ports:
        ports.append(port_entry)
        svc['ports'] = ports
        data.setdefault('services', {})['$FIRST_SERVICE'] = svc
        with open('$OVERRIDE_PATH', 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
except Exception as e:
    print(f'Warning: Failed to modify firewall override for $service: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1; then
                            echo -e "${YELLOW}  Warning: Could not modify firewall override for $service; continuing without updated firewall override${NC}" >&2
                        fi
                    else
                        cat > "$OVERRIDE_PATH" << FWEOF
services:
  $FIRST_SERVICE:
    ports:
      - "$port:$port"
FWEOF
                    fi
                    echo "    Port $port exposed for $service ($FIRST_SERVICE)"
                fi
            fi
        fi
    done < <(echo "$FIREWALL_JSON" | jq -r 'to_entries[] | "\(.key | sub("-[0-9]+$"; "")) \(.value.port)"' 2>/dev/null)

    # Special handling for RedPanda: Generate firewall-specific config
    # Instead of using docker-compose override with CLI flags, we generate
    # a firewall-specific redpanda.yaml with external advertised addresses
    REDPANDA_PORTS=$(echo "$FIREWALL_JSON" | jq -r 'to_entries[] | select(.key | startswith("redpanda-")) | .value.port' 2>/dev/null | sort -n)
    if [ -n "$REDPANDA_PORTS" ]; then
        echo "  Configuring RedPanda for external TCP access (with SASL)..."

        if [ -n "$DOMAIN" ]; then
            # Build ports list for RedPanda dual-listener setup:
            # - Internal listener (port 9092): no auth, Docker network only
            # - External listener (port 19092): SASL auth, for Databricks/external clients
            # Host port 9092 maps to container port 19092 (external SASL listener)
            PORTS_LIST=""
            for p in $REDPANDA_PORTS; do
                if [ "$p" = "9092" ]; then
                    PORTS_LIST="${PORTS_LIST}      - \"9092:19092\"\n"
                else
                    PORTS_LIST="${PORTS_LIST}      - \"$p:$p\"\n"
                fi
            done

            # Remove old override file before regenerating (avoid conflicts from previous runs)
            rm -f "stacks/redpanda/docker-compose.firewall.yml"

            # Create docker-compose override with port mappings only (no command flags)
            cat > "stacks/redpanda/docker-compose.firewall.yml" << RPEOF
services:
  redpanda:
    ports:
$(echo -e "$PORTS_LIST")
RPEOF

            # Generate firewall-specific redpanda.yaml from template
            # This replaces the standard redpanda.yaml when firewall is enabled
            REDPANDA_FIREWALL_CONFIG="stacks/redpanda/config/redpanda-firewall.yaml"
            sed "s/__REDPANDA_KAFKA_DOMAIN__/redpanda-kafka.$DOMAIN/g" \
                "stacks/redpanda/config/redpanda-firewall.yaml.template" > "$REDPANDA_FIREWALL_CONFIG"

            echo "    RedPanda configured for external access (SASL):"
            if echo "$REDPANDA_PORTS" | grep -q "9092"; then
                echo "      Kafka: redpanda-kafka.$DOMAIN:9092 (SASL_PLAINTEXT)"
            fi
            if echo "$REDPANDA_PORTS" | grep -q "8081"; then
                echo "      Schema Registry: redpanda-schema-registry.$DOMAIN:8081"
            fi
        fi
    fi

else
    echo "  No firewall rules enabled (Zero Entry mode)"
fi

# Copy firewall override files to server (only for enabled services)
echo ""
echo -e "${YELLOW}Copying firewall override files to server...${NC}"
for override_file in stacks/*/docker-compose.firewall.yml; do
    if [ -f "$override_file" ]; then
        service=$(basename $(dirname "$override_file"))
        # Only copy if service is enabled (directory exists on server)
        if echo "$ENABLED_SERVICES" | grep -qw "$service"; then
            echo "  Copying $service firewall override..."
            scp -q "$override_file" nexus:/opt/docker-server/stacks/$service/ || {
                echo -e "${RED}  Failed to copy $service firewall override${NC}"
                exit 1
            }
        else
            echo "  Skipping $service (not enabled)"
        fi
    fi
done
echo -e "${GREEN}✓ Firewall override files copied${NC}"

# Copy RedPanda production configuration directory
if echo "$ENABLED_SERVICES" | grep -qw "redpanda"; then
    echo ""
    echo -e "${YELLOW}Copying RedPanda production configuration...${NC}"
    if [ -d "stacks/redpanda/config" ]; then
        # Create config directory on server if it doesn't exist
        ssh nexus "mkdir -p /opt/docker-server/stacks/redpanda/config" || {
            echo -e "${RED}  Failed to create config directory${NC}"
            exit 1
        }

        # Check if firewall is enabled for RedPanda
        REDPANDA_FIREWALL_ENABLED=$(echo "$FIREWALL_JSON" | jq -r 'to_entries[] | select(.key | startswith("redpanda-")) | .value.port' 2>/dev/null)

        if [ -n "$REDPANDA_FIREWALL_ENABLED" ] && [ -f "stacks/redpanda/config/redpanda-firewall.yaml" ]; then
            # Firewall mode: Use the generated firewall-specific config
            echo "  Using firewall configuration (external advertised addresses)"
            scp -q "stacks/redpanda/config/redpanda-firewall.yaml" nexus:/opt/docker-server/stacks/redpanda/config/redpanda.yaml || {
                echo -e "${RED}  Failed to copy firewall config${NC}"
                exit 1
            }
        else
            # Normal mode: Use standard config
            scp -q "stacks/redpanda/config/redpanda.yaml" nexus:/opt/docker-server/stacks/redpanda/config/redpanda.yaml || {
                echo -e "${RED}  Failed to copy redpanda config${NC}"
                exit 1
            }
        fi

        # Remove old redpanda.yaml file from root (if exists from previous deployment)
        ssh nexus "rm -f /opt/docker-server/stacks/redpanda/redpanda.yaml" 2>/dev/null || true

        # Set write permissions on config directory (RedPanda needs to create temp files)
        # Try to set owner to redpanda user (101:101), fallback to world-writable
        if ! ssh nexus "sudo chown -R 101:101 /opt/docker-server/stacks/redpanda/config" 2>/dev/null; then
            echo -e "${YELLOW}  Warning: Could not set config ownership to redpanda user (101:101), using world-writable fallback${NC}" >&2
            ssh nexus "sudo chmod -R 777 /opt/docker-server/stacks/redpanda/config" || {
                echo -e "${RED}  Error: Could not set world-writable (chmod 777) permissions on RedPanda config directory${NC}" >&2
                exit 1
            }
        fi

        if [ -n "$REDPANDA_FIREWALL_ENABLED" ]; then
            echo -e "${GREEN}✓ RedPanda firewall configuration copied${NC}"
        else
            echo -e "${GREEN}✓ RedPanda configuration copied (production mode)${NC}"
        fi
    else
        echo -e "${RED}  redpanda config directory not found!${NC}"
        exit 1
    fi
fi

# -----------------------------------------------------------------------------
# Pre-pull Docker images (parallel)
# -----------------------------------------------------------------------------
# Start containers (parallel)
# Note: --build ensures stacks with Dockerfiles (e.g. Spark) are always rebuilt.
# Docker build cache makes this fast when nothing changed. For image-only
# services, --build is a no-op.
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[6/7] Starting enabled containers (parallel)...${NC}"

ssh nexus "
set -euo pipefail
# Export image versions from global .env
if [ -f /opt/docker-server/stacks/.env ]; then
    set -a
    source /opt/docker-server/stacks/.env
    set +a
fi

STARTED_SERVICES=()
FAILED_SERVICES=()
PIDS=()

# Virtual services that use a parent stack (defined via 'stack' field in services.yaml)
VIRTUAL_SERVICES=\"seaweedfs-filer seaweedfs-manager\"

# Map virtual services to their parent stack
declare -A STACK_PARENTS
STACK_PARENTS[\"seaweedfs-filer\"]=\"seaweedfs\"
STACK_PARENTS[\"seaweedfs-manager\"]=\"seaweedfs\"

# Ensure parent stacks are started when virtual services are enabled
PARENT_STACKS_STARTED=\"\"
for service in $ENABLED_LIST; do
    PARENT=\"\${STACK_PARENTS[\$service]:-}\"
    if [ -n \"\$PARENT\" ] && ! echo \"\$PARENT_STACKS_STARTED\" | grep -qw \"\$PARENT\"; then
        if [ -f /opt/docker-server/stacks/\$PARENT/docker-compose.yml ]; then
            echo \"  Starting parent stack: \$PARENT (required by \$service)...\"
            (cd /opt/docker-server/stacks/\$PARENT && docker compose up -d --build 2>&1) &
            PID=\$!
            PIDS+=(\$PID)
            STARTED_SERVICES+=(\"\$PARENT:\$PID\")
            PARENT_STACKS_STARTED=\"\$PARENT_STACKS_STARTED \$PARENT\"
        fi
    fi
done

# Services that are started later after their dependencies are ready
# Woodpecker requires Gitea OAuth credentials, so it starts after Gitea setup
DEFERRED_SERVICES=\"woodpecker\"

# Fix Dify storage permissions (API/worker run as uid 1001)
if echo \"$ENABLED_LIST\" | grep -qw \"dify\"; then
    mkdir -p /mnt/nexus-data/dify/storage /mnt/nexus-data/dify/plugins
    chown -R 1001:1001 /mnt/nexus-data/dify/storage /mnt/nexus-data/dify/plugins
fi

for service in $ENABLED_LIST; do
    echo \"[DEBUG] Checking service: \$service\" >&2

    # Skip virtual services (they're covered by their parent stack)
    if echo \"\$VIRTUAL_SERVICES\" | grep -qw \"\$service\"; then
        echo \"[DEBUG] Skipping virtual service \$service (uses parent stack)\" >&2
        continue
    fi

    # Skip parent stacks that were already started
    if echo \"\$PARENT_STACKS_STARTED\" | grep -qw \"\$service\"; then
        echo \"[DEBUG] Skipping \$service (already started as parent stack)\" >&2
        continue
    fi

    # Skip deferred services (started later after dependencies are ready)
    if echo \"\$DEFERRED_SERVICES\" | grep -qw \"\$service\"; then
        echo \"[DEBUG] Deferring \$service (started after dependency setup)\" >&2
        continue
    fi

    if [ -f /opt/docker-server/stacks/\$service/docker-compose.yml ]; then
        echo \"  Starting \$service...\"
        if [ -f /opt/docker-server/stacks/\$service/docker-compose.firewall.yml ]; then
            echo \"    (with firewall port overrides)\"
            (cd /opt/docker-server/stacks/\$service && docker compose -f docker-compose.yml -f docker-compose.firewall.yml up -d --build 2>&1) &
        else
            (cd /opt/docker-server/stacks/\$service && docker compose up -d --build 2>&1) &
        fi
        PID=\$!
        PIDS+=(\$PID)
        STARTED_SERVICES+=(\"\$service:\$PID\")
    else
        echo \"[DEBUG] docker-compose.yml not found for \$service\" >&2
        FAILED_SERVICES+=(\"\$service (no docker-compose.yml)\")
    fi
done

# Wait for all background jobs and collect exit codes
FAILED_COUNT=0
for i in \"\${!PIDS[@]}\"; do
    PID=\${PIDS[\$i]}
    SERVICE_PID_PAIR=\${STARTED_SERVICES[\$i]}
    SERVICE_NAME=\$(echo \"\$SERVICE_PID_PAIR\" | cut -d: -f1)
    
    if wait \$PID; then
        # Verify container is actually running
        if docker ps --format '{{.Names}}' | grep -q \"^\${SERVICE_NAME}\$\"; then
            echo \"  ✓ \$SERVICE_NAME started and running\"
        else
            echo \"  ⚠️  \$SERVICE_NAME started but container not found in 'docker ps'\" >&2
            FAILED_SERVICES+=(\"\$SERVICE_NAME (container not running)\")
            FAILED_COUNT=\$((FAILED_COUNT + 1))
        fi
    else
        EXIT_CODE=\$?
        echo \"  ✗ \$SERVICE_NAME failed to start (exit code: \$EXIT_CODE)\" >&2
        FAILED_SERVICES+=(\"\$SERVICE_NAME (exit code: \$EXIT_CODE)\")
        FAILED_COUNT=\$((FAILED_COUNT + 1))
    fi
done

echo ''
if [ \$FAILED_COUNT -eq 0 ] && [ \${#FAILED_SERVICES[@]} -eq 0 ]; then
    echo '  ✓ All enabled stacks started successfully'
else
    echo \"  ⚠️  Started \${#STARTED_SERVICES[@]} services, \$FAILED_COUNT failed\" >&2
    echo \"  Failed services: \${FAILED_SERVICES[*]}\" >&2
    exit 1
fi
" 2>&1 | tee /tmp/docker-start.log

DOCKER_EXIT_CODE=${PIPESTATUS[0]}
if [ $DOCKER_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}  ✓ All containers started successfully${NC}"
else
    echo -e "${RED}  ✗ Some containers failed to start${NC}"
    echo -e "${YELLOW}  Check /tmp/docker-start.log for details${NC}"
    exit $DOCKER_EXIT_CODE
fi

# -----------------------------------------------------------------------------
# Auto-configure services
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[7/7] Auto-configuring services...${NC}"

# Initialize array for background configuration jobs
CONFIG_JOBS=()

# Configure Infisical admin and push secrets
if echo "$ENABLED_SERVICES" | grep -qw "infisical"; then
    echo "  Configuring Infisical..."
    
    # Wait for Infisical to be ready (optimized: check container status first)
    echo "  Waiting for Infisical to be ready (may take up to 2min)..."
    INFISICAL_READY=false
    # First check if container is running (faster than HTTP)
    for i in $(seq 1 20); do
        CONTAINER_STATUS=$(ssh nexus "docker inspect --format='{{.State.Status}}' infisical 2>/dev/null" || echo "")
        if [ "$CONTAINER_STATUS" = "running" ]; then
            break
        fi
        sleep 2
    done
    # Then check HTTP endpoint (allow up to 120s total)
    for i in $(seq 1 40); do
        if ssh nexus "curl -s --connect-timeout 3 'http://localhost:8070/api/v1/admin/config'" 2>/dev/null | grep -q 'initialized'; then
            INFISICAL_READY=true
            break
        fi
        sleep 3
    done
    
    if [ "$INFISICAL_READY" = "false" ]; then
        echo -e "${YELLOW}  ⚠ Infisical not responding after 120s - skipping config${NC}"
    else
    # Check if already initialized
    INIT_CHECK=$(ssh nexus "curl -s 'http://localhost:8070/api/v1/admin/config'" 2>/dev/null || echo "")
    
    if echo "$INIT_CHECK" | grep -q '"initialized":true'; then
        echo -e "${YELLOW}  ⚠ Infisical already configured - skipping setup${NC}"
        # WARNING: Infisical will NOT auto-populate secrets for newly enabled services.
        # After initial bootstrap, new service secrets (e.g. MinIO) must be added
        # manually via the Infisical UI, or perform a full destroy/spin-up cycle
        # to bootstrap fresh with all current service credentials.
    else
        # Build JSON payload locally and base64 encode to avoid escaping issues
        BOOTSTRAP_JSON=$(cat <<EOF
{"email": "$ADMIN_EMAIL", "password": "$INFISICAL_PASS", "organization": "Nexus"}
EOF
)
        # Bootstrap with admin user
        BOOTSTRAP_RESULT=$(ssh nexus "curl -s -X POST 'http://localhost:8070/api/v1/admin/bootstrap' \
            -H 'Content-Type: application/json' \
            -d '$(echo "$BOOTSTRAP_JSON" | tr -d '\n')'" 2>&1 || echo "")
        
        if echo "$BOOTSTRAP_RESULT" | grep -q '"user"'; then
            echo -e "${GREEN}  ✓ Infisical admin created (user: $ADMIN_EMAIL)${NC}"
            
            # Extract token and org ID for pushing secrets
            INFISICAL_TOKEN=$(echo "$BOOTSTRAP_RESULT" | jq -r '.identity.credentials.token // empty')
            ORG_ID=$(echo "$BOOTSTRAP_RESULT" | jq -r '.organization.id // empty')
            
            if [ -n "$INFISICAL_TOKEN" ] && [ -n "$ORG_ID" ]; then
                echo "  Creating Nexus secrets project..."
                
                # Create a project for Nexus secrets
                PROJECT_JSON="{\"projectName\": \"Nexus Stack\", \"organizationId\": \"$ORG_ID\"}"
                PROJECT_RESULT=$(ssh nexus "curl -s -X POST 'http://localhost:8070/api/v2/workspace' \
                    -H 'Authorization: Bearer $INFISICAL_TOKEN' \
                    -H 'Content-Type: application/json' \
                    -d '$PROJECT_JSON'" 2>&1 || echo "")
                
                PROJECT_ID=$(echo "$PROJECT_RESULT" | jq -r '.project.id // .workspace.id // empty')
                
                if [ -n "$PROJECT_ID" ] && [ "$PROJECT_ID" != "null" ]; then
                    echo -e "${GREEN}  ✓ Project 'Nexus Stack' created${NC}"
                    
                    # Create tags for organizing secrets
                    echo "  Creating tags..."
                    for TAG_NAME in "infisical" "portainer" "uptime-kuma" "grafana" "n8n" "kestra" "metabase" "cloudbeaver" "clickhouse" "mage" "minio" "nocodb" "dify" "rustfs" "seaweedfs" "garage" "lakefs" "filestash" "redpanda" "meltano" "postgres" "pgadmin" "prefect" "windmill" "openmetadata" "gitea" "wikijs" "woodpecker" "config" "ssh"; do
                        TAG_JSON="{\"slug\": \"$TAG_NAME\", \"color\": \"#3b82f6\"}"
                        ssh nexus "curl -s -X POST 'http://localhost:8070/api/v1/projects/$PROJECT_ID/tags' \
                            -H 'Authorization: Bearer $INFISICAL_TOKEN' \
                            -H 'Content-Type: application/json' \
                            -d '$TAG_JSON'" >/dev/null 2>&1 || true
                    done
                    
                    # Get tag IDs
                    TAGS_RESULT=$(ssh nexus "curl -s 'http://localhost:8070/api/v1/projects/$PROJECT_ID/tags' \
                        -H 'Authorization: Bearer $INFISICAL_TOKEN'" 2>/dev/null || echo "{}")
                    
                    INFISICAL_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="infisical") | .id // empty' 2>/dev/null)
                    PORTAINER_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="portainer") | .id // empty' 2>/dev/null)
                    KUMA_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="uptime-kuma") | .id // empty' 2>/dev/null)
                    GRAFANA_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="grafana") | .id // empty' 2>/dev/null)
                    N8N_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="n8n") | .id // empty' 2>/dev/null)
                    KESTRA_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="kestra") | .id // empty' 2>/dev/null)
                    METABASE_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="metabase") | .id // empty' 2>/dev/null)
                    CLOUDBEAVER_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="cloudbeaver") | .id // empty' 2>/dev/null)
                    CLICKHOUSE_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="clickhouse") | .id // empty' 2>/dev/null)
                    MAGE_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="mage") | .id // empty' 2>/dev/null)
                    MINIO_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="minio") | .id // empty' 2>/dev/null)
                    NOCODB_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="nocodb") | .id // empty' 2>/dev/null)
                    DIFY_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="dify") | .id // empty' 2>/dev/null)
                    RUSTFS_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="rustfs") | .id // empty' 2>/dev/null)
                    SEAWEEDFS_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="seaweedfs") | .id // empty' 2>/dev/null)
                    GARAGE_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="garage") | .id // empty' 2>/dev/null)
                    LAKEFS_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="lakefs") | .id // empty' 2>/dev/null)
                    FILESTASH_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="filestash") | .id // empty' 2>/dev/null)
                    REDPANDA_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="redpanda") | .id // empty' 2>/dev/null)
                    MELTANO_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="meltano") | .id // empty' 2>/dev/null)
                    POSTGRES_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="postgres") | .id // empty' 2>/dev/null)
                    PGADMIN_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="pgadmin") | .id // empty' 2>/dev/null)
                    PREFECT_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="prefect") | .id // empty' 2>/dev/null)
                    WINDMILL_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="windmill") | .id // empty' 2>/dev/null)
                    OPENMETADATA_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="openmetadata") | .id // empty' 2>/dev/null)
                    GITEA_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="gitea") | .id // empty' 2>/dev/null)
                    WIKIJS_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="wikijs") | .id // empty' 2>/dev/null)
                    WOODPECKER_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="woodpecker") | .id // empty' 2>/dev/null)
                    CONFIG_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="config") | .id // empty' 2>/dev/null)
                    SSH_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="ssh") | .id // empty' 2>/dev/null)
                    
                    echo -e "${GREEN}  ✓ Tags created${NC}"
                    echo "  Pushing secrets to Infisical..."
                    
                    # Build secrets payload with usernames and tags
                    # Prepare optional secrets as pre-built JSON fragments
                    # (avoids ${:+} brace conflicts inside heredoc that produce invalid JSON)
                    WOODPECKER_GITEA_SECRETS=""
                    if [ -n "${WOODPECKER_GITEA_CLIENT:-}" ]; then
                        WOODPECKER_GITEA_SECRETS=",{\"secretKey\": \"WOODPECKER_GITEA_CLIENT\", \"secretValue\": \"$WOODPECKER_GITEA_CLIENT\", \"tagIds\": [\"$WOODPECKER_TAG\"]}"
                    fi
                    if [ -n "${WOODPECKER_GITEA_SECRET:-}" ]; then
                        WOODPECKER_GITEA_SECRETS="$WOODPECKER_GITEA_SECRETS,{\"secretKey\": \"WOODPECKER_GITEA_SECRET\", \"secretValue\": \"$WOODPECKER_GITEA_SECRET\", \"tagIds\": [\"$WOODPECKER_TAG\"]}"
                    fi
                    SSH_KEY_SECRET=""
                    if [ -n "${SSH_PRIVATE_KEY_CONTENT:-}" ]; then
                        SSH_KEY_BASE64=$(echo "$SSH_PRIVATE_KEY_CONTENT" | base64 | tr -d '\n')
                        SSH_KEY_SECRET=",{\"secretKey\": \"SSH_PRIVATE_KEY_BASE64\", \"secretValue\": \"$SSH_KEY_BASE64\", \"tagIds\": [\"$SSH_TAG\"]}"
                    fi
                    
                    # Using v4 batch API which supports tagIds
                    # Environment can be overridden via INFISICAL_ENV (default: dev)
                    # Note: "prod" may not exist in new Infisical projects
                    SECRETS_PAYLOAD=$(cat <<SECRETS_EOF
{
  "projectId": "$PROJECT_ID",
  "environment": "${INFISICAL_ENV:-dev}",
  "secretPath": "/",
  "secrets": [
    {"secretKey": "DOMAIN", "secretValue": "$DOMAIN", "tagIds": ["$CONFIG_TAG"]},
    {"secretKey": "ADMIN_EMAIL", "secretValue": "$ADMIN_EMAIL", "tagIds": ["$CONFIG_TAG"]},
    {"secretKey": "ADMIN_USERNAME", "secretValue": "$ADMIN_USERNAME", "tagIds": ["$CONFIG_TAG"]},
    {"secretKey": "INFISICAL_USERNAME", "secretValue": "$ADMIN_EMAIL", "tagIds": ["$INFISICAL_TAG"]},
    {"secretKey": "INFISICAL_PASSWORD", "secretValue": "$INFISICAL_PASS", "tagIds": ["$INFISICAL_TAG"]},
    {"secretKey": "PORTAINER_USERNAME", "secretValue": "$ADMIN_USERNAME", "tagIds": ["$PORTAINER_TAG"]},
    {"secretKey": "PORTAINER_PASSWORD", "secretValue": "$PORTAINER_PASS", "tagIds": ["$PORTAINER_TAG"]},
    {"secretKey": "UPTIME_KUMA_USERNAME", "secretValue": "$ADMIN_USERNAME", "tagIds": ["$KUMA_TAG"]},
    {"secretKey": "UPTIME_KUMA_PASSWORD", "secretValue": "$KUMA_PASS", "tagIds": ["$KUMA_TAG"]},
    {"secretKey": "GRAFANA_USERNAME", "secretValue": "$ADMIN_USERNAME", "tagIds": ["$GRAFANA_TAG"]},
    {"secretKey": "GRAFANA_PASSWORD", "secretValue": "$GRAFANA_PASS", "tagIds": ["$GRAFANA_TAG"]},
    {"secretKey": "N8N_USERNAME", "secretValue": "$ADMIN_EMAIL", "tagIds": ["$N8N_TAG"]},
    {"secretKey": "N8N_PASSWORD", "secretValue": "$N8N_PASS", "tagIds": ["$N8N_TAG"]},
    {"secretKey": "KESTRA_USERNAME", "secretValue": "$ADMIN_EMAIL", "tagIds": ["$KESTRA_TAG"]},
    {"secretKey": "KESTRA_PASSWORD", "secretValue": "$KESTRA_PASS", "tagIds": ["$KESTRA_TAG"]},
    {"secretKey": "METABASE_USERNAME", "secretValue": "$ADMIN_EMAIL", "tagIds": ["$METABASE_TAG"]},
    {"secretKey": "METABASE_PASSWORD", "secretValue": "$METABASE_PASS", "tagIds": ["$METABASE_TAG"]},
    {"secretKey": "CLOUDBEAVER_USERNAME", "secretValue": "$ADMIN_USERNAME", "tagIds": ["$CLOUDBEAVER_TAG"]},
    {"secretKey": "CLOUDBEAVER_PASSWORD", "secretValue": "$CLOUDBEAVER_PASS", "tagIds": ["$CLOUDBEAVER_TAG"]},
    {"secretKey": "MAGE_USERNAME", "secretValue": "${USER_EMAIL:-$ADMIN_EMAIL}", "tagIds": ["$MAGE_TAG"]},
    {"secretKey": "MAGE_PASSWORD", "secretValue": "$MAGE_PASS", "tagIds": ["$MAGE_TAG"]},
    {"secretKey": "MINIO_ROOT_USER", "secretValue": "nexus-minio", "tagIds": ["$MINIO_TAG"]},
    {"secretKey": "MINIO_ROOT_PASSWORD", "secretValue": "$MINIO_ROOT_PASS", "tagIds": ["$MINIO_TAG"]},
    {"secretKey": "NOCODB_USERNAME", "secretValue": "$ADMIN_EMAIL", "tagIds": ["$NOCODB_TAG"]},
    {"secretKey": "NOCODB_PASSWORD", "secretValue": "$NOCODB_ADMIN_PASS", "tagIds": ["$NOCODB_TAG"]},
    {"secretKey": "NOCODB_DB_PASSWORD", "secretValue": "$NOCODB_DB_PASS", "tagIds": ["$NOCODB_TAG"]},
    {"secretKey": "NOCODB_JWT_SECRET", "secretValue": "$NOCODB_JWT_SECRET", "tagIds": ["$NOCODB_TAG"]},
    {"secretKey": "DIFY_USERNAME", "secretValue": "$ADMIN_EMAIL", "tagIds": ["$DIFY_TAG"]},
    {"secretKey": "DIFY_PASSWORD", "secretValue": "$DIFY_ADMIN_PASS", "tagIds": ["$DIFY_TAG"]},
    {"secretKey": "DIFY_DB_PASSWORD", "secretValue": "$DIFY_DB_PASS", "tagIds": ["$DIFY_TAG"]},
    {"secretKey": "DIFY_SECRET_KEY", "secretValue": "$DIFY_SECRET_KEY", "tagIds": ["$DIFY_TAG"]},
    {"secretKey": "DIFY_REDIS_PASSWORD", "secretValue": "$DIFY_REDIS_PASS", "tagIds": ["$DIFY_TAG"]},
    {"secretKey": "DIFY_WEAVIATE_API_KEY", "secretValue": "$DIFY_WEAVIATE_API_KEY", "tagIds": ["$DIFY_TAG"]},
    {"secretKey": "DIFY_SANDBOX_API_KEY", "secretValue": "$DIFY_SANDBOX_API_KEY", "tagIds": ["$DIFY_TAG"]},
    {"secretKey": "DIFY_PLUGIN_DAEMON_KEY", "secretValue": "$DIFY_PLUGIN_DAEMON_KEY", "tagIds": ["$DIFY_TAG"]},
    {"secretKey": "DIFY_PLUGIN_INNER_API_KEY", "secretValue": "$DIFY_PLUGIN_INNER_API_KEY", "tagIds": ["$DIFY_TAG"]},
    {"secretKey": "RUSTFS_ACCESS_KEY", "secretValue": "nexus-rustfs", "tagIds": ["$RUSTFS_TAG"]},
    {"secretKey": "RUSTFS_SECRET_KEY", "secretValue": "$RUSTFS_ROOT_PASS", "tagIds": ["$RUSTFS_TAG"]},
    {"secretKey": "SEAWEEDFS_ACCESS_KEY", "secretValue": "nexus-seaweedfs", "tagIds": ["$SEAWEEDFS_TAG"]},
    {"secretKey": "SEAWEEDFS_SECRET_KEY", "secretValue": "$SEAWEEDFS_ADMIN_PASS", "tagIds": ["$SEAWEEDFS_TAG"]},
    {"secretKey": "GARAGE_ADMIN_TOKEN", "secretValue": "$GARAGE_ADMIN_TOKEN", "tagIds": ["$GARAGE_TAG"]},
    {"secretKey": "LAKEFS_DB_PASSWORD", "secretValue": "$LAKEFS_DB_PASS", "tagIds": ["$LAKEFS_TAG"]},
    {"secretKey": "LAKEFS_ACCESS_KEY_ID", "secretValue": "$LAKEFS_ADMIN_ACCESS_KEY", "tagIds": ["$LAKEFS_TAG"]},
    {"secretKey": "LAKEFS_SECRET_ACCESS_KEY", "secretValue": "$LAKEFS_ADMIN_SECRET_KEY", "tagIds": ["$LAKEFS_TAG"]},
    {"secretKey": "FILESTASH_S3_BUCKET", "secretValue": "$HETZNER_S3_BUCKET_GENERAL", "tagIds": ["$FILESTASH_TAG"]},
    {"secretKey": "FILESTASH_ADMIN_PASSWORD", "secretValue": "$FILESTASH_ADMIN_PASSWORD", "tagIds": ["$FILESTASH_TAG"]},
    {"secretKey": "REDPANDA_SASL_USERNAME", "secretValue": "nexus-redpanda", "tagIds": ["$REDPANDA_TAG"]},
    {"secretKey": "REDPANDA_SASL_PASSWORD", "secretValue": "$REDPANDA_ADMIN_PASS", "tagIds": ["$REDPANDA_TAG"]},
    {"secretKey": "MELTANO_DB_PASSWORD", "secretValue": "$MELTANO_DB_PASS", "tagIds": ["$MELTANO_TAG"]},
    {"secretKey": "POSTGRES_USERNAME", "secretValue": "nexus-postgres", "tagIds": ["$POSTGRES_TAG"]},
    {"secretKey": "POSTGRES_PASSWORD", "secretValue": "$POSTGRES_PASS", "tagIds": ["$POSTGRES_TAG"]},
    {"secretKey": "PGADMIN_USERNAME", "secretValue": "$ADMIN_EMAIL", "tagIds": ["$PGADMIN_TAG"]},
    {"secretKey": "PGADMIN_PASSWORD", "secretValue": "$PGADMIN_PASS", "tagIds": ["$PGADMIN_TAG"]},
    {"secretKey": "PREFECT_DB_PASSWORD", "secretValue": "$PREFECT_DB_PASS", "tagIds": ["$PREFECT_TAG"]},
    {"secretKey": "WINDMILL_ADMIN_EMAIL", "secretValue": "$ADMIN_EMAIL", "tagIds": ["$WINDMILL_TAG"]},
    {"secretKey": "WINDMILL_ADMIN_PASSWORD", "secretValue": "$WINDMILL_ADMIN_PASS", "tagIds": ["$WINDMILL_TAG"]},
    {"secretKey": "WINDMILL_DB_PASSWORD", "secretValue": "$WINDMILL_DB_PASS", "tagIds": ["$WINDMILL_TAG"]},
    {"secretKey": "WINDMILL_SUPERADMIN_SECRET", "secretValue": "$WINDMILL_SUPERADMIN_SECRET", "tagIds": ["$WINDMILL_TAG"]},
    {"secretKey": "OPENMETADATA_USERNAME", "secretValue": "admin@$OM_PRINCIPAL_DOMAIN", "tagIds": ["$OPENMETADATA_TAG"]},
    {"secretKey": "OPENMETADATA_PASSWORD", "secretValue": "$OPENMETADATA_ADMIN_PASS", "tagIds": ["$OPENMETADATA_TAG"]},
    {"secretKey": "OPENMETADATA_DB_PASSWORD", "secretValue": "$OPENMETADATA_DB_PASS", "tagIds": ["$OPENMETADATA_TAG"]},
    {"secretKey": "GITEA_ADMIN_USERNAME", "secretValue": "$ADMIN_USERNAME", "tagIds": ["$GITEA_TAG"]},
    {"secretKey": "GITEA_ADMIN_PASSWORD", "secretValue": "$GITEA_ADMIN_PASS", "tagIds": ["$GITEA_TAG"]},
    {"secretKey": "GITEA_USER_USERNAME", "secretValue": "$GITEA_USER_USERNAME", "tagIds": ["$GITEA_TAG"]},
    {"secretKey": "GITEA_USER_PASSWORD", "secretValue": "$GITEA_USER_PASS", "tagIds": ["$GITEA_TAG"]},
    {"secretKey": "GITEA_REPO_URL", "secretValue": "https://git.${DOMAIN}/${ADMIN_USERNAME}/nexus-${DOMAIN//./-}-gitea.git", "tagIds": ["$GITEA_TAG"]},
    {"secretKey": "GITEA_DB_PASSWORD", "secretValue": "$GITEA_DB_PASS", "tagIds": ["$GITEA_TAG"]},
    {"secretKey": "CLICKHOUSE_USERNAME", "secretValue": "nexus-clickhouse", "tagIds": ["$CLICKHOUSE_TAG"]},
    {"secretKey": "CLICKHOUSE_PASSWORD", "secretValue": "$CLICKHOUSE_ADMIN_PASS", "tagIds": ["$CLICKHOUSE_TAG"]},
    {"secretKey": "WIKIJS_USERNAME", "secretValue": "${USER_EMAIL:-$ADMIN_EMAIL}", "tagIds": ["$WIKIJS_TAG"]},
    {"secretKey": "WIKIJS_PASSWORD", "secretValue": "$WIKIJS_ADMIN_PASS", "tagIds": ["$WIKIJS_TAG"]},
    {"secretKey": "WIKIJS_DB_PASSWORD", "secretValue": "$WIKIJS_DB_PASS", "tagIds": ["$WIKIJS_TAG"]},
    {"secretKey": "WOODPECKER_AGENT_SECRET", "secretValue": "$WOODPECKER_AGENT_SECRET", "tagIds": ["$WOODPECKER_TAG"]}$WOODPECKER_GITEA_SECRETS$SSH_KEY_SECRET
  ]
}
SECRETS_EOF
)
                    
                    # Write payload to temp file on server to avoid SSH/shell quoting issues
                    echo "$SECRETS_PAYLOAD" | ssh nexus "cat > /tmp/infisical-secrets.json"
                    SECRETS_RESULT=$(ssh nexus "curl -s -X POST 'http://localhost:8070/api/v4/secrets/batch' \
                        -H 'Authorization: Bearer $INFISICAL_TOKEN' \
                        -H 'Content-Type: application/json' \
                        -d @/tmp/infisical-secrets.json; rm -f /tmp/infisical-secrets.json" 2>&1 || echo "")
                    
                    # Check for actual success (secrets array present) and no error
                    if echo "$SECRETS_RESULT" | grep -q '"error"'; then
                        echo -e "${YELLOW}  ⚠ Failed to push secrets - API error${NC}"
                        echo -e "${DIM}    Response: $(echo "$SECRETS_RESULT" | head -c 300)${NC}"
                    elif echo "$SECRETS_RESULT" | jq -e '.secrets | length > 0' >/dev/null 2>&1; then
                        SECRETS_COUNT=$(echo "$SECRETS_RESULT" | jq '.secrets | length' 2>/dev/null || echo "?")
                        echo -e "${GREEN}  ✓ $SECRETS_COUNT secrets pushed to Infisical (dev environment)${NC}"
                        if [ -n "${SSH_PRIVATE_KEY_CONTENT:-}" ]; then
                            echo -e "${GREEN}  ✓ SSH private key stored (base64 encoded)${NC}"
                            echo -e "${DIM}    Decode with: base64 -d <<< \"\$SSH_PRIVATE_KEY_BASE64\" > ~/.ssh/nexus_key${NC}"
                        fi
                    else
                        echo -e "${YELLOW}  ⚠ Failed to push secrets - unexpected response${NC}"
                        echo -e "${DIM}    Response: $(echo "$SECRETS_RESULT" | head -c 300)${NC}"
                    fi
                else
                    echo -e "${YELLOW}  ⚠ Failed to create project${NC}"
                fi
            fi
        elif echo "$BOOTSTRAP_RESULT" | grep -q 'already'; then
            echo -e "${YELLOW}  ⚠ Infisical already configured${NC}"
        else
            echo -e "${YELLOW}  ⚠ Infisical bootstrap failed${NC}"
        fi
    fi
    fi  # End of INFISICAL_READY check
fi

# Configure Portainer admin (non-blocking, can run in parallel with other configs)
if echo "$ENABLED_SERVICES" | grep -qw "portainer" && [ -n "$PORTAINER_PASS" ]; then
    (
        echo "  Configuring Portainer admin..."
        # Quick readiness check
        for i in $(seq 1 5); do
            if ssh nexus "curl -s --connect-timeout 2 'http://localhost:9090/api/system/status'" >/dev/null 2>&1; then
                break
            fi
            sleep 1
        done

        PORTAINER_JSON="{\"Username\":\"$ADMIN_USERNAME\",\"Password\":\"$PORTAINER_PASS\"}"
        PORTAINER_RESULT=$(ssh nexus "curl -s -X POST 'http://localhost:9090/api/users/admin/init' \
            -H 'Content-Type: application/json' \
            -d '$PORTAINER_JSON'" 2>/dev/null || echo "")

        if echo "$PORTAINER_RESULT" | grep -q '"Id"' 2>/dev/null; then
            echo -e "${GREEN}  ✓ Portainer admin created (user: $ADMIN_USERNAME)${NC}"
        elif echo "$PORTAINER_RESULT" | grep -q 'already initialized' 2>/dev/null; then
            echo -e "${YELLOW}  ⚠ Portainer already initialized${NC}"
        else
            echo -e "${YELLOW}  ⚠ Portainer setup skipped (may already be configured)${NC}"
        fi
    ) &
    CONFIG_JOBS+=($!)
fi

# Configure Filestash (host, force_ssl, S3 backend)
if echo "$ENABLED_SERVICES" | grep -qw "filestash"; then
    (
        set +e  # Disable exit on error for background job to allow proper error handling

        echo "  Configuring Filestash..."

        # Wait for Filestash to be ready
        FILESTASH_READY=false
        for i in $(seq 1 15); do
            if ssh nexus "curl -s --connect-timeout 2 'http://localhost:8334/healthz'" >/dev/null 2>&1; then
                FILESTASH_READY=true
                break
            fi
            sleep 3
        done

        if [ "$FILESTASH_READY" = "false" ]; then
            echo -e "${YELLOW}  ⚠ Filestash not ready after 45s - skipping auto-configuration${NC}"
            exit 0
        fi

        # Check if config.json exists (wait up to 30s for it to be created)
        CONFIG_EXISTS="no"
        for i in $(seq 1 10); do
            CONFIG_EXISTS=$(ssh nexus "docker exec filestash test -f /app/data/state/config/config.json && echo 'yes' || echo 'no'" 2>/dev/null || echo "no")
            if [ "$CONFIG_EXISTS" = "yes" ]; then
                break
            fi
            sleep 3
        done

        if [ "$CONFIG_EXISTS" = "yes" ]; then
            # Check if host is correctly set (without protocol)
            CURRENT_HOST=$(ssh nexus "docker exec filestash cat /app/data/state/config/config.json" 2>/dev/null | grep -o '"host"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4 || echo "")

            if [ -n "$CURRENT_HOST" ] && echo "$CURRENT_HOST" | grep -q "^https://"; then
                # Fix host - remove protocol
                ssh nexus "docker exec filestash sed -i 's|\"host\": \"https://|\"host\": \"|g' /app/data/state/config/config.json" 2>/dev/null || true
                echo -e "${GREEN}  ✓ Fixed Filestash host (removed protocol)${NC}"
            fi

            # Ensure force_ssl is true
            ssh nexus "docker exec filestash sed -i 's/\"force_ssl\": null/\"force_ssl\": true/g' /app/data/state/config/config.json" 2>/dev/null || true
            ssh nexus "docker exec filestash sed -i 's/\"force_ssl\": false/\"force_ssl\": true/g' /app/data/state/config/config.json" 2>/dev/null || true

            # Restart Filestash to apply force_ssl changes
            echo "  Restarting Filestash..."
            ssh nexus "docker restart filestash" >/dev/null 2>&1 || true

            # Wait for Filestash to fully initialize after restart
            sleep 10

            # Wait for Filestash to be ready after restart
            FILESTASH_RESTARTED=false
            for i in $(seq 1 10); do
                if ssh nexus "curl -s --connect-timeout 2 'http://localhost:8334/healthz'" >/dev/null 2>&1; then
                    FILESTASH_RESTARTED=true
                    break
                fi
                sleep 2
            done

            if [ "$FILESTASH_RESTARTED" = "false" ]; then
                echo -e "${YELLOW}  ⚠ Filestash not ready after restart - skipping S3 configuration${NC}"
            else
                # Add S3 connection if Hetzner is configured (AFTER restart)
                if [ -n "$HETZNER_S3_SERVER" ] && [ -n "$HETZNER_S3_ACCESS_KEY" ] && [ -n "$HETZNER_S3_SECRET_KEY" ] && [ -n "$HETZNER_S3_BUCKET_GENERAL" ]; then
                    # Check if Hetzner Storage connection already exists
                    HAS_HETZNER=$(ssh nexus "docker exec filestash cat /app/data/state/config/config.json" 2>/dev/null | grep -o '"label"[[:space:]]*:[[:space:]]*"Hetzner Storage"' || echo "")

                    # Configure S3 auto-connect via passthrough middleware
                    echo "  Configuring Hetzner S3 backend in Filestash..."

                    # Create temporary file with updated config
                    ssh nexus "docker exec filestash cat /app/data/state/config/config.json" > /tmp/filestash-config.json 2>/dev/null || true

                    if [ -f /tmp/filestash-config.json ] && [ -s /tmp/filestash-config.json ]; then
                        # Configure passthrough middleware with S3 auto-connect
                        # This skips the login form - users connect directly to S3
                        # Authentication is handled by Cloudflare Access upstream
                        # IMPORTANT: params MUST be JSON strings (tojson) because Filestash
                        # encrypts/decrypts these fields, and Config.Get().String() returns
                        # empty for object values in the form tree
                        jq --arg endpoint "https://${HETZNER_S3_SERVER}" \
                           --arg access_key "${HETZNER_S3_ACCESS_KEY}" \
                           --arg secret_key "${HETZNER_S3_SECRET_KEY}" \
                           --arg region "${HETZNER_S3_REGION}" \
                           --arg bucket "${HETZNER_S3_BUCKET_GENERAL}" \
                           '.connections = [{"type":"s3","label":"Hetzner Storage"}] | .middleware.identity_provider = {"type":"passthrough","params":({"strategy":"direct"} | tojson)} | .middleware.attribute_mapping = {"related_backend":"Hetzner Storage","params":({"Hetzner Storage":{"type":"s3","access_key_id":$access_key,"secret_access_key":$secret_key,"endpoint":$endpoint,"region":$region,"path":("/"+$bucket+"/")}} | tojson)}' /tmp/filestash-config.json > /tmp/filestash-config-updated.json 2>/dev/null || true

                        # Upload updated config back to container and restart
                        if [ -f /tmp/filestash-config-updated.json ] && [ -s /tmp/filestash-config-updated.json ]; then
                            cat /tmp/filestash-config-updated.json | ssh nexus "docker exec -i filestash sh -c 'cat > /app/data/state/config/config.json'" 2>/dev/null || true
                            rm -f /tmp/filestash-config.json /tmp/filestash-config-updated.json

                            # Restart to load the new middleware config
                            ssh nexus "docker restart filestash" >/dev/null 2>&1 || true
                            echo -e "${GREEN}  ✓ Hetzner S3 backend configured (passthrough auto-connect)${NC}"
                        else
                            echo -e "${YELLOW}  ⚠ Failed to update Filestash config - configure S3 manually at /admin${NC}"
                            rm -f /tmp/filestash-config.json /tmp/filestash-config-updated.json
                        fi
                    else
                        echo -e "${YELLOW}  ⚠ Could not read Filestash config - configure S3 manually at /admin${NC}"
                        rm -f /tmp/filestash-config.json
                    fi
                fi

                echo -e "${GREEN}  ✓ Filestash configured (force_ssl enabled)${NC}"
            fi
        else
            echo -e "${YELLOW}  ⚠ Filestash config not found - will auto-initialize from CONFIG_JSON${NC}"
        fi

        exit 0  # Ensure clean exit
    ) &
    CONFIG_JOBS+=($!)
fi

# Configure RedPanda SASL authentication (only when external TCP ports are exposed)
if echo "$ENABLED_SERVICES" | grep -qw "redpanda" && [ -n "$REDPANDA_ADMIN_PASS" ] && [ -f "stacks/redpanda/docker-compose.firewall.yml" ]; then
    (
        echo "  Configuring RedPanda SASL..."
        # Wait for RedPanda admin API to be ready
        for i in $(seq 1 10); do
            if ssh nexus "docker exec redpanda curl -s --connect-timeout 2 'http://localhost:9644/v1/status/ready'" >/dev/null 2>&1; then
                break
            fi
            sleep 2
        done

        # SASL is configured in redpanda.yaml - just create user and set superuser

        # Create SASL user using rpk (password via stdin to avoid process list exposure)
        USER_RESULT=$(ssh nexus "echo '$REDPANDA_ADMIN_PASS' | docker exec -i redpanda rpk acl user create nexus-redpanda \
            --password-stdin \
            --mechanism SCRAM-SHA-256 2>&1" || echo "")

        # Configure superuser (grants full permissions without ACLs)
        ssh nexus "docker exec redpanda rpk cluster config set superusers '[\"nexus-redpanda\"]'" >/dev/null 2>&1

        # Restart RedPanda to apply SASL configuration to listeners
        echo "  Restarting RedPanda to apply SASL configuration..."
        if ssh nexus "test -f /opt/docker-server/stacks/redpanda/docker-compose.firewall.yml" 2>/dev/null; then
            ssh nexus "cd /opt/docker-server/stacks/redpanda && docker compose -f docker-compose.yml -f docker-compose.firewall.yml restart" >/dev/null 2>&1
        else
            ssh nexus "cd /opt/docker-server/stacks/redpanda && docker compose restart" >/dev/null 2>&1
        fi

        # Wait for RedPanda to be ready after restart
        echo "  Waiting for RedPanda to be ready..."
        sleep 5
        for i in $(seq 1 10); do
            if ssh nexus "docker exec redpanda curl -s --connect-timeout 2 'http://localhost:9644/v1/status/ready'" >/dev/null 2>&1; then
                break
            fi
            sleep 2
        done

        # Verify user exists after restart
        USERS=$(ssh nexus "docker exec redpanda curl -s http://localhost:9644/v1/security/users" 2>/dev/null || echo "[]")
        if echo "$USERS" | grep -q "nexus-redpanda"; then
            echo -e "${GREEN}  ✓ RedPanda SASL configured (user: nexus-redpanda, superuser)${NC}"

            # Restart redpanda-console to connect with SASL credentials
            if echo "$ENABLED_SERVICES" | grep -qw "redpanda-console"; then
                echo "  Restarting RedPanda Console to connect with SASL..."
                ssh nexus "cd /opt/docker-server/stacks/redpanda-console && docker compose restart" >/dev/null 2>&1
                sleep 3
            fi
        else
            echo -e "${YELLOW}  ⚠ RedPanda SASL setup may have failed - check logs${NC}"
        fi
    ) &
    CONFIG_JOBS+=($!)
fi

# Configure n8n owner account
if echo "$ENABLED_SERVICES" | grep -qw "n8n" && [ -n "$N8N_PASS" ]; then
    echo "  Configuring n8n..."
    
    # Wait for n8n to be ready
    echo "  Waiting for n8n to be ready..."
    N8N_READY=false
    for i in $(seq 1 30); do
        N8N_HEALTH=$(ssh nexus "curl -s -o /dev/null -w '%{http_code}' http://localhost:5678/healthz 2>/dev/null" || echo "000")
        if [ "$N8N_HEALTH" = "200" ]; then
            N8N_READY=true
            break
        fi
        sleep 2
    done
    
    if [ "$N8N_READY" = "false" ]; then
        echo -e "${YELLOW}  ⚠ n8n not ready after 60s - skipping config${NC}"
    else
        # Check if setup is needed (showSetupOnFirstLoad=true means setup needed)
        SETUP_CHECK=$(ssh nexus "curl -s http://localhost:5678/rest/settings" 2>/dev/null || echo "{}")
        # jq outputs boolean as 'true'/'false' string, fallback to 'true' if parsing fails
        NEEDS_SETUP=$(echo "$SETUP_CHECK" | jq -r '.data.userManagement.showSetupOnFirstLoad // true | if . then "true" else "false" end' 2>/dev/null || echo "true")
        
        if [ "$NEEDS_SETUP" = "false" ]; then
            echo -e "${YELLOW}  ⚠ n8n already configured - skipping owner setup${NC}"
        else
            # Create owner account via API (use jq for proper JSON escaping)
            N8N_SETUP_PAYLOAD=$(jq -n --arg email "$ADMIN_EMAIL" --arg password "$N8N_PASS" \
                '{email: $email, firstName: "Admin", lastName: "User", password: $password}')
            N8N_RESULT=$(printf '%s' "$N8N_SETUP_PAYLOAD" | ssh nexus "curl -s -X POST 'http://localhost:5678/rest/owner/setup' \
                -H 'Content-Type: application/json' \
                -d @-" 2>&1 || echo "")
            
            if echo "$N8N_RESULT" | grep -q '"id"'; then
                echo -e "${GREEN}  ✓ n8n owner account created (email: $ADMIN_EMAIL)${NC}"
            else
                echo -e "${YELLOW}  ⚠ n8n auto-setup failed - configure manually at first login${NC}"
                echo -e "${YELLOW}    Credentials available in Infisical${NC}"
            fi
        fi
    fi
fi

# Configure Metabase admin account
if echo "$ENABLED_SERVICES" | grep -qw "metabase" && [ -n "$METABASE_PASS" ]; then
    echo "  Configuring Metabase..."

    # Metabase port (from services.yaml)
    METABASE_PORT=3000
    
    # Quick health check (max 10s - for already running instances)
    echo "  Checking Metabase status..."
    METABASE_READY=false
    for i in $(seq 1 5); do
        METABASE_HEALTH=$(ssh nexus "curl -s -o /dev/null -w '%{http_code}' http://localhost:$METABASE_PORT/api/health 2>/dev/null" || echo "000")
        if [ "$METABASE_HEALTH" = "200" ]; then
            METABASE_READY=true
            break
        fi
        sleep 2
    done
    
    # If not ready yet, wait longer (Java app takes ~2min on first boot)
    if [ "$METABASE_READY" = "false" ]; then
        echo "  Metabase starting (first boot takes ~2min)..."
        for i in $(seq 1 55); do
            METABASE_HEALTH=$(ssh nexus "curl -s -o /dev/null -w '%{http_code}' http://localhost:$METABASE_PORT/api/health 2>/dev/null" || echo "000")
            if [ "$METABASE_HEALTH" = "200" ]; then
                METABASE_READY=true
                break
            fi
            sleep 2
        done
    fi
    
    if [ "$METABASE_READY" = "false" ]; then
        echo -e "${YELLOW}  ⚠ Metabase not ready after 120s - skipping config${NC}"
    else
        # Get setup token (only available before first setup)
        SETUP_TOKEN=$(ssh nexus "curl -s http://localhost:$METABASE_PORT/api/session/properties 2>/dev/null | grep -o '\"setup-token\":\"[^\"]*\"' | cut -d'\"' -f4" || echo "")
        
        if [ -z "$SETUP_TOKEN" ]; then
            echo -e "${YELLOW}  ⚠ Metabase already configured - skipping admin setup${NC}"
        else
            # Create admin user via setup API (use jq for proper JSON escaping)
            METABASE_SETUP_PAYLOAD=$(jq -n \
                --arg token "$SETUP_TOKEN" \
                --arg email "$ADMIN_EMAIL" \
                --arg password "$METABASE_PASS" \
                '{
                    token: $token,
                    user: {
                        email: $email,
                        first_name: "Admin",
                        last_name: "User",
                        password: $password
                    },
                    prefs: {
                        site_name: "Nexus Stack Analytics",
                        allow_tracking: false
                    }
                }')
            METABASE_RESULT=$(printf '%s' "$METABASE_SETUP_PAYLOAD" | ssh nexus "curl -s -X POST 'http://localhost:$METABASE_PORT/api/setup' \
                -H 'Content-Type: application/json' \
                -d @-" 2>&1 || echo "")
            
            if echo "$METABASE_RESULT" | grep -q '"id"'; then
                echo -e "${GREEN}  ✓ Metabase admin created (email: $ADMIN_EMAIL)${NC}"
            else
                echo -e "${YELLOW}  ⚠ Metabase auto-setup failed - configure manually at first login${NC}"
                echo -e "${YELLOW}    Credentials available in Infisical${NC}"
            fi
        fi
    fi
fi

# -----------------------------------------------------------------------------
# TODO: Fix Uptime Kuma auto-configuration (Issue #145)
# -----------------------------------------------------------------------------
# The Socket.io-based setup fails with "server error" when connecting from
# inside the container. This needs investigation - possibly a socket.io
# client/server version mismatch or container networking issue.
# For now, users must configure Uptime Kuma manually on first login.
# Credentials are available in Infisical.
# -----------------------------------------------------------------------------
# Configure Uptime Kuma admin
# if echo "$ENABLED_SERVICES" | grep -qw "uptime-kuma" && [ -n "$KUMA_PASS" ]; then
#     ... (disabled - see TODO above)
# fi

if echo "$ENABLED_SERVICES" | grep -qw "uptime-kuma"; then
    echo -e "${YELLOW}  ⚠ Uptime Kuma requires manual setup on first login${NC}"
    echo -e "${YELLOW}    Credentials available in Infisical${NC}"
fi

# Configure LakeFS admin user via API (one-time setup)
# Note: LAKEFS_INSTALLATION_* env vars only work with database.type=local
# Since we use PostgreSQL, we must configure via API
if echo "$ENABLED_SERVICES" | grep -qw "lakefs" && [ -n "$LAKEFS_ADMIN_ACCESS_KEY" ]; then
    (
        echo "  Configuring LakeFS admin user..."
        # Wait for LakeFS to be ready
        LAKEFS_READY=false
        for i in $(seq 1 30); do
            if ssh nexus "curl -sf http://localhost:8000/api/v1/healthcheck" >/dev/null 2>&1; then
                LAKEFS_READY=true
                break
            fi
            sleep 2
        done

        if [ "$LAKEFS_READY" = "true" ]; then
            # Check if setup is already complete
            SETUP_CHECK=$(ssh nexus "curl -s http://localhost:8000/api/v1/config" 2>/dev/null || echo "")
            if echo "$SETUP_CHECK" | grep -q '"setup_complete":true'; then
                echo -e "${YELLOW}  ⚠ LakeFS already configured${NC}"
            else
                # Create admin user via setup API
                SETUP_PAYLOAD="{\"username\":\"nexus-lakefs\",\"key\":{\"access_key_id\":\"$LAKEFS_ADMIN_ACCESS_KEY\",\"secret_access_key\":\"$LAKEFS_ADMIN_SECRET_KEY\"}}"
                SETUP_RESULT=$(ssh nexus "curl -s -X POST 'http://localhost:8000/api/v1/setup_lakefs' \
                    -H 'Content-Type: application/json' \
                    -d '$SETUP_PAYLOAD'" 2>&1 || echo "")

                if echo "$SETUP_RESULT" | grep -q 'access_key_id'; then
                    echo -e "${GREEN}  ✓ LakeFS admin created (user: nexus-lakefs)${NC}"
                elif echo "$SETUP_RESULT" | grep -q 'already'; then
                    echo -e "${YELLOW}  ⚠ LakeFS already configured${NC}"
                else
                    echo -e "${YELLOW}  ⚠ LakeFS setup failed - configure manually${NC}"
                    echo -e "${DIM}    Response: $(echo "$SETUP_RESULT" | head -c 200)${NC}"
                fi
            fi

            # Create default repository (independent of admin setup)
            echo "  Creating default repository..."

            # Determine storage namespace and repository name based on configuration
            if [ -n "$HETZNER_S3_SERVER" ] && [ -n "$HETZNER_S3_BUCKET" ]; then
                STORAGE_NAMESPACE="s3://${HETZNER_S3_BUCKET}/lakefs/"
                BACKEND_TYPE="Hetzner Object Storage"
                REPO_NAME="hetzner-object-storage"
            else
                STORAGE_NAMESPACE="local://data/lakefs/"
                BACKEND_TYPE="local storage"
                REPO_NAME="local-storage"
            fi

            REPO_PAYLOAD="{\"name\":\"$REPO_NAME\",\"storage_namespace\":\"$STORAGE_NAMESPACE\",\"default_branch\":\"main\",\"sample_data\":false}"
            REPO_RESULT=$(ssh nexus "curl -s -X POST 'http://localhost:8000/api/v1/repositories' \
                -u '$LAKEFS_ADMIN_ACCESS_KEY:$LAKEFS_ADMIN_SECRET_KEY' \
                -H 'Content-Type: application/json' \
                -d '$REPO_PAYLOAD'" 2>&1 || echo "")

            if echo "$REPO_RESULT" | grep -q '"id"'; then
                echo -e "${GREEN}  ✓ Repository '$REPO_NAME' created ($BACKEND_TYPE)${NC}"
            elif echo "$REPO_RESULT" | grep -q 'already exists'; then
                echo -e "${YELLOW}  ⚠ Repository '$REPO_NAME' already exists${NC}"
            else
                echo -e "${YELLOW}  ⚠ Repository creation skipped${NC}"
                echo -e "${DIM}    Response: $(echo "$REPO_RESULT" | head -c 200)${NC}"
            fi
        else
            echo -e "${YELLOW}  ⚠ LakeFS not ready after 60s - skipping setup${NC}"
        fi
    ) &
    CONFIG_JOBS+=($!)
fi

# Configure Garage layout (one-time setup after first start)
if echo "$ENABLED_SERVICES" | grep -qw "garage" && [ -n "$GARAGE_ADMIN_TOKEN" ]; then
    (
        echo "  Configuring Garage layout..."
        # Wait for Garage to be ready (check health endpoint)
        for i in $(seq 1 15); do
            if ssh nexus "curl -sf http://localhost:3903/health" >/dev/null 2>&1; then
                break
            fi
            sleep 2
        done

        # Check if layout is already configured (roles exist)
        LAYOUT_CHECK=$(ssh nexus "docker exec garage /garage layout show 2>&1" || echo "")
        if echo "$LAYOUT_CHECK" | grep -q "No nodes currently have"; then
            # Get full node ID and validate it's a valid hex string (64 chars)
            FULL_NODE_ID=$(ssh nexus "docker exec garage /garage node id 2>&1 | head -1" || echo "")
            if [ -n "$FULL_NODE_ID" ] && [ ${#FULL_NODE_ID} -eq 64 ] && echo "$FULL_NODE_ID" | grep -qE '^[0-9a-fA-F]{64}$'; then
                # Extract short form (first 16 chars) for layout commands
                NODE_ID="${FULL_NODE_ID:0:16}"
                # Assign node to layout with 100GB capacity
                ssh nexus "docker exec garage /garage layout assign -z dc1 -c 100G $NODE_ID" >/dev/null 2>&1
                # Apply layout with version 1
                ssh nexus "docker exec garage /garage layout apply --version 1" >/dev/null 2>&1
                # Create default access key
                ssh nexus "docker exec garage /garage key create nexus-garage-key" >/dev/null 2>&1
                echo -e "${GREEN}  ✓ Garage layout configured with 100GB capacity${NC}"
            else
                echo -e "${YELLOW}  ⚠ Could not get Garage node ID - layout setup skipped${NC}"
            fi
        else
            echo -e "${YELLOW}  ⚠ Garage layout already configured${NC}"
        fi
    ) &
    CONFIG_JOBS+=($!)
fi

# Configure Windmill (create admin user, workspace, secure default account)
if echo "$ENABLED_SERVICES" | grep -qw "windmill" && [ -n "$WINDMILL_ADMIN_PASS" ] && [ -n "$WINDMILL_SUPERADMIN_SECRET" ]; then
    (
        echo "  Configuring Windmill..."

        # Wait for Windmill to be ready (check version endpoint)
        WINDMILL_READY=false
        for i in $(seq 1 30); do
            if ssh nexus "curl -s --connect-timeout 2 'http://localhost:8200/api/version'" >/dev/null 2>&1; then
                WINDMILL_READY=true
                break
            fi
            sleep 2
        done

        if [ "$WINDMILL_READY" = "false" ]; then
            echo -e "${YELLOW}  ⚠ Windmill not ready after 60s - skipping auto-configuration${NC}"
            exit 0
        fi

        # All API calls use SUPERADMIN_SECRET as bearer token
        WM_AUTH="Authorization: Bearer $WINDMILL_SUPERADMIN_SECRET"
        WM_CT="Content-Type: application/json"
        WM_URL="http://localhost:8200/api"

        # --- Step 1: Create superadmin user for ADMIN_EMAIL ---
        WINDMILL_CREATE_JSON=$(jq -n --arg email "$ADMIN_EMAIL" --arg password "$WINDMILL_ADMIN_PASS" \
            '{email: $email, password: $password, super_admin: true, name: "Admin"}')
        WINDMILL_CREATE_RESULT=$(printf '%s' "$WINDMILL_CREATE_JSON" | ssh nexus "curl -s -X POST '$WM_URL/users/create' \
            -H '$WM_AUTH' \
            -H '$WM_CT' \
            -d @-" 2>/dev/null || echo "")

        if echo "$WINDMILL_CREATE_RESULT" | grep -q '"email"' 2>/dev/null; then
            echo -e "${GREEN}  ✓ Windmill admin created (user: $ADMIN_EMAIL)${NC}"
        elif echo "$WINDMILL_CREATE_RESULT" | grep -qi 'already exists' 2>/dev/null; then
            echo -e "${YELLOW}  ⚠ Windmill admin already exists${NC}"
        else
            echo -e "${YELLOW}  ⚠ Windmill admin creation: ${WINDMILL_CREATE_RESULT:-no response}${NC}"
        fi

        # --- Step 2: Create regular user for USER_EMAIL (if different from ADMIN_EMAIL) ---
        if [ -n "$USER_EMAIL" ] && [ "$USER_EMAIL" != "$ADMIN_EMAIL" ]; then
            WINDMILL_USER_JSON=$(jq -n --arg email "$USER_EMAIL" --arg password "$WINDMILL_ADMIN_PASS" \
                '{email: $email, password: $password, super_admin: false, name: "User"}')
            WINDMILL_USER_RESULT=$(printf '%s' "$WINDMILL_USER_JSON" | ssh nexus "curl -s -X POST '$WM_URL/users/create' \
                -H '$WM_AUTH' \
                -H '$WM_CT' \
                -d @-" 2>/dev/null || echo "")

            if echo "$WINDMILL_USER_RESULT" | grep -q '"email"' 2>/dev/null; then
                echo -e "${GREEN}  ✓ Windmill user created (user: $USER_EMAIL)${NC}"
            elif echo "$WINDMILL_USER_RESULT" | grep -qi 'already exists' 2>/dev/null; then
                echo -e "${YELLOW}  ⚠ Windmill user already exists${NC}"
            fi
        fi

        # --- Step 3: Create "nexus" workspace ---
        WINDMILL_WS_JSON=$(jq -n '{id: "nexus", name: "Nexus Stack"}')
        WINDMILL_WS_RESULT=$(printf '%s' "$WINDMILL_WS_JSON" | ssh nexus "curl -s -X POST '$WM_URL/workspaces/create' \
            -H '$WM_AUTH' \
            -H '$WM_CT' \
            -d @-" 2>/dev/null || echo "")

        if [ "$WINDMILL_WS_RESULT" = "\"nexus\"" ] || echo "$WINDMILL_WS_RESULT" | grep -qi 'created' 2>/dev/null; then
            echo -e "${GREEN}  ✓ Windmill workspace 'nexus' created${NC}"
        elif echo "$WINDMILL_WS_RESULT" | grep -qi 'already exists' 2>/dev/null; then
            echo -e "${YELLOW}  ⚠ Windmill workspace 'nexus' already exists${NC}"
        else
            echo -e "${YELLOW}  ⚠ Windmill workspace creation: ${WINDMILL_WS_RESULT:-no response}${NC}"
        fi

        # --- Step 4: Secure the default admin@windmill.dev account ---
        # Change the default password to a random value to prevent unauthorized access
        RANDOM_PW=$(openssl rand -base64 32)
        WINDMILL_DEFPW_JSON=$(jq -n --arg password "$RANDOM_PW" '{password: $password}')
        printf '%s' "$WINDMILL_DEFPW_JSON" | ssh nexus "curl -s -X POST '$WM_URL/users/setpassword' \
            -H '$WM_AUTH' \
            -H '$WM_CT' \
            -d @-" >/dev/null 2>&1 || true
        echo -e "${GREEN}  ✓ Windmill default admin password secured${NC}"

    ) &
    CONFIG_JOBS+=($!)
fi

# Configure OpenMetadata admin (change default password)
if echo "$ENABLED_SERVICES" | grep -qw "openmetadata" && [ -n "$OPENMETADATA_ADMIN_PASS" ]; then
    (
        echo "  Configuring OpenMetadata..."
        OM_PRINCIPAL_DOMAIN=$(echo "$ADMIN_EMAIL" | cut -d'@' -f2)

        # Wait for OpenMetadata to be ready (Java app, may take 2-3 min on first boot)
        OPENMETADATA_READY=false
        echo "  Waiting for OpenMetadata to be ready (may take up to 3min)..."
        for i in $(seq 1 60); do
            if ssh nexus "curl -s --connect-timeout 3 'http://localhost:8585/api/v1/system/version'" 2>/dev/null | grep -q 'version'; then
                OPENMETADATA_READY=true
                break
            fi
            sleep 3
        done

        if [ "$OPENMETADATA_READY" = "false" ]; then
            echo -e "${YELLOW}  ⚠ OpenMetadata not ready after 180s - skipping auto-configuration${NC}"
            echo -e "${YELLOW}    Default credentials: admin@${OM_PRINCIPAL_DOMAIN} / admin${NC}"
            exit 0
        fi

        # Login with default credentials to get JWT token
        # Note: OpenMetadata requires passwords to be base64 encoded in API requests
        OM_DEFAULT_PW_B64=$(echo -n "admin" | base64)
        OM_LOGIN_JSON=$(jq -n --arg email "admin@${OM_PRINCIPAL_DOMAIN}" --arg password "$OM_DEFAULT_PW_B64" \
            '{email: $email, password: $password}')
        OM_LOGIN_RESULT=$(printf '%s' "$OM_LOGIN_JSON" | ssh nexus "curl -s -X POST 'http://localhost:8585/api/v1/users/login' \
            -H 'Content-Type: application/json' \
            -d @-" 2>/dev/null || echo "")

        OM_TOKEN=$(echo "$OM_LOGIN_RESULT" | jq -r '.accessToken // empty' 2>/dev/null)

        if [ -n "$OM_TOKEN" ] && [ "$OM_TOKEN" != "null" ]; then
            # Change admin password using the password change API
            # Note: Password change API uses plain text (NOT base64 like login API)
            OM_PW_JSON=$(jq -n --arg old "admin" --arg new "$OPENMETADATA_ADMIN_PASS" \
                '{username: "admin", oldPassword: $old, newPassword: $new, confirmPassword: $new, requestType: "SELF"}')
            OM_PW_RESULT=$(printf '%s' "$OM_PW_JSON" | ssh nexus "curl -s -X PUT 'http://localhost:8585/api/v1/users/changePassword' \
                -H 'Authorization: Bearer $OM_TOKEN' \
                -H 'Content-Type: application/json' \
                -d @-" 2>/dev/null || echo "")

            # Verify new password works by logging in with it
            OM_NEW_PW_B64=$(echo -n "$OPENMETADATA_ADMIN_PASS" | base64)
            OM_VERIFY_JSON=$(jq -n --arg email "admin@${OM_PRINCIPAL_DOMAIN}" --arg password "$OM_NEW_PW_B64" \
                '{email: $email, password: $password}')
            OM_VERIFY_RESULT=$(printf '%s' "$OM_VERIFY_JSON" | ssh nexus "curl -s -X POST 'http://localhost:8585/api/v1/users/login' \
                -H 'Content-Type: application/json' \
                -d @-" 2>/dev/null || echo "")

            if echo "$OM_VERIFY_RESULT" | jq -r '.accessToken // empty' 2>/dev/null | grep -q '.'; then
                echo -e "${GREEN}  ✓ OpenMetadata admin configured (user: admin@${OM_PRINCIPAL_DOMAIN})${NC}"
            else
                echo "    Password change response: $(echo "$OM_PW_RESULT" | head -c 200)"
                echo "    Login verify response: $(echo "$OM_VERIFY_RESULT" | head -c 200)"
                echo -e "${YELLOW}  ⚠ OpenMetadata password change failed - password may not meet complexity requirements${NC}"
            fi
        elif echo "$OM_LOGIN_RESULT" | grep -qi 'invalid\|unauthorized\|credentials' 2>/dev/null; then
            # Login with default password failed - already configured
            echo -e "${YELLOW}  ⚠ OpenMetadata already configured (default password already changed)${NC}"
        else
            echo -e "${YELLOW}  ⚠ OpenMetadata auto-setup failed - configure manually at first login${NC}"
            echo -e "${YELLOW}    Credentials available in Infisical${NC}"
        fi
    ) &
    CONFIG_JOBS+=($!)
fi

# Configure Gitea admin account and shared workspace repo
# NOTE: This runs synchronously (not in background) because other services
# depend on the Gitea repo being created before they can be configured.
if echo "$ENABLED_SERVICES" | grep -qw "gitea" && [ -n "$GITEA_ADMIN_PASS" ]; then
    echo "  Configuring Gitea..."

    # Sync DB password with the current OpenTofu-generated value.
    # This handles persistent volume scenarios where the DB was initialized with
    # a different password (e.g., after OpenTofu state recreation).
    # Uses socket auth (peer) inside the container - no password required for the ALTER.
    if [ -n "$GITEA_DB_PASS" ]; then
        echo "  Syncing Gitea DB password..."
        # Escape password for safe use in SQL string literal
        GITEA_DB_PASS_ESC=$GITEA_DB_PASS
        GITEA_DB_PASS_ESC=${GITEA_DB_PASS_ESC//\\/\\\\}
        GITEA_DB_PASS_ESC=${GITEA_DB_PASS_ESC//\'/\'\'}
        GITEA_DB_SYNCED=false
        for i in $(seq 1 15); do
            if ssh nexus "docker exec gitea-db psql -U nexus-gitea -d gitea \
                -c \"ALTER USER \\\"nexus-gitea\\\" WITH PASSWORD '$GITEA_DB_PASS_ESC'\" \
                >/dev/null 2>&1"; then
                echo -e "${GREEN}  ✓ Gitea DB password synced${NC}"
                GITEA_DB_SYNCED=true
                break
            fi
            sleep 2
        done
        if [ "$GITEA_DB_SYNCED" != "true" ]; then
            echo -e "${YELLOW}  ⚠ Failed to sync Gitea DB password after 15 attempts${NC}"
        fi
    fi

    # Wait for Gitea to be ready
    GITEA_READY=false
    for i in $(seq 1 30); do
        if ssh nexus "curl -sf http://localhost:3200/api/healthz" >/dev/null 2>&1; then
            GITEA_READY=true
            break
        fi
        sleep 2
    done

    if [ "$GITEA_READY" = "true" ]; then
        # Check if admin user already exists
        ADMIN_EXISTS=$(ssh nexus "docker exec -u git gitea gitea admin user list --admin 2>/dev/null | grep -c '$ADMIN_USERNAME'" || echo "0")

        if [ "$ADMIN_EXISTS" -gt 0 ]; then
            # Sync password to match current OpenTofu state (persistent volume may have old password)
            echo "  Syncing Gitea admin password..."
            ssh nexus "docker exec -u git gitea gitea admin user change-password \
                --username '$ADMIN_USERNAME' \
                --password '$GITEA_ADMIN_PASS' \
                --must-change-password=false" >/dev/null 2>&1 \
                && echo -e "${GREEN}  ✓ Gitea admin password synced${NC}" \
                || echo -e "${YELLOW}  ⚠ Could not sync Gitea admin password${NC}"
        else
            # Create admin user via CLI
            GITEA_RESULT=$(ssh nexus "docker exec -u git gitea gitea admin user create \
                --admin \
                --username '$ADMIN_USERNAME' \
                --password '$GITEA_ADMIN_PASS' \
                --email '$ADMIN_EMAIL' \
                --must-change-password=false" 2>&1 || echo "")

            if echo "$GITEA_RESULT" | grep -qi "created\|success\|New user"; then
                echo -e "${GREEN}  ✓ Gitea admin created (user: $ADMIN_USERNAME)${NC}"
            else
                echo -e "${YELLOW}  ⚠ Gitea admin setup needs manual configuration${NC}"
                echo -e "${YELLOW}    Credentials available in Infisical${NC}"
            fi
        fi

        # --- Create regular user account (for students/user_email) ---
        # Extract username from user_email (part before @)
        GITEA_USER_USERNAME="${USER_EMAIL%%@*}"
        if [ -n "$USER_EMAIL" ] && [ -n "$GITEA_USER_PASS" ]; then
            USER_EXISTS=$(ssh nexus "docker exec -u git gitea gitea admin user list 2>/dev/null | grep -c '$GITEA_USER_USERNAME'" || echo "0")

            if [ "$USER_EXISTS" -gt 0 ]; then
                # Sync password to match current OpenTofu state (persistent volume may have old password)
                echo "  Syncing Gitea user password..."
                ssh nexus "docker exec -u git gitea gitea admin user change-password \
                    --username '$GITEA_USER_USERNAME' \
                    --password '$GITEA_USER_PASS' \
                    --must-change-password=false" >/dev/null 2>&1 \
                    && echo -e "${GREEN}  ✓ Gitea user password synced${NC}" \
                    || echo -e "${YELLOW}  ⚠ Could not sync Gitea user password${NC}"
            else
                GITEA_USER_RESULT=$(ssh nexus "docker exec -u git gitea gitea admin user create \
                    --username '$GITEA_USER_USERNAME' \
                    --password '$GITEA_USER_PASS' \
                    --email '$USER_EMAIL' \
                    --must-change-password=false" 2>&1 || echo "")

                if echo "$GITEA_USER_RESULT" | grep -qi "created\|success\|New user"; then
                    echo -e "${GREEN}  ✓ Gitea user created (user: $GITEA_USER_USERNAME)${NC}"
                else
                    echo -e "${YELLOW}  ⚠ Gitea user setup needs manual configuration${NC}"
                fi
            fi
        fi

        # --- Create shared workspace repo ---
        REPO_NAME="nexus-${DOMAIN//./-}-gitea"
        echo "  Creating shared workspace repo: $REPO_NAME..."

        # Create API token for automation (reuse existing if present)
        # Use curl -s (not -sf) to avoid exit code 22 on HTTP errors with set -e
        GITEA_TOKEN=$(ssh nexus "curl -s -X POST 'http://localhost:3200/api/v1/users/$ADMIN_USERNAME/tokens' \
            -u '$ADMIN_USERNAME:$GITEA_ADMIN_PASS' \
            -H 'Content-Type: application/json' \
            -d '{\"name\":\"nexus-automation\",\"scopes\":[\"all\"]}'" 2>/dev/null | jq -r '.sha1 // empty')

        if [ -z "$GITEA_TOKEN" ]; then
            # Token may already exist, try to delete and recreate
            ssh nexus "curl -s -X DELETE 'http://localhost:3200/api/v1/users/$ADMIN_USERNAME/tokens/nexus-automation' \
                -u '$ADMIN_USERNAME:$GITEA_ADMIN_PASS'" >/dev/null 2>&1 || true
            GITEA_TOKEN=$(ssh nexus "curl -s -X POST 'http://localhost:3200/api/v1/users/$ADMIN_USERNAME/tokens' \
                -u '$ADMIN_USERNAME:$GITEA_ADMIN_PASS' \
                -H 'Content-Type: application/json' \
                -d '{\"name\":\"nexus-automation\",\"scopes\":[\"all\"]}'" 2>/dev/null | jq -r '.sha1 // empty')
        fi

        if [ -n "$GITEA_TOKEN" ]; then
            # Create private repo (requires auth for clone and push)
            # Use curl -s (not -sf) - repo may already exist (409), which is fine
            REPO_RESULT=$(ssh nexus "curl -s -X POST 'http://localhost:3200/api/v1/user/repos' \
                -H 'Authorization: token $GITEA_TOKEN' \
                -H 'Content-Type: application/json' \
                -d '{
                    \"name\": \"$REPO_NAME\",
                    \"description\": \"Shared workspace for notebooks, workflows, and pipelines\",
                    \"private\": true,
                    \"auto_init\": true,
                    \"default_branch\": \"main\"
                }'" 2>/dev/null || echo "")

            if echo "$REPO_RESULT" | jq -e '.id' >/dev/null 2>&1; then
                echo -e "${GREEN}  ✓ Shared repo '$REPO_NAME' created (private)${NC}"
            elif echo "$REPO_RESULT" | grep -q "already exists"; then
                echo -e "${YELLOW}  ⚠ Repo '$REPO_NAME' already exists${NC}"
                # Ensure existing repo is set to private
                ssh nexus "curl -s -X PATCH 'http://localhost:3200/api/v1/repos/$ADMIN_USERNAME/$REPO_NAME' \
                    -H 'Authorization: token $GITEA_TOKEN' \
                    -H 'Content-Type: application/json' \
                    -d '{\"private\": true}'" >/dev/null 2>&1 || true
            else
                echo -e "${YELLOW}  ⚠ Repo creation returned unexpected response${NC}"
            fi

            # --- Add user as collaborator to the repo ---
            if [ -n "$GITEA_USER_USERNAME" ] && [ -n "$GITEA_USER_PASS" ]; then
                ssh nexus "curl -s -X PUT 'http://localhost:3200/api/v1/repos/$ADMIN_USERNAME/$REPO_NAME/collaborators/$GITEA_USER_USERNAME' \
                    -H 'Authorization: token $GITEA_TOKEN' \
                    -H 'Content-Type: application/json' \
                    -d '{\"permission\": \"write\"}'" >/dev/null 2>&1 || true
                echo -e "${GREEN}  ✓ User '$GITEA_USER_USERNAME' added as collaborator${NC}"
            fi

            # --- Restart services that have Git integration (to pick up .env vars) ---
            # Services had their Git .env vars generated in Step 3 but Gitea wasn't
            # ready yet. Now that the repo exists, restart them to trigger git clone.
            RESTART_SERVICES=""
            for SERVICE in jupyter marimo code-server meltano prefect; do
                if echo "$ENABLED_SERVICES" | grep -qw "$SERVICE"; then
                    RESTART_SERVICES="$RESTART_SERVICES $SERVICE"
                fi
            done

            if [ -n "$RESTART_SERVICES" ]; then
                echo "  Restarting services with Git integration..."
                for SERVICE in $RESTART_SERVICES; do
                    ssh nexus "cd $REMOTE_STACKS_DIR/$SERVICE && docker compose restart" >/dev/null 2>&1 || true
                    echo "    Restarted $SERVICE"
                done
                echo -e "${GREEN}  ✓ Git-integrated services restarted${NC}"
            fi

            # --- Configure Kestra Git sync flow ---
            if echo "$ENABLED_SERVICES" | grep -qw "kestra"; then
                echo "  Configuring Kestra Git sync..."

                # Wait for Kestra to be ready
                KESTRA_READY=false
                for i in $(seq 1 20); do
                    if ssh nexus "curl -sf http://localhost:8085/api/v1/flows" >/dev/null 2>&1; then
                        KESTRA_READY=true
                        break
                    fi
                    sleep 3
                done

                if [ "$KESTRA_READY" = "true" ]; then
                    # Store GITEA_TOKEN as Kestra secret
                    ssh nexus "curl -sf -X PUT 'http://localhost:8085/api/v1/secrets/system/GITEA_TOKEN' \
                        -u '${ADMIN_EMAIL}:${KESTRA_PASS}' \
                        -H 'Content-Type: text/plain' \
                        -d '$GITEA_TOKEN'" >/dev/null 2>&1 || true

                    # Create git-sync flow (SyncNamespaceFiles from Gitea)
                    ssh nexus "curl -sf -X POST 'http://localhost:8085/api/v1/flows' \
                        -u '${ADMIN_EMAIL}:${KESTRA_PASS}' \
                        -H 'Content-Type: application/x-yaml' \
                        -d 'id: git-sync
namespace: system
tasks:
  - id: sync
    type: io.kestra.plugin.git.SyncNamespaceFiles
    url: http://gitea:3000/${ADMIN_USERNAME}/${REPO_NAME}.git
    branch: main
    username: ${ADMIN_USERNAME}
    password: \"{{ secret('\''GITEA_TOKEN'\'') }}\"
    namespace: \"{{ flow.namespace }}\"
    gitDirectory: workflows
triggers:
  - id: schedule
    type: io.kestra.core.models.triggers.types.Schedule
    cron: \"*/15 * * * *\"'" >/dev/null 2>&1 || true

                    echo -e "${GREEN}  ✓ Kestra Git sync flow created${NC}"
                else
                    echo -e "${YELLOW}  ⚠ Kestra not ready - skipping Git sync flow${NC}"
                fi
            fi

            # --- Create Woodpecker CI OAuth application in Gitea ---
            if echo "$ENABLED_SERVICES" | grep -qw "woodpecker" && [ -n "$WOODPECKER_AGENT_SECRET" ]; then
                echo "  Creating Woodpecker CI OAuth app in Gitea..."

                # Delete existing OAuth app if present (idempotent re-deploy)
                EXISTING_APPS=$(ssh nexus "curl -s 'http://localhost:3200/api/v1/user/applications/oauth2' \
                    -H 'Authorization: token $GITEA_TOKEN'" 2>/dev/null || echo "[]")
                EXISTING_APP_ID=$(echo "$EXISTING_APPS" | jq -r '.[] | select(.name=="Woodpecker CI") | .id // empty' 2>/dev/null)
                if [ -n "$EXISTING_APP_ID" ]; then
                    ssh nexus "curl -s -X DELETE 'http://localhost:3200/api/v1/user/applications/oauth2/$EXISTING_APP_ID' \
                        -H 'Authorization: token $GITEA_TOKEN'" >/dev/null 2>&1 || true
                fi

                # Create new OAuth application
                OAUTH_RESULT=$(ssh nexus "curl -s -X POST 'http://localhost:3200/api/v1/user/applications/oauth2' \
                    -H 'Authorization: token $GITEA_TOKEN' \
                    -H 'Content-Type: application/json' \
                    -d '{
                        \"name\": \"Woodpecker CI\",
                        \"redirect_uris\": [\"https://woodpecker.${DOMAIN}/authorize\"],
                        \"confidential_client\": true
                    }'" 2>/dev/null || echo "")

                WOODPECKER_GITEA_CLIENT=$(echo "$OAUTH_RESULT" | jq -r '.client_id // empty')
                WOODPECKER_GITEA_SECRET=$(echo "$OAUTH_RESULT" | jq -r '.client_secret // empty')

                if [ -n "$WOODPECKER_GITEA_CLIENT" ] && [ -n "$WOODPECKER_GITEA_SECRET" ]; then
                    echo -e "${GREEN}  ✓ Woodpecker OAuth app created${NC}"

                    # Update Woodpecker .env with OAuth credentials
                    cat > "$STACKS_DIR/woodpecker/.env" << WPEOF
# Auto-generated - DO NOT COMMIT
DOMAIN=${DOMAIN}
WOODPECKER_AGENT_SECRET=${WOODPECKER_AGENT_SECRET}
WOODPECKER_ADMIN=${ADMIN_USERNAME:-}
WOODPECKER_GITEA_CLIENT=${WOODPECKER_GITEA_CLIENT}
WOODPECKER_GITEA_SECRET=${WOODPECKER_GITEA_SECRET}
WPEOF

                    # Sync updated .env to server and start Woodpecker
                    rsync -az "$STACKS_DIR/woodpecker/" nexus:$REMOTE_STACKS_DIR/woodpecker/
                    if ssh nexus "cd $REMOTE_STACKS_DIR/woodpecker && source /opt/docker-server/stacks/.env && docker compose up -d" 2>&1; then
                        echo -e "${GREEN}  ✓ Woodpecker started with Gitea forge${NC}"
                    else
                        echo -e "${YELLOW}  ⚠ Failed to start Woodpecker - check container logs${NC}"
                    fi
                else
                    echo -e "${YELLOW}  ⚠ Could not create Woodpecker OAuth app in Gitea${NC}"
                fi
            fi

            echo -e "${GREEN}  ✓ Gitea workspace setup complete${NC}"
        else
            echo -e "${YELLOW}  ⚠ Could not create Gitea API token - skipping repo setup${NC}"
        fi
    else
        echo -e "${YELLOW}  ⚠ Gitea not ready after 60s - skipping admin setup${NC}"
        echo -e "${YELLOW}    Credentials available in Infisical${NC}"
    fi
fi

# =============================================================================
# GitHub Mirror Setup (optional)
# Mirrors one or more private GitHub repos into Gitea as pull mirrors.
# Requires GH_MIRROR_TOKEN (GitHub PAT with Contents:read permission) and
# GH_MIRROR_REPOS (comma-separated list of GitHub repo URLs).
# If either variable is unset, this block is skipped entirely.
# =============================================================================
if echo "$ENABLED_SERVICES" | grep -qw "gitea" \
    && [ -n "${GH_MIRROR_TOKEN:-}" ] \
    && [ -n "${GH_MIRROR_REPOS:-}" ] \
    && [ -n "${GITEA_TOKEN:-}" ]; then

    echo ""
    echo "=========================================="
    echo "  Setting up GitHub Mirrors"
    echo "=========================================="

    # Get admin user ID (required by Gitea migration API)
    GITEA_ADMIN_UID=$(ssh nexus "curl -s \
        'http://localhost:3200/api/v1/users/$ADMIN_USERNAME' \
        -H 'Authorization: token $GITEA_TOKEN'" 2>/dev/null \
        | jq -r '.id // empty')

    if [ -z "$GITEA_ADMIN_UID" ]; then
        echo -e "${YELLOW}  ⚠ Could not get Gitea admin UID - skipping mirrors${NC}"
    else
        IFS=',' read -ra MIRROR_REPOS <<< "$GH_MIRROR_REPOS"
        for REPO_URL in "${MIRROR_REPOS[@]}"; do
            REPO_URL=$(echo "$REPO_URL" | tr -d ' ')
            [ -z "$REPO_URL" ] && continue
            REPO_NAME="mirror-$(basename "$REPO_URL" .git)"

            echo "  Mirroring: $REPO_NAME..."

            # Skip if mirror already exists (idempotent re-deploy)
            HTTP_CODE=$(ssh nexus "curl -s -o /dev/null -w '%{http_code}' \
                'http://localhost:3200/api/v1/repos/$ADMIN_USERNAME/$REPO_NAME' \
                -H 'Authorization: token $GITEA_TOKEN'")

            if [ "$HTTP_CODE" = "200" ]; then
                echo -e "${YELLOW}  ⚠ Mirror '$REPO_NAME' already exists, skipping${NC}"
                continue
            fi

            MIGRATE_PAYLOAD=$(jq -n \
                --arg clone_addr "$REPO_URL" \
                --arg repo_name "$REPO_NAME" \
                --arg auth_token "$GH_MIRROR_TOKEN" \
                --argjson uid "$GITEA_ADMIN_UID" \
                '{
                    clone_addr: $clone_addr,
                    repo_name: $repo_name,
                    private: true,
                    mirror: true,
                    mirror_interval: "10m0s",
                    auth_token: $auth_token,
                    uid: $uid
                }')

            MIRROR_RESULT=$(printf '%s' "$MIGRATE_PAYLOAD" | ssh nexus "curl -s -X POST \
                'http://localhost:3200/api/v1/repos/migrate' \
                -H 'Authorization: token $GITEA_TOKEN' \
                -H 'Content-Type: application/json' \
                -d @-" 2>/dev/null || echo "")

            if echo "$MIRROR_RESULT" | jq -e '.id' >/dev/null 2>&1; then
                echo -e "${GREEN}  ✓ Mirror '$REPO_NAME' created (syncs every 10 min)${NC}"

                # Grant student user (gitea_user) read-only access
                if [ -n "$GITEA_USER_USERNAME" ]; then
                    COLLAB_PAYLOAD=$(jq -n '{permission: "read"}')
                    printf '%s' "$COLLAB_PAYLOAD" | ssh nexus "curl -s -X PUT \
                        'http://localhost:3200/api/v1/repos/$ADMIN_USERNAME/$REPO_NAME/collaborators/$GITEA_USER_USERNAME' \
                        -H 'Authorization: token $GITEA_TOKEN' \
                        -H 'Content-Type: application/json' \
                        -d @-" >/dev/null 2>&1 || true
                    echo -e "${GREEN}  ✓ Read access granted to '$GITEA_USER_USERNAME'${NC}"
                fi
            else
                echo -e "${YELLOW}  ⚠ Mirror '$REPO_NAME' setup failed${NC}"
                echo -e "${YELLOW}    Verify GH_MIRROR_TOKEN has Contents:read permission${NC}"
                echo -e "${YELLOW}    and GH_MIRROR_REPOS contains valid GitHub HTTPS URLs${NC}"
            fi
        done
    fi
fi

# Configure Wiki.js admin (uses user_email, not admin)
if echo "$ENABLED_SERVICES" | grep -qw "wikijs" && [ -n "$WIKIJS_ADMIN_PASS" ]; then
    (
        echo "  Configuring Wiki.js admin..."
        WIKIJS_EMAIL="${USER_EMAIL:-$ADMIN_EMAIL}"
        for i in $(seq 1 30); do
            if ssh nexus "curl -fsS --connect-timeout 2 'http://localhost:3005/healthz'" 2>/dev/null | grep -qi 'ok'; then
                break
            fi
            sleep 3
        done

        # Wiki.js finalize setup via GraphQL API
        SETUP_PAYLOAD=$(jq -n \
            --arg email "$WIKIJS_EMAIL" \
            --arg pass "$WIKIJS_ADMIN_PASS" \
            --arg url "https://wiki.${DOMAIN}" \
            '{query: "mutation ($input: SetupInput!) { setup(input: $input) { responseResult { succeeded message } } }", variables: {input: {adminEmail: $email, adminPassword: $pass, adminPasswordConfirm: $pass, siteUrl: $url, telemetry: false}}}')

        RESULT=$(printf '%s' "$SETUP_PAYLOAD" | ssh nexus "curl -s -X POST 'http://localhost:3005/graphql' \
            -H 'Content-Type: application/json' \
            -d @-" 2>&1 || echo "")

        if echo "$RESULT" | grep -q '"succeeded":true'; then
            echo -e "${GREEN}  ✓ Wiki.js admin created (user: $WIKIJS_EMAIL)${NC}"
        elif echo "$RESULT" | grep -q 'already'; then
            echo -e "${YELLOW}  ⚠ Wiki.js already configured${NC}"
        else
            echo -e "${YELLOW}  ⚠ Wiki.js auto-setup failed - configure manually at first login${NC}"
            echo -e "${YELLOW}    Credentials available in Infisical${NC}"
        fi
    ) &
    CONFIG_JOBS+=($!)
fi

# Configure Dify admin account
if echo "$ENABLED_SERVICES" | grep -qw "dify" && [ -n "$DIFY_ADMIN_PASS" ]; then
    (
        echo "  Configuring Dify..."

        # Wait for Dify API to be ready (returns 307 when working)
        DIFY_READY=false
        for i in $(seq 1 40); do
            DIFY_HEALTH=$(ssh nexus "curl -s -o /dev/null -w '%{http_code}' http://localhost:8501/ 2>/dev/null" || echo "000")
            if [ "$DIFY_HEALTH" = "200" ] || [ "$DIFY_HEALTH" = "302" ] || [ "$DIFY_HEALTH" = "307" ]; then
                DIFY_READY=true
                break
            fi
            sleep 3
        done

        if [ "$DIFY_READY" = "false" ]; then
            echo -e "${YELLOW}  ⚠ Dify not ready after 120s - skipping auto-configuration${NC}"
            exit 0
        fi

        # Wait for API to be fully initialized
        sleep 5

        # Check if setup is already completed
        SETUP_CHECK=$(ssh nexus "curl -s http://localhost:8501/console/api/setup" 2>/dev/null || echo "")
        if echo "$SETUP_CHECK" | grep -q '"step":"finished"'; then
            echo -e "${YELLOW}  ⚠ Dify already configured - skipping admin setup${NC}"
        else
            # Step 1: Validate init password (required before setup)
            INIT_RESULT=$(ssh nexus "curl -s -c /tmp/dify-cookies -X POST 'http://localhost:8501/console/api/init' \
                -H 'Content-Type: application/json' \
                -d '{\"password\":\"$DIFY_ADMIN_PASS\"}'" 2>&1 || echo "")

            if ! echo "$INIT_RESULT" | grep -q '"result":"success"'; then
                echo -e "${YELLOW}  ⚠ Dify init validation failed - configure manually${NC}"
                exit 0
            fi

            # Step 2: Create admin account via setup API (uses session cookie from init)
            DIFY_SETUP_PAYLOAD=$(jq -n \
                --arg email "$ADMIN_EMAIL" \
                --arg password "$DIFY_ADMIN_PASS" \
                '{email: $email, name: "Admin", password: $password}')
            DIFY_RESULT=$(printf '%s' "$DIFY_SETUP_PAYLOAD" | ssh nexus "curl -s -b /tmp/dify-cookies -X POST 'http://localhost:8501/console/api/setup' \
                -H 'Content-Type: application/json' \
                -d @-" 2>&1 || echo "")

            # Clean up cookies
            ssh nexus "rm -f /tmp/dify-cookies" 2>/dev/null || true

            if echo "$DIFY_RESULT" | grep -q '"result":"success"'; then
                echo -e "${GREEN}  ✓ Dify admin created (email: $ADMIN_EMAIL)${NC}"
            elif echo "$DIFY_RESULT" | grep -qi 'already'; then
                echo -e "${YELLOW}  ⚠ Dify already configured${NC}"
            else
                echo -e "${YELLOW}  ⚠ Dify auto-setup failed - configure manually at /install${NC}"
                echo -e "${YELLOW}    Credentials available in Infisical${NC}"
            fi
        fi
    ) &
    CONFIG_JOBS+=($!)
fi

# Wait for all background configuration jobs to complete
if [ ${#CONFIG_JOBS[@]} -gt 0 ]; then
    echo "  Waiting for background configuration jobs to complete..."
    wait "${CONFIG_JOBS[@]}"
else
    echo "  No background configuration jobs to wait for"
fi

# -----------------------------------------------------------------------------
# Done!
# -----------------------------------------------------------------------------
echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                    ✅ Deployment Complete!                    ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Show service URLs from tofu output
echo -e "${CYAN}🔗 Your Services:${NC}"
cd "$TOFU_DIR" && tofu output -json service_urls 2>/dev/null | jq -r 'to_entries | .[] | "   \(.key): \(.value)"' || echo "   (service URLs not available)"
echo ""

echo -e "${CYAN}📌 SSH Access:${NC}"
echo -e "   ssh nexus"
echo ""
echo -e "${CYAN}🔐 View credentials:${NC}"
echo -e "   Credentials available in Infisical"
echo ""
