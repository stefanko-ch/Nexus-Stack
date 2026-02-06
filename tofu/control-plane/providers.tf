# =============================================================================
# Control Plane - Terraform Configuration
# =============================================================================
# Separate state for the Control Plane (Cloudflare Pages + Worker).
# This allows the Control Plane to persist independently of the Nexus Stack.
# =============================================================================

terraform {
  required_version = ">= 1.10"

  backend "s3" {
    # bucket is set dynamically via -backend-config=backend.hcl
    # Format: {domain-with-dashes}-terraform-state (e.g., nexus-stack-ch-terraform-state)
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
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
    minio = {
      source  = "aminueza/minio"
      version = ">= 3.13.0"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# Hetzner Cloud (for persistent volumes that survive teardown)
provider "hcloud" {
  token = var.hcloud_token
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
