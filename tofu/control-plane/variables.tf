# =============================================================================
# Control Plane Variables
# =============================================================================
# Only the variables needed for the Control Plane infrastructure.
# =============================================================================

variable "cloudflare_api_token" {
  description = "Cloudflare API token (set via TF_VAR_cloudflare_api_token)"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare Account ID (set via TF_VAR_cloudflare_account_id)"
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for your domain"
  type        = string
}

variable "domain" {
  description = "Your domain name (e.g., example.com)"
  type        = string
}

variable "admin_email" {
  description = "Admin email for Cloudflare Access"
  type        = string
}

variable "server_name" {
  description = "Name prefix for resources"
  type        = string
  default     = "nexus"
}

variable "server_type" {
  description = "Hetzner server type (passed to Control Plane for display)"
  type        = string
  default     = "cax11"
}

variable "server_location" {
  description = "Hetzner datacenter location (passed to Control Plane for display)"
  type        = string
  default     = "fsn1"
}

variable "github_owner" {
  description = "GitHub repository owner"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "Nexus-Stack"
}
