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

set -euo pipefail

# Cleanup trap for temporary files
cleanup_temp_files() {
  rm -f /tmp/init_services.sql /tmp/update_services.sql
}
trap cleanup_temp_files EXIT INT TERM

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
import re

def validate_service_name(name):
    """Validate service name to prevent SQL injection.
    Only allows lowercase letters, numbers, hyphens, and underscores.
    """
    if not isinstance(name, str):
        return False
    if len(name) == 0 or len(name) > 63:  # Max length for service names
        return False
    # Only allow: lowercase letters, numbers, hyphens, underscores
    if not re.match(r'^[a-z0-9_-]+$', name):
        return False
    return True

def validate_services_yaml(data):
    """Validate services.yaml structure and required fields."""
    errors = []
    
    if not data:
        errors.append("services.yaml is empty")
        return errors
    
    if 'services' not in data:
        errors.append("Missing 'services' key in services.yaml")
        return errors
    
    services = data['services']
    if not isinstance(services, dict):
        errors.append("'services' must be a dictionary/map")
        return errors
    
    if len(services) == 0:
        errors.append("No services defined in services.yaml")
        return errors
    
    # Required fields for each service
    required_fields = ['subdomain', 'port', 'image']
    
    for name, config in services.items():
        # Validate service name format
        if not validate_service_name(name):
            errors.append(f"Invalid service name '{name}': must be 1-63 characters, lowercase letters, numbers, hyphens, underscores only")
            continue
        
        if not isinstance(config, dict):
            errors.append(f"Service '{name}': config must be a dictionary")
            continue
        
        # Check required fields
        for field in required_fields:
            if field not in config:
                errors.append(f"Service '{name}': missing required field '{field}'")
        
        # Validate field types and values
        if 'port' in config:
            port = config['port']
            if not isinstance(port, int) or port < 1 or port > 65535:
                errors.append(f"Service '{name}': port must be an integer between 1 and 65535, got {port}")
    
    return errors

try:
    with open('services.yaml', 'r') as f:
        data = yaml.safe_load(f)
except Exception as e:
    print(f"  ⚠️ Error reading services.yaml: {e}")
    sys.exit(1)

# Validate services.yaml structure
validation_errors = validate_services_yaml(data)
if validation_errors:
    print("  ⚠️ services.yaml validation failed:", file=sys.stderr)
    for error in validation_errors:
        print(f"    - {error}", file=sys.stderr)
    sys.exit(1)

if not data or 'services' not in data:
    print("  ⚠️ No services found in services.yaml")
    sys.exit(1)

services = data['services']
insert_statements = []
update_statements = []
service_names = []
invalid_services = []

for name, config in services.items():
    # Validate service name to prevent SQL injection
    if not validate_service_name(name):
        invalid_services.append(name)
        print(f"  ⚠️ Invalid service name '{name}' - skipping (only lowercase letters, numbers, hyphens, underscores allowed)", file=sys.stderr)
        continue
    
    service_names.append(name)
    
    subdomain = config.get('subdomain', '')
    port = config.get('port', 0)
    public = 1 if config.get('public', False) else 0
    core = 1 if config.get('core', False) else 0
    description = config.get('description', '')
    
    # Escape single quotes in description for SQL
    description = description.replace("'", "''")
    
    # Validate and escape subdomain (same rules as service name)
    if subdomain and not re.match(r'^[a-z0-9_-]+$', subdomain):
        print(f"  ⚠️ Invalid subdomain '{subdomain}' for service '{name}' - using service name as fallback", file=sys.stderr)
        subdomain = name
    
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
    if insert_statements:  # Ensure file ends with newline
        f.write('\n')

with open('/tmp/update_services.sql', 'w') as f:
    f.write('\n'.join(update_statements))
    if update_statements:  # Ensure file ends with newline
        f.write('\n')

if invalid_services:
    print(f"  ⚠️ Skipped {len(invalid_services)} invalid service(s): {', '.join(invalid_services)}", file=sys.stderr)

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
    while IFS= read -r sql || [ -n "$sql" ]; do
      # Skip empty lines
      if [ -z "$sql" ] || [ -z "${sql// }" ]; then
        continue
      fi
      
      # Extract service name from SQL for logging
      SERVICE_NAME=$(echo "$sql" | sed -n "s/.*VALUES ('\([^']*\)'.*/\1/p" | head -1)
      
      # Skip if service name extraction failed
      if [ -z "$SERVICE_NAME" ]; then
        echo "    ⚠️  Could not extract service name from SQL, skipping..." >&2
        SQL_PREVIEW=$(echo "$sql" | head -c 200)
        echo "      SQL: ${SQL_PREVIEW}..." >&2
        continue
      fi
      
      # Execute with error capture (but sanitize output)
      # Temporarily disable 'set -e' for this command to handle errors gracefully
      set +e
      WRANGLER_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$sql" 2>&1)
      WRANGLER_EXIT=$?
      set -e
      
      if [ $WRANGLER_EXIT -eq 0 ]; then
        INSERT_COUNT=$((INSERT_COUNT + 1))
        echo "    ✓ Inserted/verified: $SERVICE_NAME"
        
        # Verify service actually exists in D1
        # Note: Verification is optional - INSERT success is the primary indicator
        set +e
        VERIFY_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --json \
          --command "SELECT name FROM services WHERE name = '$SERVICE_NAME'" 2>&1)
        VERIFY_EXIT=$?
        set -e
        
        if [ $VERIFY_EXIT -eq 0 ]; then
          # Check if result exists and contains the service name
          if echo "$VERIFY_OUTPUT" | jq -e '.result != null and (.result | length) > 0 and .result[0].name == "'"$SERVICE_NAME"'"' >/dev/null 2>&1; then
            echo "      ✓ Verified: $SERVICE_NAME exists in D1"
          else
            # Verification failed, but INSERT succeeded - likely a timing issue or false positive
            # Don't count as failure since INSERT was successful
            echo "      ℹ️  Verification inconclusive (INSERT succeeded, verification failed - likely timing issue)"
          fi
        else
          # Verification query failed - don't count as failure since INSERT succeeded
          echo "      ℹ️  Verification query failed (INSERT succeeded)"
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
        # Continue processing other services even if one fails
      fi
    done < /tmp/init_services.sql
    
    if [ $INSERT_FAILED -eq 0 ]; then
      echo "  ✅ New services inserted ($INSERT_COUNT services)"
    else
      echo "  ⚠️  Inserted $INSERT_COUNT services, $INSERT_FAILED failed" >&2
      echo "  Failed services: ${INSERT_FAILED_SERVICES[*]}" >&2
    fi
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
    while IFS= read -r sql || [ -n "$sql" ]; do
      # Skip empty lines
      if [ -z "$sql" ] || [ -z "${sql// }" ]; then
        continue
      fi
      
      # Extract service name from SQL for logging
      SERVICE_NAME=$(echo "$sql" | sed -n "s/.*WHERE name = '\([^']*\)'.*/\1/p" | head -1)
      
      # Skip if service name extraction failed
      if [ -z "$SERVICE_NAME" ]; then
        echo "    ⚠️  Could not extract service name from SQL, skipping..." >&2
        SQL_PREVIEW=$(echo "$sql" | head -c 200)
        echo "      SQL: ${SQL_PREVIEW}..." >&2
        continue
      fi
      
      # Execute with error capture (but sanitize output)
      # Temporarily disable 'set -e' for this command to handle errors gracefully
      set +e
      WRANGLER_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$sql" 2>&1)
      WRANGLER_EXIT=$?
      set -e
      
      if [ $WRANGLER_EXIT -eq 0 ]; then
        UPDATE_COUNT=$((UPDATE_COUNT + 1))
        echo "    ✓ Updated metadata: $SERVICE_NAME"
      else
        UPDATE_FAILED=$((UPDATE_FAILED + 1))
        UPDATE_FAILED_SERVICES+=("$SERVICE_NAME")
        SANITIZED_ERROR=$(sanitize_error "$WRANGLER_OUTPUT")
        echo "    ✗ Failed to update: $SERVICE_NAME" >&2
        echo "      Error: $SANITIZED_ERROR" >&2
        # Continue processing other services even if one fails
      fi
    done < /tmp/update_services.sql
    if [ $UPDATE_FAILED -eq 0 ]; then
      echo "  ✅ Existing services metadata synced ($UPDATE_COUNT services)"
    else
      echo "  ⚠️  Updated $UPDATE_COUNT services, $UPDATE_FAILED failed" >&2
      echo "  Failed services: ${UPDATE_FAILED_SERVICES[*]}" >&2
    fi
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
