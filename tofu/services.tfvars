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
#
# CORE SERVICES (core = true):
# - mailpit: Required for email testing by other services
# - infisical: Required for secret management
# These services cannot be disabled from the Control Plane.
# =============================================================================

services = {
  it-tools = {
    enabled     = false
    subdomain   = "it-tools"
    port        = 8080
    public      = false
    description = "Collection of handy online tools for developers - encoders, converters, generators, and more."
  }

  excalidraw = {
    enabled     = false
    subdomain   = "excalidraw"
    port        = 8082
    public      = false
    description = "Virtual whiteboard for sketching hand-drawn diagrams with collaboration support."
  }

  portainer = {
    enabled     = false
    subdomain   = "portainer"
    port        = 9090
    public      = false
    description = "Docker container management UI for easy deployment and monitoring."
  }

  uptime-kuma = {
    enabled     = false
    subdomain   = "uptime-kuma"
    port        = 3001
    public      = false
    description = "A fancy self-hosted monitoring tool for tracking service uptime and status."
  }

  infisical = {
    enabled     = true
    subdomain   = "infisical"
    port        = 8070
    public      = false
    core        = true
    description = "Open-source secret management platform for teams. CORE SERVICE - cannot be disabled."
  }

  grafana = {
    enabled     = true
    subdomain   = "grafana"
    port        = 3100
    public      = false
    description = "Observability platform for metrics, logs, and traces visualization."
  }

  info = {
    enabled     = true
    subdomain   = "info"
    port        = 8090
    public      = false
    core        = true
    description = "This landing page - your Nexus Stack dashboard. CORE SERVICE - cannot be disabled."
  }

  kestra = {
    enabled     = false
    subdomain   = "kestra"
    port        = 8085
    public      = false
    description = "Open-source orchestration and scheduling platform for data pipelines and workflows."
  }

  n8n = {
    enabled     = false
    subdomain   = "n8n"
    port        = 5678
    public      = false
    description = "Workflow automation tool with 400+ integrations for connecting apps and services."
  }

  mailpit = {
    enabled     = true
    subdomain   = "mailpit"
    port        = 8025
    public      = false
    core        = true
    description = "Email testing tool that catches all outgoing emails. CORE SERVICE - cannot be disabled."
  }
}
