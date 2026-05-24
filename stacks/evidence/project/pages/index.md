---
title: Nexus-Stack on Evidence
---

Welcome to Evidence. This file is `pages/index.md` in the project mounted at
`/evidence-workspace`. Edit it from the host (or via the `code-server` /
`gitea` stacks) and the dev server reloads on save.

## Postgres source

The bundled `sources/nexus_postgres/` reads the in-stack Postgres credentials
through the env vars that `docker-compose` populates from Infisical. The
sample query below lists the largest tables in the `public` schema — if you
have not yet loaded data, the result will be empty, which is also a healthy
signal that the connection is wired up.

```sql database_overview
select * from nexus_postgres.database_overview
```

<DataTable data={database_overview} rows=25 />

## Adding more sources

Drop a sibling directory under `project/sources/` with its own
`connection.yaml` and Evidence will pick it up on the next `npm run sources`.
Connection strings can reference environment variables via `${VAR}` syntax,
so the recommended pattern is to add the relevant credentials to the
`stacks/evidence/.env` file (which the deploy pipeline renders from
Infisical) and reference them here.

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
