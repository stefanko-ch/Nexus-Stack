---
title: "SQLMesh"
---

## SQLMesh

![SQLMesh](https://img.shields.io/badge/SQLMesh-6C47FF?logoColor=white)

**SQL transformations with plans, virtual environments and tests**

SQLMesh transforms data with SQL or Python models, like dbt, but it parses the SQL. That lets it:
- compute a **plan** of what a change affects before applying it;
- keep a cheap **virtual environment** per branch;
- backfill only the intervals that changed;
- run unit tests and audits on models.

This stack runs SQLMesh's browser IDE.

| Setting | Value |
|---------|-------|
| Default Port | `8116` (bound to `127.0.0.1` on the host) |
| Suggested Subdomain | `sqlmesh` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | None — the IDE has no accounts |
| Engine | DuckDB, inside the project directory |
| Persistence | Docker volume `sqlmesh-project` (see [Persistence](#persistence)) |
| Website | [sqlmesh.com](https://sqlmesh.com) |
| Source | [GitHub](https://github.com/TobikoData/sqlmesh) |

### The browser UI is deprecated upstream

On start, SQLMesh prints a warning: the browser UI will be removed in a future version, and the VS Code extension is the recommended way to work. The UI still ships and runs in the pinned `0.236.4`, which is why this stack offers it. When upstream removes it, the same project works from [code-server](code-server.md): `pip install "sqlmesh==0.236.4"` in a terminal, then `sqlmesh plan`, `sqlmesh run` and `sqlmesh test` there.

### First steps

On first start the stack creates SQLMesh's example project (`sqlmesh init duckdb`) in `/project`: three models (`seed_model`, `incremental_model`, `full_model`), a seed CSV, an audit and a test. An existing project is left alone.

In the IDE:
1. Open a model.
2. Change it and click **Plan**.
3. SQLMesh lists the directly and indirectly affected models before anything runs.
4. **Apply** runs the backfill into the `dev` environment, and **Promote** makes it production.

### SQLMesh next to dbt

dbt is in the [code-server](code-server.md) image. Both read SQL models from a project directory. The difference lies in what happens on a change: dbt rebuilds what you select, while SQLMesh compares the new version with the old and rebuilds only what changed, in an isolated environment. A course can run the same models through both.

### Image

SQLMesh publishes no Docker image. `stacks/sqlmesh/Dockerfile` builds one from `python:3.12-slim` with `sqlmesh[web]==0.236.4`, so it is arch-correct on amd64 and arm64. Other engines' extras are left out. `postgres`, for instance, needs a compiler and `pg_config` to build `psycopg2`.

### Authentication

The IDE has no login. Anyone who passes Cloudflare Access can edit and apply the project. SQLMesh is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`.

### Persistence

The project, including its DuckDB file, is in the `sqlmesh-project` volume.

- **`rebuild` (default): the project does not survive a teardown.** SQLMesh is not in the R2 backup list. Keep the project in Git (Forgejo).
- **`snapshot`: the project survives**, because the whole disk is imaged.
