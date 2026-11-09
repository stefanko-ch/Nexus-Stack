---
title: "ArcadeDB"
---

## ArcadeDB

![ArcadeDB](https://img.shields.io/badge/ArcadeDB-2E7D32?logoColor=white)

**Multi-model database: graph, document, key-value and time series**

ArcadeDB keeps graphs, documents, key-value pairs and time series in one engine. It answers SQL, Cypher, Gremlin and GraphQL against the same data, so one graph can be queried in several languages side by side. Next to [Neo4j](neo4j.md) (Cypher) and [Memgraph](memgraph.md) that makes the query languages themselves the subject.

| Setting | Value |
|---------|-------|
| URL | `https://arcadedb.<domain>` (ArcadeDB Studio) |
| In-cluster | `http://arcadedb:2480` (HTTP/JSON API) |
| Login | `nexus-arcadedb`, admin on every database |
| Credentials | Password generated per deployment (Infisical folder `arcadedb`); root's password is in the same folder |
| Persistence | Docker volumes `arcadedb-databases` and `arcadedb-config` |
| Licence | Apache-2.0 |
| Website | [arcadedb.com](https://arcadedb.com) |

### First steps

1. Open `https://arcadedb.<domain>` and log in as `nexus-arcadedb` with `ARCADEDB_PASSWORD` from Infisical.
2. Pick the database `nexus`, which `arcadedb-init` creates on the first start.
3. Write a graph in SQL and read it back in Cypher:

```sql
CREATE VERTEX TYPE Person IF NOT EXISTS;
CREATE EDGE TYPE Knows IF NOT EXISTS;
INSERT INTO Person SET name = 'Ada';
INSERT INTO Person SET name = 'Grace';
CREATE EDGE Knows FROM (SELECT FROM Person WHERE name = 'Ada') TO (SELECT FROM Person WHERE name = 'Grace');
```

```cypher
MATCH (a:Person)-[:Knows]->(b:Person) RETURN a.name, b.name
```

From a notebook, the HTTP API takes the same commands:

```python
import requests

auth = ("nexus-arcadedb", "<ARCADEDB_PASSWORD>")
requests.post("http://arcadedb:2480/api/v1/query/nexus", auth=auth,
              json={"language": "cypher", "command": "MATCH (p:Person) RETURN p.name AS name"}).json()
```

Tested through the HTTP API: the SQL above and the Cypher query (it returns Ada → Grace), anonymous requests refused (`401`), a wrong password refused (`403`), data kept across a restart. Studio's page was served (`200`); logging in to it in a browser was not tried here.

### Users and databases

ArcadeDB has a server-level `root` user and its own users. The stack sets root's password and then `arcadedb-init` creates `nexus-arcadedb` with admin rights on all databases, and the `nexus` database.

Creating a database is a server command, and **only root may run server commands**. To create another one, log in to Studio as `root` with `ARCADEDB_ROOT_PASSWORD`, or send `create database <name>` to `/api/v1/server` as root. `nexus-arcadedb` then has admin rights on it too.

Both passwords are read on the first start, when the users file in `arcadedb-config` is written. On later starts `arcadedb-init` checks that root and `nexus-arcadedb` still log in, and fails the deploy with a message if a password in Infisical no longer matches the stored one.

### Hardening

- **Production mode.** The image defaults to development mode. The stack runs production mode, which flushes the write-ahead log on commit and disables `LOAD CSV` from file URLs. Production mode also stops serving Studio, so `arcadedb.studio.enabled` turns it back on.
- **No remote JMX.** The image's default Java options open an unauthenticated JMX port on 9999. The stack replaces them.
- **Only HTTP.** The Postgres, Redis and MongoDB wire-protocol plugins are not enabled, so only port 2480 listens.

The root password is passed as the environment variable `arcadedb.server.rootPassword`, which ArcadeDB reads like its configuration key, rather than as a `-D` flag on the Java command line.

### Resources

The JVM may use 70 % of the 1.5 GB container limit. It used about 400 MB when idle.

### Persistence

Databases are in `arcadedb-databases`, users and server settings in `arcadedb-config`.

- **`rebuild` (default): they do not survive a teardown.** ArcadeDB is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
