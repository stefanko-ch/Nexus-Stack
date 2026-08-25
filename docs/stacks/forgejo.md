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

> ✅ **Auto-configured:** The admin account is created during deployment. A second, non-admin account is created as well *when a user identity is configured* — without one the stack has an admin login and nothing else. Their passwords, together with the database password, are stored in Infisical under the `forgejo` tag. The Actions runner registers itself; its registration secret is deliberately **not** in Infisical — everything there is copied into Kestra's environment, so it is passed straight from the OpenTofu output to the two registration steps instead. An operator who needs it can read `tofu output`.

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

- **Server side** — `forgejo forgejo-cli actions register --secret-stdin`, run
  by the `forgejo-runner-register` deploy phase.
- **Runner side** — `forgejo-runner create-runner-file`, run by the
  runner container's own entrypoint at startup.

Neither call contacts the other, so the order does not matter. If the
runner starts first it simply fails to authenticate, and the restart
policy brings it back until the server knows the secret. Both calls are
idempotent, which is what makes them safe to repeat on every spin-up.

On the **server** side the secret never appears in a process argument:
the registration script travels over SSH stdin, and the value reaches
`forgejo-cli` through `--secret-stdin` rather than a flag.

On the **runner** side it does. `forgejo-runner create-runner-file`
declares exactly four flags — `--connect`, `--instance`, `--secret`,
`--name` — with no stdin or file variant, so the value is in that
process's argv while it runs, and in the container environment that
`docker inspect` shows. (The server-side `forgejo forgejo-cli actions register`
*does* have `--secret-stdin` and `--secret-file`; the runner binary is
a different program and does not.)
Both require host-level Docker access to observe. The call is guarded
on `.runner` not already existing, so the argv window is first boot
only rather than every restart.

### Writing workflows

Put them in **`.forgejo/workflows/*.yaml`**. If that directory does not
exist, Forgejo falls back to `.github/workflows/`, so a repository
copied from GitHub will often just run — but prefer the Forgejo path
for anything written here, so it is obvious which system executes it.

> ⚠️ **One thing here is unverified, and it is this stack's wiring —
> not Forgejo.** Forgejo Actions is stable, released software; nothing
> below is a caveat about it.
>
> What has not been tested is whether a job container can reach the
> forge *in this particular topology*. Jobs run inside `forgejo-dind`,
> a separate Docker daemon from the host's, on networks that daemon
> creates. Those networks have no route to `forgejo-internal` where the
> forge lives, and dind's embedded DNS does not know the name
> `forgejo`. So `actions/checkout` against `http://forgejo:3000` — the
> address baked into the runner's registration — may not resolve.
>
> That is a consequence of choosing dind for isolation rather than
> mounting the host Docker socket, which is what this repo's Woodpecker
> agent does. The stricter choice is the reason the question exists.
> It is answerable with one real job run, and is being settled rather
> than lived with.

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
2. `forgejo-dind` sits alone with the runner on a second internal
   network, `forgejo-ci`, and publishes no port. Only `forgejo-runner`
   reaches its unauthenticated port 2375 — deliberately *not* the web
   container or the database, which live on `forgejo-internal`. An
   earlier revision put all four containers on one network, which
   would have let a compromise of the web container drive a privileged
   Docker daemon.
3. `runner-config.yml` keeps `container.docker_host: "-"` and
   `valid_volumes: []`, so the runner does not hand a job container a
   Docker socket and a workflow may not name host paths to bind-mount.

**A limit of point 3, stated because it was raised in review and is not
yet settled.** `forgejo-dind` listens unauthenticated on
`0.0.0.0:2375`, and job containers are created *by that same daemon*,
on networks it owns. A job may therefore be able to reach the daemon
through its bridge gateway and drive the Docker API directly,
regardless of what the runner chose not to mount. That would confine
an attacker to the rootless dind container rather than the host — but
it is a weaker boundary than "jobs cannot reach the daemon", which is
what an earlier version of this page implied.

Binding the daemon to a unix socket shared only with the runner would
close it. That is not done here because it needs a live test of the
rootless socket path and the uid 1000 / uid 1001 permission split, and
shipping an untested isolation change is worse than an accurately
described one.

**Resource ceilings.** `forgejo-dind` carries `mem_limit: 4g` and
`cpus: 2.0`, and job containers are its children, so the limit applies
to their aggregate. `runner.capacity: 2` bounds how many jobs run at
once; it does not bound what each may consume, which is why both are
needed.

Note these use `mem_limit` rather than the `deploy.resources.limits`
the rest of the repo uses. That is deliberate: `docker compose up`
ignores `deploy.resources` — it is a Swarm key honoured only under
`--compatibility`, which the deploy pipeline does not pass. On a stack
running arbitrary repository workflows an advisory limit is worse than
none, because it reads as protection.

**Disk is not bounded.** The layer cache lives in a named volume with
no quota. A workflow that pulls large images repeatedly can fill the
host disk and take the other services with it. Watch `docker system df`
and prune, or move CI to a dedicated host if the stack is shared.

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
