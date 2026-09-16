---
title: "Forgejo Runner"
---

## Forgejo Runner

![Forgejo](https://img.shields.io/badge/Forgejo_Runner-FB923C?logo=forgejo&logoColor=white)

**Actions CI for the Forgejo stack — runs workflows on your own server**

| Setting | Value |
|---------|-------|
| Web UI | None — runners appear in Forgejo under Site Administration → Actions → Runners |
| Public Access | No |
| Requires | The [Forgejo](./forgejo.md) stack, which is core and always present |
| Website | [Forgejo Actions docs (v15)](https://forgejo.org/docs/v15.0/admin/actions/) |

> ⚠️ **Off by default, and that is the point.** The Forgejo forge is a
> core service and always runs. This stack is separate and optional
> because it is the half that carries a **privileged** docker-in-docker
> container. On a server where nobody writes workflows that container
> would be pure risk with no benefit, so it should not be there at all.
>
> Enabling this is a deliberate trade: CI on your own hardware, at the
> cost of a privileged container and a code-execution primitive for
> everyone who can push. The Security section below is not boilerplate.

### Architecture

| Container | Role |
|---|---|
| `forgejo-runner` | Polls Forgejo for jobs and drives the daemon below |
| `forgejo-dind` | The Docker daemon those jobs actually run in |
| `forgejo-git-proxy` | Forwards port 3000 from the CI network to the forge, so jobs can clone |

The runner drives `forgejo-dind` through a **unix socket** in a volume
that only those two containers mount. `forgejo-dind` has no TCP
listener.

`forgejo-dind` is not on `app-network` with the other stacks. It sits
on `forgejo-ci`, a bridge with the fixed subnet `10.213.0.0/24`. Job
traffic leaves the daemon through that network. Two addresses on it are
fixed because jobs are told about them:

| Address | Container | What a job uses it for |
|---|---|---|
| `10.213.0.10` | `forgejo-git-proxy` | `forgejo:3000`: clone, API, artifacts |
| `10.213.0.11` | `forgejo-runner` | the Actions cache (`ACTIONS_CACHE_URL`) |

The subnet lies outside Docker's default address pools (`172.17–31.x`,
`192.168.x`). Both the host and `forgejo-dind` allocate networks from
those pools. A job network inside `forgejo-dind` with the same range
would capture the traffic meant for these addresses.

### How a job reaches the forge

The runner is registered with `http://forgejo:3000` and passes that
address to every job. `actions/checkout` clones from it.

A job container runs on a network that `forgejo-dind` creates, where the
name `forgejo` does not exist. The first Conductor deploy failed exactly
there (#679):

```text
fatal: unable to access 'http://forgejo:3000/…/': Could not resolve host: forgejo
```

`runner-config.yml` therefore adds `--add-host=forgejo:10.213.0.10` to
every job container, and `forgejo-git-proxy` forwards that port to the
real forge over `app-network`. The registered address stays the same,
so an existing runner keeps its `.runner` file.

Verified on 2026-09-16 with a real job, on a stack first brought up
from the previous revision and then updated in place:

| Check from inside the job | Result |
|---|---|
| `getent hosts forgejo` | `10.213.0.10` |
| `actions/checkout@v5` | the repository's files are present |
| `actions/cache@v4` | `Cache saved successfully` via `http://10.213.0.11:…` |
| `GET /version` on port 2375 at the job's gateway and at `10.213.0.1`–`.5` | no connection |
| `/run/dind` | does not exist |

The in-place update needed nothing by hand. `docker compose up -d`
recreated `forgejo-ci` with the new subnet and restarted the containers.

### How the runner registers itself

Forgejo supports two pairing methods. The obvious one — copy a
token out of Site Administration → Actions → Runners —
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

Three labels are declared, all pointing at the same image. With offline
registration they are set by the **server-side** `forgejo-cli actions
register --labels`, not by the runner's config: the server matches a
workflow's `runs-on:` against the record it holds, so a record
registered without labels leaves the runner green, idle and unable to
receive a single job. `runner-config.yml` carries the same list for the
daemon, and a test asserts the two never drift.

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
  reachable. See the next section for what that mirror does not carry.

### Actions that data.forgejo.org does not mirror

data.forgejo.org mirrors many GitHub actions, not all of them. A workflow
that uses a missing one fails at that step with `repository … not found`.
That is how a Conductor tenant fork found out: its first deploy stopped at
`opentofu/setup-opentofu` (#872). Nexus-Stack's own workflows now install
OpenTofu with `.github/scripts/install-opentofu.sh` instead, which needs no
action at all.

Every `uses:` in this repository, checked against data.forgejo.org on
2026-09-16. A tag was checked with `git ls-remote`; a commit SHA by fetching
that commit, since `ls-remote` cannot see it:

| Action | On data.forgejo.org | Used by |
|---|---|---|
| `actions/checkout` (`@v5` and a pinned SHA) | yes | most workflows |
| `actions/cache` (pinned SHA) | yes | the lifecycle workflows, `initial-setup`, `changelog-parse`, `toggle-silent-mode` |
| `actions/setup-node` (`@v5` and a pinned SHA) | yes | `setup-control-plane`, `spin-up`, `changelog-parse` |
| `actions/upload-artifact@v4` | yes | `python-tests` |
| `astral-sh/setup-uv@v3` | yes | `nexus-bootstrap`, the lifecycle workflows, `python-tests` |
| `opentofu/setup-opentofu` | **no** — no longer used | — |
| `raven-actions/actionlint` | **no** | `validate-workflows` |
| `googleapis/release-please-action` | **no** | `release-please` |
| `codecov/codecov-action` | **no** | `python-tests` |
| `MishaKav/pytest-coverage-comment` | **no** | `python-tests` |

So every `uses:` in the lifecycle workflows (deploy, spin-up, teardown,
destroy) resolves on a Forgejo runner. That is a statement about action
resolution only — a full lifecycle run on Forgejo is verified by running one.
The four missing actions are used only by CI workflows, which matter only if
a fork runs its CI on Forgejo too.

For a workflow of your own, either pick an action from the list above, write
it as a plain `run:` step, or give the full URL
(`uses: https://github.com/owner/repo@ref`). Forgejo accepts a full URL;
GitHub Actions does not, so a workflow that must run on both cannot use it.
To check an action before relying on it:

```bash
git ls-remote https://data.forgejo.org/<owner>/<repo> <tag>
```

### Security — read this before enabling on a shared stack

**Once this stack is enabled, anyone who can push to a repository can
execute code on your server.** Forgejo itself is a core service and is
present on every stack, but it cannot run anything without a runner —
which is exactly why the runner is separate and opt-in. Enabling it is
the moment the code-execution path opens. That is not a Forgejo quirk;
it is what self-hosted CI is.
For a class stack it means every student with commit rights has a code
execution primitive.

What bounds the blast radius:

1. **Jobs cannot reach the Docker daemon.** `forgejo-dind` listens on a
   unix socket in a volume shared only with the runner. An earlier
   revision listened on `tcp://0.0.0.0:2375`, and a job could drive
   that daemon through its own gateway: `GET /version` returned `200`
   from inside a job. Since the daemon runs as root with
   `privileged: true`, that was a way out of the sandbox. With the
   socket, the same probe gets no connection (see the table above).
2. **`forgejo-dind` is not on `app-network`.** Jobs cannot open
   connections to the addresses of containers on `app-network`
   (measured). `forgejo-ci` carries only `forgejo-dind`, the runner and
   `forgejo-git-proxy`, which forwards one port to one destination.
3. **No socket, no host paths.** `runner-config.yml` keeps
   `container.docker_host: "-"` and `valid_volumes: []`, so the runner
   does not hand a job container a Docker socket and a workflow may not
   name host paths to bind-mount.

**What jobs can still reach: ports the host publishes on all
interfaces.** A job can connect to any port the host publishes on
`0.0.0.0`, through the `forgejo-ci` gateway (`10.213.0.1`) or the
server's public address. Measured on 2026-09-16: MLflow's `5001`
answered `200` from inside a job container. Such a request bypasses
Cloudflare Access, which sits only in front of the tunnel. Stacks that
publish on `127.0.0.1` are not reachable this way. Moving the rest to
loopback is #742. Until then, treat anything a stack publishes on
`0.0.0.0` as reachable by everyone who can push a workflow.

**Resource ceilings.** `forgejo-dind` carries `mem_limit: 4g` and
`cpus: 2.0`, and job containers are its children, so the limit applies
to their aggregate. `runner.capacity: 2` bounds how many jobs run at
once; it does not bound what each may consume, which is why both are
needed.

Note these use `mem_limit` rather than the `deploy.resources.limits`
the rest of the repo uses, and the reason is uncertainty rather than a
flat claim about either key. `deploy.resources` began as a Swarm-only
setting applied under `--compatibility`; some Compose v2 releases
honour it directly. Nexus-Stack installs Docker from an unpinned
`get.docker.com`, so the Compose version on a given server is not known
in advance — which is exactly why the ambiguous key is the wrong choice
here. `mem_limit` binds on every version. On a stack running arbitrary
repository workflows, a limit that may or may not apply is worse than
none, because it reads as protection.

**Disk is not bounded.** The layer cache lives in a named volume with
no quota. A workflow that pulls large images repeatedly can fill the
host disk and take the other services with it. Watch `docker system df`
and prune, or move CI to a dedicated host if the stack is shared.

What is *not* mitigated: `forgejo-dind` runs `privileged: true` with
dockerd as **root** inside it.

An earlier revision used the `dind-rootless` image, so that an escape
would land as an unprivileged user inside the daemon container. That
does not work on this platform, and the claim has been removed rather
than left standing. Ubuntu sets
`kernel.apparmor_restrict_unprivileged_userns=1` from 23.10 onward;
RootlessKit needs exactly that capability and dies with
`fork/exec /proc/self/exe: operation not permitted` even inside a
privileged container. The two ways to make it run — clearing the sysctl
host-wide, or shipping an AppArmor profile for a binary inside an image
— both weaken the host in order to harden one container, which is a net
loss on a box running forty other services.

This is exactly why the stack is optional and off by default: a server
that never enables CI carries no root-privileged Docker daemon at all.
If that trade is unacceptable for your deployment, leave it disabled —
there is no configuration here that gives you container-based CI
without it.

To narrow further, the registration accepts a `--scope` limiting the
runner to one owner or `owner/repo`. Nexus-Stack registers
instance-wide today because Forgejo hosts only its own repositories.
