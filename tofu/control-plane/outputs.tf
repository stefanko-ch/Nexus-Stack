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
