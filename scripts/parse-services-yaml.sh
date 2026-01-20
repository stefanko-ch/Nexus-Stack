#!/bin/bash
# =============================================================================
# Parse services.yaml and output JSON
# =============================================================================
# This script reads services.yaml from the project root and outputs JSON
# for easy consumption by other scripts.
#
# Usage: ./parse-services-yaml.sh [services.yaml path]
# Output: JSON to stdout, errors to stderr
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICES_FILE="${1:-$PROJECT_ROOT/services.yaml}"

if [ ! -f "$SERVICES_FILE" ]; then
  echo "Error: services.yaml not found at $SERVICES_FILE" >&2
  exit 1
fi

# Use Python yaml library to parse and output JSON
python3 << PYEOF
import yaml
import json
import sys

try:
    with open("$SERVICES_FILE", 'r') as f:
        data = yaml.safe_load(f)
    
    if not data or 'services' not in data:
        print("{}", file=sys.stderr)
        sys.exit(1)
    
    print(json.dumps(data['services'], indent=2))
except Exception as e:
    print(f"Error parsing YAML: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
