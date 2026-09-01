---
title: Nexus-Stack on Evidence
---

Welcome to Evidence. This file is `pages/index.md` in the project mounted at
`/evidence-workspace`. Edit it from the host (or via the `code-server` /
`forgejo` stacks) and the dev server reloads on save.

## Postgres source

The bundled `sources/evidence_db/` connects to `evidence-db`, the Postgres
container this stack brings with it. Host, port, database and user are written
literally in its `connection.yaml`; only the password comes from the
environment, as `EVIDENCE_SOURCE__evidence_db__password`.

It is deliberately **not** the shared `postgres` stack. That stack is optional
and off by default, and Evidence treats an unreachable source as fatal — it
runs `npm run sources` before starting the dev server — so a stack with
Evidence enabled on its own would restart-loop instead of showing a page.

The database is seeded with a synthetic `demo_sales` table (72 rows, twelve
months across three regions and two categories) so this page renders on a fresh
stack.

⚠️ **Replace the queries before dropping the table.** `monthly_revenue.sql`
and the SQL blocks below read `demo_sales`, and a query against a missing table
fails `npm run sources` — which runs before the dev server, so Evidence would
stop starting at all rather than showing a broken chart. Retire the demo by
editing `sources/evidence_db/` and this page first, then drop the table.

```sql monthly_revenue
select * from evidence_db.monthly_revenue
```

<LineChart
    data={monthly_revenue}
    x=sale_month
    y=revenue
    series=region
    title="Monthly revenue by region"
/>

<DataTable data={monthly_revenue} rows=12 />

### What is in the schema

```sql database_overview
select * from evidence_db.database_overview
```

<DataTable data={database_overview} rows=25 />

## A query that returns nothing takes the server down

Worth knowing before you write your own, because the symptom points nowhere near
the cause. When a source query returns zero rows, Evidence writes no parquet file
but still lists it in the manifest. The page load then builds a DuckDB view over
the missing file, DuckDB throws, and nothing catches it — the node process exits
and the container restarts. You see a restart loop, not "no results".

So a query that *can* legitimately match nothing needs a guard. The bundled
`database_overview.sql` shows the cheapest one: a `UNION ALL` branch with
`WHERE NOT EXISTS` over the same source, which contributes a placeholder row
exactly when the main query contributes none.

This is [#725](https://github.com/stefanko-ch/Nexus-Stack/issues/725) defect 7,
and arguably an Evidence bug — a manifest should not list a file its writer
skipped. Until it is fixed upstream, the guard is on the query.

## Adding more sources

Drop a sibling directory under `project/sources/` with its own
`connection.yaml` and Evidence will pick it up on the next `npm run sources`.
This is also how you reach the shared `postgres` stack, the warehouse stacks,
or anything external — as an additional source alongside the bundled one.

Write the connection literally — `connection.yaml` is **not** interpolated,
so a `${VAR}` in it reaches the driver verbatim, as those literal
characters. For the
credential, add it to `stacks/evidence/.env` (the deploy pipeline renders
that from Infisical) and pass it as
`EVIDENCE_SOURCE__<source>__password` in the stack's `environment:` block.
Evidence merges that over the file.

Note that a second source has the same fatal-on-failure behaviour as the first:
if you point one at a stack that is not running, Evidence will not start. Enable
the target stack in the Control Plane before adding its source here.

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
