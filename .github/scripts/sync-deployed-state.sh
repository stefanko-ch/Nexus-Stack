#!/bin/bash
# =============================================================================
# Sync Services to D1
# =============================================================================
# After a successful spin-up:
# 1. Insert new services from services.yaml to D1 (if not exist)
#    - Core services (core: true) are enabled by default
#    - All other services are disabled by default
# 2. Update existing services metadata (subdomain, port, description, core, public)
#    while preserving the enabled state from D1 (user's Control Plane choice)
# 3. Set deployed = enabled for all services (mark as deployed)
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

# Step 1: Initialize/Update services from services.yaml
if [ -f "services.yaml" ]; then
  echo "  Syncing services from services.yaml..."
  
  # Parse services.yaml using Python yaml library and generate INSERT/UPDATE statements
  python3 << 'PYEOF'
import yaml
import sys

try:
    with open('services.yaml', 'r') as f:
        data = yaml.safe_load(f)
except Exception as e:
    print(f"  ⚠️ Error reading services.yaml: {e}")
    sys.exit(1)

if not data or 'services' not in data:
    print("  ⚠️ No services found in services.yaml")
    sys.exit(1)

services = data['services']
insert_statements = []
update_statements = []
service_names = []

for name, config in services.items():
    service_names.append(name)
    
    subdomain = config.get('subdomain', '')
    port = config.get('port', 0)
    public = 1 if config.get('public', False) else 0
    core = 1 if config.get('core', False) else 0
    description = config.get('description', '')
    
    # Escape single quotes in description for SQL
    description = description.replace("'", "''")
    
    # For new services: only core services are enabled by default
    # This is the key change: enabled = core (not from config file)
    enabled = core
    
    # INSERT OR IGNORE - only creates if not exists (preserves enabled state if already exists)
    # New services: core services enabled, others disabled
    insert_sql = f"INSERT OR IGNORE INTO services (name, enabled, deployed, subdomain, port, public, core, description, updated_at) VALUES ('{name}', {enabled}, {enabled}, '{subdomain}', {port}, {public}, {core}, '{description}', datetime('now'));"
    insert_statements.append(insert_sql)
    
    # UPDATE - sync metadata for existing services (preserve enabled state from D1)
    # This ensures subdomain, port, description, core, public are always in sync with yaml
    update_sql = f"UPDATE services SET subdomain = '{subdomain}', port = {port}, public = {public}, core = {core}, description = '{description}', updated_at = datetime('now') WHERE name = '{name}';"
    update_statements.append(update_sql)

# Write to temp files
with open('/tmp/init_services.sql', 'w') as f:
    f.write('\n'.join(insert_statements))

with open('/tmp/update_services.sql', 'w') as f:
    f.write('\n'.join(update_statements))

print(f"  Generated {len(insert_statements)} service insert statements")
print(f"  Generated {len(update_statements)} service update statements")
print(f"  Services found: {', '.join(sorted(service_names))}")
PYEOF

  # Execute the INSERT SQL (for new services)
  if [ -f /tmp/init_services.sql ] && [ -s /tmp/init_services.sql ]; then
    INSERT_COUNT=0
    INSERT_FAILED=0
    while IFS= read -r sql; do
      # Extract service name from SQL for logging
      SERVICE_NAME=$(echo "$sql" | sed -n "s/.*VALUES ('\([^']*\)'.*/\1/p" | head -1)
      if npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$sql" 2>&1 >/dev/null; then
        INSERT_COUNT=$((INSERT_COUNT + 1))
        echo "    ✓ Inserted/verified: $SERVICE_NAME"
      else
        INSERT_FAILED=$((INSERT_FAILED + 1))
        echo "    ✗ Failed to insert: $SERVICE_NAME" >&2
      fi
    done < /tmp/init_services.sql
    if [ $INSERT_FAILED -eq 0 ]; then
      echo "  ✅ New services inserted ($INSERT_COUNT services)"
    else
      echo "  ⚠️  Inserted $INSERT_COUNT services, $INSERT_FAILED failed"
    fi
    rm -f /tmp/init_services.sql
  else
    echo "  ℹ️  No new services to insert"
  fi

  # Execute the UPDATE SQL (for existing services - syncs metadata)
  if [ -f /tmp/update_services.sql ] && [ -s /tmp/update_services.sql ]; then
    UPDATE_COUNT=0
    UPDATE_FAILED=0
    while IFS= read -r sql; do
      # Extract service name from SQL for logging
      SERVICE_NAME=$(echo "$sql" | sed -n "s/.*WHERE name = '\([^']*\)'.*/\1/p" | head -1)
      if npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$sql" 2>&1 >/dev/null; then
        UPDATE_COUNT=$((UPDATE_COUNT + 1))
        echo "    ✓ Updated metadata: $SERVICE_NAME"
      else
        UPDATE_FAILED=$((UPDATE_FAILED + 1))
        echo "    ✗ Failed to update: $SERVICE_NAME" >&2
      fi
    done < /tmp/update_services.sql
    if [ $UPDATE_FAILED -eq 0 ]; then
      echo "  ✅ Existing services metadata synced ($UPDATE_COUNT services)"
    else
      echo "  ⚠️  Updated $UPDATE_COUNT services, $UPDATE_FAILED failed"
    fi
    rm -f /tmp/update_services.sql
  else
    echo "  ℹ️  No services to update"
  fi
else
  echo "  ⚠️ services.yaml not found - skipping sync"
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
