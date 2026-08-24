---
title: "Forgejo"
---

## Forgejo

![Forgejo](https://img.shields.io/badge/Forgejo-FB923C?logo=forgejo&logoColor=white)

**Community-governed Git forge with built-in Actions CI and its own runner**

Forgejo is a hard fork of Gitea, developed under a non-profit. It provides:
- Pull requests and code review
- Issue tracking, wikis, and releases
- **Forgejo Actions** — CI whose workflow syntax will look familiar to anyone who has used GitHub Actions
- An Actions runner that ships with the stack, so pipelines execute on your own server
- Repository mirroring and migration from GitHub, GitLab, Gitea and Gogs
- HTTPS access via Cloudflare Tunnel

| Setting | Value |
|---------|-------|
| Default Port | `3202` (-> internal 3000) |
| Suggested Subdomain | `forgejo` |
| Public Access | No |
| Website | [forgejo.org](https://forgejo.org) |
| Source | [Codeberg](https://codeberg.org/forgejo/forgejo) |

> ✅ **Auto-configured:** The Actions runner registers itself during deployment. Credentials are stored in Infisical under the `forgejo` tag.

### Why v15 and not v16

Forgejo v15 is the **LTS** line, supported through July 2027. v16 is a
regular release whose support window ends in October 2026. For stacks
that a class works on across a whole academic year, the LTS line is the
one that will not need a mid-term major upgrade.

### Architecture

Four containers, one stack:

| Container | Role |
|---|---|
| `forgejo` | The forge — Web UI and API |
| `forgejo-db` | Its own PostgreSQL, never the shared one |
| `forgejo-runner` | Picks up Actions jobs and runs them |
| `forgejo-dind` | The Docker daemon those jobs run against |

The runner is part of this stack rather than a stack of its own: it is
useless without Forgejo, it shares Forgejo's registration secret, and
splitting them would give the Control Plane two switches that must
always be flipped together.

### How the runner registers itself

Forgejo supports two pairing methods. The obvious one — copy a
single-use token out of Site Administration → Actions → Runners —
cannot work here, because a stack is torn down and rebuilt on a
schedule and nobody is standing by to paste a token each time.

So Nexus-Stack uses **offline registration**. OpenTofu generates one
40-character hex secret (`random_id.forgejo_runner_secret`) and both
sides receive it independently:

- **Server side** — `forgejo-cli actions register --secret-stdin`, run
  by the `forgejo-runner-register` deploy phase.
- **Runner side** — `forgejo-runner create-runner-file`, run by the
  runner container's own entrypoint at startup.

Neither call contacts the other, so the order does not matter. If the
runner starts first it simply fails to authenticate, and the restart
policy brings it back until the server knows the secret. Both calls are
idempotent, which is what makes them safe to repeat on every spin-up.

The secret never appears in a process argument on either side: the
registration script travels over SSH stdin, and the value reaches
`forgejo-cli` through `--secret-stdin` rather than a flag.

### Writing workflows

Put them in **`.forgejo/workflows/*.yaml`**. If that directory does not
exist, Forgejo falls back to `.github/workflows/`, so a repository
copied from GitHub will often just run — but prefer the Forgejo path
for anything written here, so it is obvious which system executes it.

The runner declares three labels, all pointing at the same image:

```yaml
runs-on: docker          # the Forgejo-native name
runs-on: ubuntu-latest   # alias, so copied GitHub workflows resolve
runs-on: ubuntu-22.04    # alias
```

The image behind all three is `node:22-bookworm` — Debian with Node.
That is **not** GitHub's large `ubuntu` runner image. A workflow that
assumes Python, Go, Docker CLI or the AWS CLI is preinstalled will need
to install them first.

Other known differences from GitHub Actions:

- `permissions:` and `continue-on-error:` on a job are ignored.
- Some keys of the `github` context are missing.
- `uses:` without a full URL resolves against `DEFAULT_ACTIONS_URL`,
  which this stack pins to `https://data.forgejo.org`. So
  `uses: actions/checkout@v4` fetches from data.forgejo.org, not
  github.com — deliberately, so CI does not depend on GitHub being
  reachable.

### Security — read this before enabling on a shared stack

**Anyone who can push to a repository here can execute code on your
server.** That is not a Forgejo quirk; it is what self-hosted CI is.
For a class stack it means every student with commit rights has a code
execution primitive.

Three things bound the blast radius:

1. `forgejo-dind` runs the **rootless** Docker image, so a container
   escape lands as UID 1000 inside that container rather than as root.
2. `forgejo-dind` is not on `app-network` and publishes no port. Only
   the runner can reach it — no other stack can, and neither can the
   internet.
3. `runner-config.yml` keeps `container.docker_host: "-"` and
   `valid_volumes: []`, so a job container gets **no** Docker socket of
   its own and may not bind-mount host paths. Without this, a workflow
   could start a privileged sibling container and walk straight out.

What is *not* mitigated: `forgejo-dind` itself runs with
`privileged: true`. The rootless variant still requires it in order to
unmask seccomp and AppArmor. Rootless reduces what an escape gains; it
does not remove the privilege. If that trade is unacceptable for your
deployment, disable this stack — there is no configuration that gives
you container-based CI without it.

To narrow further, the registration accepts a `--scope` limiting the
runner to one owner or `owner/repo`. Nexus-Stack registers
instance-wide today because Forgejo hosts only its own repositories.

### Persistent Storage

| Path | Contents | Owner |
|---|---|---|
| `/mnt/nexus-data/forgejo/repos` | Git repositories | `1000:1000` |
| `/mnt/nexus-data/forgejo/lfs` | Git LFS objects | `1000:1000` |
| `/mnt/nexus-data/forgejo/db` | PostgreSQL data | `70:70` |
| `/mnt/nexus-data/forgejo/runner` | Runner credentials + Actions cache | `1001:1001` |

The runner directory is a bind mount rather than a named volume
specifically because of that `1001`: the runner drops privileges to
that UID, and a fresh named volume would come up root-owned, leaving
`create-runner-file` unable to write.

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
