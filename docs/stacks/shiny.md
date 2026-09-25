---
title: "Shiny Server"
---

## Shiny Server

![Shiny](https://img.shields.io/badge/Shiny-447099?logo=r&logoColor=white)

**R web applications, hosted the way Shiny Server already hosts them**

Shiny is R's framework for interactive web apps — reactive inputs, tables and plots written entirely in R. The R counterpart to the [Streamlit](./streamlit.md) stack.

| Setting | Value |
|---------|-------|
| Host Port | `3838` |
| Suggested Subdomain | `shiny` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [posit.co](https://posit.co/products/open-source/shinyserver/) |
| Source | [rocker/shiny](https://hub.docker.com/r/rocker/shiny) |
| Image | `nexus-shiny:4.6.1` — built from `rocker/shiny:4.6.1` |

### No launcher, because Shiny Server is one

Unlike Streamlit, Shiny Server already serves a *directory* of apps and renders an index of them — that is `site_dir` plus `directory_index on` in its shipped configuration. An app is a directory containing an `app.R`. So the only decision here is what ends up in that directory:

| Entry | Where it comes from |
|---|---|
| `01_hello/` … `11_timer/`, `sample-apps/` | the upstream image's own R teaching material, left in place |
| `examples/` | `stacks/shiny/apps/` in the deployment repository, mounted read-only |
| `workspace/` | a **symlink** to `shiny/` inside the Forgejo workspace clone |

The shipped `index.html` is removed on start, so the root serves the directory index instead of upstream's welcome page — which would otherwise hide every app behind a URL you had to know already.

**Your own app, end to end:**

1. Commit a directory with an `app.R` to `shiny/` in the workspace repository.
2. Restart the Shiny stack from the Control Plane. The entrypoint clones on first start and `git pull --ff-only`s on every later one, then refreshes the symlink.
3. Open `https://shiny.YOUR_DOMAIN/workspace/<your-app>/`.

### Only `shiny/` is linked in, and only when it exists

The clone lands in `/srv/workspace`, outside the served directory, and only its `shiny/` subdirectory is linked into the tree. `site_dir` also serves *static* files, so cloning the repository into it would publish every file in that repository — `.git` included — over HTTP.

The existence check on that symlink is not defensive padding. A **dangling** link takes down the whole index page, not just its own entry. With a repository that has no `shiny/` directory — which is every repository until somebody adds one — the root answered:

```
An error has occurred
Invalid application configuration.
ENOENT: no such file or directory, stat '/srv/shiny-server/workspace'
```

### amd64 only

Every `rocker/shiny` tag on Docker Hub lists a single architecture. That is fine for the server, which is x86 (`cx43`), but building this stack on an Apple Silicon laptop needs `--platform linux/amd64`.

### What the image adds

`git`, because the base image has none and the entrypoint clones the workspace repository. And five R packages — `DBI`, `RPostgres`, `ggplot2`, `dplyr`, `DT` — from a **dated** Posit Package Manager snapshot rather than its `latest`:

```
https://p3m.dev/cran/__linux__/noble/2026-09-01
```

p3m serves Ubuntu binaries for that release, so the install is a download rather than a compile — measured at 21 seconds for the whole layer — and the date pins what a rebuild gets.

Not added: `curl` and `wget`. The base image has neither, so the healthcheck uses `python3`, which it does have.

### The shipped example

`examples/warehouse_explorer` lists the tables in the shared PostgreSQL, runs a query and plots the first numeric column. Its connection sets `default_transaction_read_only`, so PostgreSQL itself refuses a write — verified:

```
Failed to fetch row : ERROR:  cannot execute UPDATE in a read-only transaction
```

That is a property of that example's connection, not of the stack. An app you write opens its own.

### Authentication

None of its own — Shiny Server's own auth is a Posit Connect feature, not an open-source one. Cloudflare Access is the gate, as with every other stack here. Anything on `app-network` can reach port 3838 directly.

### Related

- [Streamlit](./streamlit.md) — the same idea in Python
- [Superset](./superset.md), [Metabase](./metabase.md) — dashboards you configure rather than write
- [Forgejo](./forgejo.md) — the workspace repository this stack clones
