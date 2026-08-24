---
title: "Sling"
---

## Sling

![Sling](https://img.shields.io/badge/Sling-FF6B35?logo=data&logoColor=white)

**Lightweight CLI tool for database-to-database and file-to-database transfers**

Sling is a fast data integration CLI for moving data between databases and storage systems. Features include:
- Database replication (full, incremental, snapshot)
- File ingestion (CSV, JSON, Parquet from local/S3/GCS/MinIO)
- 30+ connectors (PostgreSQL, MySQL, SQL Server, Oracle, ClickHouse, S3, etc.)
- Schema auto-detection and type mapping
- Streaming mode for large datasets (low memory footprint)
- Simple YAML-based configuration

| Setting | Value |
|---------|-------|
| Access | Internal only (CLI tool, no web UI) |
| Website | [slingdata.io](https://slingdata.io) |
| Source | [GitHub](https://github.com/slingdata-io/sling-cli) |

### Custom Build

Sling is built from a custom Dockerfile rather than the official image, which does not cover every architecture Nexus-Stack targets. The binary is downloaded from the upstream GitHub release, which publishes both `linux/amd64` and `linux/arm64`; the Dockerfile selects the matching one via `dpkg --print-architecture`, verifies it against the release's checksum file, and runs `sling --version` so an architecture mismatch fails the image build instead of surfacing later as an unhealthy container.

### Usage

Access via SSH or docker exec:

```bash
# Check version
docker exec -it sling sling --version

# List available connectors
docker exec -it sling sling conns

# Replicate a table from PostgreSQL to ClickHouse
docker exec -it sling sling run \
  --src-conn "postgresql://nexus-postgres:password@postgres:5432/postgres" \
  --src-stream "public.my_table" \
  --tgt-conn "clickhouse://nexus-clickhouse:password@clickhouse:9000/default" \
  --tgt-object "my_table"

# Load a CSV file into PostgreSQL
docker exec -it sling sling run \
  --src-stream "file:///workspace/data.csv" \
  --tgt-conn "postgresql://nexus-postgres:password@postgres:5432/postgres" \
  --tgt-object "public.imported_data"
```

### Connection Configuration

Connections can be set via environment variables or a YAML config file at `/workspace/.sling/env.yaml`:

```yaml
connections:
  POSTGRES:
    type: postgres
    url: postgresql://nexus-postgres:password@postgres:5432/postgres
  CLICKHOUSE:
    type: clickhouse
    url: clickhouse://nexus-clickhouse:password@clickhouse:9000/default
  MINIO:
    type: s3
    url: s3://bucket-name
    access_key_id: minioadmin
    secret_access_key: minioadmin
    endpoint: http://minio:9000
```
