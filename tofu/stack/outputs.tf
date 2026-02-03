# =============================================================================
# Server Outputs
# =============================================================================

output "server_ip" {
  description = "Public IPv4 address of the server"
  value       = hcloud_server.main.ipv4_address
}

output "server_id" {
  description = "Hetzner server ID (used by ssh-setup state)"
  value       = hcloud_server.main.id
}

output "tunnel_token" {
  description = "Cloudflare Tunnel token for installation on server"
  sensitive   = true
  value       = cloudflare_zero_trust_tunnel_cloudflared.main.tunnel_token
}

output "resource_prefix" {
  description = "Resource name prefix (e.g., nexus-example-com)"
  value       = local.resource_prefix
}

output "ssh_firewall_id" {
  description = "SSH setup firewall ID (for workflow attach/detach via API)"
  value       = hcloud_firewall.ssh_setup.id
}

output "ssh_command" {
  description = "SSH command via Cloudflare Tunnel (requires cloudflared locally)"
  value       = "cloudflared access ssh --hostname ssh.${var.domain}"
}

output "ssh_config" {
  description = "Add this to ~/.ssh/config for easy access"
  value       = <<-EOT
    Host nexus
      HostName ssh.${var.domain}
      User root
      ProxyCommand cloudflared access ssh --hostname %h
  EOT
}

# =============================================================================
# SSH Service Token (for headless/CI access)
# =============================================================================

output "ssh_service_token" {
  description = "Service Token for SSH access without browser login"
  sensitive   = true
  value = {
    client_id     = cloudflare_zero_trust_access_service_token.ssh.client_id
    client_secret = cloudflare_zero_trust_access_service_token.ssh.client_secret
  }
}

# =============================================================================
# Cloudflare Outputs
# =============================================================================

output "tunnel_id" {
  description = "Cloudflare Tunnel ID"
  value       = cloudflare_zero_trust_tunnel_cloudflared.main.id
}

output "service_urls" {
  description = "URLs for all enabled services with a subdomain"
  value = {
    for key, service in local.enabled_services_with_subdomain :
    key => "https://${service.subdomain}.${var.domain}"
  }
}

output "enabled_services" {
  description = "List of enabled service names (for deploy script)"
  value       = keys(local.enabled_services)
}

output "image_versions" {
  description = "Docker image versions for each service (extracted from services config)"
  value = merge(
    { for name, svc in var.services : name => svc.image if svc.image != "" },
    merge([for name, svc in var.services : svc.support_images if svc.support_images != null]...)
  )
}

# =============================================================================
# Firewall Outputs
# =============================================================================

output "firewall_rules" {
  description = "Enabled firewall rules for external TCP access (for deploy script)"
  value = var.firewall_rules
}

# =============================================================================
# Secrets Outputs
# =============================================================================

output "secrets" {
  description = "Generated secrets for services (auto-pushed to Infisical)"
  sensitive   = true
  value = {
    # Admin credentials
    admin_email    = var.admin_email
    admin_username = var.admin_username

    # Infisical
    infisical_admin_password = random_password.infisical_admin.result
    infisical_encryption_key = random_password.infisical_encryption_key.result
    infisical_auth_secret    = random_password.infisical_auth_secret.result
    infisical_db_password    = random_password.infisical_db_password.result

    # Portainer
    portainer_admin_password = random_password.portainer_admin.result

    # Uptime Kuma
    kuma_admin_password = random_password.kuma_admin.result

    # Grafana
    grafana_admin_password = random_password.grafana_admin.result

    # Kestra
    kestra_admin_password = random_password.kestra_admin.result
    kestra_db_password    = random_password.kestra_db.result

    # n8n
    n8n_admin_password = random_password.n8n_admin.result

    # Metabase
    metabase_admin_password = random_password.metabase_admin.result

    # CloudBeaver
    cloudbeaver_admin_password = random_password.cloudbeaver_admin.result

    # Mage AI
    mage_admin_password = random_password.mage_admin.result

    # MinIO
    minio_root_password = random_password.minio_root.result

    # Hoppscotch
    hoppscotch_db_password    = random_password.hoppscotch_db.result
    hoppscotch_jwt_secret     = random_password.hoppscotch_jwt.result
    hoppscotch_session_secret = random_password.hoppscotch_session.result
    hoppscotch_encryption_key = random_password.hoppscotch_encryption.result

    # Meltano
    meltano_db_password = random_password.meltano_db.result

    # Soda
    soda_db_password = random_password.soda_db.result

    # Prefect
    prefect_db_password = random_password.prefect_db.result

    # PostgreSQL
    postgres_password = random_password.postgres.result

    # pgAdmin
    pgadmin_password = random_password.pgadmin.result

    # RedPanda SASL (for external Kafka access)
    redpanda_admin_password = random_password.redpanda_admin.result

    # RustFS
    rustfs_root_password = random_password.rustfs_root.result

    # SeaweedFS
    seaweedfs_admin_password = random_password.seaweedfs_admin.result

    # Garage
    garage_admin_token = random_password.garage_admin_token.result
    garage_rpc_secret  = random_id.garage_rpc_secret.hex

    # LakeFS
    lakefs_db_password    = random_password.lakefs_db.result
    lakefs_encrypt_secret = random_password.lakefs_encrypt_secret.result

    # Hetzner Object Storage (pass-through for LakeFS)
    hetzner_s3_server     = var.hetzner_object_storage_server
    hetzner_s3_region     = var.hetzner_object_storage_region
    hetzner_s3_access_key = var.hetzner_object_storage_access_key
    hetzner_s3_secret_key = var.hetzner_object_storage_secret_key
    hetzner_s3_bucket     = var.hetzner_object_storage_access_key != "" ? minio_s3_bucket.lakefs[0].bucket : ""

    # Docker Hub (optional)
    dockerhub_username = var.dockerhub_username
    dockerhub_token    = var.dockerhub_token
  }
}

# =============================================================================
# Individual Secret Outputs (for CI/CD)
# =============================================================================

output "infisical_admin_password" {
  description = "Infisical admin password (for GitHub Secrets)"
  sensitive   = true
  value       = random_password.infisical_admin.result
}
