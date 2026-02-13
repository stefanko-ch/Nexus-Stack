## MinIO

![MinIO](https://img.shields.io/badge/MinIO-C72E49?logo=minio&logoColor=white)

**High-performance S3-compatible object storage**

MinIO is a high-performance, S3-compatible object storage system designed for large-scale data infrastructure. Features include:
- Amazon S3 API compatible
- High performance for both streaming and throughput
- Distributed mode for high availability
- Lambda-compatible event notifications
- Encryption (at rest and in transit)
- Perfect for data lakes, ML models, backups

| Setting | Value |
|---------|-------|
| Default Port | `9001` (Console), `9000` (API) |
| Suggested Subdomain | `minio` |
| Public Access | No (storage infrastructure) |
| Website | [min.io](https://min.io) |
| Source | [GitHub](https://github.com/minio/minio) |

> ✅ **Auto-configured:** Root user (admin) is automatically created during deployment. Credentials are available in Infisical.

### Usage

Access MinIO Console at `https://minio.<domain>` to:
- Create buckets
- Upload/download objects
- Manage access policies
- Configure lifecycle rules

**S3 API Access:**
- **Console UI**: `https://minio.<domain>` (accessible via Cloudflare Tunnel)
- **S3 API**: `http://localhost:9000` (cluster/localhost only - not exposed via tunnel)

For S3 API access from external applications, use the Console UI or SSH tunnel. Direct S3 API exposure via Cloudflare Tunnel is not configured by default for security reasons.
