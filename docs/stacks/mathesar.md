---
title: "Mathesar"
---

## Mathesar

![Mathesar](https://img.shields.io/badge/Mathesar-5EBA7D?logoColor=white)

**Spreadsheet-like interface for PostgreSQL**

Mathesar puts a spreadsheet view on real PostgreSQL schemas. Create tables and columns, edit records, follow foreign keys, and filter, group and save explorations, all without writing SQL. PostgreSQL's own roles and permissions sit underneath.

| Setting | Value |
|---------|-------|
| Default Port | `8119` (bound to `127.0.0.1` on the host; container port `8000`) |
| Suggested Subdomain | `mathesar` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | Admin `nexus-admin`, password generated per deployment (Infisical folder `mathesar`) |
| Persistence | Dedicated PostgreSQL (`mathesar-db`) in a Docker volume |
| Website | [mathesar.org](https://mathesar.org) |
| Source | [GitHub](https://github.com/mathesar-foundation/mathesar) |

### Mathesar next to NocoDB and pgAdmin

[NocoDB](nocodb.md) is a spreadsheet app with its own data model. [pgAdmin](pgadmin.md) and [CloudBeaver](cloudbeaver.md) are SQL clients. Mathesar is in between: a spreadsheet interface whose tables are ordinary PostgreSQL tables that any SQL client can read.

### Authentication

Mathesar asks for an admin account on its first page view, and whoever answers first gets it. `mathesar-init` creates the admin before the web server starts: username `nexus-admin`, password `MATHESAR_PASSWORD` from the Infisical folder `mathesar`. The web server waits for it, so that page is never reachable.

### First steps

1. Log in as `nexus-admin`.
2. **Connect Database** → **Create a New Database**. It is created on Mathesar's internal server (`mathesar-db`), so no credentials are needed. Sample schemas such as "Library Makerspace" or "Bike Shop" can be installed with it.
3. Create tables, or import a CSV, and work with them as a spreadsheet.

Other PostgreSQL servers in the stack are added with **Connect Database** → **Connect to an Existing Database**, for example the shared `postgres` (`postgres:5432`), [ParadeDB](paradedb.md) (`paradedb:5432`) or [TimescaleDB](timescaledb.md) (`timescaledb:5432`), with their credentials from Infisical.

### Persistence

Mathesar's settings and the databases created on `mathesar-db` are in the `mathesar-db-data` volume.

- **`rebuild` (default): the data does not survive a teardown.** Mathesar is not in the R2 backup list.
- **`snapshot`: the data survives**, because the whole disk is imaged.
