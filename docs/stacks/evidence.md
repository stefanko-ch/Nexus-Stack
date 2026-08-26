---
title: "Evidence"
---

## Evidence

![Evidence](https://img.shields.io/badge/Evidence-7B61FF?logo=markdown&logoColor=white)

**SQL + markdown BI for analytics engineers**

[Evidence](https://evidence.dev) is an open-source "BI as code" framework: each page is a Markdown file with embedded SQL blocks that render to charts, tables, and inline values. Projects are plain text — version them in Git, edit them in your normal tools, and the dev server reloads on save.

This stack ships the Evidence `devenv` runtime preloaded with a sample project that queries the in-stack Postgres. Extend the `sources/` directory to connect ClickHouse, Trino, DuckDB, Iceberg/Lakekeeper, or any external warehouse.

| Setting | Value |
|---------|-------|
| Host Port | `3007` (container internal port is Evidence's default `3000`; 3000–3006 are already taken by Metabase/Uptime-Kuma/Wetty/Hoppscotch/Dagster/Wiki.js/big-AGI) |
| Suggested Subdomain | `evidence` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [evidence.dev](https://evidence.dev) |
| Source | [GitHub](https://github.com/evidence-dev/evidence) |
| Docker image | [`evidencedev/devenv`](https://hub.docker.com/r/evidencedev/devenv) |
| Project root | `/opt/docker-server/stacks/evidence/project/` on the server (mounted at `/evidence-workspace` inside the container) |

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

```
project/sources/
├── nexus_postgres/         # shipped with the stack
│   ├── connection.yaml     # connection config (env-var interpolated)
│   └── database_overview.sql
└── my_clickhouse/          # operator adds this
    ├── connection.yaml
    └── ...
```

`connection.yaml` supports `${VAR}` interpolation against the container's environment, so the recommended pattern is:

1. Add the credentials to Infisical under a folder of your choice.
2. Reference them from `stacks/evidence/.env` (the deploy pipeline renders this from Infisical on every spin-up).
3. Use `${VAR}` in `connection.yaml` to reference them.

For ClickHouse, Trino, MySQL, BigQuery, Snowflake, and others, see the [Evidence connector docs](https://docs.evidence.dev/core-concepts/data-sources/). Add the matching `@evidence-dev/<driver>` package to `stacks/evidence/project/package.json` and run `docker compose restart evidence` to pull it in.

### Building a static site

For a production hand-off, the devenv runtime can build a static HTML export:

```bash
ssh nexus 'docker exec evidence npm run sources && docker exec evidence npm run build'
```

Output lands in `/opt/docker-server/stacks/evidence/project/build/` on the server. Copy it into any of the file-store stacks (MinIO, Garage, SeaweedFS, RustFS) and serve as static HTML — or commit it to a GitHub Pages / Cloudflare Pages repo for a fully decoupled deploy.

### Secrets

No Tofu-managed secrets specific to Evidence. The bundled sample project reads the in-stack Postgres credentials (`POSTGRES_PASSWORD`) which are already managed via the **postgres** stack and Infisical. Operator-added data sources reference whatever credentials the operator wires into `stacks/evidence/.env` — no double-managing.
