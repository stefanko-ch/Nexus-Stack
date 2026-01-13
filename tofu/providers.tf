terraform {
  required_version = ">= 1.6"

  # =============================================================================
  # Remote State Backend (Cloudflare R2)
  # =============================================================================
  # State is stored in Cloudflare R2 with automatic encryption at rest (AES-256).
  # 
  # Prerequisites:
  # 1. Create an R2 bucket named "nexus-terraform-state" in Cloudflare Dashboard
  # 2. Generate R2 API tokens (R2 > Manage R2 API Tokens)
  # 3. Set environment variables before running tofu init:
  #    export AWS_ACCESS_KEY_ID="your-r2-access-key-id"
  #    export AWS_SECRET_ACCESS_KEY="your-r2-secret-access-key"
  #
  # First-time setup: tofu init
  # Migration from local: tofu init -migrate-state
  # =============================================================================
  backend "s3" {
    bucket = "nexus-terraform-state"
    key    = "terraform.tfstate"
    region = "auto"

    # Cloudflare R2 endpoint - replace YOUR_ACCOUNT_ID with your Cloudflare account ID
    # Find it at: https://dash.cloudflare.com/ (right sidebar)
    # The actual endpoint is set via -backend-config or backend.hcl
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    use_path_style              = true

    # State locking (OpenTofu 1.10+)
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
