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

# RedPanda SASL admin password (for external Kafka access)
resource "random_password" "redpanda_admin" {
  length  = 24
  special = false
}

# Prefect database password
resource "random_password" "prefect_db" {
  length  = 24
  special = false
}

# pgAdmin password
resource "random_password" "pgadmin" {
  length  = 24
  special = false
}

# RustFS root password
resource "random_password" "rustfs_root" {
  length  = 24
  special = false
}

# SeaweedFS admin password
resource "random_password" "seaweedfs_admin" {
  length  = 24
  special = false
}

# Garage admin token
resource "random_password" "garage_admin_token" {
  length  = 32
  special = false
}

# Garage RPC secret (must be 32 bytes hex-encoded = 64 hex chars)
resource "random_id" "garage_rpc_secret" {
  byte_length = 32  # Generates 64 hex characters (32 bytes in hex)
}

# LakeFS database password
resource "random_password" "lakefs_db" {
  length  = 24
  special = false
}

# LakeFS auth encryption secret
resource "random_password" "lakefs_encrypt_secret" {
  length  = 32
  special = false
}

# LakeFS admin access key (16 chars, uppercase alphanumeric like AWS)
resource "random_string" "lakefs_admin_access_key" {
  length  = 16
  special = false
  upper   = true
  lower   = false
  numeric = true
}

# LakeFS admin secret key
resource "random_password" "lakefs_admin_secret_key" {
  length  = 40
  special = false
}

# Filestash admin password
resource "random_password" "filestash_admin" {
  length  = 24
  special = false
}

# Windmill admin password
resource "random_password" "windmill_admin" {
  length  = 24
  special = false
}

# Windmill database password
resource "random_password" "windmill_db" {
  length  = 24
  special = false
}

# Windmill superadmin secret (for API automation)
resource "random_password" "windmill_superadmin_secret" {
  length  = 32
  special = false
}

# OpenMetadata admin password
# Note: OpenMetadata requires at least 1 special character (PasswordUtil.java)
# override_special restricts to chars safe in JSON strings and shell heredocs
resource "random_password" "openmetadata_admin" {
  length           = 24
  special          = true
  override_special = "!@#%^*()_+"
}

# OpenMetadata database password
resource "random_password" "openmetadata_db" {
  length  = 24
  special = false
}

# OpenMetadata Airflow password
resource "random_password" "openmetadata_airflow" {
  length  = 24
  special = false
}

# OpenMetadata Fernet key (base64-encoded 32-byte key for Airflow encryption)
resource "random_id" "openmetadata_fernet_key" {
  byte_length = 32
}

# ClickHouse admin password
resource "random_password" "clickhouse_admin" {
  length  = 24
  special = false
}

# Gitea admin password
resource "random_password" "gitea_admin" {
  length  = 24
  special = false
}

# Gitea user password (for user_email account - shared with students)
resource "random_password" "gitea_user" {
  length  = 24
  special = false
}

# Gitea database password
resource "random_password" "gitea_db" {
  length  = 24
  special = false
}

# Wiki.js
resource "random_password" "wikijs_admin" {
  length  = 24
  special = false
}

resource "random_password" "wikijs_db" {
  length  = 24
  special = false
}

# Woodpecker CI
resource "random_password" "woodpecker_agent_secret" {
  length  = 64
  special = false
}

# NocoDB admin password
resource "random_password" "nocodb_admin" {
  length  = 24
  special = false
}

# NocoDB database password
resource "random_password" "nocodb_db" {
  length  = 24
  special = false
}

# NocoDB JWT secret
resource "random_password" "nocodb_jwt_secret" {
  length  = 32
  special = false
}

# Dify admin password
resource "random_password" "dify_admin" {
  length  = 24
  special = false
}

# Dify database password
resource "random_password" "dify_db" {
  length  = 24
  special = false
}

# Dify Redis password
resource "random_password" "dify_redis" {
  length  = 24
  special = false
}

# Dify secret key (session/encryption)
resource "random_password" "dify_secret_key" {
  length  = 42
  special = false
}

# Dify Weaviate API key
resource "random_password" "dify_weaviate_api_key" {
  length  = 32
  special = false
}

# Dify sandbox API key
resource "random_password" "dify_sandbox_api_key" {
  length  = 32
  special = false
}

# Dify plugin daemon key
resource "random_password" "dify_plugin_daemon_key" {
  length  = 48
  special = false
}

# Dify plugin inner API key
resource "random_password" "dify_plugin_inner_api_key" {
  length  = 48
  special = false
}

# Note: Hetzner Object Storage bucket is created in control-plane/main.tf
# to persist through teardown. The bucket name is passed via hetzner_s3_bucket variable.

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

# SSH Setup Firewall (temporary, attached via workflow)
resource "hcloud_firewall" "ssh_setup" {
  name = "${local.resource_prefix}-ssh-setup-fw"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # No apply_to block - attachment happens via API in spin-up workflow
  # This ensures port 22 is only open during tunnel installation
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
  firewall_ids = [hcloud_firewall.main.id]

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
# Persistent Volume Attachment
# =============================================================================
# Attaches the persistent Hetzner Cloud Volume to the server.
# Volume is created in control-plane state to survive teardown.

resource "hcloud_volume_attachment" "persistent" {
  count     = var.persistent_volume_id > 0 ? 1 : 0
  volume_id = var.persistent_volume_id
  server_id = hcloud_server.main.id
  automount = true
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

  # Filter services that need Cloudflare Access protection (non-public only)
  # Public services (e.g., git-proxy) get DNS + Tunnel but NO Access Application
  # Cloudflare Access is default-deny: an Application without Allow policy blocks everything
  private_services_with_subdomain = {
    for key, service in local.enabled_services_with_subdomain :
    key => service if try(service.public, false) == false
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

# Dynamic Access Applications for private services only
# Public services (e.g., git-proxy) are excluded - they handle auth at the application level
resource "cloudflare_zero_trust_access_application" "services" {
  for_each = local.private_services_with_subdomain

  zone_id           = var.cloudflare_zone_id
  name              = "${local.resource_prefix} ${title(each.key)}"
  domain            = "${each.value.subdomain}.${var.domain}"
  type              = "self_hosted"
  # Wetty uses shorter session duration (1h) for enhanced security
  # Other services use 24h for better user experience
  session_duration  = each.key == "wetty" ? "1h" : "24h"
  skip_interstitial = true
}

# Dynamic Access Policies for private services (Email OTP)
resource "cloudflare_zero_trust_access_policy" "services_email" {
  for_each = local.private_services_with_subdomain

  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_zero_trust_access_application.services[each.key].id
  name           = "Email Access to ${title(each.key)}"
  precedence     = 1
  decision       = "allow"

  include {
    email = local.allowed_emails
  }
}
