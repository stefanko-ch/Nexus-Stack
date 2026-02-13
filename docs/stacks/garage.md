## Garage

![Garage](https://img.shields.io/badge/Garage-59C6A6?logo=amazons3&logoColor=white)

**Lightweight S3-compatible object storage for self-hosting**

Garage is an S3-compatible distributed object storage service designed for self-hosting. It runs on minimal hardware (even Raspberry Pi) and uses a separate web UI. Features include:
- S3-compatible API (core operations)
- Designed for unreliable networks and consumer hardware
- Extremely lightweight resource usage
- Third-party web UI via garage-webui
- Can scale from single-node to multi-node cluster

| Setting | Value |
|---------|-------|
| Default Port | `3909` (Web UI), `3900` (S3 API), `3903` (Admin API) |
| Suggested Subdomain | `garage` |
| Public Access | No (storage infrastructure) |
| Website | [garagehq.deuxfleurs.fr](https://garagehq.deuxfleurs.fr) |
| Source | [Gitea](https://git.deuxfleurs.fr/Deuxfleurs/garage) |

> ✅ **Auto-configured:** Admin token and layout are automatically configured during deployment.

### Architecture

| Container | Purpose |
|-----------|---------|
| `garage` | S3 API + Admin API + RPC |
| `garage-webui` | Third-party web UI for bucket management |

### Usage

Access Garage Web UI at `https://garage.<domain>` to:
- Create and manage buckets
- Create S3 access keys
- View cluster health

**S3 API Access:**
- **Web UI**: `https://garage.<domain>` (accessible via Cloudflare Tunnel)
- **S3 API**: Port `3900` (configurable via firewall rules for external access)
