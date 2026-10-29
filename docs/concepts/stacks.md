---
title: "Stacks and services"
description: "What a stack is made of, how one becomes reachable, and which parts of it hold data"
order: 3
---

# Stacks and services

A **stack** is one entry in the service catalogue: Postgres, Redpanda, Kestra,
Jupyter, Metabase. Nexus Stack ships 80+ of them and you run the handful you
actually need.

Most are opt-in — you switch them on in the Control Plane and off again when you
are done. A few are marked `core` and are always on, because the deployment does
not work without them; the Control Plane will not let you disable those. A few
more are marked `proven`, which promises more than the rest (see [What each tier
promises](#what-each-tier-promises)). Which are which is in `services.yaml`, not in
this page, so that this page cannot go stale about it.

Every stack has at least these two things in this repository:

- **An entry in `services.yaml`** — the metadata: which subdomain and port it uses,
  which category it belongs to, what it is for, which image version is pinned.
- **A `stacks/<name>/docker-compose.yml`** — the containers themselves, attached to
  the shared external `app-network` so stacks can reach each other by service name.

Many need more than that, and about a third do: a `Dockerfile` where no usable
upstream image exists, seed SQL, config templates, notebooks. Those live in the same
`stacks/<name>/` directory. What there is *not* is a plugin system or a registry —
a stack is files in this repository, and adding one is adding files.

## What each tier promises

A project with 100+ stacks cannot test all of them before every release, so it
does not pretend to. Every stack is in one of three tiers, and the tier says
exactly what you can rely on:

| Tier | Which stacks | Promise |
|---|---|---|
| **core** | `core: true` in `services.yaml` | Part of the platform. Always deployed, cannot be disabled. |
| **proven** | `tier: proven` in `services.yaml` | Works on every release, across a teardown and a restore. Issues about it are handled first. |
| **best-effort** | everything else | Available and maintained, but not tested before a release and not prioritised. |

The `proven` stacks are the ones courses run on, and the set is kept small on
purpose: the promise only holds if every one of them can be tested on one server,
before every release, in reasonable time.

**What "works" means.** Starting and answering on its port is not enough. A
`proven` stack has to keep what a user made in it — a notebook, a flow, a file —
across a teardown and the following spin-up. The failures found while preparing
a course were of that kind: a stack that came up healthy and empty.

**What is enforced today, and what is not yet.** Every image a core or `proven`
stack uses is one exact release, never a line of releases such as `17-alpine` or
`v2.0`. For a stack built from its own `Dockerfile`, that covers the base image
and every Python package too. `tests/unit/test_stack_conventions.py` fails CI on
any violation, so a version only changes when someone changes it. The release
test itself, which would block a release when a `proven` stack fails, is not
automated yet ([#712](https://github.com/stefanko-ch/Nexus-Stack/issues/712)).
Until it is, the check before a release is manual.

The Control Plane marks `proven` stacks with a badge and can filter for them.
`best-effort` stacks carry no badge.

## Catalogue, state, and reality

Three things could each be called "the list of services", and confusing them
explains most surprises:

| | Where | What it means |
|---|---|---|
| **Catalogue** | `services.yaml` in this repository | Everything that *could* be deployed |
| **Desired state** | The `services` table in the Control Plane's D1 database | What you have switched on |
| **Reality** | Containers on the server, DNS records, Access applications | What is actually running |

You change the middle one in the Control Plane. A spin-up or deploy reconciles the
third with it. The catalogue only changes when the repository changes.

## What the metadata controls

The fields in a `services.yaml` entry are not documentation — OpenTofu reads them
and creates real resources from them.

- **`subdomain` and `port`** — together these produce a DNS record for
  `subdomain.yourdomain.com` and a tunnel route to `localhost:<port>` on the server.
- **`public`** — `false` (the near-universal default) means Cloudflare Access with
  email OTP sits in front of the service. `true` means it does not, and the service
  is expected to handle its own authentication. Exactly one shipped stack,
  `git-proxy`, does this.
- **`internal_only`** — the service gets no subdomain at all. Postgres, Vector,
  Debezium and friends are reachable from other containers on `app-network` and
  nowhere else.
- **`core`** — always enabled, never opt-in: `forgejo`, `grafana`, `infisical`,
  `portainer`. These are the stacks the platform itself depends on, which is also
  why Portainer is reachable when something else is broken.
- **`tcp_ports`** — declares that this service is meant to be reachable by a
  non-HTTP client (a Kafka consumer, `psql`, an S3 SDK). It does not open anything
  by itself; see below.

## How a service becomes reachable

For an ordinary web service, four things have to line up, and OpenTofu creates all
four from one `services.yaml` entry:

1. A DNS `CNAME` for `service.yourdomain.com` pointing at the Cloudflare Tunnel.
2. A tunnel route mapping that hostname to `localhost:<port>` on the server.
3. A Cloudflare Access application on that hostname, with an email OTP policy —
   unless the service is `public`.
4. The container, listening on that port.

Which is why a service that is not enabled is not merely hidden: it has no DNS
record, no route, and no application. From the outside it does not exist.

## The TCP exception

A Kafka client or `psql` cannot speak through an HTTP tunnel. For those cases the
Control Plane's Firewall page opens a real inbound port on the Hetzner firewall and
creates an unproxied DNS `A` record pointing at the server's IP.

This is the one place where the zero-open-ports property is deliberately traded
away, so it is worth knowing what you get for it: the service is now exposed to
whatever source ranges you allowed, protected only by its own authentication rather
than by Cloudflare Access. Firewall rules are reset on every teardown, which keeps
the exception from outliving the reason for it. See
[Security model](./security-model.md).

## Which stacks hold data

Some stacks are stateless — a UI over something else, a converter, a viewer.
Restarting them loses nothing. Others own real state: repositories, uploaded files,
tables, dashboards.

That distinction matters because in the default `rebuild` lifecycle **only a
hard-coded subset of stacks has its data carried across a teardown**. If you are
about to put work into a stack, check whether it is one of them before assuming it
will be there tomorrow — [Lifecycle](./lifecycle.md) explains where that list lives
and what the alternative is.

## Credentials

Stacks that need a password get one generated by OpenTofu on every spin-up and
stored in Infisical, the central secrets stack. You read it in the Control Plane or
in Infisical itself — never from the repository, which never sees service passwords.

For four stacks — Kestra, Jupyter, Marimo and code-server — the deploy goes one step
further and injects the secrets as environment variables, so a notebook or a flow
can use a database without anyone copy-pasting a password into a file. The details,
including the cases where a secret is deliberately skipped, are in the
[Setup Guide](../admin-guides/setup-guide.md).

## Adding a stack

Adding a service to the catalogue means: a `services.yaml` entry, a Compose file, a
documentation page in `docs/stacks/`, and the README table. The exact steps, in
order, are in the [stacks README](../stacks/README.md)
and in `CLAUDE.md`. Two rules are worth stating here because they are easy to get
wrong: pin the image version rather than tracking `latest`, and if the stack holds
data anybody would miss, it needs a persistence target — otherwise it is ephemeral
and nothing will tell you so.

## Related reading

- [Stack catalogue](../stacks/README.md) — every available service
- [Lifecycle](./lifecycle.md) — what happens to a stack's data on teardown
- [Security model](./security-model.md) — what sits in front of a stack
- [Control Plane](../user-guides/control-plane.md) — switching stacks on and off
