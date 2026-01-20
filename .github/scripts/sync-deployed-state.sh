#!/bin/bash
# =============================================================================
# Sync Services to D1
# =============================================================================
# After a successful spin-up:
# 1. Initialize services from services.tfvars to D1 (if not exist)
# 2. Set deployed = enabled for all services (mark as deployed)
#
# Environment variables required:
#   CLOUDFLARE_API_TOKEN  - Cloudflare API token with D1 access
#   CLOUDFLARE_ACCOUNT_ID - Cloudflare account ID
#   DOMAIN                - Domain for database name derivation
# =============================================================================

set -e

# Validate required environment variables
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ] || [ -z "${DOMAIN:-}" ]; then
  echo "⚠️ Missing required env vars for D1 sync - skipping"
  exit 0
fi

# Derive D1 database name from domain
D1_DATABASE_NAME="nexus-${DOMAIN//./-}-db"

echo "📊 Syncing services to D1..."

# Step 1: Initialize services from services.tfvars (insert if not exist)
if [ -f "tofu/services.tfvars" ]; then
  echo "  Initializing services from services.tfvars..."
  
  # Parse services.tfvars and generate INSERT statements
  # Only parse actual service blocks (not the outer wrapper or nested blocks)
  python3 << 'PYEOF'
import re
import os

with open('tofu/services.tfvars', 'r') as f:
    content = f.read()

# First, extract the inner content of services = { ... }
# This skips the outer wrapper to avoid matching "services" as a service name
services_match = re.search(r'^services\s*=\s*\{(.+)\}\s*$', content, re.DOTALL | re.MULTILINE)
if not services_match:
    print("  ⚠️ Could not find services block in services.tfvars")
    exit(1)

inner_content = services_match.group(1)

# Match service blocks by locating the start of each block, then
# scanning forward to find the matching closing brace so that
# nested braces are handled correctly.
# Only match blocks that are direct children of the services block
pattern = r'([a-zA-Z0-9-]+)\s*=\s*\{'
matches = []

for match in re.finditer(pattern, inner_content):
    name = match.group(1)
    
    # Skip known non-service blocks
    if name in ['services', 'support_images']:
        continue
    
    # Position of the opening brace '{'
    start = match.end() - 1
    depth = 1
    i = start + 1
    while i < len(inner_content) and depth > 0:
        ch = inner_content[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                block = inner_content[start + 1:i]
                matches.append((name, block))
                break
        i += 1

sql_statements = []
for name, block in matches:
    # Only process blocks that have an 'enabled' field (real services)
    # This filters out any nested blocks we might have missed
    enabled_match = re.search(r'enabled\s*=\s*(true|false)', block)
    if not enabled_match:
        # Skip blocks without enabled field (not a real service)
        continue
    
    # Extract values from block
    subdomain_match = re.search(r'subdomain\s*=\s*"([^"]*)"', block)
    port_match = re.search(r'port\s*=\s*(\d+)', block)
    public_match = re.search(r'public\s*=\s*(true|false)', block)
    core_match = re.search(r'core\s*=\s*(true|false)', block)
    description_match = re.search(r'description\s*=\s*"([^"]*)"', block)
    
    enabled = 1 if enabled_match.group(1) == 'true' else 0
    subdomain = subdomain_match.group(1) if subdomain_match else ''
    port = int(port_match.group(1)) if port_match else 0
    public = 1 if public_match and public_match.group(1) == 'true' else 0
    core = 1 if core_match and core_match.group(1) == 'true' else 0
    description = description_match.group(1) if description_match else ''
    
    # Escape single quotes in description for SQL
    description = description.replace("'", "''")
    
    # INSERT OR IGNORE - only creates if not exists, preserves enabled state
    sql = f"INSERT OR IGNORE INTO services (name, enabled, deployed, subdomain, port, public, core, description, updated_at) VALUES ('{name}', {enabled}, {enabled}, '{subdomain}', {port}, {public}, {core}, '{description}', datetime('now'));"
    sql_statements.append(sql)

# Write to temp file
with open('/tmp/init_services.sql', 'w') as f:
    f.write('\n'.join(sql_statements))

print(f"  Generated {len(sql_statements)} service init statements")
PYEOF

  # Execute the init SQL
  if [ -f /tmp/init_services.sql ] && [ -s /tmp/init_services.sql ]; then
    while IFS= read -r sql; do
      npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$sql" 2>/dev/null || true
    done < /tmp/init_services.sql
    echo "  ✅ Services initialized"
    rm -f /tmp/init_services.sql
  fi
else
  echo "  ⚠️ services.tfvars not found - skipping init"
fi

# Step 2: Sync deployed state (set deployed = enabled for all)
echo "  Syncing deployed state..."
SQL="UPDATE services SET deployed = enabled, updated_at = datetime('now') WHERE deployed != enabled"

if npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$SQL" 2>/dev/null; then
  echo "  ✅ Deployed state synced"
else
  echo "  ⚠️ Failed to sync deployed state (non-critical)"
fi

echo "✅ D1 sync complete"
exit 0
