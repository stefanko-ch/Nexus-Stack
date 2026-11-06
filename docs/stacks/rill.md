---
title: "Rill"
---

## Rill

![Rill](https://img.shields.io/badge/Rill-1E40AF?logoColor=white)

**Fast BI dashboards on DuckDB**

Rill builds dashboards straight from data files. A project holds sources (Parquet, CSV, S3, PostgreSQL), SQL models on top of them, a metrics view that names dimensions and measures, and an explorable dashboard generated from it. An embedded DuckDB computes everything, and every part is a file in the project.

| Setting | Value |
|---------|-------|
| Default Port | `9009` (bound to `127.0.0.1` on the host) |
| Suggested Subdomain | `rill` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | None — Rill Developer has no accounts |
| Persistence | Docker volume `rill-home` (see [Persistence](#persistence)) |
| Website | [rilldata.com](https://www.rilldata.com) |
| Source | [GitHub](https://github.com/rilldata/rill) |

### Rill next to Metabase and Superset

[Metabase](metabase.md) and [Superset](superset.md) are for shared reporting on a database. Rill is for the exploratory side: point it at a Parquet file and slice it in seconds. Because a project is plain files, it can live in Git next to the dbt or SQLMesh models that produce its data.

### First steps

The stack starts Rill Developer on an empty project. In the UI, add a source:

- **A file in S3-compatible storage** — MinIO, Garage or SeaweedFS from this stack. Give Rill the bucket URL and credentials in the source dialog.
- **A public URL** — any HTTPS link to a CSV or Parquet file.
- **PostgreSQL** — for example the shared `postgres` stack at `postgres:5432`.

Then generate a model and a metrics view from the source, and Rill builds the dashboard.

### Authentication

Rill Developer has no login. Anyone who passes Cloudflare Access can open and change the project. It is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`, which keeps it from ever being made public or given a firewall rule.

### Persistence

The project is `/home/rill/project`, inside the `rill-home` volume. The volume is mounted at the home directory rather than at the project, because the image owns `/home/rill` as its `rill` user (1001). A fresh named volume takes over that owner. Mounted at a path the image lacks, it would be root's, and Rill could not write.

- **`rebuild` (default): the project does not survive a teardown.** Rill is not in the R2 backup list, so the volume is destroyed with the server. Keep the project in a Git repository (Forgejo) and clone it back.
- **`snapshot`: the project survives**, because the whole disk is imaged.

### Architecture

The image is published for `linux/amd64` only. The default servers are x86 (`cx43`), so it runs natively. On an ARM server (`cax*`) it would need amd64 emulation (binfmt/QEMU), which the deploy does not set up. Use an x86 server for Rill.
