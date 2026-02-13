## Quickwit

![Quickwit](https://img.shields.io/badge/Quickwit-0C1E2C?logo=quickwit&logoColor=white)

**Cloud-native log search engine**

Quickwit is a cloud-native search engine designed for log management and analytics, built on top of object storage. It provides sub-second search on log data with minimal infrastructure. Features include:
- Full-text search on log data with sub-second latency
- Built for object storage (S3, MinIO, Hetzner Object Storage)
- OpenTelemetry-native for traces and logs ingestion
- Elasticsearch-compatible query API
- Standalone single-node mode (no external dependencies)
- Decoupled compute and storage architecture

| Setting | Value |
|---------|-------|
| Default Port | `8092` |
| Suggested Subdomain | `quickwit` |
| Public Access | No (log data may contain sensitive information) |
| Website | [quickwit.io](https://quickwit.io) |
| Source | [GitHub](https://github.com/quickwit-oss/quickwit) |

### Usage

1. Enable the Quickwit service in the Control Plane
2. Access `https://quickwit.<domain>` to open the search UI
3. Create indexes and ingest data via the REST API:
   ```bash
   # Create an index
   curl -X POST https://quickwit.<domain>/api/v1/indexes \
     -H 'Content-Type: application/yaml' \
     --data-binary @my-index-config.yaml

   # Ingest JSON data
   curl -X POST https://quickwit.<domain>/api/v1/<index>/ingest \
     -H 'Content-Type: application/json' \
     --data-binary @logs.json
   ```

### Connecting to Object Storage

Quickwit can use S3-compatible storage backends for index data. Configure via a `quickwit.yaml` mounted into the container. By default, data is stored locally in the `quickwit-data` Docker volume.

> **Note:** ARM64 support is experimental. Report any issues to the Quickwit team.
