# =============================================================================
# Control Plane - Cloudflare Pages with Functions
# =============================================================================
# This creates the control plane infrastructure on Cloudflare.
# It survives "teardown" but is destroyed on "destroy-all".
# 
# Uses Cloudflare Pages Functions for the API (no separate Worker needed).
# Environment variables are set via wrangler or Cloudflare dashboard.
# =============================================================================

locals {
  # Resource prefix derived from domain (e.g., "example.com" → "nexus-example-com")
  resource_prefix = "nexus-${replace(var.domain, ".", "-")}"

  # List of emails allowed to access control plane (admin + optional user)
  allowed_emails = compact([var.admin_email, var.user_email])
}

# -----------------------------------------------------------------------------
# D1 Database for Control Plane State
# -----------------------------------------------------------------------------
# Stores: scheduled teardown config, enabled services
# Does NOT store: credentials (those go in Cloudflare Secrets)

resource "cloudflare_d1_database" "nexus" {
  account_id = var.cloudflare_account_id
  name       = "${local.resource_prefix}-db"
}

# -----------------------------------------------------------------------------
# Scheduled Teardown Worker
# -----------------------------------------------------------------------------

# Cloudflare Worker for scheduled teardown
resource "cloudflare_workers_script" "scheduled_teardown" {
  account_id = var.cloudflare_account_id
  name       = "${local.resource_prefix}-worker"
  content    = file("${path.module}/../../control-plane/worker/src/index.js")
  module     = true

  d1_database_binding {
    name        = "NEXUS_DB"
    database_id = cloudflare_d1_database.nexus.id
  }

  # Environment variables for worker
  plain_text_binding {
    name = "DOMAIN"
    text = var.domain
  }

  plain_text_binding {
    name = "ADMIN_EMAIL"
    text = var.admin_email
  }

  plain_text_binding {
    name = "USER_EMAIL"
    text = var.user_email
  }

  plain_text_binding {
    name = "GITHUB_OWNER"
    text = var.github_owner
  }

  plain_text_binding {
    name = "GITHUB_REPO"
    text = var.github_repo
  }

  plain_text_binding {
    name = "NOTIFICATION_CRON"
    text = "45 20 * * *"  # Notification at 20:45 UTC (21:45 CET)
  }

  plain_text_binding {
    name = "TEARDOWN_CRON"
    text = "0 21 * * *"  # Teardown at 21:00 UTC (22:00 CET)
  }

  # Note: RESEND_API_KEY and GITHUB_TOKEN are set via setup-control-plane-secrets.sh
}

# Cron triggers for scheduled teardown
# IMPORTANT: Must be a single resource — multiple resources for the same script
# will overwrite each other (Cloudflare API replaces all schedules on each PUT)
resource "cloudflare_workers_cron_trigger" "scheduled_teardown" {
  account_id  = var.cloudflare_account_id
  script_name = cloudflare_workers_script.scheduled_teardown.name
  schedules   = [
    "45 20 * * *",  # Notification at 20:45 UTC (21:45 CET)
    "0 21 * * *",   # Teardown at 21:00 UTC (22:00 CET)
  ]
}

# -----------------------------------------------------------------------------
# Cloudflare Pages Project (Frontend + API Functions)
# -----------------------------------------------------------------------------

resource "cloudflare_pages_project" "control_plane" {
  account_id        = var.cloudflare_account_id
  name              = "${local.resource_prefix}-control"
  production_branch = "main"
  
  build_config {
    build_command   = ""
    destination_dir = "pages"
    root_dir        = "control-plane"
  }
  
  deployment_configs {
    production {
      environment_variables = {
        GITHUB_OWNER                 = var.github_owner
        GITHUB_REPO                  = var.github_repo
        DOMAIN                       = var.domain
        ADMIN_EMAIL                  = var.admin_email
        USER_EMAIL                   = var.user_email
        SERVER_TYPE                  = var.server_type
        SERVER_LOCATION              = var.server_location
        ALLOW_DISABLE_AUTO_SHUTDOWN  = tostring(var.allow_disable_auto_shutdown)
      }
      
      d1_databases = {
        NEXUS_DB = cloudflare_d1_database.nexus.id
      }
      
      # Note: GITHUB_TOKEN, RESEND_API_KEY, and CREDENTIALS_JSON are set via wrangler secret
      # (secrets block in Terraform isn't supported for Pages yet)
    }

    preview {
      environment_variables = {
        GITHUB_OWNER                 = var.github_owner
        GITHUB_REPO                  = var.github_repo
        DOMAIN                       = var.domain
        ADMIN_EMAIL                  = var.admin_email
        USER_EMAIL                   = var.user_email
        SERVER_TYPE                  = var.server_type
        SERVER_LOCATION              = var.server_location
        ALLOW_DISABLE_AUTO_SHUTDOWN  = tostring(var.allow_disable_auto_shutdown)
      }
      
      d1_databases = {
        NEXUS_DB = cloudflare_d1_database.nexus.id
      }
    }
  }
}

# -----------------------------------------------------------------------------
# DNS Record
# -----------------------------------------------------------------------------

resource "cloudflare_record" "control_plane" {
  zone_id = var.cloudflare_zone_id
  name    = "control"
  content = "${cloudflare_pages_project.control_plane.name}.pages.dev"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

resource "cloudflare_pages_domain" "control_plane" {
  account_id   = var.cloudflare_account_id
  project_name = cloudflare_pages_project.control_plane.name
  domain       = "control.${var.domain}"
  
  depends_on = [cloudflare_record.control_plane]
}

# -----------------------------------------------------------------------------
# Cloudflare Access Protection
# -----------------------------------------------------------------------------

resource "cloudflare_zero_trust_access_application" "control_plane" {
  zone_id          = var.cloudflare_zone_id
  name             = "${local.resource_prefix} Control Plane"
  domain           = "control.${var.domain}"
  type             = "self_hosted"
  session_duration = "24h"

  skip_interstitial    = true
  app_launcher_visible = true

  http_only_cookie_attribute = true
  same_site_cookie_attribute = "lax"
  
  cors_headers {
    allowed_origins   = ["https://control.${var.domain}"]
    allowed_methods   = ["GET", "POST", "OPTIONS"]
    allow_credentials = true
  }
}

resource "cloudflare_zero_trust_access_policy" "control_plane_email" {
  account_id     = var.cloudflare_account_id
  application_id = cloudflare_zero_trust_access_application.control_plane.id
  name           = "Email Access"
  precedence     = 1
  decision       = "allow"

  include {
    email = local.allowed_emails
  }
}

# -----------------------------------------------------------------------------
# Hetzner Object Storage Bucket (for LakeFS)
# -----------------------------------------------------------------------------
# This bucket persists through teardown - only destroyed on destroy-all.
# Created conditionally when Hetzner Object Storage credentials are provided.

resource "minio_s3_bucket" "lakefs" {
  count         = var.hetzner_object_storage_access_key != "" ? 1 : 0
  bucket        = "${local.resource_prefix}-lakefs"
  force_destroy = true
}

# -----------------------------------------------------------------------------
# Hetzner Object Storage Bucket (General Purpose)
# -----------------------------------------------------------------------------
# Shared bucket for services like Filestash. Persists through teardown.
# Created conditionally when Hetzner Object Storage credentials are provided.

resource "minio_s3_bucket" "general" {
  count         = var.hetzner_object_storage_access_key != "" ? 1 : 0
  bucket        = local.resource_prefix
  force_destroy = true
}

# -----------------------------------------------------------------------------
# Hetzner Cloud Persistent Volume
# -----------------------------------------------------------------------------
# This volume persists through teardown - only destroyed on destroy-all.
# Used by services that need persistent storage (e.g., Gitea repositories).
# Mounted at /mnt/nexus-data/ on the server with subdirectories per service.

resource "hcloud_volume" "persistent" {
  name     = "${local.resource_prefix}-data"
  size     = var.persistent_volume_size
  location = var.server_location
  format   = "ext4"

  labels = {
    managed_by = "opentofu"
    purpose    = "persistent-data"
  }
}
