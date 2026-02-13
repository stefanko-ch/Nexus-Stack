## Filestash

![Filestash](https://img.shields.io/badge/Filestash-2B3A67?logo=files&logoColor=white)

**Web-based file manager with S3/FTP/SFTP/WebDAV backend support**

Filestash is a modern file manager that makes data accessible from anywhere via a web browser. Features include:
- S3, FTP, SFTP, WebDAV, and many more backend support
- Clean, responsive web interface
- Image and document previews
- File sharing with links
- Full-text search across files
- Collaborative features

| Setting | Value |
|---------|-------|
| Default Port | `8334` |
| Suggested Subdomain | `filestash` |
| Public Access | No (file access) |
| Website | [filestash.app](https://www.filestash.app) |
| Source | [GitHub](https://github.com/mickael-kerjean/filestash) |

### Auto-configured S3 Backend

When Hetzner Object Storage credentials are configured (via GitHub Secrets), Filestash is automatically pre-configured with an S3 connection:

| Setting | Value |
|---------|-------|
| Connection Name | Hetzner Storage |
| Bucket | `nexus-<resource-prefix>` (shared bucket) |
| Endpoint | Hetzner Object Storage |

### Usage

1. Access Filestash at `https://filestash.<domain>`
2. Login to admin console at `/admin` with credentials from Infisical (`FILESTASH_ADMIN_PASSWORD`)
3. S3 backend is pre-configured (if Hetzner credentials exist)
4. Start browsing and uploading files

> ✅ **Auto-configured:** Admin password is automatically set via bcrypt hash. S3 backend is pre-configured when Hetzner Object Storage credentials are available. Credentials are available in Infisical.

> **Note:** Only `latest` Docker image tag is available - no semantic versioning published.
