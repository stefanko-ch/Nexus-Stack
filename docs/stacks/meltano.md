## Meltano

![Meltano](https://img.shields.io/badge/Meltano-512EFF?logo=meltano&logoColor=white)

**Open-source CLI data integration platform for building modular data pipelines**

Meltano is a modular, open-source data integration platform that allows data teams to build, test, and deploy custom data pipelines. It is a CLI-only tool (the web UI was removed in Meltano v3.0). Features include:
- Modular architecture with Singer protocol support
- 500+ pre-built data connectors (Tap/Target plugins)
- dbt integration for transformations
- Version control friendly with Git-based configs
- State management for incremental loading
- Job scheduling and orchestration via CLI

| Setting | Value |
|---------|-------|
| Internal Only | Yes (CLI access only) |
| Database | PostgreSQL 16 |
| Website | [meltano.com](https://meltano.com) |
| Source | [GitHub](https://github.com/meltano/meltano) |

### Architecture

The stack includes:
- **Meltano** - CLI application (runs as long-lived container)
- **PostgreSQL** - Database for metadata storage

### Configuration

Meltano uses PostgreSQL for metadata storage. All project data (pipelines, schedules, logs) is persisted in the `meltano-data` volume.

### Getting Started

Meltano is accessible via CLI only. You have two options to access the Meltano CLI:

**Option 1: Web-based Terminal (Wetty)**

1. Access Wetty at `https://wetty.<domain>` (requires Cloudflare Access login)
2. In the web terminal, run Meltano commands:

```bash
docker exec -it meltano meltano --help
```

**Option 2: SSH Access**

1. Connect via SSH (see [SSH Access Guide](../ssh-access.md))
2. Run Meltano commands:

```bash
ssh nexus
docker exec -it meltano meltano --help
```

**Common Meltano Commands:**

```bash
# Initialize a new project
docker exec -it meltano meltano init my-project

# List available commands
docker exec -it meltano meltano --help

# Add an extractor (tap) - e.g., CSV files, APIs, databases
docker exec -it meltano meltano add extractor tap-csv

# Add a loader (target) - e.g., PostgreSQL, S3, Data Warehouse
docker exec -it meltano meltano add loader target-postgres

# Run a pipeline (extract + load)
docker exec -it meltano meltano run tap-csv target-postgres

# Schedule a pipeline (runs automatically)
docker exec -it meltano meltano schedule add my-pipeline \
  --extractor tap-csv \
  --loader target-postgres \
  --interval '@daily'

# View logs
docker exec -it meltano meltano logs
```

> **Note:** Meltano has no web UI since v3.0. All interaction is via the CLI through Wetty or SSH.
