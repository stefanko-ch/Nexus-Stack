# =============================================================================
# Locals
# =============================================================================

locals {
  # Resource prefix derived from domain (e.g., "example.com" → "nexus-example-com")
  # This ensures unique resource names when multiple users deploy Nexus-Stack
  resource_prefix = "nexus-${replace(var.domain, ".", "-")}"

  # List of emails allowed to access services (admin + optional user)
  # Filter out empty strings
  allowed_emails = compact([var.admin_email, var.user_email])
}

# =============================================================================
# SSH Key
# =============================================================================

resource "hcloud_ssh_key" "main" {
  name       = "${local.resource_prefix}-key"
  public_key = file(var.ssh_public_key_path)
}

# =============================================================================
# Generated Secrets
# =============================================================================

# Infisical secrets
resource "random_password" "infisical_admin" {
  length  = 24
  special = false
}

resource "random_password" "infisical_encryption_key" {
  length  = 32
  special = false
}

resource "random_password" "infisical_auth_secret" {
  length  = 32
  special = false
}

resource "random_password" "infisical_db_password" {
  length  = 24
  special = false
}

# Portainer admin password (for future use)
resource "random_password" "portainer_admin" {
  length  = 24
  special = false
}

# Uptime Kuma admin password
resource "random_password" "kuma_admin" {
  length  = 24
  special = false
}

# Grafana admin password
resource "random_password" "grafana_admin" {
  length  = 24
  special = false
}

# Kestra admin password
resource "random_password" "kestra_admin" {
  length  = 24
  special = false
}

# Kestra database password
resource "random_password" "kestra_db" {
  length  = 24
  special = false
}

# n8n admin password
resource "random_password" "n8n_admin" {
  length  = 24
  special = false
}

# Metabase admin password
resource "random_password" "metabase_admin" {
  length  = 24
  special = false
}

# CloudBeaver admin password
resource "random_password" "cloudbeaver_admin" {
  length  = 24
  special = false
}

# Mage AI admin password
resource "random_password" "mage_admin" {
  length  = 24
  special = false
}

# MinIO root password
resource "random_password" "minio_root" {
  length  = 24
  special = false
}

# Hoppscotch secrets
resource "random_password" "hoppscotch_db" {
  length  = 24
  special = false
}

resource "random_password" "hoppscotch_jwt" {
  length  = 32
  special = false
}

resource "random_password" "hoppscotch_session" {
  length  = 32
  special = false
}

resource "random_password" "hoppscotch_encryption" {
  length  = 32
  special = false
}

# Meltano database password
resource "random_password" "meltano_db" {
  length  = 24
  special = false
}

# Soda database password
resource "random_password" "soda_db" {
  length  = 24
  special = false
}

# PostgreSQL password
resource "random_password" "postgres" {
  length  = 24
  special = false
}

# pgAdmin password
resource "random_password" "pgadmin" {
  length  = 24
  special = false
}

# =============================================================================
# Firewall
# =============================================================================

resource "hcloud_firewall" "main" {
  name = "${local.resource_prefix}-fw"

  # By default: No inbound rules = Zero Entry (all traffic via Cloudflare Tunnel)
  # When firewall_rules are configured, dynamic inbound rules allow external TCP access
  dynamic "rule" {
    for_each = var.firewall_rules
    content {
      direction  = "in"
      protocol   = rule.value.protocol
      port       = tostring(rule.value.port)
      source_ips = length(rule.value.source_ips) > 0 ? rule.value.source_ips : ["0.0.0.0/0", "::/0"]
    }
  }
}

# Temporary firewall for initial setup (SSH access)
resource "hcloud_firewall" "setup" {
  name = "${local.resource_prefix}-setup-fw"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

# =============================================================================
# Server
# =============================================================================

resource "hcloud_server" "main" {
  name         = local.resource_prefix
  server_type  = var.server_type
  location     = var.server_location
  image        = var.server_image
  ssh_keys     = [hcloud_ssh_key.main.id]
  firewall_ids = [hcloud_firewall.main.id, hcloud_firewall.setup.id] # Both firewalls during setup

  # IPv6-only mode: Disable public IPv4 to reduce costs
  # Note: Cloudflare Tunnel works over IPv6, so no public IPv4 is needed
  public_net {
    ipv4_enabled = !var.ipv6_only
    ipv6_enabled = true
  }

  labels = {
    environment = "production"
    managed_by  = "opentofu"
  }

  user_data = <<-EOT
    #!/bin/bash
    set -e
    
    # Update system
    apt-get update && apt-get upgrade -y
    
    # Install Docker
    curl -fsSL https://get.docker.com | sh
    
    # Install security tools
    apt-get install -y fail2ban unattended-upgrades
    
    # Configure automatic security updates
    cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
    APT::Periodic::Update-Package-Lists "1";
    APT::Periodic::Unattended-Upgrade "1";
    APT::Periodic::AutocleanInterval "7";
    EOF
    
    systemctl enable fail2ban unattended-upgrades
    systemctl start fail2ban unattended-upgrades
    
    # Detect architecture and install cloudflared
    ARCH=$(dpkg --print-architecture)
    if [ "$ARCH" = "arm64" ]; then
      CLOUDFLARED_ARCH="arm64"
    else
      CLOUDFLARED_ARCH="amd64"
    fi
    curl -L --output cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$${CLOUDFLARED_ARCH}.deb"
    dpkg -i cloudflared.deb
    rm cloudflared.deb
    
    # Create app directories
    mkdir -p /opt/docker-server/stacks
    
    # Create Docker network
    docker network create app-network || true
    
    # Signal completion
    touch /opt/docker-server/.setup-complete
  EOT
}

# =============================================================================
# Cloudflare Tunnel
# =============================================================================

resource "random_id" "tunnel_secret" {
  byte_length = 32
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "main" {
  account_id = var.cloudflare_account_id
  name       = local.resource_prefix
  secret     = random_id.tunnel_secret.b64_std
}

# Filter enabled services
locals {
  enabled_services = {
    for key, service in var.services :
    key => service if service.enabled
  }

  # Filter services that have a subdomain (exclude internal-only services like PostgreSQL)
  enabled_services_with_subdomain = {
    for key, service in local.enabled_services :
    key => service if can(service.subdomain) && service.subdomain != null && service.subdomain != ""
  }
}

# Tunnel configuration - dynamic based on services
resource "cloudflare_zero_trust_tunnel_cloudflared_config" "main" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.main.id

  config {
    # SSH access
    ingress_rule {
      hostname = "ssh.${var.domain}"
      service  = "ssh://localhost:22"
    }

    # Dynamic service ingress rules
    dynamic "ingress_rule" {
      for_each = local.enabled_services_with_subdomain
      content {
        hostname = "${ingress_rule.value.subdomain}.${var.domain}"
        service  = "http://localhost:${ingress_rule.value.port}"
      }
    }

    # Catch-all rule (required)
    ingress_rule {
      service = "http_status:404"
    }
  }
}

# =============================================================================
# Start Tunnel on Server
# =============================================================================

resource "null_resource" "start_tunnel" {
  triggers = {
    server_id = hcloud_server.main.id
    tunnel_id = cloudflare_zero_trust_tunnel_cloudflared.main.id
  }

  provisioner "remote-exec" {
    inline = [
      "echo 'Waiting for cloud-init to complete...'",
      "cloud-init status --wait || true",
      "echo 'Installing/updating Cloudflare Tunnel...'",
      # Stop existing service if running (in case of tunnel update)
      "systemctl stop cloudflared 2>/dev/null || true",
      # Install/update tunnel with new token
      "cloudflared service install ${cloudflare_zero_trust_tunnel_cloudflared.main.tunnel_token}",
      "systemctl enable cloudflared",
      "systemctl start cloudflared",
      # Wait a moment for service to start
      "sleep 3",
      # Verify tunnel is running
      "systemctl status cloudflared --no-pager || echo 'Warning: Tunnel service status check failed'",
      "echo 'Tunnel started successfully!'"
    ]

    connection {
      type        = "ssh"
      user        = "root"
      # Use IPv6 if IPv4 is disabled, otherwise use IPv4
      host        = var.ipv6_only ? hcloud_server.main.ipv6_address : hcloud_server.main.ipv4_address
      private_key = file(var.ssh_private_key_path)
      agent       = false
      timeout     = "10m"
    }
  }

  depends_on = [
    hcloud_server.main,
    cloudflare_zero_trust_tunnel_cloudflared.main,
    cloudflare_zero_trust_tunnel_cloudflared_config.main
  ]
}

# =============================================================================
# Close SSH Port after Tunnel is running
# =============================================================================

resource "null_resource" "close_ssh_port" {
  triggers = {
    tunnel_started = null_resource.start_tunnel.id
  }

  # Remove the setup firewall from the server (closes port 22)
  provisioner "local-exec" {
    command = <<-EOT
      echo "Closing SSH port (removing setup firewall)..."
      curl -s -X POST \
        -H "Authorization: Bearer ${var.hcloud_token}" \
        -H "Content-Type: application/json" \
        -d '{"remove_from":[{"type":"server","server":{"id":${hcloud_server.main.id}}}]}' \
        "https://api.hetzner.cloud/v1/firewalls/${hcloud_firewall.setup.id}/actions/remove_from_resources"
      echo "SSH port closed. Access now only via Cloudflare Tunnel."
    EOT
  }

  depends_on = [null_resource.start_tunnel]
}

# =============================================================================
# DNS Records
# =============================================================================

resource "cloudflare_record" "ssh" {
  zone_id = var.cloudflare_zone_id
  name    = "ssh"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.main.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

# Dynamic DNS records for all enabled services
resource "cloudflare_record" "services" {
  for_each = local.enabled_services_with_subdomain

  zone_id = var.cloudflare_zone_id
  name    = each.value.subdomain
  content = "${cloudflare_zero_trust_tunnel_cloudflared.main.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

# =============================================================================
# DNS A Records for External TCP Access
# =============================================================================
# These records point directly to the server IP (proxied = false)
# so external clients can connect via TCP (Kafka, PostgreSQL, MinIO S3 API)

locals {
  firewall_dns_records = {
    for key, rule in var.firewall_rules :
    key => rule if rule.dns_record != ""
  }
}

resource "cloudflare_record" "firewall_tcp" {
  for_each = local.firewall_dns_records

  zone_id = var.cloudflare_zone_id
  name    = each.value.dns_record
  content = hcloud_server.main.ipv4_address
  type    = "A"
  proxied = false
  ttl     = 300
}

# =============================================================================
# Cloudflare Access (Zero Trust)
# =============================================================================

# SSH Access Application
resource "cloudflare_zero_trust_access_application" "ssh" {
  zone_id          = var.cloudflare_zone_id
  name             = "${local.resource_prefix} SSH"
  domain           = "ssh.${var.domain}"
  type             = "ssh"
  session_duration = "1h"
}

# SSH Access Policy (Email OTP)
resource "cloudflare_zero_trust_access_policy" "ssh_email" {
  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_zero_trust_access_application.ssh.id
  name           = "Email SSH Access"
  precedence     = 1
  decision       = "allow"

  include {
    email = [var.admin_email]
  }
}

resource "cloudflare_zero_trust_access_short_lived_certificate" "ssh" {
  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_zero_trust_access_application.ssh.id
}

# SSH Service Token for headless/CI authentication (no browser required)
resource "cloudflare_zero_trust_access_service_token" "ssh" {
  account_id = var.cloudflare_account_id
  name       = "${local.resource_prefix}-ssh-token"
  duration   = "forever"
}

# Allow Service Token to access SSH
resource "cloudflare_zero_trust_access_policy" "ssh_service_token" {
  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_zero_trust_access_application.ssh.id
  name           = "Service Token SSH Access"
  precedence     = 2
  decision       = "non_identity"

  include {
    service_token = [cloudflare_zero_trust_access_service_token.ssh.id]
  }
}

# Dynamic Access Applications for all enabled services
resource "cloudflare_zero_trust_access_application" "services" {
  for_each = local.enabled_services_with_subdomain

  zone_id           = var.cloudflare_zone_id
  name              = "${local.resource_prefix} ${title(each.key)}"
  domain            = "${each.value.subdomain}.${var.domain}"
  type              = "self_hosted"
  # Wetty uses shorter session duration (1h) for enhanced security
  # Other services use 24h for better user experience
  session_duration  = each.key == "wetty" ? "1h" : "24h"
  skip_interstitial = true
}

# Dynamic Access Policies for all enabled services (Email OTP)
resource "cloudflare_zero_trust_access_policy" "services_email" {
  for_each = {
    for k, v in local.enabled_services_with_subdomain : k => v
    if !v.public
  }

  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_zero_trust_access_application.services[each.key].id
  name           = "Email Access to ${title(each.key)}"
  precedence     = 1
  decision       = "allow"

  include {
    email = local.allowed_emails
  }
}
