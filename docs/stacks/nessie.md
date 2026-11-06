---
title: "Project Nessie"
---

## Project Nessie

![Project Nessie](https://img.shields.io/badge/Project_Nessie-0B2A4A?logoColor=white)

**Transactional catalog with Git semantics for Iceberg tables**

Project Nessie versions a whole lakehouse the way Git versions code. You create a branch, change several Iceberg tables on it, and merge the branch back atomically, or tag a state for reproducible reads. The web UI shows branches, commits and table contents.

| Setting | Value |
|---------|-------|
| Default Port | `19120` — web UI and REST API (bound to `127.0.0.1` on the host) |
| In-cluster API | `http://nessie:19120/api/v2` |
| Suggested Subdomain | `nessie` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | None — Nessie runs without authentication |
| Persistence | RocksDB in the Docker volume `nessie-data` |
| Website | [projectnessie.org](https://projectnessie.org) |
| Source | [GitHub](https://github.com/projectnessie/nessie) |

### Nessie next to Lakekeeper and Unity Catalog

[Lakekeeper](lakekeeper.md) and [Unity Catalog](unity-catalog.md) are the REST catalogs already here. Nessie is the one for branching and transactions across several tables: a pipeline writes to a branch, checks the result, and merges, so readers never see a half-finished state.

### Connecting

Spark, Flink, Trino and Dremio use Nessie through its API at `http://nessie:19120/api/v2`, and each brings its own warehouse location. PyIceberg does not: it has no Nessie catalog type (its types are `rest`, `hive`, `glue`, `dynamodb`, `sql`, `in-memory` and `bigquery` in 0.12.0), so it needs Nessie's Iceberg REST endpoint, which is not set up here (see below). For Spark, for example:

```python
spark = (
    SparkSession.builder
    .config("spark.sql.catalog.nessie", "org.apache.iceberg.spark.SparkCatalog")
    .config("spark.sql.catalog.nessie.catalog-impl", "org.apache.iceberg.nessie.NessieCatalog")
    .config("spark.sql.catalog.nessie.uri", "http://nessie:19120/api/v2")
    .config("spark.sql.catalog.nessie.ref", "main")
    .config("spark.sql.catalog.nessie.warehouse", "s3a://<bucket>/warehouse")
    .getOrCreate()
)
```

The Iceberg and Nessie Spark extensions must be on the classpath, and the warehouse needs S3 credentials for one of the storage stacks (MinIO, Garage, SeaweedFS).

**Nessie's own Iceberg REST endpoint** (`/iceberg`) is not set up. It needs a warehouse bucket and object-store credentials configured on the Nessie server, which this stack leaves to the course, and until then it answers 500. The Nessie API above works without it; PyIceberg and other REST-only clients need the endpoint.

### Authentication

Nessie runs with authentication and authorization off, and it logs a warning at start saying so. Anyone who passes Cloudflare Access can read and change every branch. Nessie is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`, which keeps it from being made public or given a firewall rule. Inside `app-network`, any container can reach the API.

### Persistence

The commit history is in RocksDB in the `nessie-data` volume, mounted at `/deployments/data`. The image owns that directory as its `nessie` user (10000), and a fresh named volume takes over that owner. Table data itself lives in the warehouse buckets, not in Nessie.

- **`rebuild` (default): the history does not survive a teardown.** Nessie is not in the R2 backup list.
- **`snapshot`: the history survives**, because the whole disk is imaged.
