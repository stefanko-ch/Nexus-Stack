# =============================================================================
# Control Plane - Terraform Configuration
# =============================================================================
# Separate state for the Control Plane (Cloudflare Pages + Worker).
# This allows the Control Plane to persist independently of the Nexus Stack.
# =============================================================================

terraform {
  required_version = ">= 1.10"

  backend "s3" {
    bucket = "nexus-terraform-state"
    key    = "control-plane.tfstate"  # Separate state file
    region = "auto"

    # Cloudflare R2 S3-compatible settings
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    use_path_style              = true
    use_lockfile                = true
  }

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
