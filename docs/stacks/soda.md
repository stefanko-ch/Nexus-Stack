## Soda Core

![Soda](https://img.shields.io/badge/Soda-6C47FF?logo=database&logoColor=white)

**CLI-based data quality testing tool using SodaCL checks**

Soda Core is an open-source data quality tool that uses SodaCL (Soda Checks Language) to define and run data quality checks against your databases. Features include:
- YAML-based check definitions (SodaCL)
- Support for PostgreSQL, MySQL, Snowflake, BigQuery, and more
- Schema validation and freshness checks
- Row count, missing value, and duplicate detection
- Custom SQL-based quality checks
- Over 25 built-in metrics

| Setting | Value |
|---------|-------|
| Internal Only | Yes (CLI access only) |
| Database | PostgreSQL 16 |
| Website | [soda.io](https://www.soda.io) |
| Source | [GitHub](https://github.com/sodadata/soda-core) |

### Architecture

The stack includes:
- **Soda Core** - CLI application (runs as long-lived container, custom-built for ARM64)
- **PostgreSQL** - Database for test data and quality checks

> **Note:** Soda Core uses a custom Dockerfile because the official `sodadata/soda-core` image doesn't support ARM64 architecture (required for cax31 servers).

### Configuration

Soda requires two types of YAML configuration files in the `/workspace` directory:

**1. Data Source Configuration (`configuration.yml`):**
```yaml
data_source soda_postgres:
  type: postgres
  host: soda-db
  port: "5432"
  username: soda
  password: ${SODA_DB_PASSWORD}
  database: soda
```

**2. Check Definitions (`checks.yml`):**
```yaml
checks for my_table:
  - row_count > 0
  - missing_count(column_name) = 0
  - duplicate_count(id) = 0
  - schema:
      fail:
        when required column missing: [id, name, created_at]
  - freshness(created_at) < 1d
```

### Getting Started

Soda Core is accessible via CLI only. You have two options:

**Option 1: Web-based Terminal (Wetty)**

1. Access Wetty at `https://wetty.<domain>` (requires Cloudflare Access login)
2. In the web terminal, run Soda commands:

```bash
docker exec -it soda soda --help
```

**Option 2: SSH Access**

1. Connect via SSH (see [SSH Access Guide](../ssh-access.md))
2. Run Soda commands:

```bash
ssh nexus
docker exec -it soda soda --help
```

**Common Soda Commands:**

```bash
# Check Soda version
docker exec -it soda soda --version

# Test connection to a data source
docker exec -it soda soda test-connection \
  -d soda_postgres \
  -c /workspace/configuration.yml

# Run a scan against the Soda PostgreSQL database
docker exec -it soda soda scan \
  -d soda_postgres \
  -c /workspace/configuration.yml \
  /workspace/checks.yml

# Run a scan with verbose output
docker exec -it soda soda scan \
  -d soda_postgres \
  -c /workspace/configuration.yml \
  /workspace/checks.yml -V
```

> **Note:** Soda Core has no web UI. All interaction is via the CLI through Wetty or SSH. Database credentials are available in Infisical.
