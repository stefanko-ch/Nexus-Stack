## Gitea

![Gitea](https://img.shields.io/badge/Gitea-609926?logo=gitea&logoColor=white)

**Self-hosted Git service with pull requests, code review, and CI/CD**

A lightweight, self-hosted Git hosting solution that provides:
- Pull requests and code review
- Issue tracking and project management
- CI/CD via Gitea Actions
- Repository mirroring from GitHub
- HTTPS access via Cloudflare Tunnel

| Setting | Value |
|---------|-------|
| Default Port | `3200` (-> internal 3000) |
| Suggested Subdomain | `gitea` |
| Public Access | No |
| Website | [gitea.com](https://about.gitea.com) |
| Source | [GitHub](https://github.com/go-gitea/gitea) |

> ✅ **Auto-configured:** Admin account is automatically created during deployment. Credentials are stored in Infisical under the `gitea` tag.

### Architecture

The stack includes:
- **Gitea** - Git service (Web UI + API)
- **Git Proxy** - Nginx reverse proxy for public Git HTTPS access (separate stack)
- **PostgreSQL** - Database for users, issues, PRs, and metadata

### Shared Workspace Repo

During deployment, a shared workspace repo named `nexus-<domain>-gitea` is automatically created. This repo is auto-cloned into the following services:

| Service | Clone Location | Method |
|---------|---------------|--------|
| Jupyter | `/home/jovyan/work/<repo>` | Entrypoint + jupyterlab-git |
| Marimo | `/app/notebooks/<repo>` | Entrypoint clone |
| code-server | `/home/coder/<repo>` | Entrypoint clone (opens as workspace) |
| Meltano | `/project/<repo>` | Entrypoint clone |
| Prefect | `/flows/<repo>` (worker) | Entrypoint clone |
| Kestra | Git sync flow | `plugin-git` SyncNamespaceFiles (every 15 min) |

### Persistent Storage

Gitea stores repository data and its database on a **persistent Hetzner Cloud Volume** that survives teardown:
- Git repositories: `/mnt/nexus-data/gitea/repos`
- LFS objects: `/mnt/nexus-data/gitea/lfs`
- PostgreSQL data: `/mnt/nexus-data/gitea/db`

The volume size is configurable via `persistent_volume_size` (default: 10 GB, minimum: 10 GB).

On **teardown**: Volume and all data are preserved.
On **spin-up**: Existing data is automatically reattached. Gitea resumes with all repositories and metadata intact.
On **destroy-all**: Volume is permanently deleted.
