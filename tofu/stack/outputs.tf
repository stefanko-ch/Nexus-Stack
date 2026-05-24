# =============================================================================
# Server Outputs
# =============================================================================

output "server_ip" {
  description = "Public IP address of the server (IPv4 or IPv6 depending on config)"
  value       = var.ipv6_only ? hcloud_server.main.ipv6_address : hcloud_server.main.ipv4_address
}

output "server_id" {
  description = "Hetzner server ID (used by ssh-setup state)"
  value       = hcloud_server.main.id
}

output "tunnel_token" {
  description = "Cloudflare Tunnel token for installation on server"
  sensitive   = true
  value       = cloudflare_zero_trust_tunnel_cloudflared.main.tunnel_token
}

output "resource_prefix" {
  description = "Resource name prefix (e.g., nexus-example-com)"
  value       = local.resource_prefix
}

output "ssh_firewall_id" {
  description = "SSH setup firewall ID (for workflow attach/detach via API)"
  value       = hcloud_firewall.ssh_setup.id
}

output "ssh_command" {
  description = "SSH command via Cloudflare Tunnel (requires cloudflared locally)"
  value       = "cloudflared access ssh --hostname ssh.${var.domain}"
}

output "ssh_config" {
  description = "Add this to ~/.ssh/config for easy access"
  value       = <<-EOT
    Host nexus
      HostName ssh.${var.domain}
      User root
      ProxyCommand cloudflared access ssh --hostname %h
  EOT
}

# =============================================================================
# SSH Service Token (for headless/CI access)
# =============================================================================

output "ssh_service_token" {
  description = "Service Token for SSH access without browser login"
  sensitive   = true
  value = {
    client_id     = cloudflare_zero_trust_access_service_token.ssh.client_id
    client_secret = cloudflare_zero_trust_access_service_token.ssh.client_secret
  }
}

# =============================================================================
# Infisical Service Token (for Control Plane API access)
# =============================================================================

output "infisical_service_token" {
  description = "Service Token for Infisical API access from Control Plane (no browser login required)"
  sensitive   = true
  value = length(cloudflare_zero_trust_access_service_token.infisical) > 0 ? {
    client_id     = cloudflare_zero_trust_access_service_token.infisical[0].client_id
    client_secret = cloudflare_zero_trust_access_service_token.infisical[0].client_secret
  } : null
}

# =============================================================================
# Cloudflare Outputs
# =============================================================================

output "tunnel_id" {
  description = "Cloudflare Tunnel ID"
  value       = cloudflare_zero_trust_tunnel_cloudflared.main.id
}

output "service_urls" {
  description = "URLs for all enabled services with a subdomain"
  value = {
    for key, service in local.enabled_services_with_subdomain :
    key => "https://${service.subdomain}.${var.domain}"
  }
}

output "enabled_services" {
  description = "List of enabled service names (for deploy script)"
  value       = keys(local.enabled_services)
}

output "image_versions" {
  description = "Docker image versions for each service (extracted from services config)"
  value = merge(
    { for name, svc in var.services : name => svc.image if svc.image != "" },
    merge([for name, svc in var.services : svc.support_images if svc.support_images != null]...)
  )
}

# =============================================================================
# Firewall Outputs
# =============================================================================

output "firewall_rules" {
  description = "Enabled firewall rules for external TCP access (for deploy script)"
  value       = var.firewall_rules
}

# =============================================================================
# Secrets Outputs
# =============================================================================

output "secrets" {
  description = "Generated secrets for services (auto-pushed to Infisical)"
  sensitive   = true
  value = {
    # Admin credentials
    admin_email    = var.admin_email
    admin_username = var.admin_username

    # Infisical
    infisical_admin_password = random_password.infisical_admin.result
    infisical_encryption_key = random_password.infisical_encryption_key.result
    infisical_auth_secret    = random_password.infisical_auth_secret.result
    infisical_db_password    = random_password.infisical_db_password.result

    # Portainer
    portainer_admin_password = random_password.portainer_admin.result

    # Uptime Kuma
    kuma_admin_password = random_password.kuma_admin.result

    # Grafana
    grafana_admin_password = random_password.grafana_admin.result

    # Dagster
    dagster_db_password = random_password.dagster_db.result

    # Kestra
    kestra_admin_password = random_password.kestra_admin.result
    kestra_db_password    = random_password.kestra_db.result

    # n8n
    n8n_admin_password = random_password.n8n_admin.result

    # Metabase
    metabase_admin_password = random_password.metabase_admin.result

    # Superset
    superset_admin_password = random_password.superset_admin.result
    superset_db_password    = random_password.superset_db.result
    superset_secret_key     = random_password.superset_secret_key.result

    # CloudBeaver
    cloudbeaver_admin_password = random_password.cloudbeaver_admin.result

    # Meilisearch
    meilisearch_master_key = random_password.meilisearch_master_key.result

    # HedgeDoc
    hedgedoc_session_secret = random_password.hedgedoc_session_secret.result
    hedgedoc_db_password    = random_password.hedgedoc_db_password.result
    hedgedoc_admin_password = random_password.hedgedoc_admin.result

    # LiteLLM Proxy
    litellm_master_key  = random_password.litellm_master_key.result
    litellm_salt_key    = random_password.litellm_salt_key.result
    litellm_db_password = random_password.litellm_db_password.result

    # Lakekeeper (Iceberg REST Catalog)
    lakekeeper_db_password = random_password.lakekeeper_db_password.result

    # ClickHouse
    clickhouse_admin_password = random_password.clickhouse_admin.result

    # Mage AI
    mage_admin_password = random_password.mage_admin.result

    # MinIO
    minio_root_password = random_password.minio_root.result

    # SFTPGo
    sftpgo_admin_password = random_password.sftpgo_admin.result
    sftpgo_user_password  = random_password.sftpgo_user.result

    # Hoppscotch
    hoppscotch_db_password    = random_password.hoppscotch_db.result
    hoppscotch_jwt_secret     = random_password.hoppscotch_jwt.result
    hoppscotch_session_secret = random_password.hoppscotch_session.result
    hoppscotch_encryption_key = random_password.hoppscotch_encryption.result

    # Meltano
    meltano_db_password = random_password.meltano_db.result

    # Soda
    soda_db_password = random_password.soda_db.result

    # Prefect
    prefect_db_password = random_password.prefect_db.result

    # PostgreSQL
    postgres_password = random_password.postgres.result

    # pg_ducklake
    pgducklake_password          = random_password.pgducklake.result
    hetzner_s3_bucket_pgducklake = var.hetzner_s3_bucket_pgducklake

    # pgAdmin
    pgadmin_password = random_password.pgadmin.result

    # RedPanda SASL (for external Kafka access)
    redpanda_admin_password             = random_password.redpanda_admin.result
    redpanda_kafka_public_url           = "redpanda-kafka.${var.domain}:9092"
    redpanda_schema_registry_public_url = "http://redpanda-schema-registry.${var.domain}:18081"

    # RustFS
    rustfs_root_password = random_password.rustfs_root.result

    # SeaweedFS
    seaweedfs_admin_password = random_password.seaweedfs_admin.result

    # Garage
    garage_admin_token = random_password.garage_admin_token.result
    garage_rpc_secret  = random_id.garage_rpc_secret.hex

    # LakeFS
    lakefs_db_password      = random_password.lakefs_db.result
    lakefs_encrypt_secret   = random_password.lakefs_encrypt_secret.result
    lakefs_admin_access_key = random_string.lakefs_admin_access_key.result
    lakefs_admin_secret_key = random_password.lakefs_admin_secret_key.result

    # Filestash
    filestash_admin_password = random_password.filestash_admin.result

    # Windmill
    windmill_admin_password    = random_password.windmill_admin.result
    windmill_db_password       = random_password.windmill_db.result
    windmill_superadmin_secret = random_password.windmill_superadmin_secret.result

    # OpenMetadata
    openmetadata_admin_password   = random_password.openmetadata_admin.result
    openmetadata_db_password      = random_password.openmetadata_db.result
    openmetadata_airflow_password = random_password.openmetadata_airflow.result
    openmetadata_fernet_key       = random_id.openmetadata_fernet_key.b64_std

    # Gitea
    gitea_admin_password = random_password.gitea_admin.result
    gitea_user_password  = random_password.gitea_user.result
    gitea_db_password    = random_password.gitea_db.result

    # Wiki.js
    wikijs_admin_password = random_password.wikijs_admin.result
    wikijs_db_password    = random_password.wikijs_db.result

    # Woodpecker CI
    woodpecker_agent_secret = random_password.woodpecker_agent_secret.result

    # NocoDB
    nocodb_admin_password = random_password.nocodb_admin.result
    nocodb_db_password    = random_password.nocodb_db.result
    nocodb_jwt_secret     = random_password.nocodb_jwt_secret.result

    # Appsmith
    appsmith_encryption_password = random_password.appsmith_encryption_password.result
    appsmith_encryption_salt     = random_password.appsmith_encryption_salt.result

    # Dinky
    dinky_admin_password = random_password.dinky_admin.result

    # Dify
    dify_admin_password       = random_password.dify_admin.result
    dify_db_password          = random_password.dify_db.result
    dify_redis_password       = random_password.dify_redis.result
    dify_secret_key           = random_password.dify_secret_key.result
    dify_weaviate_api_key     = random_password.dify_weaviate_api_key.result
    dify_sandbox_api_key      = random_password.dify_sandbox_api_key.result
    dify_plugin_daemon_key    = random_password.dify_plugin_daemon_key.result
    dify_plugin_inner_api_key = random_password.dify_plugin_inner_api_key.result

    # Hetzner Object Storage (pass-through for LakeFS and Filestash)
    # Server/region/bucket come from control-plane, credentials from GitHub Secrets
    hetzner_s3_server         = var.hetzner_object_storage_server
    hetzner_s3_region         = var.hetzner_object_storage_region
    hetzner_s3_access_key     = var.hetzner_object_storage_access_key
    hetzner_s3_secret_key     = var.hetzner_object_storage_secret_key
    hetzner_s3_bucket_lakefs  = var.hetzner_s3_bucket
    hetzner_s3_bucket_general = var.hetzner_s3_bucket_general

    # External S3 (optional - for Filestash multi-backend)
    external_s3_endpoint   = var.external_s3_endpoint
    external_s3_region     = var.external_s3_region
    external_s3_access_key = var.external_s3_access_key
    external_s3_secret_key = var.external_s3_secret_key
    external_s3_bucket     = var.external_s3_bucket
    external_s3_label      = var.external_s3_label

    # Cloudflare R2 Datalake
    r2_data_endpoint   = "https://${var.cloudflare_account_id}.r2.cloudflarestorage.com"
    r2_data_access_key = var.r2_data_access_key
    r2_data_secret_key = var.r2_data_secret_key
    r2_data_bucket     = var.r2_data_bucket

    # Docker Hub (optional)
    dockerhub_username = var.dockerhub_username
    dockerhub_token    = var.dockerhub_token
  }
}

# =============================================================================
# Individual Secret Outputs (for CI/CD)
# =============================================================================

output "infisical_admin_password" {
  description = "Infisical admin password (for GitHub Secrets)"
  sensitive   = true
  value       = random_password.infisical_admin.result
}

# persistent_volume_id output — REMOVED in RFC 0001 cutover.
# Replaced by R2-backed snapshots (see tofu/control-plane/main.tf).
