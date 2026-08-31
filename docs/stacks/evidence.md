---
title: "Evidence"
---

## Evidence

![Evidence](https://img.shields.io/badge/Evidence-7B61FF?logo=markdown&logoColor=white)

**SQL + markdown BI for analytics engineers**

[Evidence](https://evidence.dev) is an open-source "BI as code" framework: each page is a Markdown file with embedded SQL blocks that render to charts, tables, and inline values. Projects are plain text — version them in Git, edit them in your normal tools, and the dev server reloads on save.

This stack ships the Evidence `devenv` runtime preloaded with a sample project, plus its own PostgreSQL container (`evidence-db`) seeded with demo data so the sample page renders on a fresh stack. Extend the `sources/` directory to connect the shared **postgres** stack, ClickHouse, Trino, DuckDB, Iceberg/Lakekeeper, or any external warehouse.

| Setting | Value |
|---------|-------|
| Host Port | `3007` (container internal port is Evidence's default `3000`; 3000–3006 are already taken by Metabase/Uptime-Kuma/Wetty/Hoppscotch/Dagster/Wiki.js/big-AGI) |
| Suggested Subdomain | `evidence` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [evidence.dev](https://evidence.dev) |
| Source | [GitHub](https://github.com/evidence-dev/evidence) |
| Docker image | [`evidencedev/devenv`](https://hub.docker.com/r/evidencedev/devenv) |
| Database | `postgres:18-alpine` as `evidence-db`, on the stack-private `evidence-internal` bridge |
| Host header | Rewritten by the tunnel to `localhost:3007` — see below |
| Project root | `/opt/docker-server/stacks/evidence/project/` on the server (mounted at `/evidence-workspace` inside the container) |

### Why the tunnel rewrites the Host header

Evidence serves through vite's dev server. Since the 5.4.12 DNS-rebinding fix,
vite rejects any request whose `Host` header is not listed in
`server.allowedHosts`, answering:

```
Blocked request. This host ("evidence.YOUR_DOMAIN") is not allowed.
To allow this host, add "evidence.YOUR_DOMAIN" to `server.allowedHosts` in vite.config.js.
```

Following that advice is not possible here. Evidence regenerates
`.evidence/template/vite.config.js` on every start and exposes no hook to inject
into it, and the vite it pins (5.4.21) has no environment escape — the
`__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` variable is Vite 6 and later.

So `services.yaml` marks the service `strict_host_check: true`, and
`tofu/stack/main.tf` gives its tunnel ingress rule an `origin_request` block
setting `http_host_header` to `localhost:<port>`. Cloudflare rewrites the header
before the request reaches the origin; vite allows localhost, and the page
loads. Cloudflare Access is unaffected — it runs at the edge, before the tunnel.

This does not change Evidence's own links: canonical URLs and OG tags come from
`EVIDENCE_BASE_URL`, which is set from the public domain.

Set the same flag on any other stack whose dev server refuses foreign Host
headers. It has no effect on an `internal_only` service, which gets no ingress
rule at all, and both the tfvars generator and the unit tests reject that
combination rather than letting it sit there silently.

### Why Evidence

Most BI tools assume a GUI workflow: drag dimensions onto a canvas, save the chart as a binary artifact, hope the underlying SQL stays in sync. Evidence inverts that: SQL is the source of truth, charts are derived, the whole project diffs as plain text. That makes it a natural fit alongside the existing **code-server**, **forgejo**, and **woodpecker-ci** stacks — you edit pages like you edit any other code, push to a feature branch, and review the rendered diff before merging to main.

Compared to the other BI tools in this stack:

| Tool | Best for | Auth |
|---|---|---|
| **Metabase** | Self-service exploration by non-technical users | Built-in user management |
| **Superset** | Dashboards with rich GUI editing + drilldowns | Built-in user management |
| **Evidence** | Code-first, Git-reviewed analytics pages | Cloudflare Access at the edge |

### Usage

1. Enable **Evidence** in the Control Plane → Spin Up.
2. Open `https://evidence.YOUR_DOMAIN` → CF Access email OTP → landing page.
3. Edit the sample page at `/opt/docker-server/stacks/evidence/project/pages/index.md` on the server (the project root is bind-mounted into the container at `/evidence-workspace`, so changes apply on save).
4. Add new pages as `.md` files in `/opt/docker-server/stacks/evidence/project/pages/` — each one renders at `https://evidence.YOUR_DOMAIN/<filename>`.

### Adding data sources

Each source lives in its own directory under `project/sources/<name>/`:

```text
project/sources/
├── evidence_db/            # shipped with the stack
│   ├── connection.yaml     # connection config (literal values)
│   ├── database_overview.sql
│   └── monthly_revenue.sql
└── my_clickhouse/          # operator adds this
    ├── connection.yaml
    └── ...
```

⚠️ **A source that cannot connect stops Evidence from starting.** The image
entrypoint runs `npm run sources` before the dev server and exits non-zero if
any source fails, so the container restart-loops rather than serving a page
with one broken query. Enable the target stack before adding a source that
points at it — and note that a stack being listed in the Control Plane does not
mean it is running.

That is why the bundled source is the stack's own `evidence-db` and not the
shared **postgres** stack: `postgres` is not a core service, so it is off unless
you enable it, and enabling Evidence on its own used to crash-loop on
`getaddrinfo EAI_AGAIN postgres`.

⚠️ **`connection.yaml` does not interpolate `${VAR}`.** Evidence reads the
file as written, so a `${POSTGRES_HOST}` there reaches the driver verbatim
and the connection fails on a hostname that does not exist. This page said
otherwise until [#725](https://github.com/stefanko-ch/Nexus-Stack/issues/725);
the shipped source was written to that advice and never connected.

Secrets have their own route. Evidence reads
`EVIDENCE_SOURCE__<source>__<field>` from the environment and merges it over
`connection.yaml`, which keeps the credential out of the repository while the
rest of the connection stays readable:

1. Add the credential to Infisical under a folder of your choice.
2. Reference it from `stacks/evidence/.env` (the deploy pipeline renders this
   from Infisical on every spin-up).
3. Pass it as `EVIDENCE_SOURCE__<source>__password` in the stack's
   `environment:` block — see how `evidence_db` does it.
4. Write everything else — host, port, database, user — literally in
   `connection.yaml`.

For ClickHouse, Trino, MySQL, BigQuery, Snowflake, and others, see the [Evidence connector docs](https://docs.evidence.dev/core-concepts/data-sources/). Add the matching `@evidence-dev/<driver>` package to `stacks/evidence/project/package.json` and run `docker compose restart evidence` to pull it in.

### Building a static site

For a production hand-off, the devenv runtime can build a static HTML export:

```bash
ssh nexus 'docker exec evidence npm run sources && docker exec evidence npm run build'
```

Output lands in `/opt/docker-server/stacks/evidence/project/build/` on the server. Copy it into any of the file-store stacks (MinIO, Garage, SeaweedFS, RustFS) and serve as static HTML — or commit it to a GitHub Pages / Cloudflare Pages repo for a fully decoupled deploy.

### Secrets

| Secret | Where |
|---|---|
| `EVIDENCE_DB_PASSWORD` | Generated by OpenTofu, pushed to Infisical under the `evidence` folder, rendered into `stacks/evidence/.env` on every spin-up |
| `EVIDENCE_DB_USERNAME` | Fixed at `nexus-evidence`; published to the same folder for convenience |

`evidence-db` is only on the stack-private `evidence-internal` bridge, so this
credential is not usable from pgAdmin, Adminer, or CloudBeaver the way the
shared PostgreSQL is. Reach it with `ssh nexus 'docker exec -it evidence-db
psql -U nexus-evidence -d evidence'`.

Operator-added data sources reference whatever credentials the operator wires
into `stacks/evidence/.env` — no double-managing.
