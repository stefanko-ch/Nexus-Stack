---
title: "Streamlit"
---

## Streamlit

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)

**One server, every app**

Streamlit turns a Python script into an interactive web app — inputs, tables and charts, no frontend code. This stack runs a launcher as its entrypoint, so adding an app means adding a file, not a service.

| Setting | Value |
|---------|-------|
| Host Port | `8502` (container `8080`; 8501 is Streamlit's default and belongs to `dify` here) |
| Suggested Subdomain | `streamlit` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [streamlit.io](https://streamlit.io) |
| Source | [GitHub](https://github.com/streamlit/streamlit) |
| Image | `nexus-streamlit:1.64.0` — built from `python:3.13-slim`, see below |

### Where apps come from

Streamlit runs exactly one entrypoint script per process. Here that script is `Home.py`, a launcher: it walks two sources, builds an `st.Page` for each `.py` file, and passes the result to `st.navigation`, which draws the sidebar.

| Source | Path in the container | Where it lives |
|---|---|---|
| Examples | `/srv/apps` | `stacks/streamlit/apps/` in the deployment repository, mounted read-only |
| Workspace | `/srv/workspace/<repo>/streamlit` and `/srv/workspace/<repo>/nexus_seeds/streamlit` | the Forgejo workspace repository, cloned when the stack starts |

**Your own app, end to end:**

1. Commit a `.py` file to `streamlit/` in the workspace repository.
2. Restart the Streamlit stack from the Control Plane. The entrypoint clones on first start and `git pull --ff-only`s on every later one.
3. Refresh the browser — the walk runs on every rerun, so the new page appears in the sidebar without a redeploy.

Files and directories whose name starts with `_` are treated as helper modules and are not listed, the same convention the marimo seeds use.

### Why only two directories of the workspace are scanned

The workspace repository also holds Kestra flows, marimo notebooks and dbt models. A recursive scan of the whole clone would list every `.py` file in it as a Streamlit app and then fail the moment somebody clicked one. So the clone deliberately lands **outside** the scan root, and only `streamlit/` and `nexus_seeds/streamlit/` inside it are read.

### There is no official image

Docker Hub has no `streamlit/streamlit` — the repository does not exist, and upstream's deployment guide tells you to write a Dockerfile. `stacks/streamlit/Dockerfile` is that file: `python:3.13-slim`, plus Streamlit and three packages an app here is likely to want.

| Package | Why |
|---|---|
| `duckdb` | reading Parquet and CSV off the datalake without a warehouse |
| `plotly` | charts beyond `st.line_chart` |
| `psycopg2-binary` | the shared PostgreSQL |
| `git` | the workspace clone |

pandas, numpy, altair and pyarrow arrive as Streamlit's own dependencies. Installing any of this at container start would mean every restart waits on PyPI.

### The shipped example

`Warehouse explorer` lists the tables in the shared PostgreSQL, runs a query and charts the numeric columns. It exists so a fresh Streamlit is not an empty page, and so the connection to the `postgres` stack is demonstrated once instead of rediscovered in every app.

Its connection is opened read-only, which stops an accident rather than an attacker:

```
cannot execute UPDATE in a read-only transaction
```

That is a session **default**, not a guarantee — anyone typing SQL can lift it with `SET default_transaction_read_only = off`, measured. It is the right level for this stack: [Adminer](./adminer.md) and [CloudBeaver](./cloudbeaver.md) already give the same audience unrestricted writes, and Cloudflare Access is what decides who reaches any of them. An app that needs a real boundary should open its own connection as a role with `SELECT` only.

### Authentication

None of its own. Cloudflare Access is the gate, as with every other stack here. Streamlit's XSRF protection stays on; `STREAMLIT_SERVER_ENABLE_CORS` is off because the tunnel terminates TLS and rewrites nothing useful for an origin check.

Anything on `app-network` can reach port 8080 directly.

### Related

- [Marimo](./marimo.md) — reactive notebooks, also deployable as apps
- [Jupyter](./jupyter.md) — the exploratory half of the same workflow
- [Superset](./superset.md), [Metabase](./metabase.md) — dashboards you configure rather than write
- [Forgejo](./forgejo.md) — the workspace repository this stack clones
