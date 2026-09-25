---
title: "MindsDB"
---

## MindsDB

![MindsDB](https://img.shields.io/badge/MindsDB-00A3E0?logo=databricks&logoColor=white)

**SQL over everything**

Connect a PostgreSQL, a file, or a model provider, and MindsDB presents each as a schema you can `SELECT` from and `JOIN` across in one query.

| Setting | Value |
|---------|-------|
| Host Port | `47334` (HTTP API + editor) |
| MySQL wire | `47335`, loopback only |
| Suggested Subdomain | `mindsdb` |
| Public Access | No (Cloudflare Access, **and** MindsDB's own login) |
| Website | [mindsdb.com](https://mindsdb.com) |
| Image | `mindsdb/mindsdb:v26.1.0` |
| Credentials | `nexus-mindsdb` / Infisical `/mindsdb/MINDSDB_PASSWORD` |

### Read this before enabling it

**Upstream has moved on.** The GitHub repository `mindsdb/mindsdb` now redirects to `mindsdb/mindshub` — a different product ("the unified workspace where open-source models get things done for you") — and the last MindsDB release is **26.1.0, from 2026-04-23**. This stack pins that release.

It works; everything below was measured against it. But it will not get fixes, and that is a deliberate trade-off rather than an oversight. If the federated-SQL part is what you want and you would rather have something maintained, [Trino](./trino.md) does that half and is actively developed.

### Authentication is not optional here

Two environment variables carry the whole thing, and the difference between setting them and not is stark. Measured on this image:

| | `/api/sql/query` | MySQL wire, user `mindsdb`, empty password |
|---|---|---|
| Without `MINDSDB_USERNAME` / `MINDSDB_PASSWORD` | answers the query | **connects** |
| With them | `401` | `Access denied for user mindsdb` |

An unauthenticated MindsDB is not a read-only dashboard left open: it is an SQL engine that can open connections to every other database in the deployment. `_render_mindsdb` refuses to render an empty password for that reason.

One oddity worth knowing, because it looks like a contradiction: the config file inside the container prints `"user": "mindsdb", "password": ""` **either way**. It is not what governs — the environment variables are.

### The two APIs

**HTTP, on 47334.** The editor, and a REST SQL endpoint. Log in first, then query:

```bash
curl -c jar -X POST https://mindsdb.YOUR_DOMAIN/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"nexus-mindsdb","password":"<from Infisical>"}'

curl -b jar -X POST https://mindsdb.YOUR_DOMAIN/api/sql/query \
  -H 'Content-Type: application/json' -d '{"query":"SHOW DATABASES"}'
```

`/api/status` answers without credentials even when auth is on — it reports whether the server is up, not what it holds. That is what the container healthcheck uses.

**MySQL wire, on 47335.** Any MySQL client connects to it as if it were a MySQL server. It is published on loopback only: it is authenticated, but it is a database wire protocol with no TLS in front of it once it leaves the host, so it gets no firewall rule. Reach it from `app-network` as `mindsdb:47335`, or over an SSH tunnel.

### Federating a database

```sql
CREATE DATABASE pg
WITH ENGINE = 'postgres',
PARAMETERS = {
  "host": "postgres", "port": 5432, "database": "postgres",
  "user": "nexus-postgres", "password": "<from Infisical>"
};

SELECT region, amount FROM pg.sales ORDER BY amount;
```

Verified end to end against the shared PostgreSQL, over both APIs.

### Storage

Project metadata goes into MindsDB's own PostgreSQL (`mindsdb-db`) rather than the SQLite default, which would put it in a single file inside the storage directory. Uploaded files, model artefacts and handler state live under `/mnt/nexus-data/mindsdb/storage`.

### Related

- [Trino](./trino.md) — federated SQL without the model half, and actively developed
- [Ollama](./ollama.md) — a local model provider MindsDB can be pointed at
- [CloudBeaver](./cloudbeaver.md) — a browser client that speaks the MySQL wire protocol
