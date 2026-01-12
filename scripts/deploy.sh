#!/bin/bash
set -e

# =============================================================================
# Nexus-Stack Deploy Script
# Runs after tofu apply to start containers
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TOFU_DIR="$PROJECT_ROOT/tofu"
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
# Check OpenTofu state
# -----------------------------------------------------------------------------
if [ ! -f "$TOFU_DIR/terraform.tfstate" ]; then
    echo -e "${RED}Error: No OpenTofu state found. Run 'make up' first.${NC}"
    exit 1
fi

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
DOCKERHUB_USER=$(echo "$SECRETS_JSON" | jq -r '.dockerhub_username // empty')
DOCKERHUB_TOKEN=$(echo "$SECRETS_JSON" | jq -r '.dockerhub_token // empty')

echo -e "${GREEN}  ✓ Secrets loaded (admin user: $ADMIN_USERNAME)${NC}"

# Clean old SSH known_hosts entries
SERVER_IP=$(cd "$TOFU_DIR" && tofu output -raw server_ip 2>/dev/null || echo "")
[ -n "$SSH_HOST" ] && ssh-keygen -R "$SSH_HOST" 2>/dev/null || true
[ -n "$SERVER_IP" ] && ssh-keygen -R "$SERVER_IP" 2>/dev/null || true

# -----------------------------------------------------------------------------
# Setup SSH Config (if not already present)
# -----------------------------------------------------------------------------
SSH_CONFIG="$HOME/.ssh/config"

if ! grep -q "Host nexus" "$SSH_CONFIG" 2>/dev/null; then
    echo -e "${YELLOW}[1/7] Adding SSH config for nexus...${NC}"
    mkdir -p "$HOME/.ssh"
    cat >> "$SSH_CONFIG" << EOF

Host nexus
  HostName ${SSH_HOST}
  User root
  ProxyCommand cloudflared access ssh --hostname %h
EOF
    chmod 600 "$SSH_CONFIG"
    echo -e "${GREEN}  ✓ SSH config added to ~/.ssh/config${NC}"
else
    echo -e "${GREEN}[1/7] SSH config for nexus already exists${NC}"
fi

# -----------------------------------------------------------------------------
# Cloudflare Zero Trust Authentication
# -----------------------------------------------------------------------------
echo ""
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  ${YELLOW}⚠️  Cloudflare Zero Trust Authentication Required${CYAN}            ║${NC}"
echo -e "${CYAN}╠═══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  Opening browser for Zero Trust login...                      ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  1. Check your email for the verification code               ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  2. Enter the code in the browser                            ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  3. Press Enter here when done                               ${CYAN}║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

cloudflared access login "https://${SSH_HOST}" >/dev/null 2>&1 &
CFLOGIN_PID=$!
sleep 2

read -p "Press Enter after completing Zero Trust authentication... "
kill $CFLOGIN_PID 2>/dev/null || true
echo ""

# -----------------------------------------------------------------------------
# Wait for SSH connection
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[2/7] Waiting for SSH via Cloudflare Tunnel...${NC}"
MAX_RETRIES=30
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 nexus 'echo ok' 2>/dev/null; then
        echo -e "${GREEN}  ✓ SSH connection established${NC}"
        break
    fi
    RETRY=$((RETRY + 1))
    echo "  Attempt $RETRY/$MAX_RETRIES - waiting for tunnel..."
    sleep 10
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
# Start containers (only enabled services)
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[6/7] Starting enabled containers...${NC}"

ssh nexus "
set -e
for service in $ENABLED_LIST; do
    if [ -f /opt/docker-server/stacks/\$service/docker-compose.yml ]; then
        echo \"  Starting \$service...\"
        cd /opt/docker-server/stacks/\$service
        docker compose up -d
    fi
done
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
    
    # Wait for Infisical to be ready (can take 30-60s on first start)
    echo "  Waiting for Infisical to be ready..."
    INFISICAL_READY=false
    for i in $(seq 1 30); do
        if ssh nexus "curl -s --connect-timeout 5 'http://localhost:8070/api/v1/admin/config'" 2>/dev/null | grep -q 'initialized'; then
            INFISICAL_READY=true
            break
        fi
        sleep 2
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
                    for TAG_NAME in "infisical" "portainer" "uptime-kuma" "grafana" "config"; do
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
                    CONFIG_TAG=$(echo "$TAGS_RESULT" | jq -r '.tags[] | select(.slug=="config") | .id // empty' 2>/dev/null)
                    
                    echo -e "${GREEN}  ✓ Tags created${NC}"
                    echo "  Pushing secrets to Infisical..."
                    
                    # Build secrets payload with usernames and tags
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
    {"secretKey": "GRAFANA_PASSWORD", "secretValue": "$GRAFANA_PASS", "tagIds": ["$GRAFANA_TAG"]}
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

# Configure Portainer admin
if echo "$ENABLED_SERVICES" | grep -qw "portainer" && [ -n "$PORTAINER_PASS" ]; then
    echo "  Configuring Portainer admin..."
    sleep 3
    
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
fi

# Configure Uptime Kuma admin
if echo "$ENABLED_SERVICES" | grep -qw "uptime-kuma" && [ -n "$KUMA_PASS" ]; then
    echo "  Configuring Uptime Kuma..."
    
    # Wait for Uptime Kuma container to be ready
    echo "  Waiting for Uptime Kuma to be ready..."
    KUMA_READY=false
    for i in $(seq 1 30); do
        # Check if container is healthy
        KUMA_HEALTH=$(ssh nexus "docker inspect --format='{{.State.Health.Status}}' uptime-kuma 2>/dev/null" || echo "")
        if [ "$KUMA_HEALTH" = "healthy" ]; then
            KUMA_READY=true
            break
        fi
        sleep 2
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
            echo -e "${YELLOW}    Username: $ADMIN_USERNAME / Password: $KUMA_PASS${NC}"
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
