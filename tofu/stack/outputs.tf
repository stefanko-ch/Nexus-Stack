# =============================================================================
# Server Outputs
# =============================================================================

output "server_ip" {
  description = "Public IPv4 address of the server"
  value       = hcloud_server.main.ipv4_address
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
  description = "URLs for all enabled services"
  value = {
    for key, service in local.enabled_services :
    key => "https://${service.subdomain}.${var.domain}"
  }
}

output "enabled_services" {
  description = "List of enabled service names (for deploy script)"
  value = keys(local.enabled_services)
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
    infisical_admin_password   = random_password.infisical_admin.result
    infisical_encryption_key   = random_password.infisical_encryption_key.result
    infisical_auth_secret      = random_password.infisical_auth_secret.result
    infisical_db_password      = random_password.infisical_db_password.result
    
    # Portainer
    portainer_admin_password   = random_password.portainer_admin.result
    
    # Uptime Kuma
    kuma_admin_password        = random_password.kuma_admin.result
    
    # Grafana
    grafana_admin_password     = random_password.grafana_admin.result
    
    # Kestra
    kestra_admin_password      = random_password.kestra_admin.result
    kestra_db_password         = random_password.kestra_db.result
    
    # n8n
    n8n_admin_password         = random_password.n8n_admin.result
    
    # Metabase
    metabase_admin_password    = random_password.metabase_admin.result
    
    # Docker Hub (optional)
    dockerhub_username         = var.dockerhub_username
    dockerhub_token            = var.dockerhub_token
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
