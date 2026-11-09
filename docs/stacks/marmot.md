---
title: "Marmot"
---

## Marmot

![Marmot](https://img.shields.io/badge/Marmot-8B5CF6?logoColor=white)

**Lightweight data catalog with lineage**

Marmot is a data catalog in one Go binary on PostgreSQL. It ingests assets from more than 70 sources, among them PostgreSQL, Kafka, dbt, Airflow and S3. On top it adds search, lineage, a glossary, ownership, and an MCP server for AI assistants. Next to [OpenMetadata](openmetadata.md) it shows the catalog idea at a fraction of the footprint.

| Setting | Value |
|---------|-------|
| URL | `https://marmot.<domain>` |
| In-cluster | `http://marmot:8080` (REST API, MCP server) |
| Login | `admin` |
| Credentials | Password generated per deployment (Infisical folder `marmot`) |
| Persistence | Docker volume `marmot-db-data` |
| Licence | MIT |
| Website | [marmotdata.io](https://marmotdata.io) |

### First steps

1. Open `https://marmot.<domain>` and log in as `admin` with `MARMOT_PASSWORD` from Infisical.
2. Under **Ingestion**, add a source, for example the [Postgres](postgres.md) stack at host `postgres`. Run it to pull in schemas and tables.
3. Search the catalog, open an asset for its schema and lineage, and add owners and glossary terms.

For scripts and the CLI, create an API key under your profile. The REST API is at `http://marmot:8080/api/v1/`.

### The admin password

Marmot creates an `admin` account with the password `admin`, and the first visitor would get it. `marmot-init` closes that:

- **On the first start** it logs in with `admin` and sets the generated password.
- **On later starts** it only checks that the generated password works.
- **If neither the generated nor the default password works,** it fails with a message instead of passing silently.

The init runs in a small Python container, because the Marmot image has only `wget`, which would put the password on a command line.

Tested:
- the default password was replaced on the first start;
- `admin`/`admin` was refused afterwards (`401`);
- anonymous API requests were refused (`401`);
- the init found the generated password in place after a restart.

**Not tried here:** ingesting a source.

### Settings

- **Anonymous browsing** is off.
- **Telemetry** is off. It is on by default.
- **Stored source credentials** are encrypted with a 32-byte key generated per deployment. Without it, Marmot refuses to start rather than store them in plain text.

Marmot exits when its database is not reachable at startup instead of retrying, so it waits for PostgreSQL's healthcheck.

### Resources

Marmot used about 90 MB and its PostgreSQL about 60 MB.

### Persistence

The catalog is in Marmot's PostgreSQL (`marmot-db-data`).

- **`rebuild` (default): it does not survive a teardown.** Marmot is not in the R2 backup list. Ingestion can rebuild most of it from the sources.
- **`snapshot`: it survives**, because the whole disk is imaged.
