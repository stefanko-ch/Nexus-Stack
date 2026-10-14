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

# The AUD tag of the Control Plane's Access application. Every JWT Access
# issues for this application carries it in the `aud` claim, and the Pages
# Functions verify against it — see
# control-plane/functions/api/_utils/access-jwt.js. setup-control-plane.yaml
# reads this output and stores it as the ACCESS_AUD Pages secret.
#
# Not sensitive: it identifies an application, it does not authorise
# anything. It is, however, the value that makes a forged token fail, so a
# wrong one locks everyone out rather than letting anyone in.
output "access_aud" {
  description = "AUD tag of the Control Plane Access application"
  value       = cloudflare_zero_trust_access_application.control_plane.aud
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

output "hetzner_s3_bucket_pgducklake" {
  description = "Hetzner Object Storage bucket name for pg_ducklake (empty if not configured)"
  value       = var.hetzner_object_storage_access_key != "" ? minio_s3_bucket.pgducklake[0].bucket : ""
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
# Persistent Volume outputs — REMOVED in RFC 0001 cutover.
# Replaced by R2-backed snapshots; see tofu/control-plane/main.tf.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# KV Namespace
# -----------------------------------------------------------------------------

output "kv_namespace_id" {
  description = "Cloudflare KV namespace ID for persistent config"
  value       = cloudflare_workers_kv_namespace.config.id
}
