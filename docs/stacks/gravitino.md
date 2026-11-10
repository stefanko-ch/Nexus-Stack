---
title: "Apache Gravitino"
---

## Apache Gravitino

![Gravitino](https://img.shields.io/badge/Apache_Gravitino-2B6CB0?logo=apache&logoColor=white)

**Unified metadata catalog**

Gravitino federates metadata. A *metalake* holds catalogs for many kinds of source:

- relational databases (PostgreSQL, MySQL),
- lakehouse tables (Iceberg, Hudi, Paimon),
- Hive,
- Kafka topics,
- file sets.

All of them are browsed and managed through one web UI and REST API.

| Setting | Value |
|---------|-------|
| Default Port | `8128` (bound to `127.0.0.1` on the host; container port 8090) |
| Suggested Subdomain | `gravitino` |
| Public Access | No (protected by Cloudflare Access) |
| In-cluster | `http://gravitino:8090` |
| Credentials | None — simple auth mode, Cloudflare Access is the gate |
| Persistence | Docker volume `gravitino-data` (embedded H2) |
| Website | [gravitino.apache.org](https://gravitino.apache.org) |

### Where it fits

[Lakekeeper](lakekeeper.md), [Nessie](nessie.md) and [Unity Catalog](unity-catalog.md) each serve one table format. [Hive Metastore](hive-metastore.md) serves one engine family. Gravitino sits above such systems, with one namespace (`metalake.catalog.schema.table`) across all of them. Spark, Trino and Flink can read through its connectors, which are not set up here.

### First steps

In the UI, create a metalake, then a catalog. Or over the REST API, here for the [Postgres](postgres.md) stack:

```bash
H='Accept: application/vnd.gravitino.v1+json'
curl -X POST -H "$H" -H 'Content-Type: application/json' \
  http://gravitino:8090/api/metalakes -d '{"name": "nexus"}'

curl -X POST -H "$H" -H 'Content-Type: application/json' \
  http://gravitino:8090/api/metalakes/nexus/catalogs -d '{
    "name": "pg", "type": "RELATIONAL", "provider": "jdbc-postgresql",
    "properties": {
      "jdbc-url": "jdbc:postgresql://postgres:5432/postgres",
      "jdbc-driver": "org.postgresql.Driver", "jdbc-database": "postgres",
      "jdbc-user": "nexus-postgres", "jdbc-password": "<POSTGRES_PASSWORD>"}}'

curl -H "$H" http://gravitino:8090/api/metalakes/nexus/catalogs/pg/schemas
```

Tested locally against a scratch Postgres: the metalake, the catalog, listing its schemas, and all of it surviving a restart.

### Authentication

Gravitino authenticates with OAuth or Kerberos, and this stack sets up neither. It runs in simple mode: the API trusts the caller, and actions are recorded as `anonymous`. Anyone past Cloudflare Access, and any container on `app-network`, can change the catalog. Gravitino is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`.

The image's built-in Iceberg REST and Lance REST side services are switched off (`GRAVITINO_AUX_SERVICE_NAMES`). The Iceberg one would keep its tables only in memory.

### Persistence

The metadata is in an embedded H2 database in `gravitino-data`. H2 is Gravitino's default store, meant for trying Gravitino out: Gravitino makes no durability promise for it, and a crash at the wrong moment can lose recent catalog changes. That fits a learning stack, where the catalog describes data that lives elsewhere and can be registered again. For metadata you cannot recreate, Gravitino supports PostgreSQL or MySQL as its store, which this stack does not set up.

- **`rebuild` (default): it does not survive a teardown.**
- **`snapshot`: it survives**, because the whole disk is imaged.
