terraform {
  # OpenTofu 1.10+ required for use_lockfile state locking
  required_version = ">= 1.10"

  # =============================================================================
  # Remote State Backend (Cloudflare R2)
  # =============================================================================
  # State is stored in Cloudflare R2 with automatic encryption at rest (AES-256).
  # 
  # Prerequisites (handled automatically by 'make init'):
  # 1. R2 bucket "nexus-terraform-state" is created by init-r2-state.sh
  # 2. R2 API credentials are generated and stored in tofu/.r2-credentials
  # 3. Backend config is generated in tofu/backend.hcl
  #
  # First-time setup: make init
  # =============================================================================
  backend "s3" {
    bucket = "nexus-terraform-state"
    key    = "terraform.tfstate"
    region = "auto"

    # Cloudflare R2 S3-compatible settings
    # The actual endpoint is set via -backend-config=backend.hcl
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    use_path_style              = true

    # State locking via lockfile (requires OpenTofu 1.10+)
    use_lockfile = true
  }

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
