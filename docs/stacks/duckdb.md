---
title: "DuckDB"
---

## DuckDB

![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?logo=duckdb&logoColor=black)

**One DuckDB database that many clients can use at once.**

DuckDB is normally embedded: each process opens its own database file, and only one process may open a file for writing. [DuckDB 2.0](https://duckdb.org/2026/08/17/duckdb-20-highlights) (released 21 October 2026, a long-term-support release) added a server mode. The [Quack protocol](https://duckdb.org/docs/2.0/quack/overview) lets one DuckDB process serve its database to other DuckDB processes over HTTP.

This stack runs that server with one persistent database file. Notebooks, scripts and flows attach to it as a remote catalog and share the same tables. Filters and aggregates on those tables run on the server, and only the results travel back.

| Setting | Value |
|---------|-------|
| Internal address | `quack:duckdb:9494` (plain HTTP on `app-network`) |
| Host port | `127.0.0.1:9494`, loopback only, for SSH forwarding |
| Subdomain | None. The stack is internal-only (see [Why there is no subdomain](#why-there-is-no-subdomain)) |
| Token | Infisical, `/duckdb/DUCKDB_QUACK_TOKEN` |
| Database file | `/data/nexus.duckdb` in the `duckdb-data` volume |
| Memory | Container limit 2 GB, DuckDB `memory_limit` 1536 MB, spill to `/data/tmp` |
| Docker image | [`duckdb/duckdb`](https://hub.docker.com/r/duckdb/duckdb), pinned to `2.0.0`, amd64 + arm64 |
| Licence | MIT |

### Clients must be DuckDB 2.0

A DuckDB 1.x client cannot attach to this server. Tested against `duckdb/duckdb:2.0.0`:

| Client | Result |
|---|---|
| `duckdb==2.0.0` (Python), DuckDB 2.0.0 CLI | Attaches, reads, writes |
| `duckdb==1.5.5` | `Serialization Error: Failed to deserialize: expected end of object, but found field id: 2` |
| `duckdb==1.5.2` | `Extension "…/quack.duckdb_extension" not found` |

So which stacks can talk to the server today depends on the DuckDB version each one carries:

| Where | DuckDB | Works? |
|---|---|---|
| A container running `duckdb/duckdb:2.0.0` (including this one, see below) | 2.0.0 | Yes |
| Your laptop, through SSH forwarding | Whatever you install. Use 2.0 | Yes, with 2.0 |
| Jupyter | Whatever the upstream `pyspark-notebook` image carries, if any. Not pinned here | After `%pip install duckdb==2.0.0` in the notebook |
| code-server | The CLI comes from GitHub's `releases/latest` at image build time (`stacks/code-server/Dockerfile`), and the venv's `duckdb` is unpinned | Check with `duckdb --version`. An image built before 21 October 2026 is 1.x |
| Marimo | 1.5.2, from the `marimo[sql]` base image | **No.** See [Marimo](#marimo-not-yet) |
| Streamlit | Pinned to `1.5.5` in `stacks/streamlit/Dockerfile` | No |

### Connecting

The token is the only credential. When Jupyter, Marimo, code-server or Kestra is enabled and the spin-up's secret sync succeeds, the token reaches that container as the environment variable `DUCKDB_QUACK_TOKEN`, because the sync copies every Infisical folder into it. The sync skips a target that is disabled, and on an Infisical outage it leaves the previous environment file in place. If the variable is missing, or anywhere else, take the token from Infisical.

**SQL (any DuckDB 2.0 client on `app-network`)**

```sql
-- The token goes into a secret scoped to the server's URI, which DuckDB
-- recommends over writing it into the ATTACH line.
CREATE SECRET duckdb_server (
    TYPE quack,
    TOKEN '<token>',
    SCOPE 'quack:duckdb:9494'
);

-- DISABLE_SSL is needed: the client assumes HTTPS for every host except
-- localhost, and the server speaks plain HTTP on the Docker network.
ATTACH 'quack:duckdb:9494' AS srv (DISABLE_SSL true);

CREATE TABLE srv.events AS SELECT * FROM read_parquet('…');
SELECT count(*) FROM srv.events;

-- Or make the server the default catalog for the session:
CONNECT srv;
SELECT count(*) FROM events;
DISCONNECT;
```

**Python**

```python
import os
import duckdb

con = duckdb.connect()
token = os.environ["DUCKDB_QUACK_TOKEN"].replace("'", "''")
con.execute(f"CREATE SECRET duckdb_server (TYPE quack, TOKEN '{token}', SCOPE 'quack:duckdb:9494')")
con.execute("ATTACH 'quack:duckdb:9494' AS srv (DISABLE_SSL true)")

con.sql("SELECT count(*) FROM srv.events").pl()  # relation API works on qualified names
```

**From the server container itself.** The `duckdb` container carries the CLI, and from inside it the server is `localhost`. Local URIs default to plain HTTP, so you do not need `DISABLE_SSL`:

```bash
ssh nexus
docker exec -it duckdb /duckdb
```

```sql
ATTACH 'quack:localhost:9494' AS srv (TOKEN '<token>');
```

You cannot open `/data/nexus.duckdb` directly from there. The server process holds the file's write lock.

**From your laptop.** The port is published on `127.0.0.1` only, so forward it over the [SSH tunnel](../admin-guides/ssh-access.md):

```bash
ssh -N -L 9494:localhost:9494 nexus
```

Then, in a local DuckDB 2.0:

```sql
ATTACH 'quack:localhost:9494' AS srv (TOKEN '<token>');
```

### Not yet, over Quack

These were all measured against 2.0.0. They are worth knowing before you port code that works locally:

- **Prepared-statement parameters fail.** `con.execute("INSERT INTO srv.t VALUES (?)", [1])` returns *Values were not provided for the following parameters: 1*. The same happens after `CONNECT`. The workaround is to write values into the SQL text, and that is safe only for constants your own code controls. Do not treat hand-escaping as a replacement for parameters when the input is untrusted: a quoting mistake runs as SQL with the token's full privileges. For data from outside, load it into a local table first (for example from a DataFrame) and `INSERT INTO srv.t SELECT … FROM local_table`, so the values never pass through the SQL text.
- **The Python relation API refuses while `CONNECT`-ed.** `con.sql(…).pl()` and `.df()` fail with *materialize() is not available while CONNECT-ed; DISCONNECT first*. `con.execute(…).fetchall()` works. With qualified `srv.` names and no `CONNECT`, the relation API works.
- **A half-read remote result blocks the connection.** After `con.execute("SELECT …").fetchone()` on a server table, the next query on that connection fails with *connection has an unfinished result from execute()*. Read results to the end with `fetchall()`, or use a second cursor. A local connection does not behave this way.
- **`ATTACH` reads the remote catalog once.** A table that another client creates later is visible after `DETACH` and a fresh `ATTACH`. Upstream also notes that one remote table definition that fails to bind fails the whole `ATTACH`.

Concurrent writes from separate clients work. Four Python clients inserting into one table at the same time all committed, and the row count matched.

### Marimo: not yet

Marimo's base image brings DuckDB 1.5.2, which cannot attach. Replacing it with 2.0.0 is one `pip install`, and it works for DuckDB itself: both the existing `Getting_Started_DuckDB.py` seed and `mo.sql` ran unchanged. The problem is Ibis, which the Marimo image pins at 10.5.0 for its Spark path:

- Ibis 10.5.0's DuckDB backend fails to import under DuckDB 2.0 (`module 'duckdb' has no attribute 'functional'`). That backend is also Ibis's default for `ibis.memtable(...)`, so any Ibis code that never names Spark breaks. The `ibis.pyspark` path still imports.
- Ibis 12.0.0 works with DuckDB 2.0, but its `pyspark` extra requires `pyspark<4.1,>=3.5`. Installing it moved PySpark from the pinned `4.2.0` to `4.0.5`, which breaks the Spark Connect wire compatibility the image's pins exist to protect.

Bumping Marimo is therefore its own change, with a Spark Connect test, rather than part of this stack.

### Why there is no subdomain

Quack is HTTP, so in principle it could go through the Cloudflare Tunnel like any web service. In practice its clients are DuckDB processes, not browsers, and Cloudflare Access would stop every one of them at the email-OTP page. There is no `tcp_ports` entry either. That would open the Hetzner firewall, and the token travels in plain HTTP on this port.

The same reasoning puts the compose port mapping on `127.0.0.1:9494` rather than `9494`. Inside the container the server binds `0.0.0.0`, because other containers must reach it. The loopback mapping keeps it off the host's public interface, so the firewall is not the only thing between it and the internet. `tests/unit/test_stack_conventions.py` enforces the loopback binding.

### Security: the token is root

The server has one credential and no roles. Whoever holds the token can run any SQL the server can, including:

- reading and overwriting every table;
- reading and writing files inside the container (`COPY … TO '/data/…'`, `read_csv('/…')`), all verified over Quack;
- making outbound HTTP requests from the server (`read_csv('https://…')`), also verified.

Quack also supports [custom authentication and authorization functions](https://duckdb.org/docs/2.0/quack/reference) (`quack_authentication_function`, `quack_authorization_function`). This stack does not configure them.

If the token is empty, the deploy stops before the container starts. `src/nexus_deploy/service_env.py` raises with a pointer to `random_password.duckdb_quack_token`. Even if it did not, the server would not run open. `quack_serve` rejects a token shorter than four characters, and `-bail` stops the CLI on that error.

The compose command reads the token with `getenv()` inside the process, so it is not on the command line, where any user on the host could read it with `ps`. It is still in the container's environment. `docker inspect duckdb` shows it, as it shows every stack's `.env` values, so treat that output as secret-bearing. The command also selects only `listen_uri` from `quack_serve`. That function returns the token as a column, and the CLI would otherwise print it into the container log.

### How the container is put together

The image is distroless. It contains the `duckdb` binary and nothing else, not even `/bin/sh`. Each of three compose settings fixes a failure observed during testing:

| Setting | Without it |
|---|---|
| `stdin_open: true` | The CLI serves until stdin reaches EOF. A container's stdin is closed by default, so the server answered for a moment and the container exited with code 0 |
| `init: true` | The CLI ignores `SIGTERM` as PID 1, so every `docker stop` waited ten seconds and then sent `SIGKILL` mid-write. Under `tini` it stops in about 0.1 s, and every committed row is present after a restart |
| `-bail` | A failed `quack_serve` left the CLI idle on stdin: a running container that served nothing |

`HOME=/data` puts DuckDB's extension directory in the volume. The `quack` extension downloads from `extensions.duckdb.org` on first start and is reused afterwards, including by the healthcheck.

The healthcheck is a real authenticated round trip, not a port probe. A second DuckDB process runs `quack_query('quack:localhost:9494', 'SELECT 1', token = getenv('DUCKDB_QUACK_TOKEN'))`. It exits non-zero on a wrong token or an unreachable server.

DuckDB sizes its default `memory_limit` from the host's RAM, not from the container's cgroup. It reported 12.5 GiB inside a container capped far lower. The stack therefore sets `memory_limit = '1536MB'` under the 2 GB container limit, and gives queries a `temp_directory` in the volume to spill into.

### Persistence

The database lives in the `duckdb-data` volume:

- **Snapshot lifecycle** (`lifecycle_mode = snapshot`): the volume is part of the disk snapshot and survives teardown.
- **Rebuild lifecycle** (`lifecycle_mode = rebuild`): the volume is **not** in `s3_restore.standard_targets()`, so the database is gone after a teardown. Keep anything that matters in object storage as well. Writing it out with `COPY srv.my_table TO 's3://…' (FORMAT parquet)` is one line.

See [Snapshot lifecycle](../admin-guides/snapshot-lifecycle.md) for how the two modes differ.

A file written by DuckDB 2.0's default storage format cannot be opened by DuckDB 1.x. That matters only if you copy `nexus.duckdb` out of the volume and open it with an older client.

### Troubleshooting

```bash
ssh nexus "docker ps --filter name=^duckdb$"   # (healthy) means an authenticated round trip succeeded
ssh nexus "docker logs duckdb"                  # the startup line, or the error -bail stopped on
```

| Symptom | Cause |
|---|---|
| Container restarts, log shows `Quack server token must be at least 4 characters long` | `DUCKDB_QUACK_TOKEN` is empty in `stacks/duckdb/.env`. Normally the deploy refuses this before it gets here |
| Client: `Authentication failed` | Wrong token, or a secret whose `SCOPE` does not match the URI you attach |
| Client: `Serialization Error: Failed to deserialize` or `quack.duckdb_extension not found` | The client is DuckDB 1.x |
| Client: `SSL connect error … HTTP POST to 'https://duckdb:9494/quack'` | `DISABLE_SSL true` is missing. Non-local URIs default to HTTPS |
| First start is slow or fails offline | The `quack` extension downloads on first start. It needs outbound HTTPS to `extensions.duckdb.org` once per volume |
