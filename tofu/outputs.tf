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
