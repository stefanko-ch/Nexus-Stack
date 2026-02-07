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
  description = "Admin email for Cloudflare Access (full access including SSH)"
  type        = string
}

variable "user_email" {
  description = "Regular user email for Cloudflare Access (all services except SSH). Optional."
  type        = string
  default     = ""
}

variable "server_type" {
  description = "Hetzner server type (passed to Control Plane for display)"
  type        = string
  default     = "cax31"
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

variable "allow_disable_auto_shutdown" {
  description = "Allow users to disable automatic daily teardown. When false, users can only delay teardown but cannot disable it."
  type        = bool
  default     = false
}

# =============================================================================
# Hetzner Cloud (for persistent volumes)
# =============================================================================

variable "hcloud_token" {
  description = "Hetzner Cloud API token (set via TF_VAR_hcloud_token)"
  type        = string
  sensitive   = true
}

variable "persistent_volume_size" {
  description = "Size of the persistent Hetzner Cloud Volume in GB (minimum 10)"
  type        = number
  default     = 10

  validation {
    condition     = var.persistent_volume_size >= 10
    error_message = "Volume size must be at least 10 GB (Hetzner minimum)."
  }
}

# =============================================================================
# Hetzner Object Storage (for LakeFS)
# =============================================================================
# Server and region are not secrets - stored here with sensible defaults.
# Access key and secret key are secrets - stored in GitHub Secrets.

variable "hetzner_object_storage_server" {
  description = "Hetzner Object Storage S3 endpoint (e.g., fsn1.your-objectstorage.com)"
  type        = string
  default     = "fsn1.your-objectstorage.com"
}

variable "hetzner_object_storage_region" {
  description = "Hetzner Object Storage region (e.g., fsn1, nbg1, hel1)"
  type        = string
  default     = "fsn1"
}

variable "hetzner_object_storage_access_key" {
  description = "Hetzner Object Storage access key (set via TF_VAR_hetzner_object_storage_access_key)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "hetzner_object_storage_secret_key" {
  description = "Hetzner Object Storage secret key (set via TF_VAR_hetzner_object_storage_secret_key)"
  type        = string
  default     = ""
  sensitive   = true
}
