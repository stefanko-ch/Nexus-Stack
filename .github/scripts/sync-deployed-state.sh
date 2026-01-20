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

# Function to safely sanitize error output (remove secrets/tokens)
sanitize_error() {
  local error="$1"
  # Remove potential secrets/tokens (API tokens, access keys, etc.)
  echo "$error" | sed \
    -e 's/\([Aa][Pp][Ii][_-][Tt][Oo][Kk][Ee][Nn]\)[^[:space:]]*/API_TOKEN_HIDDEN/g' \
    -e 's/\([Aa][Cc][Cc][Ee][Ss][Ss][_-][Kk][Ee][Yy]\)[^[:space:]]*/ACCESS_KEY_HIDDEN/g' \
    -e 's/\([Ss][Ee][Cc][Rr][Ee][Tt][_-][Kk][Ee][Yy]\)[^[:space:]]*/SECRET_KEY_HIDDEN/g' \
    -e 's/\([Bb][Ee][Aa][Rr][Ee][Rr]\)[^[:space:]]*/BEARER_TOKEN_HIDDEN/g' \
    -e 's/\([Aa][Uu][Tt][Hh][Oo][Rr][Ii][Zz][Aa][Tt][Ii][Oo][Nn]\)[^[:space:]]*/AUTH_TOKEN_HIDDEN/g' \
    -e 's/\([Tt][Oo][Kk][Ee][Nn]\)[^[:space:]]*/TOKEN_HIDDEN/g' \
    -e 's/\([Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]\)[^[:space:]]*/PASSWORD_HIDDEN/g'
}

# Validate required environment variables
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ] || [ -z "${DOMAIN:-}" ]; then
  echo "⚠️ Missing required env vars for D1 sync - skipping"
  exit 0
fi

# Derive D1 database name from domain
D1_DATABASE_NAME="nexus-${DOMAIN//./-}-db"

echo "📊 Syncing services to D1..."
echo "  D1 Database: $D1_DATABASE_NAME"
echo "  Domain: $DOMAIN"
echo "  Working directory: $(pwd)"
echo "  services.yaml exists: $([ -f services.yaml ] && echo 'yes' || echo 'no')"

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
    INSERT_STMT_COUNT=$(wc -l < /tmp/init_services.sql | tr -d ' ')
    echo "  Found $INSERT_STMT_COUNT INSERT statements"
    echo "  First few services to insert:"
    head -5 /tmp/init_services.sql | while IFS= read -r sql; do
      SERVICE_NAME=$(echo "$sql" | sed -n "s/.*VALUES ('\([^']*\)'.*/\1/p" | head -1)
      echo "    - $SERVICE_NAME"
    done
    
    INSERT_COUNT=0
    INSERT_FAILED=0
    INSERT_FAILED_SERVICES=()
    while IFS= read -r sql; do
      # Extract service name from SQL for logging
      SERVICE_NAME=$(echo "$sql" | sed -n "s/.*VALUES ('\([^']*\)'.*/\1/p" | head -1)
      
      # Execute with error capture (but sanitize output)
      WRANGLER_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$sql" 2>&1)
      WRANGLER_EXIT=$?
      
      if [ $WRANGLER_EXIT -eq 0 ]; then
        INSERT_COUNT=$((INSERT_COUNT + 1))
        echo "    ✓ Inserted/verified: $SERVICE_NAME"
        
        # Verify service actually exists in D1
        VERIFY_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --json \
          --command "SELECT name FROM services WHERE name = '$SERVICE_NAME'" 2>&1)
        if echo "$VERIFY_OUTPUT" | jq -e ".result[0].name == \"$SERVICE_NAME\"" >/dev/null 2>&1; then
          echo "      ✓ Verified: $SERVICE_NAME exists in D1"
        else
          echo "      ⚠️  Warning: $SERVICE_NAME INSERT may have failed (not found in D1)" >&2
          INSERT_FAILED=$((INSERT_FAILED + 1))
          INSERT_FAILED_SERVICES+=("$SERVICE_NAME")
        fi
      else
        INSERT_FAILED=$((INSERT_FAILED + 1))
        INSERT_FAILED_SERVICES+=("$SERVICE_NAME")
        SANITIZED_ERROR=$(sanitize_error "$WRANGLER_OUTPUT")
        echo "    ✗ Failed to insert: $SERVICE_NAME" >&2
        echo "      Error: $SANITIZED_ERROR" >&2
        # Log SQL statement for debugging (truncated if too long)
        SQL_PREVIEW=$(echo "$sql" | head -c 200)
        echo "      SQL: ${SQL_PREVIEW}..." >&2
      fi
    done < /tmp/init_services.sql
    
    if [ $INSERT_FAILED -eq 0 ]; then
      echo "  ✅ New services inserted ($INSERT_COUNT services)"
    else
      echo "  ⚠️  Inserted $INSERT_COUNT services, $INSERT_FAILED failed" >&2
      echo "  Failed services: ${INSERT_FAILED_SERVICES[*]}" >&2
    fi
    rm -f /tmp/init_services.sql
  else
    echo "  ℹ️  No new services to insert"
    if [ -f /tmp/init_services.sql ]; then
      echo "  ⚠️  SQL file exists but is empty"
    else
      echo "  ⚠️  SQL file not found"
    fi
  fi

  # Execute the UPDATE SQL (for existing services - syncs metadata)
  if [ -f /tmp/update_services.sql ] && [ -s /tmp/update_services.sql ]; then
    UPDATE_STMT_COUNT=$(wc -l < /tmp/update_services.sql | tr -d ' ')
    echo "  Found $UPDATE_STMT_COUNT UPDATE statements"
    UPDATE_COUNT=0
    UPDATE_FAILED=0
    UPDATE_FAILED_SERVICES=()
    while IFS= read -r sql; do
      # Extract service name from SQL for logging
      SERVICE_NAME=$(echo "$sql" | sed -n "s/.*WHERE name = '\([^']*\)'.*/\1/p" | head -1)
      
      # Execute with error capture (but sanitize output)
      WRANGLER_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$sql" 2>&1)
      WRANGLER_EXIT=$?
      
      if [ $WRANGLER_EXIT -eq 0 ]; then
        UPDATE_COUNT=$((UPDATE_COUNT + 1))
        echo "    ✓ Updated metadata: $SERVICE_NAME"
      else
        UPDATE_FAILED=$((UPDATE_FAILED + 1))
        UPDATE_FAILED_SERVICES+=("$SERVICE_NAME")
        SANITIZED_ERROR=$(sanitize_error "$WRANGLER_OUTPUT")
        echo "    ✗ Failed to update: $SERVICE_NAME" >&2
        echo "      Error: $SANITIZED_ERROR" >&2
      fi
    done < /tmp/update_services.sql
    if [ $UPDATE_FAILED -eq 0 ]; then
      echo "  ✅ Existing services metadata synced ($UPDATE_COUNT services)"
    else
      echo "  ⚠️  Updated $UPDATE_COUNT services, $UPDATE_FAILED failed" >&2
      echo "  Failed services: ${UPDATE_FAILED_SERVICES[*]}" >&2
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

DEPLOYED_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$SQL" 2>&1)
DEPLOYED_EXIT=$?

if [ $DEPLOYED_EXIT -eq 0 ]; then
  echo "  ✅ Deployed state synced"
else
  SANITIZED_ERROR=$(sanitize_error "$DEPLOYED_OUTPUT")
  echo "  ⚠️ Failed to sync deployed state (non-critical)" >&2
  echo "  Error: $SANITIZED_ERROR" >&2
fi

# Step 3: Final verification - list all services in D1
echo "  Verifying services in D1..."
VERIFY_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --json \
  --command "SELECT name FROM services ORDER BY name" 2>&1)
VERIFY_EXIT=$?

if [ $VERIFY_EXIT -eq 0 ]; then
  SERVICE_COUNT=$(echo "$VERIFY_OUTPUT" | jq -r '.result | length' 2>/dev/null || echo "0")
  echo "  ✅ Found $SERVICE_COUNT services in D1"
  if [ "$SERVICE_COUNT" -gt 0 ]; then
    echo "  Services in D1:"
    echo "$VERIFY_OUTPUT" | jq -r '.result[].name' 2>/dev/null | while read -r svc; do
      echo "    - $svc"
    done
  fi
else
  SANITIZED_ERROR=$(sanitize_error "$VERIFY_OUTPUT")
  echo "  ⚠️ Failed to verify services in D1" >&2
  echo "  Error: $SANITIZED_ERROR" >&2
fi

echo "✅ D1 sync complete"
exit 0
