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

output "kv_namespace_id" {
  description = "KV Namespace ID for scheduled teardown"
  value       = cloudflare_workers_kv_namespace.scheduled_teardown.id
}
