---
title: "QuestDB"
description: "Time-series database with a built-in web console"
---

# QuestDB

![QuestDB](https://img.shields.io/badge/QuestDB-D14671?logo=questdb&logoColor=white)

Column-oriented time-series database with SQL on top and a web console
built in. It fills the one gap the other databases leave: ClickHouse is
OLAP, PostgreSQL and pg_ducklake are relational, RisingWave is streaming —
none of them is a time-series engine.

## Configuration

| Setting | Value |
|---|---|
| Subdomain | `questdb.<your-domain>` (web console) |
| Host port | `9013` → container `9000` |
| PostgreSQL wire | `questdb:8812` — internal only |
| InfluxDB line | `questdb:9009` — internal only |
| Public | No — Cloudflare Access (email OTP) |
| Data | Named volume `questdb-data` at `/var/lib/questdb` |

The console publishes on **9013** rather than 9000 because MinIO already
binds host 9000 for its S3 API. The container port stays at upstream's
default, so QuestDB's own documentation applies unchanged.

## Three protocols, which is most of the point

An existing client reaches QuestDB without new libraries:

- **PostgreSQL wire (8812)** — `psycopg2`, JDBC, `psql`, anything that
  speaks Postgres.
- **InfluxDB line (9009)** — Telegraf and Fluent Bit write to it with no
  new plugin.
- **REST / console (9000)** — SQL over HTTP, plus the UI.

Neither 8812 nor 9009 is published to the host. They are reachable at
`questdb:8812` and `questdb:9009` over `app-network`, which is where the
notebooks and Telegraf run. An external client would need a `tcp_ports`
entry so the firewall rule is managed and reset on teardown.

## Credentials

The **web console has no authentication** in the open-source build.
Cloudflare Access at the edge is the gate, the same model
[Lakekeeper](./lakekeeper.md), [Marquez](./marquez.md) and
[Unity Catalog](./unity-catalog.md) use.

The **PostgreSQL wire protocol does authenticate**, and its shipped
defaults are `admin` / `quest` — both published in QuestDB's own
`server.conf`. Both are overridden here:

| Secret | Value |
|---|---|
| `QUESTDB_PG_USERNAME` | `nexus-questdb` |
| `QUESTDB_PG_PASSWORD` | generated, in Infisical under `questdb` |

The port is not exposed to the internet, but it *is* on `app-network`
where every other stack can reach it, which is why the documented default
is replaced rather than tolerated.

QuestDB maps a config key to an environment variable as
`"QDB_" + key.replace('.', '_').toUpperCase()`, so `pg.user` becomes
`QDB_PG_USER`. That rule is in `ServerMain.propertyPathToEnvVarName`.

## Using it

From Jupyter, Marimo or code-server — any Postgres client works:

```python
import os
import psycopg2

conn = psycopg2.connect(
    host="questdb", port=8812,
    user="nexus-questdb",
    password=os.environ["QUESTDB_PG_PASSWORD"],
    dbname="qdb",
)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS readings (
        ts TIMESTAMP, sensor SYMBOL, value DOUBLE
    ) TIMESTAMP(ts) PARTITION BY DAY
""")
cur.execute("INSERT INTO readings VALUES (now(), 'sensor-1', 21.5)")
conn.commit()
```

`SYMBOL` and `TIMESTAMP(ts) PARTITION BY DAY` are QuestDB's own — the
first is an interned string column, the second designates the partitioning
timestamp. Ordinary Postgres DDL works too, but you give up the
time-series optimisations that are the reason to use this rather than the
PostgreSQL stack.

## Debugging

```bash
# Health, on the dedicated min server — it answers without touching the
# query engine, so a busy database does not report itself unhealthy.
ssh nexus "docker exec questdb curl -s -o /dev/null -w '%{http_code}\n' http://localhost:9003/status"

# Does the query engine answer? This hits the HTTP endpoint on 9000, not
# the PostgreSQL wire protocol — it proves the engine runs, nothing about 8812.
ssh nexus "docker exec questdb curl -s 'http://localhost:9000/exec?query=SELECT%201'"

# The PostgreSQL wire listener, for real. Needs a client, and the postgres
# stack ships psql; both containers are on app-network. Take the password
# from Infisical.
ssh nexus "docker exec -e PGPASSWORD='<from-infisical>' postgres \\
  psql -h questdb -p 8812 -U nexus-questdb -d qdb -c 'SELECT 1'"

# Disk: QuestDB memory-maps its column files, so growth is on the volume
ssh nexus "docker exec questdb du -sh /var/lib/questdb"
```

## Deliberate limitations

**No published port for 8812 or 9009.** Zero open ports is the project's
baseline; in-stack clients do not need them published.

**The console has no login.** That is the open-source build, not a
configuration choice here — authentication on the console is an
enterprise feature. Access is the gate; do not add a `tcp_ports` entry
for 9013.

**Memory is capped at 2g.** QuestDB memory-maps its column files, so
resident size tracks the working set rather than a configured heap. Raise
it in the compose file if a dataset outgrows the cap.

## Related

- [ClickHouse](./clickhouse.md) — OLAP, for wide analytical scans rather than time-series
- [PostgreSQL](./postgres.md) — relational; QuestDB speaks its wire protocol
- [Telegraf](./telegraf.md) — writes over the InfluxDB line protocol on 9009
- [QuestDB documentation](https://questdb.com/docs/)
