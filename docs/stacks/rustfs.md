---
title: "RustFS"
---

## RustFS

![RustFS](https://img.shields.io/badge/RustFS-B7410E?logo=rust&logoColor=white)

**Rust-based S3-compatible object storage (MinIO alternative)**

RustFS is a high-performance object storage system written in Rust, designed as a drop-in replacement for MinIO. Features include:
- Amazon S3 API compatible (~94.7% compatibility)
- Built-in web console for bucket and object management
- Multipart uploads and object versioning
- Apache 2.0 license (vs MinIO's AGPLv3)

| Setting | Value |
|---------|-------|
| Default Port | `9002` (Console), `9003` (S3 API — firewall-gated) |
| Suggested Subdomain | `rustfs` |
| Public Access | No (storage infrastructure) |
| Website | [rustfs.com](https://rustfs.com) |
| Source | [GitHub](https://github.com/rustfs/rustfs) |

> ✅ **Auto-configured:** Root credentials are automatically created during deployment. Credentials are available in Infisical.

> **Note:** RustFS is in active/alpha development. For production workloads, consider MinIO or SeaweedFS.

### Usage

Access RustFS Console at `https://rustfs.<domain>` to:
- Create buckets
- Upload/download objects
- Manage access policies

**S3 API Access:**
- **Console UI**: `https://rustfs.<domain>` (host port 9002 → container 9001, accessible via Cloudflare Tunnel)
- **S3 API** (host port 9003): closed by default. To use it from an external client, enable the `rustfs → s3-api` rule in Control Plane → Firewall (restrict to your source IP), then hit **Spin Up** to apply the change. Once the redeploy finishes, connect to `YOUR_SERVER:9003`. Cross-stack traffic on `app-network` can still reach the API as `rustfs:9000` internally without the firewall toggle.
