#!/usr/bin/env python3
"""
Generate services and firewall configuration for OpenTofu from services.yaml

This script reads services.yaml and generates the services and firewall_rules
blocks for tofu/stack/config.tfvars, taking into account which services are
enabled in D1 (passed via ENABLED_SERVICES environment variable) and which
firewall rules are enabled (passed via FIREWALL_RULES environment variable).

Usage:
    ENABLED_SERVICES="service1,service2" \
    FIREWALL_RULES="redpanda:9092:kafka::kafka;postgres:5432:postgres::db" \
    python3 generate-services-tfvars.py

The script appends the configuration to tofu/stack/config.tfvars.
"""

import yaml
import os
import sys
import re

def validate_service_name(name):
    """Validate service name to prevent SQL injection and ensure valid format."""
    if not isinstance(name, str):
        return False
    if len(name) == 0 or len(name) > 63:
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
        if 'subdomain' in config:
            subdomain = config['subdomain']
            if not isinstance(subdomain, str) or not validate_service_name(subdomain):
                errors.append(f"Service '{name}': invalid subdomain '{subdomain}' (must be valid service name format)")
        
        if 'port' in config:
            port = config['port']
            if not isinstance(port, int) or port < 1 or port > 65535:
                errors.append(f"Service '{name}': port must be an integer between 1 and 65535, got {port}")
        
        if 'public' in config and not isinstance(config['public'], bool):
            errors.append(f"Service '{name}': 'public' must be a boolean")
        
        if 'core' in config and not isinstance(config['core'], bool):
            errors.append(f"Service '{name}': 'core' must be a boolean")
        
        if 'description' in config and not isinstance(config['description'], str):
            errors.append(f"Service '{name}': 'description' must be a string")
        
        if 'image' in config:
            image = config['image']
            if not isinstance(image, str) or len(image) == 0:
                errors.append(f"Service '{name}': 'image' must be a non-empty string")
    
    return errors

def main():
    enabled_input = os.environ.get('ENABLED_SERVICES', '')
    enabled_set = set(s.strip() for s in enabled_input.split(',') if s.strip())

    try:
        with open('services.yaml', 'r') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error reading services.yaml: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate services.yaml structure
    validation_errors = validate_services_yaml(data)
    if validation_errors:
        print("services.yaml validation failed:", file=sys.stderr)
        for error in validation_errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    services = data['services']
    output_lines = ['', '# Services (from services.yaml, enabled state from D1)', 'services = {']

    for name, config in sorted(services.items()):
        # For internal-only services, subdomain is empty
        is_internal_only = config.get('internal_only', False)
        subdomain = config.get('subdomain', '' if is_internal_only else name)
        port = config.get('port', 0)
        public = 'true' if config.get('public', False) else 'false'
        core = config.get('core', False)
        description = config.get('description', '').replace('"', '\\"')
        image = config.get('image', '')
        
        # Core services are always enabled, others follow D1 state
        # If no D1 state yet (empty enabled_set), only core services are enabled
        is_core = core
        if enabled_set:
            should_enable = is_core or name in enabled_set
        else:
            # No D1 state - only enable core services
            should_enable = is_core
        
        enabled = 'true' if should_enable else 'false'
        
        output_lines.append(f'  {name} = {{')
        output_lines.append(f'    enabled     = {enabled}')
        output_lines.append(f'    subdomain   = "{subdomain}"')
        output_lines.append(f'    port        = {port}')
        output_lines.append(f'    public      = {public}')
        if core:
            output_lines.append(f'    core        = true')
        output_lines.append(f'    description = "{description}"')
        output_lines.append(f'    image       = "{image}"')
        
        # Handle support_images
        support_images = config.get('support_images', {})
        if support_images:
            output_lines.append('    support_images = {')
            for img_name, img_value in support_images.items():
                output_lines.append(f'      "{img_name}" = "{img_value}"')
            output_lines.append('    }')
        
        output_lines.append('  }')
        output_lines.append('')

    output_lines.append('}')

    # Generate firewall_rules block from FIREWALL_RULES env var
    # Format: "service:port:source_ips:dns_record;service:port:source_ips:dns_record"
    # Records separated by ";", source_ips within a record are comma-separated CIDRs
    firewall_input = os.environ.get('FIREWALL_RULES', '')
    firewall_rules = []

    if firewall_input.strip():
        for entry in firewall_input.split(';'):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(':')
            if len(parts) < 2:
                print(f"Warning: Invalid firewall rule entry: {entry}", file=sys.stderr)
                continue
            service_name = parts[0]
            try:
                port = int(parts[1])
            except ValueError:
                print(f"Warning: Invalid port in firewall rule: {entry}", file=sys.stderr)
                continue
            source_ips = parts[2] if len(parts) > 2 else ''
            dns_record = parts[3] if len(parts) > 3 else ''

            # Validate that the port belongs to the service's tcp_ports
            if service_name in services:
                tcp_ports = services[service_name].get('tcp_ports', {})
                if port not in tcp_ports.values():
                    print(f"Warning: Port {port} not in tcp_ports for {service_name}, skipping", file=sys.stderr)
                    continue

            firewall_rules.append({
                'key': f'{service_name}-{port}',
                'port': port,
                'source_ips': source_ips,
                'dns_record': dns_record,
            })

    output_lines.append('')
    output_lines.append('# Firewall rules for external TCP access (from D1)')
    output_lines.append('firewall_rules = {')

    for rule in firewall_rules:
        source_ips_list = [ip.strip() for ip in rule['source_ips'].split(',') if ip.strip()] if rule['source_ips'] else []
        source_ips_tf = ', '.join(f'"{ip}"' for ip in source_ips_list)

        output_lines.append(f'  "{rule["key"]}" = {{')
        output_lines.append(f'    port       = {rule["port"]}')
        output_lines.append(f'    protocol   = "tcp"')
        output_lines.append(f'    source_ips = [{source_ips_tf}]')
        output_lines.append(f'    dns_record = "{rule["dns_record"]}"')
        output_lines.append(f'  }}')
        output_lines.append('')

    output_lines.append('}')

    with open('tofu/stack/config.tfvars', 'a') as f:
        f.write('\n'.join(output_lines))

    print(f"Generated services config for {len(services)} services, {len(firewall_rules)} firewall rules")

if __name__ == '__main__':
    main()
