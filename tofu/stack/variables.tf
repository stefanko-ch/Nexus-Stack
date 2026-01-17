# =============================================================================
# IMPORTANT: Secrets are read from environment variables!
# =============================================================================
# Set these before running OpenTofu:
#   export TF_VAR_hcloud_token="xxx"
#   export TF_VAR_cloudflare_api_token="xxx"
#   export TF_VAR_cloudflare_account_id="xxx"
#
# For local development: Create a .env file and run 'source .env'
# For CI/CD: Use GitHub Actions secrets
# =============================================================================

# =============================================================================
# Hetzner Cloud
# =============================================================================

variable "hcloud_token" {
  description = "Hetzner Cloud API token (set via TF_VAR_hcloud_token)"
  type        = string
  sensitive   = true
  # No default - must be provided via environment variable
}

variable "server_name" {
  description = "Name of the server"
  type        = string
  default     = "docker-server"
}

variable "server_type" {
  description = "Hetzner server type (e.g., cax11, cax21, cpx21)"
  type        = string
  default     = "cax11"  # 2 vCPU, 4GB RAM - ARM-based, cheapest option
}

variable "server_location" {
  description = "Hetzner datacenter location"
  type        = string
  default     = "fsn1"  # Falkenstein, Germany
}

variable "server_image" {
  description = "OS image for the server"
  type        = string
  default     = "ubuntu-24.04"
}

variable "ipv6_only" {
  description = "Use IPv6 only (no public IPv4). Reduces costs but requires IPv6-capable network."
  type        = bool
  default     = false
}

variable "ssh_public_key_path" {
  description = "Path to SSH public key file"
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "ssh_private_key_path" {
  description = "Path to SSH private key file (for provisioning)"
  type        = string
  default     = "~/.ssh/id_ed25519"
}

# =============================================================================
# Cloudflare
# =============================================================================

variable "cloudflare_api_token" {
  description = "Cloudflare API token (set via TF_VAR_cloudflare_api_token)"
  type        = string
  sensitive   = true
  # No default - must be provided via environment variable
}

variable "cloudflare_account_id" {
  description = "Cloudflare Account ID (set via TF_VAR_cloudflare_account_id)"
  type        = string
  # No default - must be provided via environment variable
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
  description = "Admin email for Cloudflare Access (allowed to access services)"
  type        = string
}

variable "admin_username" {
  description = "Admin username for services like Portainer, Uptime Kuma (default: nexus)"
  type        = string
  default     = "nexus"
}

# =============================================================================
# Services
# =============================================================================

variable "services" {
  description = "Map of services to expose via Cloudflare Tunnel"
  type = map(object({
    enabled     = bool
    subdomain   = string
    port        = number
    public      = bool   # true = no auth, false = behind Cloudflare Access
    description = optional(string, "")
  }))
  default = {}
}

# =============================================================================
# Docker Hub (optional - for increased pull rate limits)
# =============================================================================

variable "dockerhub_username" {
  description = "Docker Hub username (optional, set via TF_VAR_dockerhub_username)"
  type        = string
  default     = ""
}

variable "dockerhub_token" {
  description = "Docker Hub access token (optional, set via TF_VAR_dockerhub_token)"
  type        = string
  sensitive   = true
  default     = ""
}

# =============================================================================
# Docker Image Versions
# =============================================================================

variable "image_versions" {
  description = "Map of service names to their Docker image:tag"
  type        = map(string)
  default     = {}
}

# =============================================================================
# GitHub (shared with control-plane, declared here to avoid warnings)
# =============================================================================

variable "github_owner" {
  description = "GitHub repository owner (used by control-plane module)"
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "GitHub repository name (used by control-plane module)"
  type        = string
  default     = ""
}
