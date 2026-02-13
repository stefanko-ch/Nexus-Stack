## SeaweedFS

![SeaweedFS](https://img.shields.io/badge/SeaweedFS-4CAF50?logo=amazons3&logoColor=white)

**Distributed object storage with S3-compatible API**

SeaweedFS is a lightweight distributed object storage system with S3 API compatibility. All components (master, volume, filer, S3 gateway) run in a single container. Features include:
- S3-compatible API with versioning and multipart uploads
- Master dashboard for cluster monitoring
- Very lightweight (~500MB RAM)
- Filer for POSIX-like file access

| Setting | Value |
|---------|-------|
| Ports | `8888` (Filer UI), `9333` (Master UI), `8333` (S3 API) |
| Subdomains | `seaweedfs` (Filer), `seaweedfs-manager` (Master) |
| Public Access | No (storage infrastructure) |
| Website | [seaweedfs.com](https://seaweedfs.com) |
| Source | [GitHub](https://github.com/seaweedfs/seaweedfs) |

> ✅ **Auto-configured:** S3 credentials are automatically created during deployment. Credentials are available in Infisical.

### URLs

| URL | Purpose |
|-----|---------|
| `https://seaweedfs.<domain>` | **Filer Web UI** - File browser with upload capability |
| `https://seaweedfs-manager.<domain>` | **Master UI** - Cluster statistics and monitoring |

### Usage

**Filer Web UI** (`https://seaweedfs.<domain>`):
- Upload and download files via browser
- Navigate directory structure
- Create folders and manage files

**Master UI** (`https://seaweedfs-manager.<domain>`):
- View cluster topology and volume allocation
- Monitor storage usage and health
- Read-only dashboard for statistics

**S3 API** (Port `8333`):
- Use S3-compatible tools (AWS CLI, Cyberduck, etc.)
- Credentials available in Infisical
