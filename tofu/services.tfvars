# =============================================================================
# Nexus-Stack Services Configuration
# =============================================================================
# This file defines which services are deployed via Cloudflare Tunnel.
# Edit this file to enable/disable services or change subdomains.
#
# Each service creates:
# - Cloudflare DNS record: <subdomain>.<domain>
# - Cloudflare Tunnel route to localhost:<port>
# - Cloudflare Access policy (if public = false)
#
# Note: You also need stacks/<service>/docker-compose.yml for the container!
# =============================================================================

services = {
  it-tools = {
    enabled   = true
    subdomain = "it-tools"
    port      = 8080
    public    = false
  }

  excalidraw = {
    enabled   = true
    subdomain = "excalidraw"
    port      = 8082
    public    = false
  }

  portainer = {
    enabled   = true
    subdomain = "portainer"
    port      = 9090
    public    = false
  }

  uptime-kuma = {
    enabled   = true
    subdomain = "uptime-kuma"
    port      = 3001
    public    = false
  }

  infisical = {
    enabled   = true
    subdomain = "infisical"
    port      = 8070
    public    = false
  }

  grafana = {
    enabled   = true
    subdomain = "grafana"
    port      = 3100
    public    = false
  }

  info = {
    enabled   = true
    subdomain = "info"
    port      = 8090
    public    = false
  }

  kestra = {
    enabled   = true
    subdomain = "kestra"
    port      = 8085
    public    = false
  }

  n8n = {
    enabled   = true
    subdomain = "n8n"
    port      = 5678
    public    = false
  }
}
