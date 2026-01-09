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

# Get domain from config
DOMAIN=$(grep -E '^domain\s*=' "$TOFU_DIR/config.tfvars" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' || echo "")
SSH_HOST="ssh.${DOMAIN}"

if [ -z "$DOMAIN" ]; then
    echo -e "${RED}Error: Could not read domain from config.tfvars${NC}"
    exit 1
fi

# Clean old SSH known_hosts entries
SERVER_IP=$(cd "$TOFU_DIR" && tofu output -raw server_ip 2>/dev/null || echo "")
[ -n "$SSH_HOST" ] && ssh-keygen -R "$SSH_HOST" 2>/dev/null || true
[ -n "$SERVER_IP" ] && ssh-keygen -R "$SERVER_IP" 2>/dev/null || true

# -----------------------------------------------------------------------------
# Setup SSH Config (if not already present)
# -----------------------------------------------------------------------------
SSH_CONFIG="$HOME/.ssh/config"

if ! grep -q "Host nexus" "$SSH_CONFIG" 2>/dev/null; then
    echo -e "${YELLOW}[0/4] Adding SSH config for nexus...${NC}"
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
    echo -e "${GREEN}[0/4] SSH config for nexus already exists${NC}"
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
echo -e "${YELLOW}[1/4] Waiting for SSH via Cloudflare Tunnel...${NC}"
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
# Sync stacks (only enabled services)
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[2/4] Syncing enabled stacks to server...${NC}"

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
echo -e "${YELLOW}[3/4] Cleaning up disabled services...${NC}"

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
# Start containers (only enabled services)
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[4/4] Starting enabled containers...${NC}"

# Pass enabled services to remote script
ENABLED_LIST=$(echo $ENABLED_SERVICES | tr '\n' ' ')

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
