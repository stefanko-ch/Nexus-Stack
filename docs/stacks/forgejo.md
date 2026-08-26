---
title: "Forgejo"
---

## Forgejo

![Forgejo](https://img.shields.io/badge/Forgejo-FB923C?logo=forgejo&logoColor=white)

**Community-governed Git forge, with Actions CI available as a separate stack**

Forgejo is a hard fork of Gitea, developed under a non-profit. It provides:
- Pull requests and code review
- Issue tracking, wikis, and releases
- **Forgejo Actions** — CI whose workflow syntax will look familiar to anyone who has used GitHub Actions. The runner ships as a separate, optional stack — see [forgejo-runner.md](./forgejo-runner.md)
- Repository mirroring and migration from GitHub, GitLab, Gitea and Gogs
- HTTPS access via Cloudflare Tunnel

| Setting | Value |
|---------|-------|
| Default Port | `3202` (-> internal 3000) |
| Suggested Subdomain | `forgejo` |
| Public Access | No |
| Website | [forgejo.org](https://forgejo.org) |
| Source | [Codeberg](https://codeberg.org/forgejo/forgejo) |

> ✅ **Auto-configured:** The admin account is created during deployment. A second, non-admin account is created as well *when a user identity is configured* — without one the stack has an admin login and nothing else. Their passwords, together with the database password, are stored in Infisical under the `forgejo` tag.

### Why v15 and not v16

Forgejo v15 is the **LTS** line, supported through July 2027. v16 is a
regular release whose support window ends in October 2026. For stacks
that a class works on across a whole academic year, the LTS line is the
one that will not need a mid-term major upgrade.

### Architecture

Two containers:

| Container | Role |
|---|---|
| `forgejo` | The forge — Web UI and API |
| `forgejo-db` | Its own PostgreSQL, never the shared one |

The Actions runner is deliberately **not** here — see
[forgejo-runner.md](./forgejo-runner.md). An earlier revision bundled
all four together, on the reasoning that a runner without a forge is
useless and splitting them would give the Control Plane two switches to
flip in step. That held while both were opt-in. Once the forge became a
core service the coupling disappeared: there is one optional thing
left, and it is the one carrying a privileged container.

### Actions CI

Forgejo Actions is available but its runner lives in a separate,
optional stack — see [forgejo-runner.md](./forgejo-runner.md). The
split exists because the runner carries a privileged
docker-in-docker container: the forge is core and runs everywhere,
while the container that executes untrusted workflow code should only
exist where somebody actually uses it.

### Shared Workspace Repo

During deployment, a shared workspace repo named `nexus-<domain-with-dashes>-workspace` (for `example.com`: `nexus-example-com-workspace`) is automatically created. This repo is auto-cloned into the following services:

| Service | Clone Location | Method |
|---------|---------------|--------|
| Jupyter | `/home/jovyan/work/<repo>` | Entrypoint + jupyterlab-git |
| Marimo | `/app/notebooks/<repo>` | Entrypoint clone |
| code-server | `/home/coder/<repo>` | Entrypoint clone (opens as workspace) |
| Meltano | `/project/<repo>` | Entrypoint clone |
| Prefect | `/flows/<repo>` (worker) | Entrypoint clone |
| Kestra | Git sync flow | `plugin-git` SyncNamespaceFiles — once per spin-up, or on demand from the UI |

### GitHub Repository Mirroring (Optional)

You can automatically mirror one or more private GitHub repositories into Forgejo.
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
- During each spin-up, the orchestrator's mirror-setup phase creates a pull mirror in Forgejo for each configured URL
- The mirrored repo is named `mirror-<repo>` (e.g. GitHub `course-2025` → Forgejo `mirror-course-2025`)
- Forgejo syncs from GitHub **every 10 minutes** (delta fetch — only new commits are transferred)
- Mirrored repos are **private** in Forgejo (accessible only via Cloudflare Access)
- The student user (derived from `TF_VAR_user_email`) is automatically added as a **read-only** collaborator
- The operation is **idempotent**: re-running spin-up skips mirrors that already exist

**GitHub rate limits:** 10-minute intervals = 6 git fetches/hour per repo. These are Git-protocol fetches, not REST calls, so the 5,000/hour PAT limit does not apply to them — GitHub rate-limits Git traffic separately and does not publish a fixed figure. Six per hour per repo is far below any threshold that has been observed to bite.

**Triggering an immediate sync:** Log into Forgejo as admin → open the mirrored repo → Settings → Repository → Mirror Settings → **Synchronize Now**. This is a built-in Forgejo feature, no additional setup required.

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
> `Contents: Read-only` is the only permission required — Forgejo uses it solely for
> HTTPS git fetch operations, which only need read access to repository contents.

### Persistent Storage

| Path | Contents | Owner |
|---|---|---|
| `/mnt/nexus-data/forgejo/repos` | Git repositories | `1000:1000` |
| `/mnt/nexus-data/forgejo/lfs` | Git LFS objects | `1000:1000` |
| `/mnt/nexus-data/forgejo/db` | PostgreSQL data | `70:70` |

**These survive both lifecycles.** A disk snapshot captures them
wholesale; a rebuild teardown copies the repositories and LFS objects
to R2 and takes a `pg_dump` of the database before destroying the
server.

That coverage was added when Forgejo became core. While the stack was
opt-in an operator enabling it accepted the risk, but once it is on
every server by default, a git forge that silently loses its
repositories on a scheduled teardown is not a git forge.

The runner's own directory is not here — it belongs to the
[runner stack](./forgejo-runner.md), and is deliberately *not*
persisted: its `.runner` file is regenerated from the shared secret on
every start, and the rest is a throwaway build cache.

The Docker layer cache used by jobs lives in a **named** volume
(`forgejo-dind-data`), not under `/mnt/nexus-data`. It is rebuildable,
it grows without bound, and keeping it out of the data directory keeps
it out of the persistence targets.

### Migrating repositories into Forgejo

Forgejo does **not** support migrating a whole Gitea *instance* from
Gitea 1.23 or newer — the project withdrew that guarantee in December
2024, and Nexus-Stack's Gitea stack is on 1.23.

Individual *repositories* are a different matter and are fully
supported. In the web UI choose **New Migration**, pick Gitea as the
source, and point it at `http://gitea:3000/<owner>/<repo>.git` with a
Gitea access token. Issues, pull requests, releases, labels, milestones
and the wiki come along.
