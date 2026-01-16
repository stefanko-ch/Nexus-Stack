# =============================================================================
# Docker Image Versions
# =============================================================================
# Pin specific versions for stability. Update these manually when you want to
# upgrade services. Find latest versions at:
# - https://hub.docker.com
# - GitHub releases of each project
#
# Format: "image:tag" - the full image reference
# =============================================================================

image_versions = {
  # -------------------------------------------------------------------------
  # Main Services
  # -------------------------------------------------------------------------
  excalidraw  = "excalidraw/excalidraw:latest"          # No semver tags available
  grafana     = "grafana/grafana:12.3.1"
  infisical   = "infisical/infisical:v0.155.5"
  it-tools    = "corentinth/it-tools:2024.10.22-7ca5933"
  kestra      = "kestra/kestra:v1.0.22"
  mailpit     = "axllent/mailpit:v1.28.2"
  metabase    = "metabase/metabase:v0.58.2.3"
  n8n         = "n8nio/n8n:1.123.15"
  portainer   = "portainer/portainer-ce:2.33.6"
  uptime-kuma = "louislam/uptime-kuma:2.0.2"

  # -------------------------------------------------------------------------
  # Grafana Stack Components
  # -------------------------------------------------------------------------
  prometheus    = "prom/prometheus:v3.9.1"
  loki          = "grafana/loki:3.6.3"
  promtail      = "grafana/promtail:3.6.3"
  cadvisor      = "gcr.io/cadvisor/cadvisor:v0.56.1"
  node-exporter = "prom/node-exporter:v1.10.2"

  # -------------------------------------------------------------------------
  # Database & Support Images (pinned to major versions)
  # -------------------------------------------------------------------------
  postgres-14   = "postgres:14-alpine"
  postgres-16   = "postgres:16-alpine"
  redis         = "redis:7-alpine"
  nginx         = "nginx:alpine"
}
