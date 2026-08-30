---
title: Nexus-Stack on Evidence
---

Welcome to Evidence. This file is `pages/index.md` in the project mounted at
`/evidence-workspace`. Edit it from the host (or via the `code-server` /
`forgejo` stacks) and the dev server reloads on save.

## Postgres source

The bundled `sources/nexus_postgres/` connects to the in-stack Postgres. Host,
port, database and user are written literally in its `connection.yaml`; only
the password comes from the environment, as
`EVIDENCE_SOURCE__nexus_postgres__password`. The
sample query below lists the largest tables in the `public` schema.

⚠️ **If you have not loaded any data yet, this page will not render.** A
source query returning zero rows currently crashes the Evidence server —
defect 7 of [#725](https://github.com/stefanko-ch/Nexus-Stack/issues/725),
still open. Create a table with at least one row in the `public` schema
before expecting this page to work. An empty result is not a healthy
signal; it is the known failure.

```sql database_overview
select * from nexus_postgres.database_overview
```

<DataTable data={database_overview} rows=25 />

## Adding more sources

Drop a sibling directory under `project/sources/` with its own
`connection.yaml` and Evidence will pick it up on the next `npm run sources`.

Write the connection literally — `connection.yaml` is **not** interpolated,
so a `${VAR}` in it reaches the driver verbatim, as those literal
characters. For the
credential, add it to `stacks/evidence/.env` (the deploy pipeline renders
that from Infisical) and pass it as
`EVIDENCE_SOURCE__<source>__password` in the stack's `environment:` block.
Evidence merges that over the file.

For ClickHouse, Trino, DuckDB, Iceberg/Lakekeeper and other backends, see
the Evidence connector docs and add the matching `@evidence-dev/<driver>`
package to `package.json`.

## Building a static export

For a production hand-off, run the two commands below inside the
running container:

```bash
docker exec evidence npm run sources
docker exec evidence npm run build
```

The output lands in `project/build/`; copy it into any of the file-store
stacks (MinIO/Garage/SeaweedFS/RustFS) and serve it as static HTML.
