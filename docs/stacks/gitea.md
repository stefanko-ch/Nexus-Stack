---
title: "Gitea"
---

## Gitea

> **No longer a core service.** Forgejo took over the workspace repo,
> seeding, Kestra flow sync and Woodpecker OAuth. Gitea is now an ordinary
> opt-in stack: enable it if you want a second forge, otherwise leave it
> off. See [forgejo.md](./forgejo.md) for the platform-integrated forge.

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

### Persistent Storage

Gitea stores repository data and its database on the server's **local SSD**, snapshotted to **Cloudflare R2** on teardown and restored on spin-up (RFC 0001):
- Git repositories: `/mnt/nexus-data/gitea/repos` (uid 1000:1000)
- LFS objects: `/mnt/nexus-data/gitea/lfs` (uid 1000:1000)
- PostgreSQL data: `/mnt/nexus-data/gitea/db` (uid 70:70)

On **teardown**: `python -m nexus_deploy s3-snapshot` runs BEFORE `tofu destroy`. It briefly stops every stack it snapshots — forgejo, gitea, dify, metabase, hedgedoc, planka — pg_dumps their databases, rclone-syncs the file trees to `s3://<persistence-bucket>/snapshots/<timestamp>/`, verifies every source, and only then points `snapshots/latest.txt` at the new snapshot. Any failure aborts the teardown and the server stays up. The atomicity guarantee is on `snapshots/latest.txt`: it only flips after every source verifies. A failure mid-upload may leave a partial `snapshots/<timestamp>/` tree in R2, but since `latest.txt` doesn't point at it, the next spin-up's `restore_from_s3` never sees it. The cleanup cron (RFC 0001 v1.1) sweeps orphan trees by sort-order; in the meantime they cost only R2 storage.

On **spin-up**, the pipeline splits restore into two halves around compose-up: (1) `restore_from_s3(phase="filesystem")` BEFORE compose-up pulls `snapshots/latest.txt`, downloads the referenced filesystem trees into `/mnt/nexus-data/`; (2) `ensure_data_dirs` then chowns the rsync'd trees to the container-expected UIDs (1000:1000 for gitea, 70:70 for postgres, 999:999 for redis) BEFORE compose-up so containers start with the right ownership; (3) `restore_from_s3(phase="postgres")` AFTER compose-up applies the pg_dumps via `docker exec` against the now-running gitea-db / dify-db. A first-ever spin-up against an empty bucket fresh-starts in both halves (no data restored; compose comes up with empty data dirs).

On **destroy-all**: The Hetzner server is destroyed; the R2 bucket holding snapshots is preserved (it lives outside Tofu state) so a later `initial-setup` + `spin-up` reattaches to the existing snapshot history. To wipe persistence too, run `scripts/cleanup-s3-bucket.sh` with `CONFIRM_DELETE_DATA=DESTROY` in the environment — that's the audited deletion path per RFC 0001 decision #6 (iterates the bucket via S3 API and removes every object before the bucket-delete). The Cloudflare dashboard still works as an alternative but leaves no audit trail.
