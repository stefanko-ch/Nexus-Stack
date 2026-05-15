---
title: "code-server"
---

## code-server

![code-server](https://img.shields.io/badge/code--server-007ACC?logo=visualstudiocode&logoColor=white)

**VS Code in the browser, pre-loaded with dbt + DuckDB**

Run VS Code on a remote server and access it through the browser. Provides a consistent development environment accessible from any device. Features include:
- Full VS Code experience in the browser
- Extension marketplace support
- Integrated terminal
- Git integration
- Multi-language support
- **dbt (multi-adapter) + JupyterLab pre-installed** in the auto-activated venv at `/opt/nexus-venv`, with the **`duckdb` CLI and `psql` client available system-wide** (apt/binary, not in the venv). No Postgres SERVER — that's a separate Nexus-Stack stack. See "Pre-installed data tooling" below for the full matrix.

| Setting | Value |
|---------|-------|
| Default Port | `8100` |
| Suggested Subdomain | `code` |
| Public Access | No (development environment) |
| Website | [coder.com](https://coder.com) |
| Source | [GitHub](https://github.com/coder/code-server) |

### Usage

1. Enable the code-server service in the Control Plane
2. Access `https://code.YOUR_DOMAIN`
3. Authentication is handled by Cloudflare Access (no additional password)
4. Files are persisted in a Docker volume (`code-server-data`)

### Infisical secrets

Secrets stored in Infisical are auto-synced into the code-server container's env on every spin-up (issue #496). Reference them in scripts / dbt profiles / notebook cells exactly as named in Infisical — no manual export step needed:

```bash
# In code-server's terminal — presence check (never echo a secret value,
# scrollback/copy-paste leakage):
[ -n "$POSTGRES_PASSWORD" ] && echo "POSTGRES_PASSWORD is set"

# psql: libpq reads PGPASSWORD (not POSTGRES_PASSWORD), so either
# pass the value inline for one command…
PGPASSWORD="$POSTGRES_PASSWORD" psql -h postgres -U nexus-postgres -d postgres

# …or export it once per session for repeated invocations.
export PGPASSWORD="$POSTGRES_PASSWORD"
psql -h postgres -U nexus-postgres -d postgres
```

```python
# In a Python file or Jupyter cell:
import os
pg_password = os.environ["POSTGRES_PASSWORD"]
r2_key = os.environ["R2_ACCESS_KEY"]
```

```yaml
# In ~/.dbt/profiles.yml:
my_postgres:
  target: dev
  outputs:
    dev:
      type: postgres
      host: postgres
      port: 5432
      user: nexus-postgres
      password: "{{ env_var('POSTGRES_PASSWORD') }}"
      dbname: postgres
      schema: dbt_dev
      threads: 4
```

The sync writes to a dedicated `.infisical.env` file (not `.env`) so secret keys can't accidentally collide with Compose's `${VAR}` interpolation. Multi-line values (e.g. PEM keys) are skipped with a warning — they need a different transport mechanism (mount-as-file). Re-running spin-up after editing a secret in Infisical refreshes the value automatically; code-server restarts to pick up the new env.

**Not covered by this sync:** Databricks credentials (`databricks_host` / `databricks_token`) live in Cloudflare KV via the Control Plane's Databricks page, not in Infisical — see the Databricks caveat under "Pre-installed data tooling" below for the manual steps to wire them into `~/.dbt/profiles.yml`.

### Pre-installed data tooling

The code-server image (`stacks/code-server/Dockerfile`) ships with a Python virtual environment at **`/opt/nexus-venv`** that's auto-activated in every terminal you open. Inspired by [stefanko-ch/dbt_codespace_demo](https://github.com/stefanko-ch/dbt_codespace_demo)'s devcontainer, adapted for Nexus-Stack:

**In the `/opt/nexus-venv` Python venv** (auto-activated in every terminal):

| Tool | Version | Purpose |
|---|---|---|
| `dbt-core` | latest from PyPI | Data build tool engine |
| `dbt-postgres` | latest from PyPI | Adapter for the Nexus-Stack postgres stack |
| `dbt-duckdb` | latest from PyPI | Adapter for local DuckDB targets |
| `dbt-clickhouse` | latest from PyPI | Adapter for the Nexus-Stack clickhouse stack (official `clickhouse/clickhouse-server` image) |
| `dbt-spark` | latest from PyPI | Adapter for **external** Spark clusters (Thrift / ODBC / session modes). See "Spark caveat" below — not pre-wired to the Nexus-Stack spark stack. |
| `dbt-trino` | latest from PyPI | Adapter for the Nexus-Stack trino stack (official `trinodb/trino` image; catalogs: clickhouse + postgresql) |
| `dbt-databricks` | latest from PyPI | Adapter only — see "Databricks caveat" below. The adapter is installed, but credentials are NOT auto-injected into code-server. |
| `jupyterlab` + `jupysql` | latest | Notebook UI + SQL magic cells (`%sql`, `%%sql`) |
| `polars` | latest | Fast Rust-backed dataframes |
| `plotly` | latest | Charting |
| `duckdb` (Python) | latest | Python bindings (separate from the CLI binary below) |

**System binaries** (installed via apt / direct download into `/usr/local/bin`, not in the venv):

| Tool | Where | Purpose |
|---|---|---|
| `duckdb` CLI | `/usr/local/bin/duckdb` (latest from GitHub releases) | Interactive SQL shell — `duckdb my.db` works from any directory regardless of venv |
| `psql` | `postgresql-client` apt package from the base image's Debian suite | PostgreSQL CLI for testing dbt-postgres connections + ad-hoc queries |

**Spark caveat:** `dbt-spark` is installed but the Nexus-Stack `spark` stack is **not** an out-of-the-box dbt-spark target. The Nexus-Stack Spark deployment exposes a Spark master + Spark Connect endpoint (`sc://spark-connect:15002`, consumed by PySpark in Marimo) — but dbt-spark does not support the Spark Connect protocol. There is also no Hive Thrift Server in the spark stack, and this code-server image deliberately omits local PySpark + JDK, so `method: session` needs extra setup. The adapter is there for operators who connect dbt to an **external** Spark cluster with a Thrift / ODBC endpoint they manage themselves. There is no out-of-the-box dbt path to data that lives only on the Nexus-Stack Spark stack — for SQL workloads against other in-stack data sources (postgres, clickhouse, DuckDB files), use the matching adapter directly.

**Databricks caveat:** `dbt-databricks` is installed, but the adapter alone does not give you authenticated access. The Nexus-Stack Databricks integration (Control Plane → Databricks page → KV-stored `databricks_host` + `databricks_token`; `/api/databricks-sync` worker) pushes Infisical secrets *into* a Databricks scope so notebooks running **on** Databricks can read them — it does **not** inject `databricks_host` / `databricks_token` into code-server (or any local stack). To use `dbt-databricks` here, save host + token in the Control Plane's Databricks page, then add them to `~/.dbt/profiles.yml` manually (copy from the Control Plane's KV view).

**Why `/opt/` instead of `~`?** code-server's `docker-compose.yml` mounts `code-server-data:/home/coder` as a persistent volume. Anything the image puts at `/home/coder/<X>` is **masked** by that volume on every container start, so a rebuilt image's freshly-installed venv would never reach an existing volume — students would be stuck on whatever version was installed when their volume was first created. Putting the venv at `/opt/nexus-venv` keeps it outside the volume mount: every image rebuild guarantees the latest venv reaches every container, fresh or not. The auto-activation is appended to `/etc/bash.bashrc` (system-wide, also image-baked) for the same reason — `/home/coder/.bashrc` would be masked.

**Version stability note:** all Python packages above + the DuckDB CLI are pulled at **latest** on every image rebuild. Trade-off: stays current with security fixes and new features, but new minor/major versions may introduce breaking changes mid-semester if you trigger a rebuild during a course run. If you want reproducibility for a specific semester, add explicit constraints in `stacks/code-server/Dockerfile` (e.g. `dbt-core>=1.9,<1.10`) and rebuild — the image then constrains the venv contents to that range until you change them again. Note: range constraints don't fully lock — patch releases and transitive dependencies can still drift between rebuilds. For a fully reproducible venv, use exact pins (`==1.9.7`) or a `constraints.txt` / lock file passed to `uv pip install`.

The venv is **image-baked** at `/opt/nexus-venv` — not in your workspace. So `dbt` works immediately when you open a terminal:

```bash
# In code-server's terminal — venv is already active
(nexus-venv) coder@code-server:~$ dbt --version
Core: 1.x  (latest from PyPI at image build time)
Plugins: postgres 1.x, duckdb 1.x, clickhouse 1.x, spark 1.x, trino 1.x, databricks 1.x

(nexus-venv) coder@code-server:~$ duckdb
v1.x.x ...
D
```

If you want a per-project venv (e.g. for additional deps), create your own next to your dbt project — students typically just use the pre-installed `/opt/nexus-venv` for class material.

Not pre-installed (intentionally):
- `dbt-metabase` — Metabase runs as a separate Nexus-Stack stack and serves dashboards; the `dbt-metabase` package is a *separate* tool that pushes dbt model docs/exposures into Metabase. Add it to a per-project venv if you want that sync.
- `dbt-bigquery` / `dbt-snowflake` / `dbt-redshift` — cloud-only, no Nexus-Stack equivalent.
- `dbt-fabric` / `dbt-sqlserver` — Azure / Microsoft Stack, out of scope for a self-hosted classroom.
- `dbt-athena` — AWS-specific.
- `pyspark` + JDK — large (~300 MB combined); deliberately not in this image. dbt-spark's `session` mode needs them; if you want dbt-spark against a local-process Spark, add to a per-project venv (and apt-install a JDK). For PySpark notebook workflows, the Marimo + Jupyter stacks already provide Spark Connect plumbing (sc://spark-connect:15002) and are the recommended path.
