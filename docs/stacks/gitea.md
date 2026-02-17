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

### GitHub Repository Mirroring (Optional)

You can automatically mirror one or more private GitHub repositories into Gitea.
This is useful for distributing course material or read-only code to students.

**Setup:** Add the following two secrets to your GitHub repository
(Settings → Secrets and variables → Actions → Secrets):

| Secret | Description |
|--------|-------------|
| `GH_MIRROR_TOKEN` | GitHub Fine-grained Personal Access Token with `Contents: Read-only` permission |
| `GH_MIRROR_REPOS` | Comma-separated list of GitHub HTTPS repo URLs to mirror |

**Example value for `GH_MIRROR_REPOS`:**
```
https://github.com/my-org/course-2025.git,https://github.com/my-org/examples.git
```

> ⚠️ If either secret is not set, the mirroring step is skipped entirely.

**How it works:**
- During each spin-up, deploy.sh creates a pull mirror in Gitea for each configured URL
- The mirrored repo is named `mirror-<repo>` (e.g. GitHub `course-2025` → Gitea `mirror-course-2025`)
- Gitea syncs from GitHub **every 10 minutes** (delta fetch — only new commits are transferred)
- Mirrored repos are **private** in Gitea (accessible only via Cloudflare Access)
- The student user (derived from `TF_VAR_user_email`) is automatically added as a **read-only** collaborator
- The operation is **idempotent**: re-running spin-up skips mirrors that already exist

**GitHub rate limits:** 10-minute intervals = 6 git fetches/hour per repo — well within the 5,000/hour PAT limit.

**Triggering an immediate sync:** Log into Gitea as admin → open the mirrored repo → Settings → Mirror sync. This is a built-in Gitea feature, no additional setup required.

#### Creating a Fine-grained PAT

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens**
2. Click "Generate new token"
3. Set **Resource owner** to the org or user that owns the repo to mirror
4. Under **Repository access** → "Only select repositories" → select the repo(s) to mirror
5. Under **Permissions** → Repository permissions → set **Contents: Read-only**
   (all other permissions can remain "No access")
6. If the org enforces SAML SSO: after creating the token, go to
   Settings → Personal access tokens → "Configure SSO" → authorize the org

> The token must belong to a GitHub account that has read access to the target repo.
> It does not need to be in the same organization as your Nexus-Stack repository.
>
> `Contents: Read-only` is the only permission required — Gitea uses it solely for
> HTTPS git fetch operations, which only need read access to repository contents.

### Persistent Storage

Gitea stores repository data and its database on a **persistent Hetzner Cloud Volume** that survives teardown:
- Git repositories: `/mnt/nexus-data/gitea/repos`
- LFS objects: `/mnt/nexus-data/gitea/lfs`
- PostgreSQL data: `/mnt/nexus-data/gitea/db`

The volume size is configurable via `persistent_volume_size` (default: 10 GB, minimum: 10 GB).

On **teardown**: Volume and all data are preserved.
On **spin-up**: Existing data is automatically reattached. Gitea resumes with all repositories and metadata intact.
On **destroy-all**: Volume is permanently deleted.
