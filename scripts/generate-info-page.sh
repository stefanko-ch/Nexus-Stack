#!/bin/bash
# =============================================================================
# Generate Info Page from config.tfvars
# =============================================================================
# This script reads the services configuration from config.tfvars and generates
# the info page HTML with the correct services and domain.
# 
# Usage: ./generate-info-page.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TFVARS_FILE="$PROJECT_ROOT/tofu/stack/config.tfvars"
TEMPLATE_FILE="$PROJECT_ROOT/stacks/info/html/index.template.html"
OUTPUT_FILE="$PROJECT_ROOT/stacks/info/html/index.html"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}📄 Generating Info Page...${NC}"

# Check if required files exist
if [ ! -f "$TFVARS_FILE" ]; then
    echo -e "${RED}Error: config.tfvars not found at $TFVARS_FILE${NC}"
    exit 1
fi

if [ ! -f "$TEMPLATE_FILE" ]; then
    echo -e "${RED}Error: Template file not found at $TEMPLATE_FILE${NC}"
    exit 1
fi

# Extract domain from tfvars (using awk for macOS compatibility)
DOMAIN=$(grep '^domain' "$TFVARS_FILE" | awk -F'"' '{print $2}')

if [ -z "$DOMAIN" ]; then
    echo -e "${RED}Error: Could not extract domain from config.tfvars${NC}"
    exit 1
fi

echo -e "  Domain: ${GREEN}$DOMAIN${NC}"

# Use Python to parse tfvars and generate JSON (more reliable than awk)
SERVICES_JSON=$(python3 << PYEOF
import re
import json

tfvars_path = "$TFVARS_FILE"

with open(tfvars_path, 'r') as f:
    content = f.read()

# Find services block
services_match = re.search(r'services\s*=\s*\{(.*?)^\}', content, re.MULTILINE | re.DOTALL)
if not services_match:
    print("{}")
    exit(0)

services_block = services_match.group(1)
services = {}

# Parse each service block
current_service = None
current_props = {}

for line in services_block.split('\n'):
    line = line.strip()
    
    # Skip empty lines and comments
    if not line or line.startswith('#'):
        continue
    
    # Service block start: servicename = {
    match = re.match(r'^([\w-]+)\s*=\s*\{', line)
    if match:
        current_service = match.group(1)
        current_props = {}
        continue
    
    # Service block end
    if line == '}' and current_service:
        services[current_service] = current_props
        current_service = None
        current_props = {}
        continue
    
    # Property line
    if current_service and '=' in line:
        # Remove trailing comma
        line = line.rstrip(',')
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        
        # Parse value
        if value == 'true':
            current_props[key] = True
        elif value == 'false':
            current_props[key] = False
        elif value.isdigit():
            current_props[key] = int(value)
        else:
            current_props[key] = value.strip('"')

print(json.dumps(services, indent=2))
PYEOF
)

# Validate JSON
if ! echo "$SERVICES_JSON" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
    echo -e "${RED}Error: Failed to parse services from config.tfvars${NC}"
    exit 1
fi

# Count services
ACTIVE_COUNT=$(echo "$SERVICES_JSON" | python3 -c "import sys, json; d=json.load(sys.stdin); print(sum(1 for s in d.values() if s.get('enabled')))")
TOTAL_COUNT=$(echo "$SERVICES_JSON" | python3 -c "import sys, json; d=json.load(sys.stdin); print(len(d))")

echo -e "  Services: ${GREEN}$ACTIVE_COUNT${NC} active / $TOTAL_COUNT total"

# Get current date
GENERATED_DATE=$(date '+%Y-%m-%d %H:%M UTC')

# Generate output file using Python for reliable replacement
python3 << PYEOF
import re

template_path = "$TEMPLATE_FILE"
output_path = "$OUTPUT_FILE"
domain = "$DOMAIN"
generated_date = "$GENERATED_DATE"
services_json = '''$SERVICES_JSON'''

with open(template_path, 'r') as f:
    content = f.read()

# Replace placeholders
content = content.replace('__DOMAIN__', domain)
content = content.replace('__GENERATED_DATE__', generated_date)
content = content.replace('__SERVICES_JSON__', services_json)

with open(output_path, 'w') as f:
    f.write(content)

print(f"  Output: {output_path}")
PYEOF

echo -e "${GREEN}✓ Info page generated successfully!${NC}"
