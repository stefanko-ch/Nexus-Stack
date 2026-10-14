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

  # List of emails allowed to access control plane (admin + optional user + optional guests)
  # user_email and guest_emails may be comma-separated, so split and trim into individual entries
  allowed_emails = distinct(compact(concat(
    [trimspace(var.admin_email)],
    [for email in split(",", var.user_email) : trimspace(email)],
    [for email in split(",", var.guest_emails) : trimspace(email)]
  )))

  # Control Plane URLs. Built from the base domain and the subdomain separator
  # so flat-subdomain deployments (e.g. infisical-tenant.example.com) work
  # without code changes. Consumed by Pages Functions, the teardown Worker,
  # and the DNS / Pages domain / Access app / CORS resources below.
  control_plane_hostname = "control${var.subdomain_separator}${var.domain}"
  infisical_url          = "https://infisical${var.subdomain_separator}${var.domain}"
  control_plane_url      = "https://${local.control_plane_hostname}"
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

  # BASE_DOMAIN is the Resend-verified parent domain used as the email
  # sender. Only emit the binding when it's actually set — Cloudflare's
  # Workers API rejects `plain_text_binding` with empty text, and the
  # worker code at control-plane/worker/src/index.js falls back to
  # `env.DOMAIN` when `env.BASE_DOMAIN` is absent (same contract as the
  # Pages-side send-credentials.js handler).
  #
  # Pages-side note: Functions read BASE_DOMAIN as a Pages SECRET (see
  # setup-control-plane.yaml), not a Terraform env var, because
  # `wrangler pages deploy` wipes Terraform-managed environment_variables
  # that aren't in wrangler.toml but preserves secrets.
  dynamic "plain_text_binding" {
    for_each = var.base_domain != "" ? [1] : []
    content {
      name = "BASE_DOMAIN"
      text = var.base_domain
    }
  }

  plain_text_binding {
    name = "CONTROL_PLANE_URL"
    text = local.control_plane_url
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
    text = var.notification_cron
  }

  plain_text_binding {
    name = "TEARDOWN_CRON"
    text = var.teardown_cron
  }

  # Note: RESEND_API_KEY and GITHUB_TOKEN are set via setup-control-plane-secrets.sh
}

# Cron triggers for scheduled teardown
# IMPORTANT: Must be a single resource — multiple resources for the same script
# will overwrite each other (Cloudflare API replaces all schedules on each PUT)
resource "cloudflare_workers_cron_trigger" "scheduled_teardown" {
  account_id  = var.cloudflare_account_id
  script_name = cloudflare_workers_script.scheduled_teardown.name
  schedules = [
    var.notification_cron,
    var.teardown_cron,
  ]
}

# Note: the workers.dev subdomain for the worker stays disabled by default.
# The post-deploy health check in setup-control-plane.yaml temporarily enables
# it via the Cloudflare API just for the duration of the diagnostic call,
# then disables it again. The diagnostic endpoint also requires a Bearer
# token (GITHUB_TOKEN) to prevent reconnaissance during the open window.
# The cloudflare_workers_script_subdomain Terraform resource only exists
# in provider v5+ and we are pinned to v4 here - see issue #342.

# -----------------------------------------------------------------------------
# Cloudflare KV Namespace (persistent config)
# -----------------------------------------------------------------------------
# Used for Databricks integration credentials and other config.
# Protected from destroy-all via state rm + re-import on next setup.

resource "cloudflare_workers_kv_namespace" "config" {
  account_id = var.cloudflare_account_id
  title      = "${local.resource_prefix}-config"
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
        GITHUB_OWNER                = var.github_owner
        GITHUB_REPO                 = var.github_repo
        DOMAIN                      = var.domain
        ADMIN_EMAIL                 = var.admin_email
        USER_EMAIL                  = var.user_email
        SERVER_TYPE                 = var.server_type
        SERVER_LOCATION             = var.server_location
        ALLOW_DISABLE_AUTO_SHUTDOWN = tostring(var.allow_disable_auto_shutdown)
        MAX_EXTENSIONS_PER_DAY      = tostring(var.max_extensions_per_day)
        MAX_DELAY_HOURS             = tostring(var.max_delay_hours)
      }
      # Note: SUBDOMAIN_SEPARATOR, INFISICAL_URL, CONTROL_PLANE_URL are set as Pages
      # secrets (not environment_variables) in setup-control-plane.yaml's "Set Control
      # Plane secrets" step — environment_variables get wiped by `wrangler pages deploy`.

      d1_databases = {
        NEXUS_DB = cloudflare_d1_database.nexus.id
      }

      kv_namespaces = {
        NEXUS_KV = cloudflare_workers_kv_namespace.config.id
      }

      # Note: GITHUB_TOKEN, RESEND_API_KEY, and CREDENTIALS_JSON are set via wrangler secret
      # (secrets block in Terraform isn't supported for Pages yet)
    }

    preview {
      environment_variables = {
        GITHUB_OWNER                = var.github_owner
        GITHUB_REPO                 = var.github_repo
        DOMAIN                      = var.domain
        ADMIN_EMAIL                 = var.admin_email
        USER_EMAIL                  = var.user_email
        SERVER_TYPE                 = var.server_type
        SERVER_LOCATION             = var.server_location
        ALLOW_DISABLE_AUTO_SHUTDOWN = tostring(var.allow_disable_auto_shutdown)
        MAX_EXTENSIONS_PER_DAY      = tostring(var.max_extensions_per_day)
        MAX_DELAY_HOURS             = tostring(var.max_delay_hours)
      }
      # Same note as production: SUBDOMAIN_SEPARATOR / INFISICAL_URL / CONTROL_PLANE_URL
      # are Pages secrets, not env vars.

      d1_databases = {
        NEXUS_DB = cloudflare_d1_database.nexus.id
      }

      kv_namespaces = {
        NEXUS_KV = cloudflare_workers_kv_namespace.config.id
      }
    }
  }
}

# -----------------------------------------------------------------------------
# DNS Record
# -----------------------------------------------------------------------------

resource "cloudflare_record" "control_plane" {
  zone_id = var.cloudflare_zone_id
  name    = local.control_plane_hostname
  content = "${cloudflare_pages_project.control_plane.name}.pages.dev"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

resource "cloudflare_pages_domain" "control_plane" {
  account_id   = var.cloudflare_account_id
  project_name = cloudflare_pages_project.control_plane.name
  domain       = local.control_plane_hostname

  depends_on = [cloudflare_record.control_plane]
}

# -----------------------------------------------------------------------------
# Cloudflare Access Protection
# -----------------------------------------------------------------------------

resource "cloudflare_zero_trust_access_application" "control_plane" {
  zone_id          = var.cloudflare_zone_id
  name             = "${local.resource_prefix} Control Plane"
  domain           = local.control_plane_hostname
  type             = "self_hosted"
  session_duration = "24h"

  skip_interstitial    = true
  app_launcher_visible = true

  http_only_cookie_attribute = true
  same_site_cookie_attribute = "lax"

  cors_headers {
    allowed_origins   = [local.control_plane_url]
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
# The *.pages.dev Hostnames: Closed in Code, Not Here
# -----------------------------------------------------------------------------
# A Pages project answers on three kinds of hostname:
#
#   control.<domain>              the application above
#   <project>.pages.dev           the production Pages hostname
#   <hash>.<project>.pages.dev    one per preview deployment
#
# Only the first is in this zone, so the application above — which is
# zone-scoped — cannot cover the others, and `pages.dev` is Cloudflare's
# own zone. The obvious move is a second, account-scoped Access
# application for `<project>.pages.dev`. This file had one. It is gone,
# deliberately, and the reason is worth keeping:
#
# Owning that application means owning whatever policy is attached to it,
# and an operator has every reason to have attached one already — the
# hostname existed and needed protecting before this repository managed
# it. On the first real run, the policy found there was a *reusable*
# account-level policy shared with other applications. Terraform's plan
# was to rename it and rewrite its email list, which would have changed
# access for every application sharing it. Cloudflare refused the update
# (`access.api.error.invalid_request: can not update reusable policies
# through this endpoint`), which is the only reason it did not happen.
#
# That is not a gap to patch. A resource that must adopt whatever an
# operator configured, in a shape this repository cannot predict, is the
# wrong tool — and it was buying defence in depth that
# control-plane/functions/_middleware.js already provides more completely:
# the middleware answers 404 on every hostname but the Control Plane's
# own, which covers the production pages.dev hostname AND the
# per-deployment preview hostnames that no single Access application can
# name. It is code, so it deploys with the application and survives the
# destroy/recreate cycle this project performs routinely — the very
# property the Access application was added for.
#
# So the division is: Access protects `control.<domain>`, where this
# repository created the application and owns its policy. Every other
# hostname the Pages project answers on is closed by the middleware. An
# operator who additionally wants an Access prompt on `pages.dev` can
# keep one in the dashboard; nothing here will fight them for it.
#
# If this is ever reinstated, the thing to solve first is the policy, not
# the application: it needs a policy of its own that is not reusable and
# not shared, or no managed policy at all — and "an Access application
# with zero policies" is a behaviour to verify, not assume.

# -----------------------------------------------------------------------------
# Hetzner Object Storage Bucket (for LakeFS)
# -----------------------------------------------------------------------------
# This bucket persists through teardown - only destroyed on destroy-all.
# Created conditionally when Hetzner Object Storage credentials are provided.

resource "minio_s3_bucket" "lakefs" {
  count         = var.hetzner_object_storage_access_key != "" ? 1 : 0
  bucket        = "${local.resource_prefix}-lakefs"
  force_destroy = false
}

# -----------------------------------------------------------------------------
# Hetzner Object Storage Bucket (General Purpose)
# -----------------------------------------------------------------------------
# Shared bucket for services like Filestash. Persists through teardown.
# Created conditionally when Hetzner Object Storage credentials are provided.

resource "minio_s3_bucket" "general" {
  count         = var.hetzner_object_storage_access_key != "" ? 1 : 0
  bucket        = local.resource_prefix
  force_destroy = false
}

# -----------------------------------------------------------------------------
# Hetzner Object Storage Bucket (for pg_ducklake)
# -----------------------------------------------------------------------------
# This bucket persists through teardown - only destroyed on destroy-all.
# Created conditionally when Hetzner Object Storage credentials are provided.
# Stores Parquet data files for DuckLake tables (catalog/metadata is in Postgres).

resource "minio_s3_bucket" "pgducklake" {
  count         = var.hetzner_object_storage_access_key != "" ? 1 : 0
  bucket        = "${local.resource_prefix}-pgducklake"
  force_destroy = false
}

# -----------------------------------------------------------------------------
# Persistent storage — REMOVED in RFC 0001 cutover
# -----------------------------------------------------------------------------
# The hcloud_volume "persistent" resource that used to live here was
# the per-tenant data volume mounted at /mnt/nexus-data/. RFC 0001
# replaced it with R2-backed snapshots: spinup pulls latest.txt from
# R2 onto the server's local SSD; teardown atomically snapshots the
# live state to R2 before destroy. See:
#   - src/nexus_deploy/s3_persistence.py  (rendering)
#   - src/nexus_deploy/s3_restore.py      (orchestration)
