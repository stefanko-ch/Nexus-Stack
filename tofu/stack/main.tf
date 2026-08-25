# =============================================================================
# Locals
# =============================================================================

locals {
  # Resource prefix derived from domain (e.g., "example.com" → "nexus-example-com")
  # This ensures unique resource names when multiple users deploy Nexus-Stack
  resource_prefix = "nexus-${replace(var.domain, ".", "-")}"

  # List of emails allowed to access services (admin + optional user + optional guests)
  # user_email and guest_emails may be comma-separated, so split and trim into individual entries
  allowed_emails = distinct(compact(concat(
    [trimspace(var.admin_email)],
    [for email in split(",", var.user_email) : trimspace(email)],
    [for email in split(",", var.guest_emails) : trimspace(email)]
  )))
}

# =============================================================================
# SSH Key
# =============================================================================

resource "hcloud_ssh_key" "main" {
  name       = "${local.resource_prefix}-key"
  public_key = trimspace(file(var.ssh_public_key_path))
}

# =============================================================================
# Generated Secrets
# =============================================================================

# Infisical secrets
resource "random_password" "infisical_admin" {
  length  = 24
  special = false
}

resource "random_password" "infisical_encryption_key" {
  length  = 32
  special = false
}

resource "random_password" "infisical_auth_secret" {
  length  = 32
  special = false
}

resource "random_password" "infisical_db_password" {
  length  = 24
  special = false
}

# Portainer admin password (for future use)
resource "random_password" "portainer_admin" {
  length  = 24
  special = false
}

# Uptime Kuma admin password
resource "random_password" "kuma_admin" {
  length  = 24
  special = false
}

# Grafana admin password
resource "random_password" "grafana_admin" {
  length  = 24
  special = false
}

# Dagster database password
resource "random_password" "dagster_db" {
  length  = 24
  special = false
}

# Kestra admin password.
#
# Kestra v1.0 OSS basic-auth has a hard validator: the password MUST
# contain at least one uppercase, one lowercase, AND one digit. If any
# of the three is missing, Kestra silently *disables* basic-auth — all
# /api/v1/* calls return 401, /api/v1/configs shows
# `basicAuthEnabled: null`, and `/api/v1/basicAuthValidationErrors`
# spits out the exact rule. With `special = false` and no character-
# class minima, `random_password` produced an alphabetic-only string
# (no digit) and broke every Kestra sync-flow registration in
# deploy.sh on that spin-up.
#
# `min_numeric/upper/lower = 1` enforces Kestra's rule on every
# regenerated password.
resource "random_password" "kestra_admin" {
  length      = 24
  special     = false
  min_numeric = 1
  min_upper   = 1
  min_lower   = 1
}

# Kestra database password
resource "random_password" "kestra_db" {
  length  = 24
  special = false
}

# n8n admin password
resource "random_password" "n8n_admin" {
  length  = 24
  special = false
}

# Metabase admin password
resource "random_password" "metabase_admin" {
  length  = 24
  special = false
}

# Superset admin password
resource "random_password" "superset_admin" {
  length  = 24
  special = false
}

# Superset database password
resource "random_password" "superset_db" {
  length  = 24
  special = false
}

# Superset secret key (Flask SECRET_KEY for session signing)
resource "random_password" "superset_secret_key" {
  length  = 42
  special = false
}

# CloudBeaver admin password
resource "random_password" "cloudbeaver_admin" {
  length  = 24
  special = false
}

# Meilisearch master key — gates ALL API endpoints (read + write +
# admin). Generated with longer length (32) because the master key
# is the only auth layer between requesters and the index data;
# Meilisearch derives per-tenant API keys from this root.
resource "random_password" "meilisearch_master_key" {
  length  = 32
  special = false
}

# HedgeDoc session secret — signs the session cookie. 32 chars
# (HedgeDoc docs recommend >=32 random bytes).
resource "random_password" "hedgedoc_session_secret" {
  length  = 32
  special = false
}

# HedgeDoc Postgres password — dedicated DB, not shared.
resource "random_password" "hedgedoc_db_password" {
  length  = 24
  special = false
}

# HedgeDoc admin password — single seeded account that the deploy
# pipeline creates via `node /hedgedoc/bin/manage_users --add ...
# --pass ...` post-compose-up. With CMD_ALLOW_EMAIL_REGISTER=false
# this is the ONLY way to authenticate into HedgeDoc; CF Access at
# the edge gates "who can reach the login page" but is not the
# in-app identity.
resource "random_password" "hedgedoc_admin" {
  length  = 24
  special = false
}

# Planka session/token signing key. Planka derives JWT + session
# signing material from SECRET_KEY; 64 chars for a comfortable margin.
resource "random_password" "planka_secret_key" {
  length  = 64
  special = false
}

# Planka Postgres password — dedicated DB, not shared.
resource "random_password" "planka_db_password" {
  length  = 24
  special = false
}

# Planka admin password — the single account Planka seeds on first
# boot from DEFAULT_ADMIN_*. CF Access at the edge gates who reaches
# the login page; this is the in-app identity.
resource "random_password" "planka_admin" {
  length  = 24
  special = false
}

# PostgREST JWT signing secret. HS256 verification, so the secret
# length matters — 64 chars gives well over the 256-bit recommended
# entropy. Operators mint short-lived tokens with this secret to
# elevate from the anon role to a more-privileged Postgres role.
resource "random_password" "postgrest_jwt_secret" {
  length  = 64
  special = false
}

# LiteLLM master key — Bearer token for admin ops + /ui login.
# Length 32 because it's the single auth gate to every provider
# proxied behind it (Ollama, OpenAI, Anthropic, ...).
resource "random_password" "litellm_master_key" {
  length  = 32
  special = false
}

# LiteLLM salt key — hashes derived API keys before storing in DB.
# Operator can rotate to invalidate all student-issued keys at once.
resource "random_password" "litellm_salt_key" {
  length  = 32
  special = false
}

# LiteLLM Postgres password — dedicated DB, not shared.
resource "random_password" "litellm_db_password" {
  length  = 24
  special = false
}

# Lakekeeper Postgres password — dedicated DB, not shared. The
# catalog metadata (warehouses, namespaces, table pointers) lives
# in this DB; the actual Parquet data goes to object storage.
resource "random_password" "lakekeeper_db_password" {
  length  = 24
  special = false
}

# Mage AI admin password
resource "random_password" "mage_admin" {
  length  = 24
  special = false
}

# MinIO root password
resource "random_password" "minio_root" {
  length  = 24
  special = false
}

# SFTPGo admin (web UI / REST API) and default user (SFTP login)
resource "random_password" "sftpgo_admin" {
  length  = 24
  special = false
}

resource "random_password" "sftpgo_user" {
  length  = 24
  special = false
}

# Hoppscotch secrets
resource "random_password" "hoppscotch_db" {
  length  = 24
  special = false
}

resource "random_password" "hoppscotch_jwt" {
  length  = 32
  special = false
}

resource "random_password" "hoppscotch_session" {
  length  = 32
  special = false
}

resource "random_password" "hoppscotch_encryption" {
  length  = 32
  special = false
}

# Meltano database password
resource "random_password" "meltano_db" {
  length  = 24
  special = false
}

# Soda database password
resource "random_password" "soda_db" {
  length  = 24
  special = false
}

# PostgreSQL password
resource "random_password" "postgres" {
  length  = 24
  special = false
}

# pg_ducklake password
resource "random_password" "pgducklake" {
  length  = 24
  special = false
}

# RedPanda SASL admin password (for external Kafka access)
resource "random_password" "redpanda_admin" {
  length  = 24
  special = false
}

# Prefect database password
resource "random_password" "prefect_db" {
  length  = 24
  special = false
}

# pgAdmin password
resource "random_password" "pgadmin" {
  length  = 24
  special = false
}

# RustFS root password
resource "random_password" "rustfs_root" {
  length  = 24
  special = false
}

# SeaweedFS admin password
resource "random_password" "seaweedfs_admin" {
  length  = 24
  special = false
}

# Garage admin token
resource "random_password" "garage_admin_token" {
  length  = 32
  special = false
}

# Garage RPC secret (must be 32 bytes hex-encoded = 64 hex chars)
resource "random_id" "garage_rpc_secret" {
  byte_length = 32 # Generates 64 hex characters (32 bytes in hex)
}

# LakeFS database password
resource "random_password" "lakefs_db" {
  length  = 24
  special = false
}

# LakeFS auth encryption secret
resource "random_password" "lakefs_encrypt_secret" {
  length  = 32
  special = false
}

# LakeFS admin access key (16 chars, uppercase alphanumeric like AWS)
resource "random_string" "lakefs_admin_access_key" {
  length  = 16
  special = false
  upper   = true
  lower   = false
  numeric = true
}

# LakeFS admin secret key
resource "random_password" "lakefs_admin_secret_key" {
  length  = 40
  special = false
}

# Filestash admin password
resource "random_password" "filestash_admin" {
  length  = 24
  special = false
}

# Windmill admin password
resource "random_password" "windmill_admin" {
  length  = 24
  special = false
}

# Windmill database password
resource "random_password" "windmill_db" {
  length  = 24
  special = false
}

# Windmill superadmin secret (for API automation)
resource "random_password" "windmill_superadmin_secret" {
  length  = 32
  special = false
}

# OpenMetadata admin password
# Note: OpenMetadata requires at least 1 special character (PasswordUtil.java)
# override_special restricts to chars safe in JSON strings and shell heredocs
resource "random_password" "openmetadata_admin" {
  length           = 24
  special          = true
  override_special = "!@#%^*()_+"
}

# OpenMetadata database password
resource "random_password" "openmetadata_db" {
  length  = 24
  special = false
}

# OpenMetadata Airflow password
resource "random_password" "openmetadata_airflow" {
  length  = 24
  special = false
}

# OpenMetadata Fernet key (base64-encoded 32-byte key for Airflow encryption)
resource "random_id" "openmetadata_fernet_key" {
  byte_length = 32
}

# ClickHouse admin password
resource "random_password" "clickhouse_admin" {
  length  = 24
  special = false
}

# Gitea admin password
resource "random_password" "gitea_admin" {
  length  = 24
  special = false
}

# Gitea user password (for user_email account - shared with students)
resource "random_password" "gitea_user" {
  length  = 24
  special = false
}

# Gitea database password
resource "random_password" "gitea_db" {
  length  = 24
  special = false
}

# Forgejo admin password
resource "random_password" "forgejo_admin" {
  length  = 24
  special = false
}

# Forgejo user password (for user_email account - shared with students)
resource "random_password" "forgejo_user" {
  length  = 24
  special = false
}

# Forgejo database password
resource "random_password" "forgejo_db" {
  length  = 24
  special = false
}

# Forgejo Actions runner registration secret.
#
# random_id rather than random_password because the format is not free:
# Forgejo requires exactly 40 hexadecimal characters, of which the first
# 16 are the runner's identifier and the remaining 24 the secret proper.
# 20 bytes rendered as hex is precisely that. A random_password with
# special=false would emit mixed-case alphanumerics and be rejected.
#
# Both halves of the offline registration read this one value, but not
# the same way: the server side pipes it through `forgejo-cli actions
# register --secret-stdin=1` so it never enters argv, while the runner
# side has only `create-runner-file --secret <value>` — upstream gives
# it no stdin or file form. Do not "simplify" the server side to match
# the runner; that would put the secret back in the process list. That is what
# lets a runner register with no human pasting a single-use token, and
# what lets the pairing survive a teardown/spin-up cycle unchanged.
resource "random_id" "forgejo_runner_secret" {
  byte_length = 20
}

# Wiki.js
resource "random_password" "wikijs_admin" {
  length  = 24
  special = false
}

resource "random_password" "wikijs_db" {
  length  = 24
  special = false
}

# Woodpecker CI
resource "random_password" "woodpecker_agent_secret" {
  length  = 64
  special = false
}

# NocoDB admin password
resource "random_password" "nocodb_admin" {
  length  = 24
  special = false
}

# NocoDB database password
resource "random_password" "nocodb_db" {
  length  = 24
  special = false
}

# NocoDB JWT secret
resource "random_password" "nocodb_jwt_secret" {
  length  = 32
  special = false
}

# Dify admin password
resource "random_password" "dify_admin" {
  length  = 24
  special = false
}

# Dify database password
resource "random_password" "dify_db" {
  length  = 24
  special = false
}

# Dify Redis password
resource "random_password" "dify_redis" {
  length  = 24
  special = false
}

# Dify secret key (session/encryption)
resource "random_password" "dify_secret_key" {
  length  = 42
  special = false
}

# Dify Weaviate API key
resource "random_password" "dify_weaviate_api_key" {
  length  = 32
  special = false
}

# Dify sandbox API key
resource "random_password" "dify_sandbox_api_key" {
  length  = 32
  special = false
}

# Dify plugin daemon key
resource "random_password" "dify_plugin_daemon_key" {
  length  = 48
  special = false
}

# Dify plugin inner API key
resource "random_password" "dify_plugin_inner_api_key" {
  length  = 48
  special = false
}

# Dinky admin password
resource "random_password" "dinky_admin" {
  length  = 24
  special = false
}

# Appsmith encryption keys
resource "random_password" "appsmith_encryption_password" {
  length  = 32
  special = false
}

resource "random_password" "appsmith_encryption_salt" {
  length  = 32
  special = false
}

# Note: Hetzner Object Storage bucket is created in control-plane/main.tf
# to persist through teardown. The bucket name is passed via hetzner_s3_bucket variable.

# =============================================================================
# Firewall
# =============================================================================

resource "hcloud_firewall" "main" {
  name = "${local.resource_prefix}-fw"

  # By default: No inbound rules = Zero Entry (all traffic via Cloudflare Tunnel)
  # When firewall_rules are configured, dynamic inbound rules allow external TCP access
  dynamic "rule" {
    for_each = var.firewall_rules
    content {
      direction = "in"
      protocol  = rule.value.protocol
      port      = tostring(rule.value.port)
      # source_ips is guaranteed non-empty by the firewall_rules variable's
      # validation block (see tofu/stack/variables.tf). An empty list would
      # have silently meant "allow all" under the previous fallback — now
      # the operator must say so explicitly.
      source_ips = rule.value.source_ips
    }
  }
}

# SSH Setup Firewall (temporary, attached via workflow)
resource "hcloud_firewall" "ssh_setup" {
  name = "${local.resource_prefix}-ssh-setup-fw"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # No apply_to block - attachment happens via API in spin-up workflow
  # This ensures port 22 is only open during tunnel installation
}

# =============================================================================
# Server
# =============================================================================

resource "hcloud_server" "main" {
  name         = local.resource_prefix
  server_type  = var.server_type
  location     = var.server_location
  image        = var.server_image
  ssh_keys     = [hcloud_ssh_key.main.id]
  firewall_ids = [hcloud_firewall.main.id]

  # IPv6-only mode: Disable public IPv4 to reduce costs
  # Note: Cloudflare Tunnel works over IPv6, so no public IPv4 is needed
  public_net {
    ipv4_enabled = !var.ipv6_only
    ipv6_enabled = true
  }

  labels = {
    environment = "production"
    managed_by  = "opentofu"
  }

  # cloud-init runs on EVERY first boot of an instance — including a
  # server created from a disk snapshot, because Hetzner assigns a new
  # instance-id and cloud-init re-runs its PER_INSTANCE modules. The
  # heavy provisioning below must therefore be guarded, or a
  # snapshot-restored server would redo `apt-get upgrade` and the
  # Docker install it already carries on disk.
  #
  # Two markers, deliberately on different filesystems:
  #
  #   /opt/docker-server/.image-provisioned  (disk, survives into a
  #       snapshot)  — "this disk has been through the heavy path".
  #   /run/nexus-setup-complete  (tmpfs, CANNOT survive into a
  #       snapshot) — "this boot is ready".
  #
  # The tmpfs marker is what makes the readiness gate correct on a
  # restored server. The old disk marker .setup-complete is still
  # written on the heavy path so the existing spin-up.yml gate keeps
  # working unchanged on a fresh server, but it is useless for a
  # restore: it is already in the image, so a gate probing it would
  # pass instantly — possibly before sshd and Docker are up.
  #
  # The tmpfs marker is written by a systemd unit, NOT from this
  # script. cloud-init's scripts-user module is PER_INSTANCE, so it
  # does not run again on a plain reboot — a marker touched from here
  # would be missing for the rest of the server's life after its first
  # reboot, and a warm spin-up (server already running, the common
  # case) would then hang on the gate for six minutes and fail.
  # A unit ordered After=docker.service runs on every boot and lands
  # the marker only once Docker is actually up, which makes it a
  # stronger readiness signal than "cloud-init finished" as well.
  user_data = <<-EOT
    #!/bin/bash
    set -e

    # Non-interactive apt for everything below. `-y` only answers apt's
    # own yes/no prompts; a package whose debconf question is priority
    # medium or higher still opens an ncurses dialog and then blocks
    # FOREVER, because a cloud-init boot has no tty to answer it.
    #
    # That is not a slow boot the readiness gate can wait out — it is a
    # permanent hang, and no timeout is large enough. Observed on
    # 2026-08-24: keyboard-configuration 1.226ubuntu1.1 asked for the
    # keyboard layout, every cold spin-up stalled, and the 6-minute gate
    # failed the workflow with "cloud-init did not complete".
    #
    # This had worked for months purely because no upgraded package
    # happened to ask anything. That is luck, not a property.
    export DEBIAN_FRONTEND=noninteractive
    # needrestart has shipped enabled since 22.04 and prompts about
    # restarting services after a library upgrade. `a` applies
    # automatically.
    export NEEDRESTART_MODE=a

    if [ ! -f /opt/docker-server/.image-provisioned ]; then
      # ----- Heavy path: fresh Ubuntu image, provision from scratch -----

      # Update system.
      # --force-confold keeps the existing config file when a package
      # ships a changed one. Without it dpkg asks which to keep — the
      # same class of hang as the debconf dialog above.
      apt-get update
      apt-get upgrade -y -o Dpkg::Options::=--force-confold

      # Install Docker
      curl -fsSL https://get.docker.com | sh
      command -v docker >/dev/null 2>&1 || { echo "FATAL: Docker installation failed" >&2; exit 1; }

      # Install security tools
      apt-get install -y fail2ban unattended-upgrades jq

      # Configure automatic security updates.
      # printf rather than a heredoc: a nested heredoc terminator must
      # sit at column 0 after Terraform strips the common indentation,
      # which silently breaks the moment this block is indented.
      printf '%s\n' \
        'APT::Periodic::Update-Package-Lists "1";' \
        'APT::Periodic::Unattended-Upgrade "1";' \
        'APT::Periodic::AutocleanInterval "7";' \
        > /etc/apt/apt.conf.d/20auto-upgrades

      systemctl enable fail2ban unattended-upgrades
      systemctl start fail2ban unattended-upgrades

      # Detect architecture and install cloudflared
      ARCH=$(dpkg --print-architecture)
      if [ "$ARCH" = "arm64" ]; then
        CLOUDFLARED_ARCH="arm64"
      else
        CLOUDFLARED_ARCH="amd64"
      fi
      curl -L --output cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$${CLOUDFLARED_ARCH}.deb"
      dpkg -i cloudflared.deb
      rm cloudflared.deb
      command -v cloudflared >/dev/null 2>&1 || { echo "FATAL: cloudflared installation failed" >&2; exit 1; }

      # Create app directories
      mkdir -p /opt/docker-server/stacks

      # Create Docker network
      docker network create app-network || true

      # Boot-readiness unit. Installed once, runs on every boot —
      # including reboots and snapshot restores, neither of which
      # re-runs this script. Ordered after Docker so the marker means
      # "ready", not just "booted".
      printf '%s\n' \
        '[Unit]' \
        'Description=Nexus-Stack boot readiness marker' \
        'After=docker.service' \
        'Requires=docker.service' \
        '' \
        '[Service]' \
        'Type=oneshot' \
        'ExecStart=/bin/touch /run/nexus-setup-complete' \
        'RemainAfterExit=yes' \
        '' \
        '[Install]' \
        'WantedBy=multi-user.target' \
        > /etc/systemd/system/nexus-ready.service
      systemctl daemon-reload
      # --now because multi-user.target has usually been reached by the
      # time cloud-init gets here, so `enable` alone would not start it
      # on this first boot.
      systemctl enable --now nexus-ready.service

      # This disk is now provisioned — future boots take the light path.
      touch /opt/docker-server/.image-provisioned

      # Legacy marker, kept so the existing spin-up.yml readiness gate
      # is unchanged for fresh servers.
      touch /opt/docker-server/.setup-complete
    else
      # ----- Light path: restored from a snapshot, everything is here -----

      # The target server type may have a larger disk than the one the
      # snapshot was taken from. Hetzner only guarantees >= , so grow
      # into whatever we got. Best-effort: a wrong device name or a
      # missing growpart must not fail the boot.
      growpart /dev/sda 1 || true
      resize2fs /dev/sda1 || true

      # Docker is installed and enabled on this disk, but do not assume
      # systemd already got there.
      systemctl is-active --quiet docker || systemctl start docker

      # app-network is an external network every stack joins. It lives
      # in Docker's state on disk, so it normally survives — recreate
      # only if it somehow did not.
      docker network inspect app-network >/dev/null 2>&1 || docker network create app-network

      # nexus-ready.service is enabled on this disk and systemd will
      # already have run it during boot. Re-assert it anyway: it is
      # ordered Requires=docker.service, so if Docker happened to be
      # down earlier in this boot the unit failed and the marker never
      # appeared — and we have just started Docker above. Starting an
      # already-active RemainAfterExit oneshot is a no-op.
      systemctl start nexus-ready.service
    fi
  EOT

  # image / user_data / server_type / location are create-only.
  #
  # Without this, a snapshot-restored server is one rebuild spin-up away
  # from destruction: spin-up.yml supplies the base image through its
  # `inputs.server_image || 'ubuntu-26.04'` fallback — not a hardcode,
  # but the same effect when nothing overrides it — and select-capacity
  # rewrites server_type/location,
  # so tofu would plan a REPLACEMENT of the live server and take every
  # stack's data with it. image and user_data are ForceNew on
  # hcloud_server, which makes that a silent data-loss path rather than
  # a diff someone notices.
  #
  # This costs nothing operationally: the documented resize flow
  # (docs/admin-guides/server-resize.md) is teardown -> set SERVER_TYPE
  # -> spin-up, so the server is always created fresh with the new
  # values rather than updated in place.
  lifecycle {
    ignore_changes = [image, user_data, server_type, location]
  }
}

# =============================================================================
# Persistent Volume Attachment — REMOVED in RFC 0001 cutover.
# The hcloud_volume_attachment that lived here mounted the per-tenant
# data volume at /mnt/nexus-data/. Replaced by R2-backed snapshots
# (see tofu/control-plane/main.tf for the full rationale).
# =============================================================================

# =============================================================================
# Cloudflare Tunnel
# =============================================================================

resource "random_id" "tunnel_secret" {
  byte_length = 32
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "main" {
  account_id = var.cloudflare_account_id
  name       = local.resource_prefix
  secret     = random_id.tunnel_secret.b64_std
}

# Filter enabled services
locals {
  enabled_services = {
    for key, service in var.services :
    key => service if service.enabled
  }

  # Filter services that have a subdomain (exclude internal-only services like PostgreSQL)
  enabled_services_with_subdomain = {
    for key, service in local.enabled_services :
    key => service if can(service.subdomain) && service.subdomain != null && service.subdomain != ""
  }

  # Filter services that need Cloudflare Access protection (non-public only)
  # Public services (e.g., git-proxy) get DNS + Tunnel but NO Access Application
  # Cloudflare Access is default-deny: an Application without Allow policy blocks everything
  private_services_with_subdomain = {
    for key, service in local.enabled_services_with_subdomain :
    key => service if try(service.public, false) == false
  }
}

# Tunnel configuration - dynamic based on services
resource "cloudflare_zero_trust_tunnel_cloudflared_config" "main" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.main.id

  config {
    # SSH access
    ingress_rule {
      hostname = "ssh.${var.domain}"
      service  = "ssh://localhost:22"
    }

    # Dynamic service ingress rules
    dynamic "ingress_rule" {
      for_each = local.enabled_services_with_subdomain
      content {
        hostname = "${ingress_rule.value.subdomain}.${var.domain}"
        service  = "http://localhost:${ingress_rule.value.port}"
      }
    }

    # Catch-all rule (required)
    ingress_rule {
      service = "http_status:404"
    }
  }
}

# =============================================================================
# DNS Records
# =============================================================================

resource "cloudflare_record" "ssh" {
  zone_id = var.cloudflare_zone_id
  name    = "ssh"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.main.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

# Dynamic DNS records for all enabled services
# Depends on tunnel config to ensure traffic can be routed before DNS points to tunnel
resource "cloudflare_record" "services" {
  for_each   = local.enabled_services_with_subdomain
  depends_on = [cloudflare_zero_trust_tunnel_cloudflared_config.main]

  zone_id = var.cloudflare_zone_id
  name    = each.value.subdomain
  content = "${cloudflare_zero_trust_tunnel_cloudflared.main.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

# =============================================================================
# DNS A Records for External TCP Access
# =============================================================================
# These records point directly to the server IP (proxied = false)
# so external clients can connect via TCP (Kafka, PostgreSQL, MinIO S3 API)

locals {
  firewall_dns_records = {
    for key, rule in var.firewall_rules :
    key => rule if rule.dns_record != ""
  }
}

resource "cloudflare_record" "firewall_tcp" {
  for_each = var.ipv6_only ? {} : local.firewall_dns_records

  zone_id = var.cloudflare_zone_id
  name    = each.value.dns_record
  content = hcloud_server.main.ipv4_address
  type    = "A"
  proxied = false
  ttl     = 300
}

# =============================================================================
# Cloudflare Access (Zero Trust)
# =============================================================================

# SSH Access Application
resource "cloudflare_zero_trust_access_application" "ssh" {
  zone_id          = var.cloudflare_zone_id
  name             = "${local.resource_prefix} SSH"
  domain           = "ssh.${var.domain}"
  type             = "ssh"
  session_duration = "1h"
}

# SSH Access Policy (Email OTP)
resource "cloudflare_zero_trust_access_policy" "ssh_email" {
  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_zero_trust_access_application.ssh.id
  name           = "Email SSH Access"
  precedence     = 1
  decision       = "allow"

  include {
    email = [var.admin_email]
  }
}

resource "cloudflare_zero_trust_access_short_lived_certificate" "ssh" {
  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_zero_trust_access_application.ssh.id
}

# SSH Service Token for headless/CI authentication (no browser required)
resource "cloudflare_zero_trust_access_service_token" "ssh" {
  account_id = var.cloudflare_account_id
  name       = "${local.resource_prefix}-ssh-token"
  duration   = "forever"
}

# Allow Service Token to access SSH
resource "cloudflare_zero_trust_access_policy" "ssh_service_token" {
  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_zero_trust_access_application.ssh.id
  name           = "Service Token SSH Access"
  precedence     = 2
  decision       = "non_identity"

  include {
    service_token = [cloudflare_zero_trust_access_service_token.ssh.id]
  }
}

# Infisical Service Token for Control Plane API (server-to-server, no browser required)
# Only created when Infisical is in the enabled private services
resource "cloudflare_zero_trust_access_service_token" "infisical" {
  count      = contains(keys(local.private_services_with_subdomain), "infisical") ? 1 : 0
  account_id = var.cloudflare_account_id
  name       = "${local.resource_prefix}-infisical-token"
  duration   = "forever"
}

# Allow Service Token to access Infisical
resource "cloudflare_zero_trust_access_policy" "infisical_service_token" {
  count          = contains(keys(local.private_services_with_subdomain), "infisical") ? 1 : 0
  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_zero_trust_access_application.services["infisical"].id
  name           = "Service Token Infisical Access"
  precedence     = 2
  decision       = "non_identity"

  include {
    service_token = [cloudflare_zero_trust_access_service_token.infisical[0].id]
  }
}

# Dynamic Access Applications for private services only
# Public services (e.g., git-proxy) are excluded - they handle auth at the application level
resource "cloudflare_zero_trust_access_application" "services" {
  for_each = local.private_services_with_subdomain

  zone_id = var.cloudflare_zone_id
  name    = "${local.resource_prefix} ${title(each.key)}"
  domain  = "${each.value.subdomain}.${var.domain}"
  type    = "self_hosted"
  # Wetty uses shorter session duration (1h) for enhanced security
  # Other services use 24h for better user experience
  session_duration  = each.key == "wetty" ? "1h" : "24h"
  skip_interstitial = true
}

# Dynamic Access Policies for private services (Email OTP)
resource "cloudflare_zero_trust_access_policy" "services_email" {
  for_each = local.private_services_with_subdomain

  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_zero_trust_access_application.services[each.key].id
  name           = "Email Access to ${title(each.key)}"
  precedence     = 1
  decision       = "allow"

  include {
    email = local.allowed_emails
  }
}
