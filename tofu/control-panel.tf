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
# Scheduled Teardown Worker (must be defined before Pages Project for KV binding)
# -----------------------------------------------------------------------------

# KV Namespace for scheduled teardown configuration
resource "cloudflare_workers_kv_namespace" "scheduled_teardown" {
  account_id = var.cloudflare_account_id
  title      = "${var.server_name}-scheduled-teardown"
}

# Cloudflare Worker for scheduled teardown
resource "cloudflare_workers_script" "scheduled_teardown" {
  account_id = var.cloudflare_account_id
  name       = "${var.server_name}-scheduled-teardown"
  content    = file("${path.module}/../control-panel/worker/src/index.js")
  module     = true

  kv_namespace_binding {
    name         = "SCHEDULED_TEARDOWN"
    namespace_id = cloudflare_workers_kv_namespace.scheduled_teardown.id
  }

  # Note: Cron triggers and environment variables must be set via wrangler:
  # wrangler deploy --name=${var.server_name}-scheduled-teardown --compatibility-date=2024-01-01
  # wrangler secret put RESEND_API_KEY --name=${var.server_name}-scheduled-teardown
  # wrangler secret put ADMIN_EMAIL --name=${var.server_name}-scheduled-teardown
  # wrangler secret put DOMAIN --name=${var.server_name}-scheduled-teardown
  # wrangler secret put GITHUB_TOKEN --name=${var.server_name}-scheduled-teardown
  # wrangler secret put GITHUB_OWNER --name=${var.server_name}-scheduled-teardown
  # wrangler secret put GITHUB_REPO --name=${var.server_name}-scheduled-teardown
  # 
  # For cron triggers, use wrangler.toml or:
  # wrangler triggers cron add "45 20 * * *" --name=${var.server_name}-scheduled-teardown
  # wrangler triggers cron add "0 21 * * *" --name=${var.server_name}-scheduled-teardown
}

# Cron triggers for scheduled teardown (separate resource)
resource "cloudflare_workers_cron_trigger" "scheduled_teardown_notification" {
  account_id = var.cloudflare_account_id
  script_name = cloudflare_workers_script.scheduled_teardown.name
  schedules   = ["45 20 * * *"]  # Notification at 20:45 UTC (21:45 CET)
}

resource "cloudflare_workers_cron_trigger" "scheduled_teardown_execution" {
  account_id = var.cloudflare_account_id
  script_name = cloudflare_workers_script.scheduled_teardown.name
  schedules   = ["0 21 * * *"]  # Teardown at 21:00 UTC (22:00 CET)
}

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
        DOMAIN       = var.domain
        SERVER_TYPE  = var.server_type
        SERVER_LOCATION = var.server_location
      }
      
      # KV Namespace binding for scheduled teardown configuration
      kv_namespaces = {
        SCHEDULED_TEARDOWN = cloudflare_workers_kv_namespace.scheduled_teardown.id
      }
      
      # GITHUB_TOKEN must be set as secret via:
      # wrangler pages secret put GITHUB_TOKEN --project-name=${var.server_name}-control
      # or via Cloudflare dashboard
    }

    preview {
      environment_variables = {
        GITHUB_OWNER = var.github_owner
        GITHUB_REPO  = var.github_repo
        DOMAIN       = var.domain
        SERVER_TYPE  = var.server_type
        SERVER_LOCATION = var.server_location
      }
      
      # KV Namespace binding for preview environment
      kv_namespaces = {
        SCHEDULED_TEARDOWN = cloudflare_workers_kv_namespace.scheduled_teardown.id
      }
      
      # Note: Preview uses environment variables via Terraform for flexibility.
      # Production uses secrets via wrangler (set in deploy.yml workflow).
      # This allows preview deployments to work even if secrets aren't configured.
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
  skip_interstitial    = true
  app_launcher_visible = true
  # Note: options_preflight_bypass cannot be used with cors_headers
  
  # Cookie settings - critical for same-origin API requests
  http_only_cookie_attribute = true
  same_site_cookie_attribute = "lax"
  
  # CORS settings for API requests from the same origin
  # Note: This conflicts with options_preflight_bypass, so we use CORS headers instead
  cors_headers {
    allowed_origins   = ["https://control.${var.domain}"]
    allowed_methods   = ["GET", "POST", "OPTIONS"]
    allow_credentials = true
  }
}

# Control Panel Access Policy (Email OTP)
resource "cloudflare_zero_trust_access_policy" "control_panel_email" {
  account_id     = var.cloudflare_account_id
  application_id = cloudflare_zero_trust_access_application.control_panel.id
  name           = "Email Access"
  precedence     = 1
  decision       = "allow"

  include {
    email = [var.admin_email]
  }
}
