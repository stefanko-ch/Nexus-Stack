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
| Backing DB | Dedicated Postgres 16 (`lakekeeper-db` container, separate from any shared Postgres) |

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

1. Enable **Lakekeeper** in the Control Plane → Spin Up
2. Open `https://lakekeeper.YOUR_DOMAIN/health` → CF Access email OTP → `{"status":"ok"}`
3. Bootstrap a warehouse (one-time, points at your chosen object-storage bucket):

First pull the storage credentials out of Infisical (or your local secrets store) into shell env vars so the secrets never appear in `curl`'s argv or the shell history:

```bash
# Fetch from Infisical (or paste-in interactively via `read -s` —
# anything except hardcoding the secret into the command below):
export S3_ACCESS_KEY_ID=$(infisical secrets get GARAGE_ACCESS_KEY_ID --path=/garage --plain)
export S3_SECRET_ACCESS_KEY=$(infisical secrets get GARAGE_SECRET_ACCESS_KEY --path=/garage --plain)

# Send the warehouse-bootstrap payload via stdin (`--data-binary @-`)
# so the JSON — including the secret value — never lands in `ps`
# listings or shell-history. The heredoc expands the env vars inside
# the JSON before piping to curl; shell-history captures the heredoc
# WITHOUT expansion, so the actual secret stays out.
cat <<EOF | curl -X POST https://lakekeeper.YOUR_DOMAIN/management/v1/warehouse \
  -H "Content-Type: application/json" \
  --data-binary @-
{
  "warehouse-name": "default",
  "project-id": "00000000-0000-0000-0000-000000000000",
  "storage-profile": {
    "type": "s3",
    "bucket": "lakehouse",
    "endpoint": "http://garage:3900",
    "region": "garage",
    "path-style-access": true,
    "sts-enabled": false
  },
  "storage-credential": {
    "type": "s3",
    "credential-type": "access-key",
    "aws-access-key-id":     "${S3_ACCESS_KEY_ID}",
    "aws-secret-access-key": "${S3_SECRET_ACCESS_KEY}"
  }
}
EOF
```

If `LAKEKEEPER__AUTHZ_BACKEND` is set to something other than the shipped `allow-all`, add `-H "Authorization: Bearer $TOKEN"` to the curl above; pull the token via the same `infisical secrets get` pattern, never paste it as a literal.

4. From PyIceberg:

```python
from pyiceberg.catalog import load_catalog

catalog = load_catalog(
    "lakekeeper",
    uri="https://lakekeeper.YOUR_DOMAIN/catalog",
    warehouse="default",
)

# Create namespace + table
catalog.create_namespace("course")
catalog.create_table(
    "course.students",
    schema=...,  # standard PyArrow / Iceberg schema
)
```

5. From Spark (with `iceberg-spark-runtime`):

```python
spark = SparkSession.builder \
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
    .config("spark.sql.catalog.lk", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.lk.type", "rest") \
    .config("spark.sql.catalog.lk.uri", "https://lakekeeper.YOUR_DOMAIN/catalog") \
    .config("spark.sql.catalog.lk.warehouse", "default") \
    .getOrCreate()

spark.sql("SELECT * FROM lk.course.students").show()
```

6. From Trino — add to `tofu/stack/main.tf`'s Trino config OR drop in `/etc/trino/catalog/lakekeeper.properties` on the Trino container:

```properties
connector.name=iceberg
iceberg.catalog.type=rest
iceberg.rest-catalog.uri=https://lakekeeper.YOUR_DOMAIN/catalog
iceberg.rest-catalog.warehouse=default
```

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

### Persistence

- `lakekeeper-db-data` volume: Postgres data (warehouses, namespaces, table metadata, snapshot history)
- **Parquet data** lives in whichever object-storage bucket you wire up per warehouse — counts against that storage's quota, NOT Lakekeeper's DB

**Backup scope — important:** Nexus-Stack's `NEXUS_S3_PERSISTENCE=true` snapshot loop covers an **explicit allow-list** of per-service filesystem trees (forgejo, gitea, dify, metabase, hedgedoc, planka) plus per-service Postgres dumps (forgejo, gitea, dify, hedgedoc, planka) — see [`src/nexus_deploy/s3_restore.py`](../../src/nexus_deploy/s3_restore.py) for the canonical list. Lakekeeper is **not currently in that allow-list**, so neither the `lakekeeper-db-data` volume nor the warehouse Parquet buckets are backed up automatically. Two consequences:

1. **Catalog metadata** (`lakekeeper-db-data`): lost on a `docker compose down -v` or a fresh-start spin-up. Warehouses + tables remain physically present in object storage (the Parquet files survive), but Lakekeeper has no record of them — you'd re-register each warehouse via `POST /management/v1/warehouse` and Lakekeeper would re-discover the existing tables on next access.
2. **Parquet data**: backup is whatever the underlying object-storage backend gives you. R2 / Hetzner S3 have provider-level durability + optional cross-region replication; MinIO / Garage / SeaweedFS on the same Hetzner box are NOT redundant unless the operator wires their own replication.

If your workload needs catalog-metadata in the snapshot loop, the follow-up is to add `lakekeeper-db-data` + the relevant warehouse buckets to the allow-list in `s3_restore.py`.

### Warehouses + storage choices

Lakekeeper supports multiple warehouses per catalog, each pointing at a different bucket / storage backend. Common pattern for the existing stack:

- **In-stack warehouse**: bucket on Garage / MinIO / SeaweedFS — fast, free, internal
- **External warehouse**: bucket on R2 / Hetzner S3 — durable, geo-redundant, for long-term archival

Wire them with separate `POST /management/v1/warehouse` calls; query both from any engine via `warehouse=...`.

### Troubleshooting

- **`bootstrap` container loops on migrate**: usually `LAKEKEEPER_DB_PASSWORD` mismatch between Lakekeeper + Postgres env — caused by a previous deploy with a different password and the volume keeping the old one. `docker compose down -v` to reset (loses catalog metadata; warehouses + tables in object storage are not affected and can be re-registered)
- **`/health` returns 503**: bootstrap hasn't finished yet — wait 10-20s on first start
- **PyIceberg `404 Not Found` on namespace create**: warehouse not bootstrapped — run the `POST /management/v1/warehouse` from step 3 above
- **`AccessDenied` from object storage**: storage credentials in the warehouse profile are wrong — verify the access key has read+write on the target bucket. Lakekeeper passes the credentials through to whatever S3 client the executing engine uses, so error messages come from the engine layer (Spark / Trino), not Lakekeeper itself
- **Tables visible in Spark but not in Trino (or vice versa)**: usually a warehouse-name mismatch in the engine config — both must point at the same Lakekeeper warehouse identifier

### Related

- [Lakekeeper repo](https://github.com/lakekeeper/lakekeeper) — releases + roadmap
- [Iceberg REST Catalog Spec](https://github.com/apache/iceberg/blob/main/open-api/rest-catalog-open-api.yaml) — what every Iceberg-aware engine speaks
- [Apache Iceberg docs](https://iceberg.apache.org/docs/latest/) — table format spec, time-travel, schema evolution, partition evolution
- [lakefs](./lakefs.md) — sibling stack with a **different** lakehouse pattern (Git-like data versioning on top of object storage, not Iceberg). Pick lakefs if you want git-style branch/merge/diff semantics on data files; pick Lakekeeper if you want catalog-managed Iceberg tables with multi-engine access.
