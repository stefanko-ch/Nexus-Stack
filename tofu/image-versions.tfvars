# =============================================================================
# Docker Image Versions
# =============================================================================
# Images are pinned to MAJOR versions where available for automatic security
# patches while avoiding breaking changes. Some images only support exact
# versions or "latest".
#
# Strategy:
#   - Major version (e.g., :12) = auto-patches, manual major upgrades
#   - Exact version (e.g., :v1.0.22) = full control, manual all upgrades
#   - Latest = always newest (use only when no semver available)
#
# Find versions: https://hub.docker.com or GitHub releases
# =============================================================================

image_versions = {
  # -------------------------------------------------------------------------
  # Main Services (major version pinning where supported)
  # -------------------------------------------------------------------------
  cloudbeaver      = "dbeaver/cloudbeaver:24"                # Major: 24.x.x
  excalidraw       = "excalidraw/excalidraw:latest"          # No semver tags available
  grafana          = "grafana/grafana:11"                    # Major: 11.x.x (12 tag not yet available)
  infisical        = "infisical/infisical:v0.155.5"          # No major tags, exact only
  it-tools         = "corentinth/it-tools:latest"            # Date-based tags only
  kestra           = "kestra/kestra:v1.0"                    # Minor series: v1.0 (LTS)
  mailpit          = "axllent/mailpit:v1.28"                 # Minor stream: v1.28 (tracks latest 1.28.x patch)
  marimo           = "ghcr.io/marimo-team/marimo:latest-sql" # SQL variant with DuckDB
  metabase         = "metabase/metabase:v0.58.x"             # Minor: v0.58.x.x
  n8n              = "n8nio/n8n:1"                           # Major: 1.x.x
  portainer        = "portainer/portainer-ce:lts"            # LTS: Long-term support
  redpanda         = "redpandadata/redpanda:v24.3"           # Minor: v24.3.x
  redpanda-console = "redpandadata/console:v2.8"             # Minor: v2.8.x
  uptime-kuma      = "louislam/uptime-kuma:2"                # Major: 2.x.x

  # -------------------------------------------------------------------------
  # Grafana Stack Components
  # -------------------------------------------------------------------------
  prometheus    = "prom/prometheus:v3.9.1"              # Exact: v3.9.1 (latest stable)
  loki          = "grafana/loki:3"                      # Major: 3.x.x
  promtail      = "grafana/promtail:3"                  # Major: 3.x.x (match loki)
  cadvisor      = "ghcr.io/google/cadvisor:0.56"        # Exact: 0.56 (ghcr.io, no 'v' prefix)
  node-exporter = "prom/node-exporter:v1.10.2"          # Exact: v1.10.2 (latest stable)

  # -------------------------------------------------------------------------
  # Database & Support Images (pinned to major versions)
  # -------------------------------------------------------------------------
  postgres-14   = "postgres:14-alpine"
  postgres-16   = "postgres:16-alpine"
  redis         = "redis:7-alpine"
  nginx         = "nginx:alpine"
}
