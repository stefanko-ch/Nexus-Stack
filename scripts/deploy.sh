#!/bin/bash
set -e

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

# Check if we can access state (remote or local)
cd "$TOFU_DIR"
if ! tofu state list >/dev/null 2>&1; then
    echo -e "${RED}Error: No OpenTofu state found. Run 'make up' first.${NC}"
    exit 1
fi
cd "$PROJECT_ROOT"

# Get domain and admin email from config
DOMAIN=$(grep -E '^domain\s*=' "$TOFU_DIR/config.tfvars" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' || echo "")
ADMIN_EMAIL=$(grep -E '^admin_email\s*=' "$TOFU_DIR/config.tfvars" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' || echo "admin@$DOMAIN")
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
  ProxyCommand cloudflared access ssh --hostname %h --id '${CF_ACCESS_CLIENT_ID}' --secret '${CF_ACCESS_CLIENT_SECRET}'
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
    MAX_TOKEN_RETRIES=8
    echo "  Note: Service Token may need up to 60-90 seconds to propagate in Cloudflare..."
    
    # Initial wait for Service Token propagation (Cloudflare needs time to activate)
    # Fresh tunnels typically need 30-90 seconds to become active and connect to the edge
    INITIAL_WAIT=60
    echo "  Waiting ${INITIAL_WAIT}s for initial tunnel connection..."
    sleep $INITIAL_WAIT

    TOKEN_RETRY=0
    BACKOFF=15
    
    while [ $TOKEN_RETRY -lt $MAX_TOKEN_RETRIES ]; do
        if OUTPUT=$(ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o BatchMode=yes nexus 'echo ok' 2>&1); then
            echo -e "${GREEN}  ✓ Service Token authentication successful${NC}"
            break
        fi
        TOKEN_RETRY=$((TOKEN_RETRY + 1))
        if [ $TOKEN_RETRY -lt $MAX_TOKEN_RETRIES ]; then
            echo "  Retry $TOKEN_RETRY/$MAX_TOKEN_RETRIES - waiting ${BACKOFF}s for propagation..."
            echo "  Debug: $OUTPUT"
            sleep $BACKOFF
            BACKOFF=$((BACKOFF + 5))  # Linear increase: 10s, 15s, 20s, 25s...
        fi
    done
    
    if [ $TOKEN_RETRY -eq $MAX_TOKEN_RETRIES ]; then
        echo ""
        echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║  ${YELLOW}❌ Service Token Authentication Failed${RED}                            ║${NC}"
        echo -e "${RED}╠═══════════════════════════════════════════════════════════════╣${NC}"
        echo -e "${RED}║${NC}  Service Token authentication failed after $MAX_TOKEN_RETRIES attempts.   ${RED}║${NC}"
        echo -e "${RED}║${NC}  Browser login fallback is not supported in GitHub Actions.      ${RED}║${NC}"
        echo -e "${RED}║${NC}  Please check that the Service Token is correctly configured.     ${RED}║${NC}"
        echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        exit 1
    fi
fi

MAX_RETRIES=15
RETRY=0
TIMEOUT=5
while [ $RETRY -lt $MAX_RETRIES ]; do
    if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=$TIMEOUT -o BatchMode=yes nexus 'echo ok' 2>/dev/null; then
        echo -e "${GREEN}  ✓ SSH connection established${NC}"
        break
    fi
    RETRY=$((RETRY + 1))
    if [ $RETRY -lt $MAX_RETRIES ]; then
        echo "  Attempt $RETRY/$MAX_RETRIES - waiting for tunnel..."
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
    exit 1
fi

# -----------------------------------------------------------------------------
# Prepare stacks with secrets
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[3/7] Preparing stacks...${NC}"

# Get enabled services from tofu output
ENABLED_SERVICES=$(cd "$TOFU_DIR" && tofu output -json enabled_services 2>/dev/null | jq -r '.[]')

if [ -z "$ENABLED_SERVICES" ]; then
    echo -e "${YELLOW}  Warning: No enabled services in config.tfvars${NC}"
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
if echo "$ENABLED_SERVICES" | grep -qw "info"; then
    echo "  Generating info page..."
    "$SCRIPT_DIR/generate-info-page.sh"
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

# Sync only enabled stacks
for service in $ENABLED_SERVICES; do
    if [ -d "$STACKS_DIR/$service" ]; then
        echo "  Syncing $service..."
        rsync -av "$STACKS_DIR/$service/" "nexus:$REMOTE_STACKS_DIR/$service/"
    else
        echo -e "${YELLOW}  Warning: Stack folder 'stacks/$service' not found - skipping${NC}"
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
# Pre-pull Docker images (parallel)
# -----------------------------------------------------------------------------
# Start containers (parallel)
# Note: docker compose up -d will automatically pull missing images
# To force update images, use: docker compose pull && docker compose up -d
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[6/7] Starting enabled containers (parallel)...${NC}"

ssh nexus "
set -e
# Export image versions from global .env
if [ -f /opt/docker-server/stacks/.env ]; then
    set -a
    source /opt/docker-server/stacks/.env
    set +a
fi
for service in $ENABLED_LIST; do
    if [ -f /opt/docker-server/stacks/\$service/docker-compose.yml ]; then
        echo \"  Starting \$service...\"
        (cd /opt/docker-server/stacks/\$service && docker compose up -d) &
    fi
done
wait
echo ''
echo '  ✓ All enabled stacks started'
"

echo -e "${GREEN}  ✓ All containers started${NC}"

# -----------------------------------------------------------------------------
# Auto-configure services
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[7/7] Auto-configuring services...${NC}"

# Configure Infisical admin and push secrets
if echo "$ENABLED_SERVICES" | grep -qw "infisical"; then
    echo "  Configuring Infisical..."
    
    # Wait for Infisical to be ready (optimized: check container status first)
    echo "  Waiting for Infisical to be ready..."
    INFISICAL_READY=false
    # First check if container is running (faster than HTTP)
    for i in $(seq 1 10); do
        CONTAINER_STATUS=$(ssh nexus "docker inspect --format='{{.State.Status}}' infisical 2>/dev/null" || echo "")
        if [ "$CONTAINER_STATUS" = "running" ]; then
            break
        fi
        sleep 1
    done
    # Then check HTTP endpoint with shorter intervals initially
    for i in $(seq 1 20); do
        if ssh nexus "curl -s --connect-timeout 3 'http://localhost:8070/api/v1/admin/config'" 2>/dev/null | grep -q 'initialized'; then
            INFISICAL_READY=true
            break
        fi
        # Start with 1s intervals, increase to 2s after 10 retries
        if [ $i -lt 10 ]; then
            sleep 1
        else
            sleep 2
        fi
    done
    
    if [ "$INFISICAL_READY" = "false" ]; then
        echo -e "${YELLOW}  ⚠ Infisical not responding after 60s - skipping config${NC}"
    else
    # Check if already initialized
    INIT_CHECK=$(ssh nexus "curl -s 'http://localhost:8070/api/v1/admin/config'" 2>/dev/null || echo "")
    
    if echo "$INIT_CHECK" | grep -q '"initialized":true'; then
        echo -e "${YELLOW}  ⚠ Infisical already configured${NC}"
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
                    for TAG_NAME in "infisical" "portainer" "uptime-kuma" "grafana" "n8n" "kestra" "metabase" "cloudbeaver" "config" "ssh"; do
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
                    CONFIG_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="config") | .id // empty' 2>/dev/null)
                    SSH_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="ssh") | .id // empty' 2>/dev/null)
                    
                    echo -e "${GREEN}  ✓ Tags created${NC}"
                    echo "  Pushing secrets to Infisical..."
                    
                    # Build secrets payload with usernames and tags
                    # Prepare SSH private key for JSON (base64 encode to handle newlines)
                    SSH_KEY_SECRET=""
                    if [ -n "${SSH_PRIVATE_KEY_CONTENT:-}" ]; then
                        SSH_KEY_BASE64=$(echo "$SSH_PRIVATE_KEY_CONTENT" | base64 | tr -d '\n')
                        SSH_KEY_SECRET=",{\"secretKey\": \"SSH_PRIVATE_KEY_BASE64\", \"secretValue\": \"$SSH_KEY_BASE64\", \"tagIds\": [\"$SSH_TAG\"]}"
                    fi
                    
                    # Using v4 API which supports tagIds
                    SECRETS_PAYLOAD=$(cat <<SECRETS_EOF
{
  "projectId": "$PROJECT_ID",
  "environment": "prod",
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
    {"secretKey": "N8N_USERNAME", "secretValue": "$ADMIN_USERNAME", "tagIds": ["$N8N_TAG"]},
    {"secretKey": "N8N_PASSWORD", "secretValue": "$N8N_PASS", "tagIds": ["$N8N_TAG"]},
    {"secretKey": "KESTRA_USERNAME", "secretValue": "$ADMIN_EMAIL", "tagIds": ["$KESTRA_TAG"]},
    {"secretKey": "KESTRA_PASSWORD", "secretValue": "$KESTRA_PASS", "tagIds": ["$KESTRA_TAG"]},
    {"secretKey": "METABASE_USERNAME", "secretValue": "$ADMIN_EMAIL", "tagIds": ["$METABASE_TAG"]},
    {"secretKey": "METABASE_PASSWORD", "secretValue": "$METABASE_PASS", "tagIds": ["$METABASE_TAG"]},
    {"secretKey": "CLOUDBEAVER_USERNAME", "secretValue": "$ADMIN_USERNAME", "tagIds": ["$CLOUDBEAVER_TAG"]},
    {"secretKey": "CLOUDBEAVER_PASSWORD", "secretValue": "$CLOUDBEAVER_PASS", "tagIds": ["$CLOUDBEAVER_TAG"]}$SSH_KEY_SECRET
  ]
}
SECRETS_EOF
)
                    
                    SECRETS_RESULT=$(ssh nexus "curl -s -X POST 'http://localhost:8070/api/v4/secrets/batch' \
                        -H 'Authorization: Bearer $INFISICAL_TOKEN' \
                        -H 'Content-Type: application/json' \
                        -d '$(echo "$SECRETS_PAYLOAD" | tr -d '\n' | tr -s ' ')'" 2>&1 || echo "")
                    
                    if echo "$SECRETS_RESULT" | grep -qE '"secrets"|"secretKey"'; then
                        echo -e "${GREEN}  ✓ All secrets pushed to Infisical (with tags)${NC}"
                        if [ -n "${SSH_PRIVATE_KEY_CONTENT:-}" ]; then
                            echo -e "${GREEN}  ✓ SSH private key stored (base64 encoded)${NC}"
                            echo -e "${DIM}    Decode with: base64 -d <<< \"\$SSH_PRIVATE_KEY_BASE64\" > ~/.ssh/nexus_key${NC}"
                        fi
                    else
                        echo -e "${YELLOW}  ⚠ Failed to push secrets${NC}"
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
    
    # Get Metabase port from services config (default: 3000)
    METABASE_PORT=$(echo "$SERVICES_JSON" | jq -r '.metabase.port // 3000')
    
    # Wait for Metabase to be ready (Java app, takes longer to start)
    echo "  Waiting for Metabase to be ready..."
    METABASE_READY=false
    for i in $(seq 1 60); do
        METABASE_HEALTH=$(ssh nexus "curl -s -o /dev/null -w '%{http_code}' http://localhost:$METABASE_PORT/api/health 2>/dev/null" || echo "000")
        if [ "$METABASE_HEALTH" = "200" ]; then
            METABASE_READY=true
            break
        fi
        sleep 2
    done
    
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

# Configure Uptime Kuma admin
if echo "$ENABLED_SERVICES" | grep -qw "uptime-kuma" && [ -n "$KUMA_PASS" ]; then
    echo "  Configuring Uptime Kuma..."
    
    # Wait for Uptime Kuma container to be ready (optimized: check status first)
    echo "  Waiting for Uptime Kuma to be ready..."
    KUMA_READY=false
    # First check if container is running (faster than health check)
    for i in $(seq 1 10); do
        CONTAINER_STATUS=$(ssh nexus "docker inspect --format='{{.State.Status}}' uptime-kuma 2>/dev/null" || echo "")
        if [ "$CONTAINER_STATUS" = "running" ]; then
            break
        fi
        sleep 1
    done
    # Then check health status with shorter intervals initially
    for i in $(seq 1 20); do
        KUMA_HEALTH=$(ssh nexus "docker inspect --format='{{.State.Health.Status}}' uptime-kuma 2>/dev/null" || echo "")
        if [ "$KUMA_HEALTH" = "healthy" ]; then
            KUMA_READY=true
            break
        fi
        # Start with 1s intervals, increase to 2s after 10 retries
        if [ $i -lt 10 ]; then
            sleep 1
        else
            sleep 2
        fi
    done
    
    if [ "$KUMA_READY" = "false" ]; then
        echo -e "${YELLOW}  ⚠ Uptime Kuma not healthy after 60s - skipping config${NC}"
    else
        # Kuma uses socket.io for setup - run via container's node
        # Parameters are separate: setup(username, password, callback) - NOT an object!
        SETUP_SCRIPT='
const { io } = require("socket.io-client");
const socket = io("http://localhost:3001", { transports: ["websocket"] });
socket.on("connect", () => {
    socket.emit("needSetup", (needSetup) => {
        if (!needSetup) { console.log("ALREADY_CONFIGURED"); process.exit(0); }
        socket.emit("setup", process.env.KUMA_USER, process.env.KUMA_PASS, (res) => {
            if (res && res.ok) { console.log("SUCCESS"); process.exit(0); }
            else { console.log("FAILED"); process.exit(1); }
        });
    });
});
socket.on("connect_error", () => { console.log("CONNECTION_ERROR"); process.exit(1); });
setTimeout(() => { console.log("TIMEOUT"); process.exit(1); }, 15000);
'
        KUMA_RESULT=$(ssh nexus "docker exec -e KUMA_USER='$ADMIN_USERNAME' -e KUMA_PASS='$KUMA_PASS' uptime-kuma node -e '$SETUP_SCRIPT'" 2>&1 || echo "EXEC_FAILED")
        
        if echo "$KUMA_RESULT" | grep -q "SUCCESS"; then
            echo -e "${GREEN}  ✓ Uptime Kuma admin created (user: $ADMIN_USERNAME)${NC}"
            KUMA_SETUP_SUCCESS=true
        elif echo "$KUMA_RESULT" | grep -q "ALREADY_CONFIGURED"; then
            echo -e "${YELLOW}  ⚠ Uptime Kuma already configured${NC}"
            KUMA_SETUP_SUCCESS=true
        else
            echo -e "${YELLOW}  ⚠ Kuma auto-setup failed - configure manually at first login${NC}"
            echo -e "${YELLOW}    Credentials available in Infisical${NC}"
            KUMA_SETUP_SUCCESS=false
        fi
        
        # Sync monitors for all enabled services (add missing, remove disabled)
        # This runs on every deploy, not just first setup
        echo "  Syncing service monitors..."
        
        # Get service URLs from tofu output
        SERVICE_URLS=$(cd "$TOFU_DIR" && tofu output -json service_urls 2>/dev/null || echo "{}")
        
        # Build desired monitors JSON array (services that should be monitored)
        DESIRED_JSON="["
        FIRST=true
        for service in $ENABLED_LIST; do
            # Skip uptime-kuma itself
            [ "$service" = "uptime-kuma" ] && continue
            
            # Get the URL for this service
            SERVICE_URL=$(echo "$SERVICE_URLS" | jq -r ".\"$service\" // empty")
            [ -z "$SERVICE_URL" ] && continue
            
            # Format service name for display (capitalize, replace dashes)
            DISPLAY_NAME=$(echo "$service" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1')
            
            if [ "$FIRST" = "true" ]; then
                FIRST=false
            else
                DESIRED_JSON="$DESIRED_JSON,"
            fi
            
            DESIRED_JSON="$DESIRED_JSON{\"name\":\"$DISPLAY_NAME\",\"url\":\"$SERVICE_URL\"}"
        done
        DESIRED_JSON="$DESIRED_JSON]"
        
        # Sync monitors via socket.io (add missing, delete removed)
        SYNC_SCRIPT='
const { io } = require("socket.io-client");
const desired = JSON.parse(process.env.DESIRED);
const socket = io("http://localhost:3001", { transports: ["websocket"] });
let added = 0, deleted = 0;
let existingMonitors = {};

socket.on("monitorList", (data) => {
    existingMonitors = data;
});

socket.on("connect", () => {
    socket.emit("login", { username: process.env.KUMA_USER, password: process.env.KUMA_PASS }, async (res) => {
        if (!res || !res.ok) { console.log("LOGIN_FAILED"); process.exit(1); }
        
        // Get current monitors
        await new Promise(resolve => {
            socket.emit("getMonitorList", () => setTimeout(resolve, 500));
        });
        
        const existing = Object.values(existingMonitors);
        const existingUrls = existing.map(m => m.url);
        const desiredUrls = desired.map(m => m.url);
        
        // Add missing monitors
        for (const m of desired) {
            if (!existingUrls.includes(m.url)) {
                const monitor = {
                    type: "http",
                    name: m.name,
                    url: m.url,
                    method: "GET",
                    interval: 60,
                    retryInterval: 60,
                    maxretries: 3,
                    accepted_statuscodes: ["200-299", "401", "403"],
                    active: true
                };
                await new Promise(resolve => {
                    socket.emit("add", monitor, (r) => { if (r && r.ok) added++; resolve(); });
                });
            }
        }
        
        // Delete monitors for disabled services
        for (const m of existing) {
            if (!desiredUrls.includes(m.url)) {
                await new Promise(resolve => {
                    socket.emit("deleteMonitor", m.id, (r) => { if (r && r.ok) deleted++; resolve(); });
                });
            }
        }
        
        console.log("SYNC:" + added + ":" + deleted + ":" + desired.length);
        process.exit(0);
    });
});
socket.on("connect_error", () => { console.log("CONNECTION_ERROR"); process.exit(1); });
setTimeout(() => { console.log("TIMEOUT"); process.exit(1); }, 30000);
'
        # Escape the JSON for shell
        DESIRED_ESCAPED=$(echo "$DESIRED_JSON" | sed "s/'/'\\\\''/g")
        
        SYNC_RESULT=$(ssh nexus "docker exec -e KUMA_USER='$ADMIN_USERNAME' -e KUMA_PASS='$KUMA_PASS' -e DESIRED='$DESIRED_ESCAPED' uptime-kuma node -e '$SYNC_SCRIPT'" 2>&1 || echo "EXEC_FAILED")
        
        if echo "$SYNC_RESULT" | grep -q "SYNC:"; then
            SYNC_DATA=$(echo "$SYNC_RESULT" | grep "SYNC:" | head -1)
            ADDED_COUNT=$(echo "$SYNC_DATA" | cut -d: -f2)
            DELETED_COUNT=$(echo "$SYNC_DATA" | cut -d: -f3)
            TOTAL_COUNT=$(echo "$SYNC_DATA" | cut -d: -f4)
            
            if [ "$ADDED_COUNT" = "0" ] && [ "$DELETED_COUNT" = "0" ]; then
                echo -e "${GREEN}  ✓ Monitors in sync ($TOTAL_COUNT services)${NC}"
            else
                echo -e "${GREEN}  ✓ Monitors synced: +$ADDED_COUNT added, -$DELETED_COUNT removed ($TOTAL_COUNT total)${NC}"
            fi
        else
            echo -e "${YELLOW}  ⚠ Failed to sync monitors${NC}"
        fi
    fi
fi

# Wait for all background configuration jobs to complete
if [ ${#CONFIG_JOBS[@]} -gt 0 ]; then
    echo "  Waiting for background configuration jobs to complete..."
    wait "${CONFIG_JOBS[@]}"
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
cd "$TOFU_DIR" && tofu output -json service_urls 2>/dev/null | jq -r 'to_entries | .[] | "   \(.key): \(.value)"' || echo "   (run 'make urls' to see service URLs)"
echo ""

echo -e "${CYAN}📌 SSH Access:${NC}"
echo -e "   ssh nexus"
echo ""
echo -e "${CYAN}🔐 View credentials:${NC}"
echo -e "   make secrets"
echo ""
