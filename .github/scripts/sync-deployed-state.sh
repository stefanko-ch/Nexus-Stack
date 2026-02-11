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
    # Note: subdomain is not required for internal_only services
    required_fields = ['port', 'image']

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

        # Check subdomain is present for non-internal services
        is_internal_only = config.get('internal_only', False)
        if not is_internal_only and 'subdomain' not in config:
            errors.append(f"Service '{name}': missing required field 'subdomain' (required for non-internal services)")
        
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
    admin_only = 1 if config.get('admin_only', False) else 0
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
    insert_sql = f"INSERT OR IGNORE INTO services (name, enabled, deployed, subdomain, port, public, core, admin_only, description, updated_at) VALUES ('{name}', {enabled}, {enabled}, '{subdomain}', {port}, {public}, {core}, {admin_only}, '{description}', datetime('now'));"
    insert_statements.append(insert_sql)
    
    # UPDATE - sync metadata for existing services (preserve enabled state from D1)
    # This ensures subdomain, port, description, core, public are always in sync with yaml
    update_sql = f"UPDATE services SET subdomain = '{subdomain}', port = {port}, public = {public}, core = {core}, admin_only = {admin_only}, description = '{description}', updated_at = datetime('now') WHERE name = '{name}';"
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

  # Execute the INSERT SQL (for new services) - BATCH execution to avoid rate limits
  if [ -f /tmp/init_services.sql ] && [ -s /tmp/init_services.sql ]; then
    INSERT_COUNT=$(wc -l < /tmp/init_services.sql | tr -d ' ')
    echo "  Executing $INSERT_COUNT INSERT statements in batch..."
    
    # Show which services will be inserted
    echo "  Services to insert:"
    while IFS= read -r sql; do
      SERVICE_NAME=$(echo "$sql" | sed -n "s/.*VALUES ('\([^']*\)'.*/\1/p" | head -1)
      echo "    - $SERVICE_NAME"
    done < /tmp/init_services.sql
    
    # Execute ALL INSERTs in a single batch call (avoids rate limits)
    set +e
    WRANGLER_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" \
      --remote --file /tmp/init_services.sql 2>&1)
    WRANGLER_EXIT=$?
    set -e
    
    if [ $WRANGLER_EXIT -eq 0 ]; then
      echo "  ✅ Batch INSERT completed ($INSERT_COUNT services)"
    else
      SANITIZED_ERROR=$(sanitize_error "$WRANGLER_OUTPUT")
      echo "  ⚠️ Batch INSERT had issues (may be partial): $SANITIZED_ERROR" >&2
    fi
  else
    echo "  ℹ️  No new services to insert"
  fi

  # Execute the UPDATE SQL (for existing services - syncs metadata) - BATCH execution
  if [ -f /tmp/update_services.sql ] && [ -s /tmp/update_services.sql ]; then
    UPDATE_COUNT=$(wc -l < /tmp/update_services.sql | tr -d ' ')
    echo "  Executing $UPDATE_COUNT UPDATE statements in batch..."
    
    # Execute ALL UPDATEs in a single batch call (avoids rate limits)
    set +e
    WRANGLER_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" \
      --remote --file /tmp/update_services.sql 2>&1)
    WRANGLER_EXIT=$?
    set -e
    
    if [ $WRANGLER_EXIT -eq 0 ]; then
      echo "  ✅ Batch UPDATE completed ($UPDATE_COUNT services)"
    else
      SANITIZED_ERROR=$(sanitize_error "$WRANGLER_OUTPUT")
      echo "  ⚠️ Batch UPDATE had issues (may be partial): $SANITIZED_ERROR" >&2
    fi
  else
    echo "  ℹ️  No services to update"
  fi
else
  echo "  ⚠️ services.yaml not found - skipping sync"
fi

# Step 2: Sync firewall rules from services.yaml tcp_ports
echo "🔥 Syncing firewall rules from services.yaml..."
if [ -f "services.yaml" ]; then
  python3 << 'FWEOF'
import yaml
import sys
import re

def validate_service_name(name):
    if not isinstance(name, str):
        return False
    if len(name) == 0 or len(name) > 63:
        return False
    return bool(re.match(r'^[a-z0-9_-]+$', name))

try:
    with open('services.yaml', 'r') as f:
        data = yaml.safe_load(f)
except Exception as e:
    print(f"  Warning: Error reading services.yaml for firewall sync: {e}")
    sys.exit(0)

if not data or 'services' not in data:
    print("  No services found - skipping firewall sync")
    sys.exit(0)

services = data['services']
insert_statements = []

# DNS record mapping for known services
dns_records = {
    'redpanda': {'kafka': 'redpanda-kafka', 'schema-registry': 'redpanda-schema-registry'},
    'postgres': {'postgres': 'postgres'},
    'minio': {'s3-api': 's3'},
}

for name, config in services.items():
    if not validate_service_name(name):
        continue
    tcp_ports = config.get('tcp_ports', {})
    if not tcp_ports:
        continue

    for label, port in tcp_ports.items():
        if not isinstance(port, int) or port < 1 or port > 65535:
            continue
        # Escape values for SQL
        safe_label = label.replace("'", "''")
        safe_name = name.replace("'", "''")
        dns_record = dns_records.get(name, {}).get(label, '')
        safe_dns_record = dns_record.replace("'", "''")
        insert_sql = f"INSERT OR IGNORE INTO firewall_rules (service_name, port, protocol, label, enabled, deployed, source_ips, dns_record, updated_at) VALUES ('{safe_name}', {port}, 'tcp', '{safe_label}', 0, 0, '', '{safe_dns_record}', datetime('now'));"
        insert_statements.append(insert_sql)

with open('/tmp/init_firewall_rules.sql', 'w') as f:
    f.write('\n'.join(insert_statements))
    if insert_statements:
        f.write('\n')

print(f"  Generated {len(insert_statements)} firewall rule insert statements")
FWEOF

  if [ -f /tmp/init_firewall_rules.sql ] && [ -s /tmp/init_firewall_rules.sql ]; then
    FW_COUNT=$(wc -l < /tmp/init_firewall_rules.sql | tr -d ' ')
    echo "  Executing $FW_COUNT firewall rule INSERT statements..."

    set +e
    FW_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" \
      --remote --file /tmp/init_firewall_rules.sql 2>&1)
    FW_EXIT=$?
    set -e

    if [ $FW_EXIT -eq 0 ]; then
      echo "  ✅ Firewall rules synced ($FW_COUNT rules)"
    else
      SANITIZED_ERROR=$(sanitize_error "$FW_OUTPUT")
      echo "  ⚠️ Firewall rules sync had issues: $SANITIZED_ERROR" >&2
    fi
    rm -f /tmp/init_firewall_rules.sql
  else
    echo "  ℹ️  No firewall rules to insert"
  fi
else
  echo "  ⚠️ services.yaml not found - skipping firewall sync"
fi

# Step 3: Sync deployed state (set deployed = enabled for all)
echo "  Syncing deployed state..."
SQL="UPDATE services SET deployed = enabled, updated_at = datetime('now') WHERE deployed != enabled"

DEPLOYED_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$SQL" 2>&1)
DEPLOYED_EXIT=$?

if [ $DEPLOYED_EXIT -eq 0 ]; then
  echo "  ✅ Services deployed state synced"
else
  SANITIZED_ERROR=$(sanitize_error "$DEPLOYED_OUTPUT")
  echo "  ⚠️ Failed to sync services deployed state (non-critical)" >&2
  echo "  Error: $SANITIZED_ERROR" >&2
fi

# Step 4: Sync firewall deployed state
echo "  Syncing firewall deployed state..."
FW_SQL="UPDATE firewall_rules SET deployed = enabled, updated_at = datetime('now') WHERE deployed != enabled"

FW_DEPLOYED_OUTPUT=$(npx wrangler@latest d1 execute "$D1_DATABASE_NAME" --remote --command "$FW_SQL" 2>&1)
FW_DEPLOYED_EXIT=$?

if [ $FW_DEPLOYED_EXIT -eq 0 ]; then
  echo "  ✅ Firewall deployed state synced"
else
  SANITIZED_ERROR=$(sanitize_error "$FW_DEPLOYED_OUTPUT")
  echo "  ⚠️ Failed to sync firewall deployed state (non-critical)" >&2
  echo "  Error: $SANITIZED_ERROR" >&2
fi

# Step 5: Final verification - list all services in D1
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
