---
title: "MongoDB"
---

## MongoDB

![MongoDB](https://img.shields.io/badge/MongoDB-47A248?logo=mongodb&logoColor=white)

**Document database (NoSQL) with the mongo-express web UI**

MongoDB stores schema-flexible, JSON-like documents and queries them with filters, indexes and aggregation pipelines. It closes the document/NoSQL gap next to the relational (PostgreSQL), columnar (ClickHouse), time-series (QuestDB, InfluxDB) and vector (Chroma, Weaviate) stores already here — and it is what a lot of application code and tutorials expect to find.

The stack ships two containers:

| Container | Image | Role |
|-----------|-------|------|
| `mongodb` | `mongo:7.0.43` | The server. Wire protocol on `27017`, authentication on |
| `mongodb-express` | `mongo-express:1.0.2-20-alpine3.19` | Web UI for browsing databases, collections and documents |

| Setting | Value |
|---------|-------|
| Default Port | `8105` (mongo-express, mapped to internal 8081) |
| Suggested Subdomain | `mongodb` |
| Public Access | No (protected by Cloudflare Access) |
| Wire protocol (internal) | `mongodb:27017` on `app-network` |
| Wire protocol (external) | Port `27017`, only with the firewall rule enabled — see below |
| Root Username | `nexus-mongodb` |
| Root Password | Generated per deployment — in Infisical under `mongodb` |
| Persistence | Local Docker volumes (compose keys `mongodb-data`, `mongodb-config`) |
| Website | [mongodb.com](https://www.mongodb.com) |
| Source | [GitHub](https://github.com/mongodb/mongo), [mongo-express](https://github.com/mongo-express/mongo-express) |

### Why version 7.0

**MongoDB 8.x does not run on the servers this project deploys.** MongoDB's release notes state that Linux kernels 6.19 through 7.0.13 are incompatible with the TCMalloc it vendors, and that MongoDB "detects these kernel versions and stops during startup" ([SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912)). The fix is kernel 7.0.14. Ubuntu 26.04 reports its kernel as `7.0.0-<build>` and keeps that base version for the life of the release, so MongoDB's check will keep refusing it even after Ubuntu backports the fix.

Measured on a deployed server (`7.0.0-30-generic`), each image started in an isolated container:

| Image | Result | Allocator |
|---|---|---|
| `mongo:8.0.30`, `mongo:8.0.32` | exits at startup | – |
| `mongo:8.3.11` | exits at startup | – |
| `mongo:8.2.12` | runs | `tcmalloc-google`, `usingPerCPUCaches: true` |
| `mongo:7.0.43` | runs | `tcmalloc`, no per-CPU caches |

8.2 is not the way out, even though it starts. Its per-CPU caches are the mechanism the startup check exists to keep away from these kernels — 8.2 simply lacks the check. It is also past its end of life (31 July 2026).

7.0 uses the older TCMalloc, which does not use per-CPU caches, so it is outside the incompatibility rather than past a check. It is a **major** release, supported until 31 August 2027.

This was found by a real spin-up, not by a local run: the stack passed every local test on a different kernel, then went into a restart loop on the server with `MongoDB cannot start: Linux kernel versions 6.19 and newer has a known incompatibility with this version of MongoDB.`

**A data directory from a newer MongoDB is refused, not opened.** On the default image none can exist, because 8.x never started there. There are two ways one could:

- data copied in from elsewhere, or
- a server built with `server_image` set to an image whose kernel MongoDB 8.0 accepts (`ubuntu-24.04`, say), with MongoDB enabled during the hours `mongo:8.0.30` was the pinned version (2026-09-16), and the volume then kept by the `snapshot` lifecycle — a `rebuild` teardown destroys it (see [What survives a teardown](#what-survives-a-teardown)).

Measured: data written by `mongo:8.2.12` (FCV 8.2), then started with `mongo:7.0.43`, stops with exit 62 and `UPGRADE PROBLEM: Found an invalid featureCompatibilityVersion document`, and leaves the files as they were. The spin-up's smoke check reports the container as exited.

**Moving such data here.** Community Edition has no binary downgrade from 8.x to 7.0, and a dump is no way around that: MongoDB supports `mongorestore` only between deployments of [the same major version or the same feature compatibility version](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/), which an 8.x dump and this 7.0 server are not. Do not read a clean run as permission — a `mongodump` from 8.2.12 restored into 7.0.43 finished with exit 0 in the same test, which is exactly why an unsupported path is dangerous: nothing tells you if it went wrong.

Export at the document level instead, with the old server still running. The commands below run **on the server** (`ssh nexus`) and **inside the `mongodb` container**: port `27017` is not published unless the firewall rule is on, so a tool on the host has nothing to connect to. The container already holds `nexus-mongodb`'s credentials in `MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD`. Each command reads them from there, so the password never appears in a command line. `printf` is a shell builtin, and the tools take it from a `--config` file that exists only for the duration of the call.

If the old data is this same stack on another server, the container and variable names are the same there. Otherwise, use that deployment's own address and credentials.

```bash
# 1. On the OLD server: list the indexes, they do not travel
docker exec mongodb mongosh --quiet --norc --eval '
  db.getSiblingDB("admin").auth(process.env.MONGO_INITDB_ROOT_USERNAME, process.env.MONGO_INITDB_ROOT_PASSWORD);
  printjson(db.getSiblingDB("shop").orders.getIndexes())'

# 2. On the OLD server: export one collection as canonical Extended JSON
#    (no -i: the export reads nothing, and -i would swallow the rest of a
#    script this is pasted into)
docker exec mongodb sh -c '
  umask 077
  printf "password: %s\n" "$MONGO_INITDB_ROOT_PASSWORD" > /tmp/migrate.yaml
  mongoexport --config /tmp/migrate.yaml --username "$MONGO_INITDB_ROOT_USERNAME" \
    --authenticationDatabase admin --db shop --collection orders --jsonFormat=canonical
  rc=$?; rm -f /tmp/migrate.yaml; exit $rc' > orders.json

# 3. Copy orders.json to this server, then import it into this stack
docker exec -i mongodb sh -c '
  umask 077
  printf "password: %s\n" "$MONGO_INITDB_ROOT_PASSWORD" > /tmp/migrate.yaml
  mongoimport --config /tmp/migrate.yaml --username "$MONGO_INITDB_ROOT_USERNAME" \
    --authenticationDatabase admin --db shop --collection orders
  rc=$?; rm -f /tmp/migrate.yaml; exit $rc' < orders.json

# 4. Recreate each index from step 1, e.g. with createIndex() in mongosh
```

Steps 1 to 3 were run as written against this stack, into a scratch database. Export and import both exited 0, the documents arrived with their `Decimal128` values, the secondary index did not, and no config file was left in the container. The same import without the credentials exits 1.

`--jsonFormat=canonical` is what keeps BSON types intact. Measured from 8.2.12 into 7.0.43: `ObjectId`, `Date`, `Decimal128` (`19.99`) and a `Long` above 2⁵³ (`9007199254740993`) all arrived as the same types and values. **Indexes do not travel** — the collection arrived with only `_id_` — and neither do users or roles, which this stack creates itself.

**Before moving to 8.x**, check `uname -r` on a deployed server. It needs to report 7.0.14 or later — which on Ubuntu means a newer kernel line, not a newer build of `7.0.0`.

### Credentials

The root password is generated by OpenTofu per deployment and pushed to Infisical. It is never printed to a workflow log.

```
Infisical → mongodb → MONGODB_ROOT_USERNAME            nexus-mongodb
                      MONGODB_ROOT_PASSWORD            (generated)
                      MONGODB_EXPRESS_SESSION_SECRET   (generated, not a login)
```

The username is stored alongside the password deliberately: a reader holding only the password would otherwise try `root` or `admin`, the guessable defaults the `nexus-` convention exists to prevent. The user lives in the `admin` database, so clients authenticate with `authSource=admin`.

Like every credential in Infisical, these are also synced into Kestra as `SECRET_*` environment variables, so a Kestra flow can read them with `{{ secret('MONGODB_ROOT_PASSWORD') }}`. That is a property of the whole project rather than of MongoDB, and #716 tracks narrowing it to an allowlist.

### Authentication model

Two layers, split the same way as [OpenSearch](opensearch.md):

- **The web UI has no login of its own.** Cloudflare Access at the edge authenticates whoever reaches `https://mongodb.<domain>`. The mongo-express image enables basic auth by default with the credentials `admin` / `pass`; the stack switches that off explicitly rather than leave a documented default login in place. mongo-express connects to the server as the root user, so **anyone who passes Cloudflare Access has full read-write access to every database.** Its session secret is generated too — the image's default is the literal string `secret`.
- **The wire protocol authenticates.** Every client — a notebook on `app-network`, a Kestra flow, or Compass on your laptop — has to present the `nexus-mongodb` credentials.

The UI container is attached only to the stack's private `mongodb-internal` network, not to `app-network`, and its port is published on `127.0.0.1` only. Other stacks therefore cannot reach the login-less UI; they talk to `mongodb:27017`, which requires the password.

### Connecting from inside the stack

From Jupyter, Marimo or code-server. None of those stacks installs `pymongo` in its Dockerfile or compose file, so install it first if the notebook cannot import it (`pip install pymongo`):

```python
from pymongo import MongoClient

client = MongoClient(
    "mongodb://mongodb:27017",
    username="nexus-mongodb",
    password="...",          # Infisical → mongodb → MONGODB_ROOT_PASSWORD
    authSource="admin",
)
client.shop.orders.insert_one({"sku": "A-17", "qty": 3})
print(client.shop.orders.count_documents({}))
```

The password is **not** injected into the notebook containers' environment — the rendered `.env` belongs to this stack alone — so copy it from Infisical.

Note `mongodb:27017`: the container name and container port. Inside the Docker network there is no TLS, the same as for PostgreSQL and every other stack here; the encryption boundary is the Cloudflare Tunnel.

### Connecting from outside (Compass, mongosh)

MongoDB's wire protocol cannot go through the HTTPS tunnel, so port `27017` is closed by default and not published on the host at all.

1. In the Control Plane, open **Firewall** and, on the **mongodb** card, enable the **wire** rule (port 27017). Restrict the source IPs to your own address. The rule is listed once a spin-up has synced `services.yaml` into the Control Plane.
2. Run **Spin Up**. The deploy generates a `docker-compose.firewall.yml` that publishes `27017:27017` on the `mongodb` container and opens the Hetzner firewall for that port.
3. Connect to the server's IP address — no DNS record is created for this rule:

```bash
mongosh "mongodb://nexus-mongodb@<server-ip>:27017/?authSource=admin"
```

⚠️ The connection is **not encrypted**. MongoDB's SCRAM authentication does not send the password in clear text, but queries and documents travel unencrypted over the internet. Keep the source-IP restriction tight and close the rule when you are done. Firewall rules are reset on every teardown.

### First run

The `mongo` image's entrypoint creates `nexus-mongodb` from `MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD` only when the data directory is empty. On a later start with existing data it creates nothing — but it still adds `--auth` to `mongod` on **every** start, as long as both variables are set. They must therefore stay in the compose file permanently; removing them would serve the existing data with access control off.

Because the user is created once, the password inside MongoDB and the one in Infisical can drift only if the generated value changes while the volume survives. The two lifecycles do not produce that on their own: in `rebuild` mode the volume is destroyed along with the server, so the user is created fresh with the new password; in `snapshot` mode the volume and the OpenTofu state survive together, so the password does not change. It becomes possible only if `random_password.mongodb_root` is replaced by hand. If you do that, change the password inside MongoDB too (`db.getSiblingDB("admin").changeUserPassword(...)`) — the environment variable will not do it for you.

### What survives a teardown

- **`rebuild` mode (default): nothing.** MongoDB is not among the targets `src/nexus_deploy/s3_restore.py` backs up to R2, and its data lives in Docker volumes on the server's disk, which the teardown destroys. Every spin-up starts with an empty database.
- **`snapshot` mode: everything.** The whole root disk is imaged, Docker volumes included, and the credentials are not regenerated.

If data has to outlive a `rebuild` teardown, export it (`mongodump`, or `mongoexport` to JSON/CSV) to R2 or a Git repository before tearing down.

### Resources

The `mongodb` container is limited to 2 GB of memory, and the WiredTiger cache is pinned to 1 GB with `--wiredTigerCacheSizeGB 1`. MongoDB's documentation requires setting the cache explicitly inside a container that cannot use all of the host's RAM, because WiredTiger may otherwise size it from the host's memory. `mongodb-express` is limited to 256 MB.

### Quick check

The tunnel hostname sits behind Cloudflare Access, so an unauthenticated `curl` gets an Access page. Check from the server instead:

```bash
ssh nexus "docker ps --filter name=mongodb --format '{{.Names}}\t{{.Status}}'"
ssh nexus "curl -s http://127.0.0.1:8105/status"          # {"status":"ok"}
ssh nexus "docker exec mongodb mongosh --quiet --eval 'db.adminCommand({ ping: 1 }).ok'"   # 1
```

`ping` is answered without authentication, which is why the container healthcheck can use it without putting the password in a process argument list. Anything that reads data — `show dbs`, a `find` — returns `requires authentication` until you log in.
