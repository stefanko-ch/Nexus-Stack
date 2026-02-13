## S3 Manager

![S3 Manager](https://img.shields.io/badge/S3_Manager-2E7D32?logo=amazons3&logoColor=white)

**Web-based S3 bucket browser and manager for Hetzner Object Storage**

S3 Manager is a lightweight web UI written in Go for managing S3-compatible object storage. It connects to Hetzner Object Storage and provides:
- List all buckets in an account
- Create and delete buckets
- List, upload, download, and delete objects

| Setting | Value |
|---------|-------|
| Default Port | `8086` |
| Suggested Subdomain | `s3manager` |
| Public Access | No (behind Cloudflare Access) |
| Website | [GitHub](https://github.com/cloudlena/s3manager) |

> ✅ **Auto-configured:** S3 credentials are automatically injected from Hetzner Object Storage variables during deployment.

### Usage

Access S3 Manager at `https://s3manager.<domain>` to:
- Browse existing buckets and their contents
- Upload and download files
- Create new buckets
- Delete objects and buckets

No application-level login is required — authentication is handled by Cloudflare Access.
