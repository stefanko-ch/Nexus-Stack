# =============================================================================
# Control Panel - Cloudflare Pages with Functions
# =============================================================================
# This creates the control panel infrastructure on Cloudflare.
# It survives "teardown" but is destroyed on "destroy-all".
# 
# Uses Cloudflare Pages Functions for the API (no separate Worker needed).
# Environment variables are set via wrangler or Cloudflare dashboard.
# =============================================================================

# -----------------------------------------------------------------------------
# Cloudflare Pages Project (Frontend + API Functions)
# -----------------------------------------------------------------------------

resource "cloudflare_pages_project" "control_panel" {
  account_id        = var.cloudflare_account_id
  name              = "${var.server_name}-control"
  production_branch = "main"
  
  build_config {
    build_command   = ""
    destination_dir = "pages"
    root_dir        = "control-panel"
  }
  
  deployment_configs {
    production {
      environment_variables = {
        GITHUB_OWNER = var.github_owner
        GITHUB_REPO  = var.github_repo
      }
      
      # GITHUB_TOKEN must be set as secret via:
      # wrangler pages secret put GITHUB_TOKEN --project-name=${var.server_name}-control
      # or via Cloudflare dashboard
    }
  }
}

# -----------------------------------------------------------------------------
# DNS Record
# -----------------------------------------------------------------------------

# Control Panel (Frontend + API Functions)
resource "cloudflare_record" "control_panel" {
  zone_id = var.cloudflare_zone_id
  name    = "control"
  type    = "CNAME"
  content = cloudflare_pages_project.control_panel.subdomain
  proxied = true
  ttl     = 1
}

# Custom Domain for Cloudflare Pages
resource "cloudflare_pages_domain" "control_panel" {
  account_id   = var.cloudflare_account_id
  project_name = cloudflare_pages_project.control_panel.name
  domain       = "control.${var.domain}"
}

# -----------------------------------------------------------------------------
# Cloudflare Access Protection
# -----------------------------------------------------------------------------
# NOTE: Access protection for Pages is managed via the Cloudflare Dashboard:
# Workers & Pages > nexus-control > Settings > Enable access policy
# 
# We do NOT create a separate Access Application here because:
# 1. Pages has its own built-in Access integration
# 2. Adding a separate Access Application causes 401 errors on API routes
# 3. The Pages Access policy automatically covers all paths including /api/*
# -----------------------------------------------------------------------------