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

services = {
  # it-tools: intentionally enabled by default.
  # Previous default was `enabled = false`; this was changed to `true`
  # so new stacks have common developer tooling available out-of-the-box.
  # Control Plane / D1 still governs the *actual* enabled state at runtime.
  it-tools = {
    enabled     = true
    subdomain   = "it-tools"
    port        = 8080
    public      = false
    description = "Collection of handy online tools for developers - encoders, converters, generators, and more."
    image       = "corentinth/it-tools:latest"
  }

  excalidraw = {
    enabled     = false
    subdomain   = "excalidraw"
    port        = 8082
    public      = false
    description = "Virtual whiteboard for sketching hand-drawn diagrams with collaboration support."
    image       = "excalidraw/excalidraw:latest"
  }

  portainer = {
    enabled     = false
    subdomain   = "portainer"
    port        = 9090
    public      = false
    description = "Docker container management UI for easy deployment and monitoring."
    image       = "portainer/portainer-ce:lts"
  }

  uptime-kuma = {
    enabled     = true
    subdomain   = "uptime-kuma"
    port        = 3001
    public      = false
    description = "A fancy self-hosted monitoring tool for tracking service uptime and status."
    image       = "louislam/uptime-kuma:2"
  }

  infisical = {
    enabled     = true
    subdomain   = "infisical"
    port        = 8070
    public      = false
    core        = true
    description = "Open-source secret management platform for teams."
    image       = "infisical/infisical:v0.155.5"
    support_images = {
      postgres = "postgres:14-alpine"
      redis    = "redis:7-alpine"
    }
  }

  grafana = {
    enabled     = true
    subdomain   = "grafana"
    port        = 3100
    public      = false
    description = "Observability platform for metrics, logs, and traces visualization."
    image       = "grafana/grafana:11.6"
    support_images = {
      prometheus    = "prom/prometheus:v3.9.1"
      loki          = "grafana/loki:3"
      promtail      = "grafana/promtail:3"
      cadvisor      = "ghcr.io/google/cadvisor:0.56"
      node-exporter = "prom/node-exporter:v1.10.2"
    }
  }

  info = {
    enabled     = true
    subdomain   = "info"
    port        = 8090
    public      = false
    core        = true
    description = "Landing page showing all your Nexus Stack services and their status."
    image       = "nginx:alpine"
  }

  kestra = {
    enabled     = false
    subdomain   = "kestra"
    port        = 8085
    public      = false
    description = "Open-source orchestration and scheduling platform for data pipelines and workflows."
    image       = "kestra/kestra:v1.0"
    support_images = {
      postgres = "postgres:16-alpine"
    }
  }

  n8n = {
    enabled     = false
    subdomain   = "n8n"
    port        = 5678
    public      = false
    description = "Workflow automation tool with 400+ integrations for connecting apps and services."
    image       = "n8nio/n8n:1"
    support_images = {
      postgres = "postgres:16-alpine"
    }
  }

  marimo = {
    enabled     = false
    subdomain   = "marimo"
    port        = 2718
    public      = false
    description = "Reactive Python notebook with SQL support, reproducible and git-friendly."
    image       = "ghcr.io/marimo-team/marimo:latest-sql"
  }

  mailpit = {
    enabled     = true
    subdomain   = "mailpit"
    port        = 8025
    public      = false
    core        = true
    description = "Email testing tool that catches all outgoing emails for inspection and testing."
    image       = "axllent/mailpit:v1.28"
  }

  metabase = {
    enabled     = false
    subdomain   = "metabase"
    port        = 3000
    public      = false
    description = "Open-source business intelligence and analytics tool for data visualization."
    image       = "metabase/metabase:v0.58.x"
    support_images = {
      postgres = "postgres:16-alpine"
    }
  }

  # redpanda and redpanda-console: Changed from enabled = true to false by default.
  # These services are typically used together. This change represents a breaking change
  # for existing deployments that had these services enabled. Users can re-enable them
  # via the Control Plane UI if needed.
  redpanda = {
    enabled     = false
    subdomain   = "redpanda"
    port        = 9644
    public      = false
    description = "Kafka-compatible streaming platform that is simpler, faster, and more cost-effective."
    image       = "redpandadata/redpanda:v24.3"
  }

  redpanda-console = {
    enabled     = false
    subdomain   = "redpanda-console"
    port        = 8180
    public      = false
    description = "Web UI for managing and debugging Redpanda/Kafka workloads."
    image       = "redpandadata/console:v2.8"
  }

  cloudbeaver = {
    enabled     = false
    subdomain   = "cloudbeaver"
    port        = 8978
    public      = false
    description = "Web-based database management tool supporting PostgreSQL, MySQL, SQL Server, and more."
    image       = "dbeaver/cloudbeaver:24"
  }

  mage = {
    enabled     = false
    subdomain   = "mage"
    port        = 6789
    public      = false
    description = "Modern data pipeline tool - build, run, and manage pipelines for ETL/ELT workflows."
    image       = "mageai/mageai:latest"
    support_images = {
      postgres = "postgres:14-alpine"
    }
  }

  minio = {
    enabled     = false
    subdomain   = "minio"
    port        = 9001
    public      = false
    description = "High-performance S3-compatible object storage for data lakes, backups, and ML models."
    image       = "minio/minio:latest"
  }

  wetty = {
    enabled     = true
    subdomain   = "wetty"
    port        = 3002
    public      = false
    description = "Web-based SSH terminal that allows you to access your server via a web browser without requiring SSH client software. Uses public key authentication only for security."
    image       = "wettyoss/wetty:latest"
  }
}
