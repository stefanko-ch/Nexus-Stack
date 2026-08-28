---
title: "Unity Catalog"
description: "Open-source catalog for Delta and Iceberg tables, volumes and AI assets"
---

# Unity Catalog

![Unity Catalog](https://img.shields.io/badge/Unity%20Catalog-FF3621?logo=databricks&logoColor=white)

The open-source [Unity Catalog](https://www.unitycatalog.io) from
`unitycatalog/unitycatalog` — **not** the managed one inside a Databricks
workspace. A REST catalog that covers Delta *and* Iceberg tables,
unstructured volumes, functions and models under a single namespace, with
clients for Spark, Trino, DuckDB and Python.

## Configuration

| Setting | Value |
|---|---|
| Subdomain | `unity-catalog.<your-domain>` (UI) |
| Host port | `3211` → container `3000` |
| API | `http://unitycatalog:8080` — internal only, on `app-network` |
| Public | No — Cloudflare Access (email OTP) |
| Metastore | H2 file in the `unitycatalog-data` volume — no PostgreSQL needed |

### Containers

| Container | Role |
|---|---|
| `unitycatalog` | The server. REST API on 8080, Hibernate metastore, no published port. |
| `unitycatalog-ui` | React UI on 3000 — the only published port. |

## Independent of Lakekeeper

[Lakekeeper](./lakekeeper.md) is also a catalog, and the two overlap only
in part: Lakekeeper implements the Iceberg REST Catalog specification and
nothing else, while Unity Catalog also covers Delta, volumes and AI assets.

They share **no database, no volume and no internal network**, and neither
reads the other's configuration. Lakekeeper keeps its own PostgreSQL; Unity
Catalog keeps an H2 file in its own volume. Enable either alone, both, or
neither.

Both do join `app-network`, as every stack here does, so their containers
can reach each other over it — nothing in either makes use of that, and it
is what lets Spark or a notebook talk to both.

Which to pick depends on the lesson rather than on merit. If the exercise is
"query the same Iceberg table from Spark, Trino and DuckDB", Lakekeeper is
the narrower and lighter fit. If it is "one catalog over Delta tables,
files and models", Unity Catalog is the one.

## Known version skew

**The published UI image is much older than the server, and that is
upstream's situation rather than a choice made here.**

| Image | Last built |
|---|---|
| `unitycatalog/unitycatalog:v0.6.0` | 2026-08-20 |
| `unitycatalog/unitycatalog-ui` | 2025-05-23 |

Releases v0.4, v0.5, v0.5.1 and v0.6 all landed after that UI build, so
the UI may lag behind the server or fail against it. **The API is the part
to rely on**; treat the UI as a convenience and report anything odd rather
than assuming your catalog is broken.

Two consequences worth knowing:

- Upstream publishes **no versioned tag** for the UI, only a rolling
  `main`. It is therefore pinned by digest here, the same approach
  [Filestash](./filestash.md) uses.
- The UI runs `react-scripts start` — a Create-React-App **development**
  server, not a production build. That is what upstream's Dockerfile does.

The UI also has its proxy target compiled in at build time
(`ARG PROXY_HOST=server` rewrites `package.json`), so it only ever looks
for a host called `server`. The server container carries that as a network
alias; renaming it would break the UI silently.

## Credentials

There are none. `server.authorization=disable` in
`conf/server.properties`, because Unity Catalog's own authorization expects
an external OIDC provider (Google, Okta or Keycloak) that this stack does
not run. Same model as [Lakekeeper](./lakekeeper.md) and
[Marquez](./marquez.md).

**Be precise about what Cloudflare Access protects here.** It gates the
browser route to `unity-catalog.<your-domain>`. It does **not** gate the
API: that sits on `app-network` with no published port, so every other
container in the deployment can call `http://unitycatalog:8080` with no
credentials and no Access session.

That is deliberate — it is how Spark, Trino and the notebooks reach the
catalog — but it means the real boundary is the Docker network rather than
Access. Anything with a foothold inside the stack has full read and write
on this catalog, including the ability to drop a table registration.

## Using it

Create a catalog and list what is there:

```bash
# From inside the stack — Jupyter, Marimo, code-server
curl -X POST http://unitycatalog:8080/api/2.1/unity-catalog/catalogs \
  -H 'Content-Type: application/json' \
  -d '{"name": "teaching", "comment": "Course catalog"}'

curl -s http://unitycatalog:8080/api/2.1/unity-catalog/catalogs | jq .
```

### From Spark

**Not verified against this stack yet.** The configuration below is
transcribed from [upstream's Spark integration
guide](https://docs.unitycatalog.io/integrations/unity-catalog-spark/),
selecting the row for Spark 4.1.x because [the Spark stack](./spark.md)
runs `nexus-spark:4.1.1`. Nobody has run it here; treat the first attempt
as a test rather than a recipe, and correct this section with what actually
worked.

Two JARs are required and **neither is baked into the Nexus Spark image** —
it pre-bakes hadoop-aws, the AWS SDK and the Spark Connect server, but not
Delta. They resolve through Ivy on first use, which is the ~30-second
cold start `stacks/spark/Dockerfile` pre-bakes its own JARs to avoid.

```bash
spark-shell \
  --packages "io.delta:delta-spark_4.1_2.13:4.3.1,io.unitycatalog:unitycatalog-spark_4.1_2.13:0.5.0" \
  --conf "spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension" \
  --conf "spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog" \
  --conf "spark.sql.catalog.unity=io.unitycatalog.spark.UCSingleCatalog" \
  --conf "spark.sql.catalog.unity.uri=http://unitycatalog:8080" \
  --conf "spark.sql.defaultCatalog=unity"
```

Upstream's example also passes `spark.sql.catalog.unity.token`. It is
omitted here because `server.authorization=disable` — add it if you ever
turn Unity Catalog's own auth on.

Known unknowns, listed rather than glossed over:

- The connector version upstream documents is `0.5.0` while this stack runs
  server `v0.6.0`. Whether that pairing works is untested.
- `delta-spark_4.1_2.13:4.3.1` is the version in upstream's guide; it has
  not been checked against Maven Central from here.
- Ivy resolution needs outbound network from the Spark container on first
  use.

## External tables on object storage

`conf/server.properties` ships with the S3 slots (`s3.bucketPath.0`,
`s3.accessKey.0`, …) **empty on purpose**. This stack has four candidates —
MinIO, Garage, RustFS, SeaweedFS — and wiring one in by default would make
Unity Catalog fail whenever that stack is disabled, which is exactly what
the project's "each stack brings its own resources" rule prevents.

To register external tables, fill those in deliberately with credentials
from Infisical and re-run a spin-up. Managed tables in the local volume
work without any of it.

## Debugging

```bash
# Is the server answering? A 401 would also count as up.
ssh nexus "docker exec unitycatalog curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/2.1/unity-catalog/catalogs"

# What is registered?
ssh nexus "docker exec unitycatalog curl -s http://localhost:8080/api/2.1/unity-catalog/catalogs"

# Did the UI reach the server? It looks for the host `server`, via alias.
ssh nexus "docker logs unitycatalog-ui 2>&1 | tail -30"

# Is the metastore in the volume, where it survives a recreate?
ssh nexus "docker exec unitycatalog ls -la /opt/unitycatalog/etc/data"
```

That last one is worth knowing about. Upstream's `hibernate.properties`
points H2 at `./etc/db/h2db`, a path **outside** the persisted volume — so
every catalog registration would vanish on the next `--force-recreate`,
which this project does on every spin-up. The shipped config points it into
`/opt/unitycatalog/etc/data` instead. If you see an `h2db` file appear
somewhere else after an image bump, that change was lost.

## Related

- [Lakekeeper](./lakekeeper.md) — Iceberg REST Catalog, independent of this one
- [Marquez](./marquez.md) — lineage rather than cataloguing; what *happened* to a dataset, not what it *is*
- [OpenMetadata](./openmetadata.md) — discovery and governance over a catalog
- [Unity Catalog documentation](https://docs.unitycatalog.io)
