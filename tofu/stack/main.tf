# =============================================================================
# SSH Key
# =============================================================================

resource "hcloud_ssh_key" "main" {
  name       = "${var.server_name}-key"
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

# =============================================================================
# Firewall
# =============================================================================

resource "hcloud_firewall" "main" {
  name = "${var.server_name}-fw"

  # No inbound rules at all = true Zero Entry
  # All traffic goes through Cloudflare Tunnel
}

# Temporary firewall for initial setup (SSH access)
resource "hcloud_firewall" "setup" {
  name = "${var.server_name}-setup-fw"

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
  name         = var.server_name
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
    
    # Install cloudflared via official Cloudflare apt repository (IPv6 compatible)
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | tee /etc/apt/keyrings/cloudflare-main.gpg >/dev/null
    echo "deb [signed-by=/etc/apt/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/cloudflared.list
    apt-get update
    apt-get install -y cloudflared
    
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
  name       = var.server_name
  secret     = random_id.tunnel_secret.b64_std
}

# Filter enabled services
locals {
  enabled_services = {
    for key, service in var.services :
    key => service if service.enabled
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
      for_each = local.enabled_services
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
# Start Tunnel on Server (via SSH over IPv6 with WARP)
# =============================================================================

resource "null_resource" "start_tunnel" {
  triggers = {
    server_id   = hcloud_server.main.id
    tunnel_id   = cloudflare_zero_trust_tunnel_cloudflared.main.id
    server_ipv4 = hcloud_server.main.ipv4_address
    server_ipv6 = hcloud_server.main.ipv6_address
    force_check = "v8" # Force recreation for debugging
  }

  # 1. Diagnostic Checks (VISIBLE OUTPUT)
  provisioner "remote-exec" {
    inline = [
      "echo '=== DEBUG: Server Info ==='",
      "hostname",
      "uname -a",
      "echo ''",
      "echo '=== DEBUG: Network ==='",
      "ip addr show",
      "ip route show",
      "echo ''",
      "echo '=== DEBUG: Connectivity ==='",
      "curl -v -6 https://region1.v2.argotunnel.com/login 2>&1 || echo 'Failed to reach Argotunnel v2 (IPv6)'",
      "curl -v https://region1.v2.argotunnel.com/login 2>&1 || echo 'Failed to reach Argotunnel v2 (Default)'",
      "echo ''",
      "echo '=== DEBUG: Pre-Install Check ==='",
      "cloud-init status --wait || true",
      "which cloudflared || echo 'cloudflared not in path'"
    ]

    connection {
      type        = "ssh"
      user        = "root"
      host        = var.ipv6_only ? element(split("/", hcloud_server.main.ipv6_address), 0) : hcloud_server.main.ipv4_address
      private_key = file(var.ssh_private_key_path)
      timeout     = "5m"
    }
  }

  # 2. Sensitive Installation (SUPPRESSED OUTPUT)
  provisioner "remote-exec" {
    inline = [
      "cloudflared service install ${cloudflare_zero_trust_tunnel_cloudflared.main.tunnel_token}",
      "systemctl enable cloudflared",
      "systemctl restart cloudflared"
    ]

    connection {
      type        = "ssh"
      user        = "root"
      host        = var.ipv6_only ? element(split("/", hcloud_server.main.ipv6_address), 0) : hcloud_server.main.ipv4_address
      private_key = file(var.ssh_private_key_path)
      timeout     = "5m"
    }
  }

  # 3. Post-Install Diagnostics (VISIBLE OUTPUT)
  provisioner "remote-exec" {
    inline = [
      "echo '=== DEBUG: Post-Install Status ==='",
      "sleep 5",
      "systemctl status cloudflared --no-pager || true",
      "echo '=== DEBUG: Cloudflared Logs ==='",
      "journalctl -u cloudflared --no-pager -n 50 || true",
      "echo '=== Tunnel Setup End ==='"
    ]


    connection {
      type        = "ssh"
      user        = "root"
      # Use IPv6 if IPv4 is disabled, otherwise use IPv4
      # Note: GitHub Actions uses Cloudflare WARP for IPv6 connectivity
      # Hetzner returns IPv6 with /64 suffix (e.g. 2a01:4f8:x:x::1/64)
      # We simply remove the /64 to get the host address
      host        = var.ipv6_only ? element(split("/", hcloud_server.main.ipv6_address), 0) : hcloud_server.main.ipv4_address
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
  for_each = local.enabled_services

  zone_id = var.cloudflare_zone_id
  name    = each.value.subdomain
  content = "${cloudflare_zero_trust_tunnel_cloudflared.main.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

# =============================================================================
# Cloudflare Access (Zero Trust)
# =============================================================================

# SSH Access Application
resource "cloudflare_zero_trust_access_application" "ssh" {
  zone_id          = var.cloudflare_zone_id
  name             = "${var.server_name} SSH"
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
  name       = "${var.server_name}-ssh-token"
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
  for_each = local.enabled_services

  zone_id           = var.cloudflare_zone_id
  name              = "${var.server_name} ${title(each.key)}"
  domain            = "${each.value.subdomain}.${var.domain}"
  type              = "self_hosted"
  session_duration  = "24h"
  skip_interstitial = true
}

# Dynamic Access Policies for all enabled services (Email OTP)
resource "cloudflare_zero_trust_access_policy" "services_email" {
  for_each = {
    for k, v in local.enabled_services : k => v
    if !v.public
  }

  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_zero_trust_access_application.services[each.key].id
  name           = "Email Access to ${title(each.key)}"
  precedence     = 1
  decision       = "allow"

  include {
    email = [var.admin_email]
  }
}
