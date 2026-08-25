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
