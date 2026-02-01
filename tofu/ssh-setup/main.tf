# =============================================================================
# SSH Setup Firewall (Temporary)
# =============================================================================
# This state manages a temporary firewall that opens port 22 for SSH access
# during Cloudflare Tunnel installation. It is:
#   1. Applied BEFORE tunnel installation (opens port 22)
#   2. Destroyed AFTER tunnel installation (closes port 22)
#
# This ensures port 22 is only open during the brief tunnel setup period.
# All subsequent SSH access goes through the Cloudflare Tunnel.
# =============================================================================

terraform {
  required_version = ">= 1.10"

  backend "s3" {
    key                         = "ssh-setup.tfstate"
    region                      = "auto"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    use_path_style              = true
    use_lockfile                = true
  }

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
  }
}

# =============================================================================
# Variables
# =============================================================================

variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  sensitive   = true
}

variable "server_id" {
  description = "Hetzner server ID to attach SSH firewall to"
  type        = number
}

variable "resource_prefix" {
  description = "Resource name prefix (e.g., nexus-example-com)"
  type        = string
}

# =============================================================================
# Provider
# =============================================================================

provider "hcloud" {
  token = var.hcloud_token
}

# =============================================================================
# SSH Setup Firewall
# =============================================================================

resource "hcloud_firewall" "ssh_setup" {
  name = "${var.resource_prefix}-ssh-setup-fw"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  apply_to {
    server = var.server_id
  }
}
