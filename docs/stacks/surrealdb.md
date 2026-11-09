---
title: "SurrealDB"
---

## SurrealDB

![SurrealDB](https://img.shields.io/badge/SurrealDB-FF00A0?logo=surrealdb&logoColor=white)

**Multi-model database**

SurrealDB keeps documents, graph relations and key-value data in one database. It queries them with SurrealQL: SQL-like, with record links and `RELATE` graph edges instead of join tables.

| Setting | Value |
|---------|-------|
| In-cluster | `ws://surrealdb:8000/rpc` (SDKs), `http://surrealdb:8000/sql` (HTTP) |
| Credentials | `nexus-surrealdb` (root level), password generated per deployment (Infisical folder `surrealdb`) |
| Web UI | None — internal only, no subdomain |
| Persistence | Docker volume `surrealdb-data` (RocksDB) |
| Website | [surrealdb.com](https://surrealdb.com) |

### Where it fits

Next to [Postgres](postgres.md) (relational), [MongoDB](mongodb.md) (documents) and [Neo4j](neo4j.md) (graph), SurrealDB shows the same data in several models in one place. That makes it good for comparing them.

### First steps

SurrealDB 4 needs a namespace and a database to be defined before use:

```bash
curl -u nexus-surrealdb:<SURREALDB_PASSWORD> http://surrealdb:8000/sql \
  -H "Accept: application/json" \
  -d "DEFINE NAMESPACE IF NOT EXISTS demo; USE NS demo; DEFINE DATABASE IF NOT EXISTS demo;"

curl -u nexus-surrealdb:<SURREALDB_PASSWORD> http://surrealdb:8000/sql \
  -H "Accept: application/json" -H "surreal-ns: demo" -H "surreal-db: demo" \
  -d "CREATE person:alice SET name = 'Alice';
      CREATE person:bob SET name = 'Bob';
      RELATE person:alice->knows->person:bob;
      SELECT ->knows->person.name AS friends FROM person:alice;"
```

The last statement returns `[{"friends": ["Bob"]}]`. That sequence was tested, also after a restart. The Python SDK (`pip install surrealdb`) connects to `ws://surrealdb:8000/rpc`. It was not tried here.

### Why there is no web UI

Surrealist, SurrealDB's UI, is a web app that connects from the browser to the database. Through the tunnel that would be a second subdomain, behind a second Access login, over a websocket. So the database stays internal. Anonymous access is refused (`403`).

### Persistence

Data is in `surrealdb-data`. Telemetry is off.

- **`rebuild` (default): it does not survive a teardown.** SurrealDB is not in the R2 backup list.
- **`snapshot`: it survives**, because the whole disk is imaged.
