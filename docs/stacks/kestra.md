---
title: "Kestra"
---

## Kestra

![Kestra](https://img.shields.io/badge/Kestra-6047EC?logo=kestra&logoColor=white)

**Modern workflow orchestration for data pipelines & automation**

A powerful, event-driven workflow orchestration platform for building data pipelines, ETL processes, and infrastructure automation:
- Declarative YAML workflows
- Event-driven triggers (cron, webhooks, file, message queues)
- 400+ plugins (AWS, GCP, Azure, databases, APIs)
- Real-time execution monitoring
- Built-in code editor with live preview
- Docker-in-Docker task execution

| Setting | Value |
|---------|-------|
| Default Port | `8085` (→ internal 8080) |
| Suggested Subdomain | `kestra` |
| Public Access | **Never** (always protected) |
| Website | [kestra.io](https://kestra.io) |
| Source | [GitHub](https://github.com/kestra-io/kestra) |

> ⚠️ **Kestra 2.0, and there is no way back.** The stack runs `kestra/kestra:v2.0`,
> which is also the `latest-lts` tag (identical digest — checked). Upstream is
> explicit that the upgrade is one-way: *"Several 2.0 migrations are
> irreversible: in particular, the BasicAuth password rehash prevents rollback
> to 1.x."* A database that has been through 2.0's Flyway migrations cannot be
> served by a 1.x image again.
>
> Under the default **rebuild** lifecycle this costs nothing — Kestra's Postgres
> is not in the R2 persistence set and is recreated from migrations on every
> spin-up, so a pin change is a fresh database either way. Under a **snapshot**
> lifecycle the database survives, and the first 2.0 start migrates it for good.
>
> What was checked against 2.0 before the bump, all by registering the actual
> flows against a local 2.0 instance:
>
> | | |
> |---|---|
> | Flow registration (`POST /api/v1/flows`) | works — 200 |
> | `git` plugin tasks this stack uses | all present: `SyncFlows`, `SyncNamespaceFiles`, `PushFlows` |
> | Basic auth | still works; the generated password needs no special characters |
> | Browser UI without credentials | still open (`/ui/` → 200), so the no-popup promise above still holds |
> | Seeded + system flows | all six accepted by a fresh 2.0 |
>
> **`Loop` is not a drop-in for `ForEach`.** It runs each iteration as its
> own *sub-execution*, which changes the variables and the output shape.
> Measured on 2.0 by executing flows, not merely registering them:
>
> | expression | result |
> |---|---|
> | `{{ taskrun.value }}` | FAILED — "Unable to find `value`" |
> | `{{ item.value }}`, `{{ item.index }}` | SUCCESS |
> | `{{ outputs.x[item.value].y }}` | FAILED |
> | `{{ outputs.x.y }}` | SUCCESS — the iteration already scopes it |
>
> **Registering a flow does not validate it.** All six flows returned HTTP
> 200 on `POST /api/v1/flows` while still carrying `taskrun.value`, which
> only fails when an execution reaches the expression. Anything checked
> against Kestra has to be *run*.
>
> Three things had to change first, all in this repo rather than in Kestra:
> `io.kestra.plugin.core.flow.ForEach` is removed (now `Loop`), and
> `io.kestra.core.models.triggers.types.Schedule` is removed (now
> `io.kestra.plugin.core.trigger.Schedule`). 1.0.60 accepted the old trigger
> type and 2.0 rejects it with `422 Could not resolve type id`. And the
> `substring` Pebble filter in `parallel-http-fetch-to-r2.yaml` does not
> exist — **not in 2.0 and not in 1.0.60 either**, so that flow's upload
> step could never have run on any version this stack has shipped. `slice`
> is the filter that works on both.
>
> **Not verified:** whether the `git` tasks need explicit API credentials when
> they *execute* — 2.0 requires that for tasks calling Kestra's own API. Flow
> registration does not exercise it; the first real `system.flow-sync` run does.

> ✅ **Auth:** Cloudflare Access (email OTP) gates the UI at the edge. Kestra's own Basic-Auth popup is **disabled** by default to avoid double-authentication — students authenticate once via the CF OTP and land directly in the UI. The `KESTRA_ADMIN_USER` / `KESTRA_ADMIN_PASSWORD` env vars are still rendered for forward-compat (Kestra EE / OIDC), but unused while basic-auth is off.

### Architecture

The stack includes:
- **Kestra** - Main workflow engine with web UI
- **PostgreSQL** - Database for workflow state and metadata

### Authentication & RBAC

| Layer | What it does |
|---|---|
| **Cloudflare Access** (edge) | Email OTP. No unauthenticated request ever reaches the container. Audit log of who authenticated lives in the CF dashboard. |
| **Kestra Basic-Auth** | **Disabled** by default — see `stacks/kestra/docker-compose.yml` for the rationale comment. Re-enable only if you want the single shared `KESTRA_ADMIN_USER` name to appear in Kestra's audit log (instead of `anon/system`), or once you've moved to Kestra Enterprise with SSO/OIDC. Basic-Auth in OSS Kestra is a single shared admin — **it does NOT give per-user attribution**; every student would log in as the same admin. Real per-user attribution requires EE + SSO. |
| **Kestra namespaces** | Flow-level access boundaries (`my-flows.*`, `nexus-tutorials.*`). Independent of who's logged in — used for organizing flows, not gating them. |

## PostgreSQL 18

Kestra's database runs `postgres:18-alpine`, matching what upstream ships in its own compose file.

Under the default `rebuild` lifecycle this needs no action: the database is not in the S3 persistence set, so it is recreated from Kestra's own migrations on every spin-up.

⚠️ **Under the `snapshot` lifecycle an existing data directory carries
over physically — and the container will refuse to start, deliberately.**

PostgreSQL 18's entrypoint scans for a cluster left in a pre-18 location and
exits rather than ignoring it:

```text
Error: in 18+, these Docker images are configured to store database data in a
       format which is compatible with "pg_ctlcluster" …
       Counter to that, there appears to be PostgreSQL data in:
         /var/lib/postgresql
```

That check runs only when `PGDATA` is left at its default, which is why this
stack mounts at `/var/lib/postgresql` and sets no `PGDATA` — the layout
docker-library/postgres recommends for 18+. Pointing `PGDATA` at a
subdirectory of the old mount would also keep the data in the volume, but it
silences the scan: the server would never look at the old cluster and would
start an empty one instead. Loud beats quiet.

The way out is a `pg_dump` from a container on the old major and a restore
into the new one; [postgres.md](./postgres.md#version) has the detail.
