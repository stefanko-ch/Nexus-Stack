---
title: "Lakekeeper"
---

## Lakekeeper

![Lakekeeper](https://img.shields.io/badge/Lakekeeper-B7410E?logo=rust&logoColor=white)

**Modern Iceberg REST Catalog (Rust)**

Lakekeeper is an open-source implementation of the [Apache Iceberg REST Catalog specification](https://github.com/apache/iceberg/blob/main/open-api/rest-catalog-open-api.yaml). It turns the existing object storage (Garage / MinIO / SeaweedFS / RustFS / external R2) into a full lakehouse: register a table once via the REST API, query it from Spark, Trino, DuckDB, PyIceberg, or any other Iceberg-aware engine — no Hive Metastore, no per-engine catalog duplication.

| Setting | Value |
|---------|-------|
| Host Port | `8195` (container internal port is the upstream Lakekeeper default `8181`; host shifted to avoid a docker-compose collision with Kafka-UI which already binds host `8181:8080`) |
| Suggested Subdomain | `lakekeeper` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [lakekeeper.io](https://lakekeeper.io) |
| Source | [GitHub](https://github.com/lakekeeper/lakekeeper) |
| Docker image | [`quay.io/lakekeeper/catalog`](https://quay.io/repository/lakekeeper/catalog) |
| Backing DB | Dedicated Postgres 17 (`lakekeeper-db` container, separate from any shared Postgres) |

### Why this matters for the existing stack

Before Lakekeeper, every Iceberg-aware engine in the stack needed its own catalog config (or a local Hive Metastore). Lakekeeper centralises that:

| Engine | Before | With Lakekeeper |
|---|---|---|
| Spark | Per-job Hadoop config + own warehouse path | `spark.sql.catalog.lakekeeper.type=rest` + URL |
| Trino | Per-catalog `iceberg.yml` with separate metastore | One REST catalog config pointing at Lakekeeper |
| PyIceberg | Local `.pyiceberg.yaml` per project | `Catalog.load("lakekeeper", uri="...")` |
| DuckDB | Manual table-by-table `iceberg_scan(s3://...)` | `ATTACH 'http://...' AS lk (TYPE iceberg)` |

All engines read + write the **same** physical Parquet files in object storage, with the catalog as the single source of truth for which version of which table lives where.

### Usage

1. Enable **Lakekeeper** in the Control Plane → Spin Up.
2. The deploy does the rest. `render_lakekeeper_hook` runs in the
   `services-configure` phase and performs the two steps a fresh install
   needs, in this order:
   - `POST /management/v1/bootstrap` — creates the default project. **Not
     optional**: creating a warehouse before it returns `404 ProjectNotFound`.
   - `POST /management/v1/warehouse` — creates a warehouse named `nexus`
     backed by the deployment's Cloudflare R2 data bucket, under the
     `lakekeeper/` key prefix.

   Look for `RESULT hook=lakekeeper status=configured` in the spin-up log;
   `already-configured` on later runs, and `skipped-not-ready` when the
   deployment has no R2 bucket to point a warehouse at.
3. Open `https://lakekeeper.YOUR_DOMAIN` → Cloudflare Access email OTP → the
   warehouse is listed.

#### From a notebook (PyIceberg)

The seeded notebook `nexus_seeds/marimo/Getting_Started_Lakekeeper.py` walks
through this. The short version:

```python
from pyiceberg.catalog import load_catalog

cat = load_catalog(
    "nexus",
    **{"type": "rest", "uri": "http://lakekeeper:8181/catalog", "warehouse": "nexus"},
)
cat.create_namespace_if_not_exists("demo")
tbl = cat.load_table("demo.orders")
tbl.scan().to_polars()
```

Or use the seeded helper, which reads the URL and warehouse from the
environment:

```python
from _nexus_iceberg import get_catalog

cat = get_catalog()
```

**Always the in-cluster URL.** `https://lakekeeper.YOUR_DOMAIN/catalog` is the
browser route and sits behind Cloudflare Access, which answers an API client
with an HTML login page — PyIceberg then fails while parsing that as JSON,
which reads like a catalogue fault and is not one. Clients on `app-network`
use `http://lakekeeper:8181/catalog`; note the container port 8181, not the
host-published 8195.

#### From Spark — not available yet

Iceberg publishes no `iceberg-spark-runtime` build for the Spark 4.2 this
project runs, and the 4.1 build fails on it with a binary incompatibility.
This is measured, and the details plus the check for when it changes are in
[docs/stacks/spark.md](./spark.md#iceberg-is-not-available-from-spark-yet).
Tracked in [#828](https://github.com/stefanko-ch/Nexus-Stack/issues/828).

#### From Trino

If Trino is enabled, drop this in `stacks/trino/catalog/lakekeeper.properties`
— again the in-cluster URL, for the reason above:

```properties
connector.name=iceberg
iceberg.catalog.type=rest
iceberg.rest-catalog.uri=http://lakekeeper:8181/catalog
iceberg.rest-catalog.warehouse=nexus
```

#### Creating another warehouse by hand

The hook creates one. To add another — a second bucket, a different prefix —
post it yourself. Pull the credentials into the environment first so they
never reach `curl`'s argv or the shell history, and note the field names:
they are `access-key-id` and `secret-access-key`, **not** the `aws-`-prefixed
spellings.

```bash
export S3_ACCESS_KEY_ID=$(infisical secrets get R2_DATA_ACCESS_KEY --path=/r2 --plain)
export S3_SECRET_ACCESS_KEY=$(infisical secrets get R2_DATA_SECRET_KEY --path=/r2 --plain)

# Run this from the server, against the in-cluster address. The heredoc
# expands the env vars before piping to curl; shell history keeps the
# unexpanded form, so the secret stays out of it.
cat <<EOF | curl -X POST http://localhost:8195/management/v1/warehouse \
  -H "Content-Type: application/json" --data-binary @-
{
  "warehouse-name": "archive",
  "storage-profile": {
    "type": "s3",
    "bucket": "your-bucket",
    "region": "auto",
    "endpoint": "https://<account>.r2.cloudflarestorage.com",
    "flavor": "s3-compat",
    "path-style-access": true,
    "sts-enabled": false,
    "remote-signing-enabled": true,
    "key-prefix": "archive"
  },
  "storage-credential": {
    "type": "s3",
    "credential-type": "access-key",
    "access-key-id": "${S3_ACCESS_KEY_ID}",
    "secret-access-key": "${S3_SECRET_ACCESS_KEY}"
  }
}
EOF
```

Three settings in that profile are not stylistic, and each breaks something
different if dropped:

| Setting | Why |
|---|---|
| `flavor: s3-compat` + `path-style-access` | R2 is not AWS S3 |
| `sts-enabled: false` | R2 has no AWS STS endpoint |
| `remote-signing-enabled: true` | with both STS and remote signing off, Lakekeeper vends the client no credentials at all and the first write fails with `AWS Error ACCESS_DENIED` |

Remote signing is also why the Marimo image installs `s3fs`: PyIceberg
implements it only in its fsspec FileIO.

Lakekeeper has a `cloudflare-r2` credential type as well. This stack does not
use it — it additionally requires a `token` field, meaning a Cloudflare API
token with R2 permissions, which the deployment does not have and does not
need to mint.

### Auth model

The shipped compose sets `LAKEKEEPER__AUTHZ_BACKEND=allow-all`. **Cloudflare Access at the edge** (email OTP) is the auth gate — anyone past the gate has full catalog read/write inside.

This is the **baseline "one team per stack"** model. If you want fine-grained per-team or per-warehouse permissions inside Lakekeeper (e.g. "team-A can write `analytics.*`, team-B can read it"), Lakekeeper has a full OIDC layer. Switch by:

1. Set `LAKEKEEPER__AUTHZ_BACKEND=openid` in `stacks/lakekeeper/docker-compose.yml`
2. Add `LAKEKEEPER__OPENID_PROVIDER_URI` pointing at your IdP (Authentik / Keycloak / Auth0)
3. Re-deploy
4. Use Lakekeeper's `/management/v1/user` + `/management/v1/role` endpoints to define teams

Not done by default because (a) most stacks have one team, (b) CF Access already handles authentication, (c) adding OIDC requires standing up an IdP.

### Secrets

Generated by OpenTofu (`random_password.lakekeeper_db_password`, 24 chars) and pushed to Infisical under folder `/lakekeeper`:

- `LAKEKEEPER_DB_PASSWORD` — Postgres password for the dedicated `lakekeeper-db` container

Must be non-empty or the deploy aborts with a clear `ServiceEnvError`.

The same value is also passed as `LAKEKEEPER__PG_ENCRYPTION_KEY`, which
encrypts the warehouse storage credentials Lakekeeper stores in that
database. Reusing it rather than adding a second secret is deliberate: both
would be generated by the same `tofu apply` and would live in the same
Postgres, so a separate key would widen the blast radius of a leak by exactly
nothing while adding a value that can drift out of sync. It has to stay
stable across spin-ups or previously stored credentials stop decrypting.

The R2 credentials the warehouse uses are **not** in this stack's `.env`.
They reach `render_lakekeeper_hook` from the deploy config and go straight
into the API call, so they never land in a file on the server.

### Persistence

Two halves, and both are needed. Losing either one gives a distinct failure:
Parquet files no catalogue can name, or a catalogue pointing at files that
are gone.

| Piece | Where | How it survives a teardown |
|---|---|---|
| Warehouses, namespaces, table pointers, snapshot history | `lakekeeper-db` Postgres, bind-mounted at `/mnt/nexus-data/lakekeeper/db` | `pg_dump` to R2 on teardown, restored on spin-up — see `PostgresDumpTarget(container="lakekeeper-db", ...)` in [`src/nexus_deploy/s3_restore.py`](../../src/nexus_deploy/s3_restore.py) |
| Parquet + Iceberg metadata files | Cloudflare R2, under the `lakekeeper/` key prefix | never leaves — R2 is outside the server |

The `lakekeeper/` prefix matters: the data bucket is shared. Unity Catalog
addresses it at the root and pg-ducklake writes tables into it, so each
warehouse owns a subtree instead of the top level.

The database dump also carries the warehouse's stored R2 credentials,
encrypted with `LAKEKEEPER__PG_ENCRYPTION_KEY`. That key is the Lakekeeper DB
password, which OpenTofu keeps in state across a teardown, so a restored dump
still decrypts. Left unset, Lakekeeper logs `THIS IS UNSAFE! Using default
encryption key for secrets in postgres` and uses a built-in key — which would
put the R2 secret in the catalogue database under an encryption anyone can
reverse.

#### Upgrading an existing install: the database moved

Before this change the catalogue lived in a Docker named volume,
`lakekeeper-db-data`. It is now a bind mount at
`/mnt/nexus-data/lakekeeper/db`, and **nothing copies the old data across** —
Postgres finds an empty directory and initialises a fresh, empty catalogue.
The Parquet files in object storage are untouched, but nothing names them any
more.

Whether this affects you depends on the lifecycle mode:

- **Rebuild** (`lifecycle_mode: rebuild`) — nothing to do. The teardown
  destroys the server, so the named volume was already gone on every cycle.
- **Snapshot** (`lifecycle_mode: snapshot`) — the disk image preserved that
  volume, so it may hold a catalogue you care about. Copy it across **once**,
  on the server, before the first spin-up that carries this change:

```bash
# With the stack stopped.
docker run --rm \
  -v lakekeeper-db-data:/from \
  -v /mnt/nexus-data/lakekeeper/db:/to \
  alpine sh -c 'cd /from && cp -a . /to/'
```

Check `docker volume ls | grep lakekeeper` first: no such volume means there
is nothing to migrate. Afterwards, `docker volume rm lakekeeper-db-data`
reclaims the space — but only once a spin-up has confirmed the catalogue came
back.

**Not covered:** object-storage durability itself. R2 gives you provider-level
durability; a MinIO / Garage / SeaweedFS warehouse on the same Hetzner box is
not redundant unless the operator wires their own replication.

### Warehouses + storage choices

The deploy creates one warehouse, `nexus`, on Cloudflare R2. That is the
durable choice and the reason the default is not an in-stack bucket: R2 lives
outside the server, so its objects survive a teardown untouched, which is the
entire point of pairing it with the catalogue dump.

Lakekeeper supports more than one warehouse per catalogue, each pointing at a
different bucket or backend — see "Creating another warehouse by hand" above.
Two patterns worth knowing:

- **In-stack warehouse** on Garage / MinIO / SeaweedFS — fast and free, but on
  the same box, so a rebuild teardown takes it with the server unless the
  operator adds it to the backup allow-list.
- **A second R2 warehouse** with its own `key-prefix` — for separating a
  teaching dataset from working data inside the same bucket.

Clients pick one with `warehouse=...` when opening the catalogue; the seeded
helper takes it as `get_catalog("archive")`.

### Troubleshooting

- **`NoSuchWarehouseException: A warehouse 'nexus' does not exist`** — the
  hook did not create it. Search the spin-up log for
  `RESULT hook=lakekeeper`: `skipped-not-ready` means the deployment has no R2
  bucket configured, `failed` prints the HTTP status alongside it.
- **PyIceberg raises a JSON parse error on connect** — you pointed it at
  `https://lakekeeper.YOUR_DOMAIN`, and Cloudflare Access returned an HTML
  login page. Use `http://lakekeeper:8181/catalog` from inside the network.
- **`ModuleNotFoundError: No module named 's3fs'` on a write** — the client
  lacks `s3fs`, which remote signing needs. The Marimo image ships it; a
  hand-rolled client has to install it. Note the table has already been
  created in the catalogue at that point, leaving a real but empty table.
- **`AccessDenied` from object storage on a write** — either the warehouse
  credentials cannot write to the bucket, or the profile has both
  `sts-enabled` and `remote-signing-enabled` false, in which case Lakekeeper
  vends the client nothing at all.
- **Container permanently `unhealthy` while the API answers** — a healthcheck
  using `CMD-SHELL`. The image is distroless: the only executable in it is
  `/home/nonroot/lakekeeper`, so a shell-based probe exits 127. The shipped
  compose uses `["CMD", "/home/nonroot/lakekeeper", "healthcheck", "-s"]`.
- **`migrate` container fails on start** — usually a `LAKEKEEPER_DB_PASSWORD`
  that no longer matches what the Postgres data directory was initialised
  with. Removing `/mnt/nexus-data/lakekeeper/db` resets it and loses the
  catalogue; the Parquet files in R2 are unaffected and can be re-registered.
- **Tables visible from one engine but not another** — warehouse-name
  mismatch. Everything should point at `nexus`.

### Related

- [Lakekeeper repo](https://github.com/lakekeeper/lakekeeper) — releases + roadmap
- [Iceberg REST Catalog Spec](https://github.com/apache/iceberg/blob/main/open-api/rest-catalog-open-api.yaml) — what every Iceberg-aware engine speaks
- [Apache Iceberg docs](https://iceberg.apache.org/docs/latest/) — table format spec, time-travel, schema evolution, partition evolution
- [lakefs](./lakefs.md) — sibling stack with a **different** lakehouse pattern (Git-like data versioning on top of object storage, not Iceberg). Pick lakefs if you want git-style branch/merge/diff semantics on data files; pick Lakekeeper if you want catalog-managed Iceberg tables with multi-engine access.
