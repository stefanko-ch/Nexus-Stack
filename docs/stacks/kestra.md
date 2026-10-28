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
> Under the default **rebuild** lifecycle Kestra's Postgres is now in the R2
> persistence set (see [Persistence](#persistence)), so a spin-up restores the
> previous database and Kestra migrates it on start. Every stack has run 2.0
> since this pin, so the dumps in R2 are 2.0 databases; restoring a 1.x dump
> into 2.0 has not been tested.
>
> **Under a `snapshot` lifecycle, take a backup first.** `kestra-postgres-data`
> is a named Docker volume, so the disk image preserves it, and the first
> `v2.0` start migrates it irreversibly — there is no supported way back to a
> 1.x image afterwards. Before the first spin-up carrying this change:
>
> ```bash
> ssh nexus 'docker exec kestra-postgres pg_dump -U nexus-kestra kestra \
>   | gzip > /mnt/nexus-data/kestra-pre-2.0.sql.gz && \
>   ls -lh /mnt/nexus-data/kestra-pre-2.0.sql.gz'
> ```
>
> That dump is only useful together with a 1.x image — restoring it into 2.0
> would simply be re-migrated. Its purpose is to let you rebuild the old state
> elsewhere if something about 2.0 turns out to be unacceptable, not to enable
> an in-place rollback, which does not exist.
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
> **They did, and it broke on the first real run.** Both system flows failed
> with `Failed to export flows from Kestra for namespace <ns>` and an HTML
> body reading `302 Found … cloudflare`. `git.PushFlows` and `git.SyncFlows`
> call Kestra's own REST API, and upstream resolves that URL as
> `kestra.tasks.sdk.authentication.url` → `kestra.url` → `http://localhost:8080`.
> This stack has to set `kestra.url` for the UI's absolute links, so the
> working fallback was never reached and the tasks were handed the
> Cloudflare-Access hostname.
>
> Fixed by setting `kestra.tasks.sdk.authentication` explicitly — internal URL
> plus the basic-auth credentials 2.0 now requires for such calls. The two URLs
> are deliberately different: `kestra.url` stays public for the browser.

> ✅ **Auth:** Cloudflare Access (email OTP) gates the UI at the edge. Kestra's own Basic-Auth popup is **disabled** by default to avoid double-authentication — students authenticate once via the CF OTP and land directly in the UI. `enabled: false` turns off the **UI** prompt only — the REST API still demands authentication on 2.0. Measured on the running server: `GET /ui/` without credentials returns 200, `GET /api/v1/main/flows/...` returns 401, and 200 with them. So `KESTRA_ADMIN_USER` / `KESTRA_ADMIN_PASSWORD` are **not** spare forward-compat values: they are what `kestra.tasks.sdk.authentication` (above) hands to `git.PushFlows` / `git.SyncFlows`, and removing them breaks those tasks while leaving the UI working — a failure that looks unrelated to auth.

### Architecture

The stack includes:
- **Kestra** - Main workflow engine with web UI
- **PostgreSQL** - Database for workflow state and metadata

### Persistence

Under the `rebuild` lifecycle a teardown saves Kestra to R2 and the next
spin-up restores it:

| What | Where it lives | How it is saved |
|---|---|---|
| Flows written in the UI, executions, logs, triggers | `kestra-postgres` | `pg_dump` before the stack stops |
| Namespace files from the UI's editor, execution outputs | `/mnt/nexus-data/kestra/storage` (bind mount on `/app/storage`) | rsync of the directory, Kestra stopped |

**Which copy wins depends on the namespace.** `system.flow-sync` runs on every
spin-up, after the restore, and loads two namespaces from the workspace repo
with `delete: true`:

- `nexus-tutorials.*`, from the seeded examples;
- `my-flows.*`, which a scheduled flow pushes from the UI to the repo every
  10 minutes.

In those two namespaces the repo is canonical: a flow created or changed in the
UI less than 10 minutes before a teardown is restored from the dump and then
replaced, or deleted, by the repo's older version. Flows in **any other
namespace** are not touched by the sync, so the database dump is what brings
them back.

The database is restored after `docker compose up`, so Kestra is already
running on an empty database by then. The restore stops the `kestra`
container before replacing the database and starts it again once `pg_restore`
has finished. It cannot write into a half-restored database, and it starts on
the restored flows and triggers instead of what it cached from the empty one.
If the restore fails, the spin-up stops with Kestra left stopped.

A server that still has the old `kestra_kestra-data` named volume has it
copied into the bind mount once, while the directory is empty, with the old
container stopped first so none of its writes miss the copy. The copy goes to
a sibling directory that replaces the empty one only once it is complete, so a
copy that fails halfway is retried on the next spin-up. The volume is left in
place.

### Authentication & RBAC

| Layer | What it does |
|---|---|
| **Cloudflare Access** (edge) | Email OTP. No unauthenticated request ever reaches the container. Audit log of who authenticated lives in the CF dashboard. |
| **Kestra Basic-Auth** | **Disabled** by default — see `stacks/kestra/docker-compose.yml` for the rationale comment. Re-enable only if you want the single shared `KESTRA_ADMIN_USER` name to appear in Kestra's audit log (instead of `anon/system`), or once you've moved to Kestra Enterprise with SSO/OIDC. Basic-Auth in OSS Kestra is a single shared admin — **it does NOT give per-user attribution**; every student would log in as the same admin. Real per-user attribution requires EE + SSO. |
| **Kestra namespaces** | Flow-level access boundaries (`my-flows.*`, `nexus-tutorials.*`). Independent of who's logged in — used for organizing flows, not gating them. |

## PostgreSQL 18

Kestra's database runs `postgres:18-alpine`, matching what upstream ships in its own compose file.

Under the default `rebuild` lifecycle this needs no action: the database travels through R2 as a `pg_dump`, which is independent of the PostgreSQL major version, and is restored into a fresh 18 cluster on every spin-up.

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
