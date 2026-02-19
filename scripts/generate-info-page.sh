#!/bin/bash
# =============================================================================
# Generate Info Page from config.tfvars
# =============================================================================
# This script reads the services configuration from config.tfvars and generates
# the info page HTML with the correct services and domain.
# 
# Usage: ./generate-info-page.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TFVARS_FILE="$PROJECT_ROOT/tofu/stack/config.tfvars"
SERVICES_YAML_FILE="$PROJECT_ROOT/services.yaml"
TEMPLATE_FILE="$PROJECT_ROOT/stacks/info/html/index.template.html"
OUTPUT_FILE="$PROJECT_ROOT/stacks/info/html/index.html"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}📄 Generating Info Page...${NC}"

# Debug logging
LOG_FILE="/tmp/debug.log"
echo "{\"location\":\"generate-info-page.sh:26\",\"message\":\"Starting info page generation\",\"data\":{\"tfvars_file\":\"$TFVARS_FILE\"},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true

# Check if required files exist
if [ ! -f "$TFVARS_FILE" ]; then
    echo -e "${RED}Error: config.tfvars not found at $TFVARS_FILE${NC}"
    echo "{\"location\":\"generate-info-page.sh:30\",\"message\":\"config.tfvars not found\",\"data\":{\"tfvars_file\":\"$TFVARS_FILE\"},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true
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

# Parse services from config.tfvars (HCL format with enabled state)
SERVICES_JSON=$(python3 << PYEOF
import re
import json

tfvars_path = "$TFVARS_FILE"

with open(tfvars_path, 'r') as f:
    content = f.read()

# Find services block - match until the closing brace at the same indentation level
services_match = re.search(r'services\s*=\s*\{', content)
if not services_match:
    print("{}")
    exit(0)

# Find the matching closing brace by counting braces
start_pos = services_match.end()
brace_count = 1
pos = start_pos
while pos < len(content) and brace_count > 0:
    if content[pos] == '{':
        brace_count += 1
    elif content[pos] == '}':
        brace_count -= 1
    pos += 1

services_block = content[start_pos:pos-1]
services = {}

# Parse each service block with proper nested block handling
lines = services_block.split('\n')
i = 0
while i < len(lines):
    line = lines[i].strip()
    
    # Skip empty lines and comments
    if not line or line.startswith('#'):
        i += 1
        continue
    
    # Service block start: servicename = {
    match = re.match(r'^([\w-]+)\s*=\s*\{', line)
    if match:
        service_name = match.group(1)
        # Skip 'support_images' - it's not a service
        if service_name == 'support_images':
            # Skip the entire support_images block
            brace_count = 1
            i += 1
            while i < len(lines) and brace_count > 0:
                line = lines[i]
                brace_count += line.count('{') - line.count('}')
                i += 1
            continue
        
        current_props = {}
        brace_count = 1
        i += 1
        
        # Parse service properties until closing brace
        while i < len(lines) and brace_count > 0:
            line = lines[i].strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                i += 1
                continue
            
            # Count braces for nested blocks
            brace_count += line.count('{') - line.count('}')
            
            # If we hit the closing brace, we're done with this service
            if brace_count == 0:
                break

            # Skip nested blocks (like support_images = { ... })
            if '=' in line and '{' in line:
                # This is a nested block start, skip it entirely
                nested_brace_count = 1
                i += 1
                while i < len(lines) and nested_brace_count > 0:
                    nested_line = lines[i]
                    nested_brace_count += nested_line.count('{') - nested_line.count('}')
                    i += 1
                # Adjust brace_count: we already counted the opening brace,
                # and the closing brace was consumed in the nested loop
                brace_count -= 1
                continue

            # Property line (not a nested block)
            if '=' in line and '{' not in line:
                # Remove trailing comma
                line = line.rstrip(',')
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Skip support_images property
                if key == 'support_images':
                    # Skip the nested support_images block
                    nested_brace_count = 1
                    i += 1
                    while i < len(lines) and nested_brace_count > 0:
                        nested_line = lines[i]
                        nested_brace_count += nested_line.count('{') - nested_line.count('}')
                        i += 1
                    continue
                
                # Parse value
                if value == 'true':
                    current_props[key] = True
                elif value == 'false':
                    current_props[key] = False
                elif value.isdigit():
                    current_props[key] = int(value)
                else:
                    current_props[key] = value.strip('"')
            
            i += 1
        
        services[service_name] = current_props
        continue
    
    i += 1

print(json.dumps(services, indent=2))
PYEOF
)

# Validate JSON
echo "{\"location\":\"generate-info-page.sh:116\",\"message\":\"Validating services JSON\",\"data\":{\"services_json_length\":${#SERVICES_JSON}},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true

if ! echo "$SERVICES_JSON" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
    echo -e "${RED}Error: Failed to parse services from config.tfvars${NC}"
    echo "{\"location\":\"generate-info-page.sh:117\",\"message\":\"JSON validation failed\",\"data\":{\"services_json_preview\":\"${SERVICES_JSON:0:200}\"},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true
    exit 1
fi

# Count services
ACTIVE_COUNT=$(echo "$SERVICES_JSON" | python3 -c "import sys, json; d=json.load(sys.stdin); print(sum(1 for s in d.values() if s.get('enabled')))")
TOTAL_COUNT=$(echo "$SERVICES_JSON" | python3 -c "import sys, json; d=json.load(sys.stdin); print(len(d))")

echo -e "  Services: ${GREEN}$ACTIVE_COUNT${NC} active / $TOTAL_COUNT total"

# Extract image versions from services.yaml using YAML parser
IMAGE_VERSIONS_JSON="{}"
if [ -f "$SERVICES_YAML_FILE" ]; then
    IMAGE_VERSIONS_JSON=$(python3 << PYEOF
import yaml
import json

with open("$SERVICES_YAML_FILE", 'r') as f:
    data = yaml.safe_load(f)

if not data or 'services' not in data:
    print("{}")
    exit(0)

versions = {}
services = data['services']

for service_name, config in services.items():
    # Extract main image version
    image = config.get('image', '')
    if image:
        if ':' in image:
            tag = image.split(':')[-1]
        else:
            tag = image
        versions[service_name] = tag
    
    # Extract support_images versions
    support_images = config.get('support_images', {})
    if support_images:
        for img_name, img_value in support_images.items():
            if ':' in img_value:
                tag = img_value.split(':')[-1]
            else:
                tag = img_value
            versions[img_name] = tag

print(json.dumps(versions, indent=2))
PYEOF
)
    echo -e "  Image versions: ${GREEN}loaded from services.yaml${NC}"
else
    echo -e "  ${YELLOW}Warning: services.yaml not found - image versions not available${NC}"
fi

# Get current date
GENERATED_DATE=$(date '+%Y-%m-%d %H:%M UTC')

# Get current release version
VERSION=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
if [ -n "$VERSION" ]; then
    echo -e "  Version: ${GREEN}$VERSION${NC}"
fi

# Generate output file using Python for reliable replacement
python3 << PYEOF
import re

template_path = "$TEMPLATE_FILE"
output_path = "$OUTPUT_FILE"
domain = "$DOMAIN"
generated_date = "$GENERATED_DATE"
version = "$VERSION"
services_json = '''$SERVICES_JSON'''
image_versions_json = '''$IMAGE_VERSIONS_JSON'''

with open(template_path, 'r') as f:
    content = f.read()

# Replace placeholders
content = content.replace('__DOMAIN__', domain)
content = content.replace('__GENERATED_DATE__', generated_date)
content = content.replace('__VERSION__', version)
content = content.replace('__SERVICES_JSON__', services_json)
content = content.replace('__IMAGE_VERSIONS_JSON__', image_versions_json)

with open(output_path, 'w') as f:
    f.write(content)

print(f"  Output: {output_path}")
PYEOF

echo "{\"location\":\"generate-info-page.sh:215\",\"message\":\"Info page generation completed\",\"data\":{\"output_file\":\"$OUTPUT_FILE\",\"file_exists\":$([ -f "$OUTPUT_FILE" ] && echo "true" || echo "false")},\"timestamp\":$(date +%s)000,\"sessionId\":\"debug-session\",\"runId\":\"run1\"}" >> "$LOG_FILE" 2>/dev/null || true

echo -e "${GREEN}✓ Info page generated successfully!${NC}"
