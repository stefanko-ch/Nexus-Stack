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
- **`dbt` (core + postgres + duckdb adapters), DuckDB CLI, Jupyter, plus `psql` client pre-installed** in the auto-activated venv at `~/.nexus-venv` (no Postgres SERVER — that's a separate Nexus-Stack stack; see "Pre-installed data tooling" below)

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

The code-server image (`stacks/code-server/Dockerfile`) ships with a Python virtual environment at **`/home/coder/.nexus-venv`** that's auto-activated in every terminal you open. Inspired by [stefanko-ch/dbt_codespace_demo](https://github.com/stefanko-ch/dbt_codespace_demo)'s devcontainer, adapted for Nexus-Stack:

| Tool | Version | Purpose |
|---|---|---|
| `dbt-core` | latest from PyPI | Data build tool engine |
| `dbt-postgres` | latest from PyPI | Adapter for the Nexus-Stack postgres stack |
| `dbt-duckdb` | latest from PyPI | Adapter for local DuckDB targets |
| `jupyter` + `jupysql` | latest | SQL magic cells in notebooks (`%sql`, `%%sql`) |
| `polars` | latest | Fast Rust-backed dataframes |
| `plotly` | latest | Charting |
| `duckdb` (Python) | latest | Python bindings (separate from the CLI binary) |
| `duckdb` CLI | latest from GitHub releases | Interactive SQL shell (`duckdb my.db`) |
| `psql` | Debian-bookworm pkg | PostgreSQL CLI for testing dbt-postgres connections |

**Version stability note:** all Python packages above + the DuckDB CLI are pulled at **latest** on every image rebuild. Trade-off: stays current with security fixes and new features, but new minor/major versions may introduce breaking changes mid-semester if you trigger a rebuild during a course run. If you want reproducibility for a specific semester, add explicit constraints in `stacks/code-server/Dockerfile` (e.g. `dbt-core>=1.9,<1.10`) and rebuild — the image then locks the venv contents at those versions until you change them again.

The venv is **image-baked** at `/home/coder/.nexus-venv` — not in your workspace. So `dbt` works immediately when you open a terminal:

```bash
# In code-server's terminal — venv is already active
(.nexus-venv) coder@code-server:~$ dbt --version
Core: 1.x  (latest from PyPI at image build time)
Plugins: postgres 1.x, duckdb 1.x

(.nexus-venv) coder@code-server:~$ duckdb
v1.x.x ...
D
```

If you want a per-project venv (e.g. for additional deps), create your own next to your dbt project — students typically just use the pre-installed `.nexus-venv` for class material.

Not pre-installed (intentionally):
- `dbt-metabase` — Metabase runs as a separate Nexus-Stack stack; add it to a per-project venv if you need it
- `dbt-bigquery` / `dbt-snowflake` / other cloud adapters — out of scope for a self-hosted classroom setup
