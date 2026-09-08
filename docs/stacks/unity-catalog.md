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
| Metastore | PostgreSQL 16 (`unity-catalog-db`), bind-mounted at `/mnt/nexus-data/unity-catalog/db` |
| Data lake | Cloudflare R2 — table files live there, not on the server |

### Containers

| Container | Role |
|---|---|
| `unity-catalog` | The server. REST API on 8080, no published port. Built locally — see *The custom image* below. |
| `unity-catalog-db` | PostgreSQL 16 metastore. Internal network only. |
| `unity-catalog-ui` | React UI on 3000 — the only published port. |

The container names differ from the hostnames used elsewhere on this page,
and that is deliberate rather than an inconsistency:

| Name | Where it applies |
|---|---|
| `unity-catalog` | `docker exec`, `docker logs` — the Docker container name |
| `unitycatalog` | `http://unitycatalog:8080` — the DNS name on `app-network` |
| `server` | the extra alias the UI resolves, baked into its image at build time |

The container name has to equal the `services.yaml` key, because the deploy
proves a stack started by grepping `docker ps` for exactly that string. The
compose service key stays `unitycatalog` so the hostname other stacks
already point at keeps resolving. Both are correct; use the one the command
in front of you needs.

## Independent of Lakekeeper

[Lakekeeper](./lakekeeper.md) is also a catalog, and the two overlap only
in part: Lakekeeper implements the Iceberg REST Catalog specification and
nothing else, while Unity Catalog also covers Delta, volumes and AI assets.

They share **no database, no volume and no internal network**, and neither
reads the other's configuration. Lakekeeper keeps its own PostgreSQL; Unity
Catalog keeps its metastore in its own PostgreSQL. Enable either alone, both, or
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
  server, not a production build. That is what upstream's Dockerfile does
  (`FROM node:18`, `CMD ["yarn", "start"]`).

### Running a dev server has three consequences

All three were observed on this stack rather than predicted, and each one
presents misleadingly.

It recompiles TypeScript and antd through webpack on every container
start, so the UI does not answer immediately after a spin-up even when
the container is running.

It needs real memory to do that: the container is given **2g**, because
at 512m the compile is killed and nothing ever binds :3000. Two things
disguise that failure. The published port still accepts TCP, since
docker-proxy does, so the port looks alive while speaking no HTTP. And
the container exits **1**, not 137 — the cgroup kills the webpack child,
`react-scripts` catches it and exits on its own, so from outside it does
not look like an OOM at all. The give-away is in the container log:

```text
The build failed because the process exited too early. This probably
means the system ran out of memory or someone called `kill -9`…
```

And it runs a host check, which is why the stack sets
`DANGEROUSLY_DISABLE_HOST_CHECK=true`. react-scripts 5.0.1 disables that
check only when no `proxy` is configured, and this image's `package.json`
has one — so it admits the bind host alone and answers **`Invalid Host
header`** to Cloudflare's `Host: unity-catalog.<domain>`. This one hides
from local probing entirely: `curl http://localhost:3211/` on the server
returns 200 while the browser sees only the error. Reproduce it with the
header the tunnel actually sends:

```bash
ssh nexus "curl -s -H 'Host: unity-catalog.<your-domain>' http://localhost:3211/"
```

The flag's name deserves the scrutiny it invites. The check exists to stop
DNS-rebinding against a development server; here the route sits behind
Cloudflare Access and the port is deliberately absent from `tcp_ports`,
so the firewall refuses any direct connection and :3000 is reachable only
from cloudflared on the same host.

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

**Nothing to configure.** When both stacks are enabled, the deploy writes
the catalog into `stacks/spark/conf/spark-defaults.conf`, and the connector
and Delta JARs are baked into `nexus-spark`. Open a notebook and address a
table by its three-part name:

```sql
CREATE SCHEMA IF NOT EXISTS unity.demo;

CREATE TABLE unity.demo.trips (id INT, city STRING) USING delta
  LOCATION 's3://<your-r2-bucket>/teaching/trips';

INSERT INTO unity.demo.trips VALUES (1, 'Zürich');
SELECT * FROM unity.demo.trips;
```

Three details that are easy to get wrong, all of them measured:

- **`s3://`, never `s3a://`.** Unity Catalog rejects the latter outright
  with `Unsupported URI scheme: s3a`. The rendered config maps `fs.s3.impl`
  to `S3AFileSystem` so the `s3://` scheme still works.
- **`spark.sql.defaultCatalog` is deliberately not set.** Spark's own
  catalog stays the default, so existing notebooks keep working; a Unity
  Catalog table is always addressed as `unity.<schema>.<table>`.
- **The artefact names carry the Spark minor.** `delta-spark_4.2_2.13` and
  `unitycatalog-spark_4.2_2.13`. `io.delta:delta-spark_2.13` also publishes
  a 4.4.0 and is the wrong one. Delta is *not* a transitive dependency of
  the connector — its POM lists no `io.delta` artefact at all — which is why
  `stacks/spark/Dockerfile` bakes both trees explicitly.

The catalog block is written **only when the unity-catalog stack is
enabled**. `spark.sql.extensions` and `spark.sql.catalog.spark_catalog` are
read when a SparkSession is constructed, so naming them on a deployment
without the catalog would burden every Spark session with JARs whose only
purpose is a service that is not running.

## External tables on object storage

Table data lives in **Cloudflare R2**, wired up automatically when the
deployment has a data bucket. R2 rather than one of this stack's four
in-cluster object stores (MinIO, Garage, RustFS, SeaweedFS) for the reason
the catalog exists at all: a rebuild teardown destroys the server's disk,
and a catalogue of vanished files is worse than no catalogue.

`entrypoint.sh` appends the `s3.*` block at container start from environment
variables the deploy renders. There is nothing to fill in by hand.

### Why a credential generator, and why it had to be written

Unity Catalog does not hand Spark the bucket credentials. It *vends* a
short-lived triple per request, and both of its built-in generators are
AWS-shaped:

| Generator | Selected when | Why it cannot serve R2 |
|---|---|---|
| `StsAwsCredentialGenerator` | default | Calls STS `AssumeRole`. R2 has no STS. |
| `StaticAwsCredentialGenerator` | `s3.sessionToken.<i>` is set | R2 validates the token; an invented one returns `403 The security token included in the request is invalid`. |

Returning the plain access key with **no** session token is not a way out
either — `io.unitycatalog.hadoop.internal.auth.AwsCredential` asserts one is
present, and the client fails with `IllegalArgumentException: AWS session
token is missing` before a request ever reaches R2.

So `stacks/unity-catalog/credentials/R2TemporaryCredentialGenerator.java`
mints real ones, using [Cloudflare's local signing
scheme](https://developers.cloudflare.com/r2/api/s3/temporary-credentials/):
an HS256 JWT signed with the parent secret, whose SHA-256 hex digest is the
temporary secret and whose `base64("jwt/" + jwt)` is the session token. A
fresh token per call, scoped down to `object-read-only` when the request
only needs `SELECT`.

**Each token is confined to the locations the request named.** Without that,
a client that asked for one table would receive a token good for the entire
data lake — Unity Catalog's own STS generator narrows the same way. The JWT
carries two entries per location, and both are needed:

| Claim | Value | Why |
|---|---|---|
| `paths.prefixPaths` | `data/tbl/` | The trailing slash is what stops it. Granted `data/tbl`, the token can still write `data/tbl2/leak.txt` — R2 matches the prefix as a string and the sibling table starts with it. |
| `paths.objectPaths` | `data/tbl` | S3A's `getFileStatus` HEADs the bare key to decide whether the location exists, and that key is not under `data/tbl/`. A prefix-only grant fails `CREATE TABLE` with `AccessDeniedException … 403` before anything is written. |

Both measured against the live bucket. With the pair, the HEAD answers 404
(absent, not forbidden), LIST and writes inside succeed, and the neighbouring
table stays denied.

One non-obvious piece of configuration comes with it. A bucket entry is
dropped unless **either** `bucketPath` + `region` + `awsRoleArn` **or**
`accessKey` + `secretKey` + `sessionToken` is complete — and
`credentialGenerator` does not count towards either triple
(`ServerProperties.getS3Configurations`). The appended block therefore
carries a placeholder role ARN that is never dereferenced, purely to satisfy
that gate.

### The `unity` catalog is created for you

A fresh PostgreSQL metastore starts empty, and `spark-defaults.conf` names a
catalog called `unity`. Without something to bridge that, the first query on a
new deployment fails with `404 CATALOG_NOT_FOUND — Catalog not found: unity`
while the container is healthy and the API answers.

The services-configure phase creates it (`render_unity_catalog_hook` in
`src/nexus_deploy/services.py`), asking first so a re-run reports
`already-configured` rather than failing. It goes through
`docker exec unity-catalog wget` rather than host `curl`, because this API
publishes no port and the image carries no `curl`.

Worth knowing if you compare against upstream: their image ships a
pre-populated H2 metastore with sample catalogs, so this gap does not appear
until the metastore is switched to PostgreSQL.

### The custom image

`stacks/unity-catalog/Dockerfile` adds exactly one compiled class to
upstream's image. Everything else it needs is already there: the PostgreSQL
JDBC driver 42.7.12 is on the server classpath as shipped, and Jackson is a
compile dependency of the server itself.

The class reaches the classpath without rebuilding the server, because the
launcher runs `java -cp $(cat server/target/classpath)` — the classpath is a
*file*, and the image appends one entry to it.

**No configuration is bind-mounted.** A single-file bind mount pins the
inode, and the deploy's rsync replaces files rather than rewriting them, so
the container would serve the copy it saw at creation time for as long as it
lived — a bug this project already paid for on Spark. Mounting the whole
directory is Spark's fix and is not available here, because
`/home/unitycatalog/etc/conf` also holds `certs.json` and the token-signing
keys. Instead the static half is baked into the image and `entrypoint.sh`
writes the per-deployment half at start.

## Debugging

```bash
# Is the server answering? This is the healthcheck, run by hand.
# Only -q and -O are used: busybox wget is not GNU wget and its flag set
# is narrower. Exit 0 means a 2xx.
ssh nexus "docker exec unity-catalog wget -q -O /dev/null http://localhost:8080/api/2.1/unity-catalog/catalogs && echo UP || echo DOWN"

# What is registered?
ssh nexus "docker exec unity-catalog wget -qO- http://localhost:8080/api/2.1/unity-catalog/catalogs"

# Did the UI reach the server? It looks for the host `server`, via alias.
ssh nexus "docker logs unity-catalog-ui 2>&1 | tail -30"

# Is the metastore reachable, and does it hold the catalog tables?
ssh nexus "docker exec unity-catalog-db psql -U nexus-unitycatalog -d unitycatalog -c '\\dt'"

# What did the entrypoint actually write? (No password is printed —
# hibernate.properties is 0600 and holds one, so this reads the other file.)
ssh nexus "docker exec unity-catalog cat /home/unitycatalog/etc/conf/server.properties"
```

Two things about this image are worth knowing before debugging it, because
both produced a stack that looked broken from outside while the server
itself was fine.

**There is no `curl` in the image.** The runtime stage of upstream's
Dockerfile is bare `alpine:3.20` plus `apk add bash` and a copied JRE. A
`curl` probe exits 127 every time, so a curl-based healthcheck can never
pass — and because the UI waits on `condition: service_healthy`, it never
starts and the tunnel answers **502 Bad Gateway** for a stack whose API is
running normally. Use `wget`, which busybox provides.

**Paths are under `/home/unitycatalog`, not `/opt`.** The Dockerfile sets
`ARG HOME="/home/unitycatalog"`, copies `bin/` and `etc/` there and makes
it `WORKDIR`. Anything bind-mounted under `/opt/unitycatalog` is not an
error — it simply lands where nothing reads it, so a config file mounted
there is ignored in silence and a volume mounted there persists an empty
directory.

**`hibernate.properties` has no environment override.** Unlike
`server.properties` — whose `getProperty` checks system properties and then
the environment before the file — `HibernateConfigurator` reads the path
directly. That asymmetry is the whole reason `entrypoint.sh` exists: the
metastore DSN can only be delivered as a file.

Upstream defaults to an H2 file under `/home/unitycatalog/etc/db`. This
stack points Hibernate at PostgreSQL instead, because `pg_dump` is what
carries the catalog across a rebuild teardown — the same path Gitea and
Dify already use in `s3_restore.standard_targets()`. An rsync of a live H2
file can capture a torn state and has nothing to verify it against.

## Related

- [Lakekeeper](./lakekeeper.md) — Iceberg REST Catalog, independent of this one
- [Marquez](./marquez.md) — lineage rather than cataloguing; what *happened* to a dataset, not what it *is*
- [OpenMetadata](./openmetadata.md) — discovery and governance over a catalog
- [Unity Catalog documentation](https://docs.unitycatalog.io)
