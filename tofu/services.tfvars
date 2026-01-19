# =============================================================================
# Nexus-Stack Services Configuration
# =============================================================================
# This file defines the available services and their configuration.
# 
# The 'enabled' field here is the DEFAULT value - actual enabled status
# is stored in Cloudflare D1 and managed via the Control Plane.
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
# - info: Dashboard showing all services
# These services cannot be disabled from the Control Plane.
# =============================================================================

# =============================================================================
# Services
# =============================================================================

services = {
  it-tools = {
    enabled     = true
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
    enabled     = true
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
    description = "Open-source secret management platform for teams."
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
    description = "Landing page showing all your Nexus Stack services and their status."
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

  marimo = {
    enabled     = false
    subdomain   = "marimo"
    port        = 2718
    public      = false
    description = "Reactive Python notebook with SQL support, reproducible and git-friendly."
  }

  mailpit = {
    enabled     = true
    subdomain   = "mailpit"
    port        = 8025
    public      = false
    core        = true
    description = "Email testing tool that catches all outgoing emails for inspection and testing."
  }

  metabase = {
    enabled     = false
    subdomain   = "metabase"
    port        = 3000
    public      = false
    description = "Open-source business intelligence and analytics tool for data visualization."
  }

  redpanda = {
    enabled     = false
    subdomain   = "redpanda"
    port        = 9644
    public      = false
    description = "Kafka-compatible streaming platform that is simpler, faster, and more cost-effective."
  }

  redpanda-console = {
    enabled     = false
    subdomain   = "redpanda-console"
    port        = 8180
    public      = false
    description = "Web UI for managing and debugging Redpanda/Kafka workloads."
  }

  cloudbeaver = {
    enabled     = false
    subdomain   = "cloudbeaver"
    port        = 8978
    public      = false
    description = "Web-based database management tool supporting PostgreSQL, MySQL, SQL Server, and more."
  }

  mage = {
    enabled     = false
    subdomain   = "mage"
    port        = 6789
    public      = false
    description = "Modern data pipeline tool - build, run, and manage pipelines for ETL/ELT workflows."
  }

  minio = {
    enabled     = false
    subdomain   = "minio"
    port        = 9001
    public      = false
    description = "High-performance S3-compatible object storage for data lakes, backups, and ML models."
  }
}
