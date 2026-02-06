# =============================================================================
# Control Plane Outputs
# =============================================================================

output "control_plane_url" {
  description = "Control Plane URL"
  value       = "https://control.${var.domain}"
}

output "pages_project_name" {
  description = "Cloudflare Pages project name"
  value       = cloudflare_pages_project.control_plane.name
}

output "pages_url" {
  description = "Cloudflare Pages URL (*.pages.dev)"
  value       = "${cloudflare_pages_project.control_plane.name}.pages.dev"
}

output "d1_database_id" {
  description = "D1 Database ID for control plane state"
  value       = cloudflare_d1_database.nexus.id
}

output "d1_database_name" {
  description = "D1 Database name"
  value       = cloudflare_d1_database.nexus.name
}

# -----------------------------------------------------------------------------
# Hetzner Object Storage
# -----------------------------------------------------------------------------

output "hetzner_s3_bucket" {
  description = "Hetzner Object Storage bucket name for LakeFS (empty if not configured)"
  value       = var.hetzner_object_storage_access_key != "" ? minio_s3_bucket.lakefs[0].bucket : ""
  sensitive   = true
}

output "hetzner_s3_bucket_general" {
  description = "Hetzner Object Storage bucket (general purpose, for Filestash etc.)"
  value       = var.hetzner_object_storage_access_key != "" ? minio_s3_bucket.general[0].bucket : ""
  sensitive   = true
}

output "hetzner_s3_server" {
  description = "Hetzner Object Storage server endpoint"
  value       = var.hetzner_object_storage_server
}

output "hetzner_s3_region" {
  description = "Hetzner Object Storage region"
  value       = var.hetzner_object_storage_region
}

# -----------------------------------------------------------------------------
# Persistent Volume
# -----------------------------------------------------------------------------

output "persistent_volume_id" {
  description = "Hetzner Cloud Volume ID for persistent storage"
  value       = hcloud_volume.persistent.id
}

output "persistent_volume_name" {
  description = "Hetzner Cloud Volume name"
  value       = hcloud_volume.persistent.name
}
