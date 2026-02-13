terraform {
  # OpenTofu 1.10+ required for use_lockfile state locking
  required_version = ">= 1.10"

  # =============================================================================
  # Remote State Backend (Cloudflare R2)
  # =============================================================================
  # State is stored in Cloudflare R2 with automatic encryption at rest (AES-256).
  # 
  # Prerequisites (handled automatically by init-r2-state.sh):
  # 1. R2 bucket is created by init-r2-state.sh (name based on domain)
  # 2. R2 API credentials are generated and stored in tofu/.r2-credentials
  # 3. Backend config (bucket + endpoint) is generated in tofu/backend.hcl
  #
  # First-time setup: scripts/init-r2-state.sh
  # =============================================================================
  backend "s3" {
    # bucket is set dynamically via -backend-config=backend.hcl
    # Format: {domain-with-dashes}-terraform-state (e.g., nexus-stack-ch-terraform-state)
    key    = "nexus-stack.tfstate"  # Main stack state (separate from control-plane.tfstate)
    region = "auto"

    # Cloudflare R2 S3-compatible settings
    # The actual endpoint and bucket are set via -backend-config=backend.hcl
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
    minio = {
      source  = "aminueza/minio"
      version = ">= 3.13.0"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# Hetzner Object Storage (S3-compatible, used for LakeFS bucket)
# Only functional when hetzner_object_storage_access_key is provided
provider "minio" {
  minio_server   = var.hetzner_object_storage_server
  minio_user     = var.hetzner_object_storage_access_key
  minio_password = var.hetzner_object_storage_secret_key
  minio_region   = var.hetzner_object_storage_region
  minio_ssl      = true
}
