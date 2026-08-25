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

The runner is the only container on both `app-network` (to reach the
forge, which lives in the other stack) and `forgejo-ci` (to reach the
job daemon). That is what makes it the sole path between the two, and
it is why `forgejo-dind` is not on `app-network` with the other forty
services.

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
  reachable.

### Security — read this before enabling on a shared stack

**Anyone who can push to a repository here can execute code on your
server — and this is a core service, so it is present on every
stack.** That is not a Forgejo quirk; it is what self-hosted CI is.
For a class stack it means every student with commit rights has a code
execution primitive.

Three things bound the blast radius:

1. `forgejo-dind` sits alone with the runner on a second internal
   network, `forgejo-ci`, and publishes no port. Of the four
   containers, only `forgejo-runner` is attached to it — deliberately
   *not* the web container or the database, which live on
   `forgejo-internal`. An earlier revision put all four on one network,
   which would have let a compromise of the web container drive a
   privileged Docker daemon.

   This is a statement about the four stack containers. It says nothing
   about *job* containers, which are a separate matter — see the limit
   noted under point 3.
3. `runner-config.yml` keeps `container.docker_host: "-"` and
   `valid_volumes: []`, so the runner does not hand a job container a
   Docker socket and a workflow may not name host paths to bind-mount.

**A limit of point 3, stated because it was raised in review and is not
yet settled.** `forgejo-dind` listens unauthenticated on
`0.0.0.0:2375`, and job containers are created *by that same daemon*,
on networks it owns. A job may therefore be able to reach the daemon
through its bridge gateway and drive the Docker API directly,
regardless of what the runner chose not to mount. It is a weaker
boundary than "jobs cannot reach the daemon", which is what an earlier
version of this page implied — and since that daemon runs as root, the
consequence is correspondingly larger.

Binding the daemon to a unix socket shared only with the runner would
close it. That is not done here because it needs a live test of the
socket path and the uid split between the two containers, and shipping
an untested isolation change is worse than an accurately described
one.

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
