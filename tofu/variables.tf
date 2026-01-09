# =============================================================================
# Hetzner Cloud
# =============================================================================

variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  type        = string
  sensitive   = true
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
  description = "Cloudflare API token with Zone and Tunnel permissions"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare Account ID"
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
  description = "Admin email for Cloudflare Access (allowed to access services)"
  type        = string
}

# =============================================================================
# Services
# =============================================================================

variable "services" {
  description = "Map of services to expose via Cloudflare Tunnel"
  type = map(object({
    enabled   = bool
    subdomain = string
    port      = number
    public    = bool   # true = no auth, false = behind Cloudflare Access
  }))
  default = {}
}
