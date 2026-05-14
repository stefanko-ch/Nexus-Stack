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

### Pre-installed data tooling

The code-server image (`stacks/code-server/Dockerfile`) ships with a Python virtual environment at **`/opt/nexus-venv`** that's auto-activated in every terminal you open. Inspired by [stefanko-ch/dbt_codespace_demo](https://github.com/stefanko-ch/dbt_codespace_demo)'s devcontainer, adapted for Nexus-Stack:

**In the `/opt/nexus-venv` Python venv** (auto-activated in every terminal):

| Tool | Version | Purpose |
|---|---|---|
| `dbt-core` | latest from PyPI | Data build tool engine |
| `dbt-postgres` | latest from PyPI | Adapter for the Nexus-Stack postgres stack |
| `dbt-duckdb` | latest from PyPI | Adapter for local DuckDB targets |
| `dbt-clickhouse` | latest from PyPI | Adapter for the Nexus-Stack clickhouse stack |
| `dbt-spark` | latest from PyPI | Adapter for the Nexus-Stack spark stack (Thrift / Session / Connect modes) |
| `dbt-trino` | latest from PyPI | Adapter for the Nexus-Stack trino stack |
| `dbt-databricks` | latest from PyPI | Adapter for Databricks (uses the Nexus-Stack KV/secret-sync token plumbing) |
| `jupyterlab` + `jupysql` | latest | Notebook UI + SQL magic cells (`%sql`, `%%sql`) |
| `polars` | latest | Fast Rust-backed dataframes |
| `plotly` | latest | Charting |
| `duckdb` (Python) | latest | Python bindings (separate from the CLI binary below) |

**System binaries** (installed via apt / direct download into `/usr/local/bin`, not in the venv):

| Tool | Where | Purpose |
|---|---|---|
| `duckdb` CLI | `/usr/local/bin/duckdb` (latest from GitHub releases) | Interactive SQL shell — `duckdb my.db` works from any directory regardless of venv |
| `psql` | `postgresql-client` apt package from the base image's Debian suite | PostgreSQL CLI for testing dbt-postgres connections + ad-hoc queries |

**Why `/opt/` instead of `~`?** code-server's `docker-compose.yml` mounts `code-server-data:/home/coder` as a persistent volume. Anything the image puts at `/home/coder/<X>` is **masked** by that volume on every container start, so a rebuilt image's freshly-installed venv would never reach an existing volume — students would be stuck on whatever version was installed when their volume was first created. Putting the venv at `/opt/nexus-venv` keeps it outside the volume mount: every image rebuild guarantees the latest venv reaches every container, fresh or not. The auto-activation is appended to `/etc/bash.bashrc` (system-wide, also image-baked) for the same reason — `/home/coder/.bashrc` would be masked.

**Version stability note:** all Python packages above + the DuckDB CLI are pulled at **latest** on every image rebuild. Trade-off: stays current with security fixes and new features, but new minor/major versions may introduce breaking changes mid-semester if you trigger a rebuild during a course run. If you want reproducibility for a specific semester, add explicit constraints in `stacks/code-server/Dockerfile` (e.g. `dbt-core>=1.9,<1.10`) and rebuild — the image then locks the venv contents at those versions until you change them again.

The venv is **image-baked** at `/opt/nexus-venv` — not in your workspace. So `dbt` works immediately when you open a terminal:

```bash
# In code-server's terminal — venv is already active
(nexus-venv) coder@code-server:~$ dbt --version
Core: 1.x  (latest from PyPI at image build time)
Plugins: postgres 1.x, duckdb 1.x

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
- `pyspark` — large (~300 MB); not needed for dbt-spark (which uses Thrift/Session). If students write Spark code *outside* dbt, add `pyspark` to a per-project venv. (Marimo + Jupyter stacks already provide Spark Connect plumbing for their own notebooks.)
