#!/bin/bash
# =============================================================================
# Sync Firewall Rules from services.yaml to D1
# =============================================================================
# Runs BEFORE Tofu apply to ensure dns_record and label changes are in D1
# before firewall rules are read for infrastructure provisioning.
#
# Environment variables required:
#   CLOUDFLARE_API_TOKEN  - Cloudflare API token with D1 access
#   CLOUDFLARE_ACCOUNT_ID - Cloudflare account ID
#   DOMAIN                - Domain for database name derivation
# =============================================================================

set -euo pipefail

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ] || [ -z "${DOMAIN:-}" ]; then
  echo "  ⚠️ Missing required env vars for firewall sync - skipping"
  exit 0
fi

D1_DATABASE_NAME="nexus-${DOMAIN//./-}-db"

if [ ! -f "services.yaml" ]; then
  echo "  ⚠️ services.yaml not found - skipping firewall sync"
  exit 0
fi

python3 << 'PYEOF'
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
    print(f"  Error reading services.yaml: {e}")
    sys.exit(1)

if not data or 'services' not in data:
    print("  No services found - skipping")
    sys.exit(0)

services = data['services']
statements = []

dns_records = {
    'redpanda': {'kafka': 'redpanda-kafka', 'schema-registry': 'redpanda-schema-registry', 'admin': 'redpanda-admin'},
    'redpanda-connect': {'api': 'redpanda-connect-api'},
    'postgres': {'postgres': 'postgres'},
    'minio': {'s3-api': 's3'},
}

for name, config in services.items():
    if not validate_service_name(name):
        continue
    safe_name = name.replace("'", "''")
    tcp_ports = config.get('tcp_ports', {})

    if not tcp_ports:
        statements.append(f"DELETE FROM firewall_rules WHERE service_name = '{safe_name}';")
        continue

    valid_ports = []
    for label, port in tcp_ports.items():
        if not isinstance(port, int) or port < 1 or port > 65535:
            continue
        valid_ports.append(port)
        safe_label = label.replace("'", "''")
        dns_record = dns_records.get(name, {}).get(label, '')
        safe_dns_record = dns_record.replace("'", "''")
        statements.append(f"INSERT OR IGNORE INTO firewall_rules (service_name, port, protocol, label, enabled, deployed, source_ips, dns_record, updated_at) VALUES ('{safe_name}', {port}, 'tcp', '{safe_label}', 0, 0, '', '{safe_dns_record}', datetime('now'));")
        if safe_dns_record:
            statements.append(f"UPDATE firewall_rules SET label = '{safe_label}', dns_record = '{safe_dns_record}', updated_at = datetime('now') WHERE service_name = '{safe_name}' AND port = {port};")
        else:
            statements.append(f"UPDATE firewall_rules SET label = '{safe_label}', updated_at = datetime('now') WHERE service_name = '{safe_name}' AND port = {port};")

    if valid_ports:
        ports_list = ', '.join(str(p) for p in valid_ports)
        statements.append(f"DELETE FROM firewall_rules WHERE service_name = '{safe_name}' AND port NOT IN ({ports_list});")

with open('/tmp/sync_firewall_rules.sql', 'w') as f:
    f.write('\n'.join(statements))
    if statements:
        f.write('\n')

print(f"  Generated {len(statements)} firewall rule statements")
PYEOF

if [ -f /tmp/sync_firewall_rules.sql ] && [ -s /tmp/sync_firewall_rules.sql ]; then
  FW_COUNT=$(wc -l < /tmp/sync_firewall_rules.sql | tr -d ' ')
  echo "  Executing $FW_COUNT statements..."

  set +e
  FW_OUTPUT=$(npx wrangler@4.129.0 d1 execute "$D1_DATABASE_NAME" \
    --remote --file /tmp/sync_firewall_rules.sql 2>&1)
  FW_EXIT=$?
  set -e

  if [ $FW_EXIT -eq 0 ]; then
    echo "  ✅ Firewall rules synced"
  else
    echo "  ❌ Firewall rules sync failed" >&2
    echo "$FW_OUTPUT" >&2
    rm -f /tmp/sync_firewall_rules.sql
    exit 1
  fi
  rm -f /tmp/sync_firewall_rules.sql
fi
