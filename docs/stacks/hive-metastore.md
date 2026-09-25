---
title: "Hive Metastore"
---

## Hive Metastore

![Hive](https://img.shields.io/badge/Apache_Hive-FDEE21?logo=apachehive&logoColor=black)

**The catalog, and nothing else**

What tables exist, what columns they have, what format they are in, and where their files live. Spark, Trino and Flink all know how to ask it; each brings its own execution.

| Setting | Value |
|---------|-------|
| Port | `9083` (Thrift), bound to loopback on the host |
| Web UI | none |
| Public Access | No (internal-only, no tunnel route) |
| Website | [hive.apache.org](https://hive.apache.org) |
| Image | `nexus-hive-metastore:4.1.0` — built from `apache/hive:4.1.0` |
| Credentials | `nexus-hive` / Infisical `/hive-metastore/HIVE_DB_PASSWORD` |

### It is the alternative to Lakekeeper, not a companion

[Lakekeeper](./lakekeeper.md) serves the **Iceberg REST** catalog. This serves the **Hive** catalog, which the Hive table format and the older half of the ecosystem expect. Running both is the point: a course can put the same data behind each and compare what the engines do with it.

A table on object storage is declared EXTERNAL with its own location:

```sql
CREATE EXTERNAL TABLE sales (region string, amount int)
STORED AS PARQUET
LOCATION 's3a://<bucket>/hive/sales';
```

### Four things the image does not do

Each of these was measured against a running container, not read off a page.

**1. It has no PostgreSQL driver.** `ls /opt/hive/lib | grep -iE 'postgres|mysql'` returns nothing; the only driver shipped is `derby-10.14.2.0.jar`, and Derby would put the catalog inside the container's filesystem. `stacks/hive-metastore/Dockerfile` adds the PostgreSQL JDBC driver, pinned by version **and** sha256.

**2. It puts `SERVICE_OPTS` in the log.** The image's `/entrypoint.sh` starts with `set -x`, so every variable it expands is echoed. With the JDBC password passed that way, `docker logs hive-metastore` printed `ConnectionPassword=<the password>` twice. This stack writes `hive-site.xml` in its own entrypoint wrapper instead, before the image's entrypoint is reached — measured afterwards at **zero** occurrences of either secret in the log.

**3. `HIVE_CUSTOM_CONF_DIR` does not work.** The documented way to supply your own configuration is that variable, which the entrypoint consumes with:

```bash
find "${HIVE_CUSTOM_CONF_DIR}" -type f -exec ln -sfn {} "${HIVE_CONF_DIR}"/ \;
```

The image has no `find` — `command -v find` is empty. The step fails silently, the shipped Derby `hive-site.xml` survives, and `schematool` then runs the **PostgreSQL** schema script against a **Derby** connection and dies on `Syntax error: Encountered "statement_timeout"`. So the configuration is written straight into `/opt/hive/conf/`.

**4. S3A is in the image but not on the metastore's classpath.** `hadoop-aws-3.4.1.jar` and the AWS SDK bundle are both at `/opt/hadoop/share/hadoop/tools/lib`, but the entrypoint only adds `tools/lib` for `hiveserver2`. Creating a table with an `s3a://` location therefore fails with:

```
ClassNotFoundException: org.apache.hadoop.fs.s3a.S3AFileSystem
```

…and once that is fixed, with `NoAuthWithAWSException` until the R2 credentials are supplied. The metastore resolves a table's `LOCATION` **at create time**, EXTERNAL or not, so it needs both.

### It starts as root, and does not stay there

The image runs as `hive` (uid 1000), and a bind mount arrives root-owned — so the warehouse directory is not writable by the user that needs it. Creating a managed table then fails:

```
MetaException: file:/opt/hive/data/warehouse/probe_db.db/local_sales
is not a directory or unable to create one
```

The container therefore starts as root, chowns the warehouse and its own `hive-site.xml` (written under `umask 077`, so otherwise unreadable), and drops straight back with `setpriv` — this image has neither `gosu` nor `su-exec`. The PostgreSQL sidecars need none of this because their image starts as root, chowns, and drops to uid 70 itself.

### Credentials and reach

The Thrift protocol has no authentication of its own, which is why 9083 is published on loopback rather than opened through the firewall. Everything that talks to a metastore is another container on `app-network` and reaches it as `hive-metastore:9083`.

The schema is created by the image on first start (`schematool -initOrUpgradeSchema`), so there is no admin hook for this stack.

### Verified

Against a real object store, end to end:

```
databases: ['default', 'probe_db']
tables:    ['sales']

 TBL_NAME |    TBL_TYPE    |         LOCATION
----------+----------------+---------------------------
 sales    | EXTERNAL_TABLE | s3a://datalake/hive/sales
```

### Related

- [Lakekeeper](./lakekeeper.md) — the Iceberg REST catalog, the other half of the comparison
- [Trino](./trino.md), [Spark](./spark.md) — engines that read this over Thrift
- [Unity Catalog](./unity-catalog.md) — a third catalog, for Delta and Iceberg
