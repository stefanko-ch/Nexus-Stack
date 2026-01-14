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

resource "cloudflare_zero_trust_access_application" "control_panel" {
  zone_id          = var.cloudflare_zone_id
  name             = "${var.server_name} Control Panel"
  domain           = "control.${var.domain}"
  type             = "self_hosted"
  session_duration = "24h"

  # Important settings for Pages Functions API to work
  skip_interstitial        = true
  app_launcher_visible     = true
  options_preflight_bypass = true
  
  # Cookie settings - critical for same-origin API requests
  http_only_cookie_attribute = true
  same_site_cookie_attribute = "lax"
  
  # CORS settings for API requests from the same origin
  cors_headers = {
    allowed_origins   = ["https://control.${var.domain}"]
    allowed_methods   = ["GET", "POST", "OPTIONS"]
    allow_credentials = true
  }

  # Inline policy - this is the key difference!
  # Using inline policy instead of separate cloudflare_zero_trust_access_policy
  policies = [
    {
      name       = "Admin Access"
      precedence = 1
      decision   = "allow"
      include = [
        {
          email = {
            email = var.admin_email
          }
        }
      ]
    }
  ]
}