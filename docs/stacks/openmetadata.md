## OpenMetadata

![OpenMetadata](https://img.shields.io/badge/OpenMetadata-7147E8?logoColor=white)

**Open-source metadata management platform for data discovery, governance, and quality**

OpenMetadata is a unified platform for metadata management, data discovery, and data governance. It helps data teams discover, understand, and trust their data. Features include:
- Centralized metadata catalog for all data assets
- Data lineage tracking across pipelines and services
- Data quality monitoring with profiler and tests
- Collaboration with conversations and tasks on data assets
- Role-based access control and data policies
- Built-in connectors for databases, dashboards, pipelines, and messaging
- Glossary and classification for data governance

| Setting | Value |
|---------|-------|
| Default Port | `8585` |
| Suggested Subdomain | `openmetadata` |
| Public Access | No (metadata management) |
| Website | [open-metadata.org](https://open-metadata.org) |
| Source | [GitHub](https://github.com/open-metadata/OpenMetadata) |

### Architecture (5 containers)

| Container | Image | Purpose |
|-----------|-------|---------|
| `openmetadata` | `docker.getcollate.io/openmetadata/server:1.6.6` | API server + web UI (port 8585) |
| `openmetadata-migrate` | `docker.getcollate.io/openmetadata/server:1.6.6` | One-shot database migration |
| `openmetadata-ingestion` | `docker.getcollate.io/openmetadata/ingestion:1.6.6` | Airflow-based ingestion pipelines |
| `openmetadata-db` | `postgres:16-alpine` | Dedicated PostgreSQL (2 databases) |
| `openmetadata-elasticsearch` | `docker.elastic.co/elasticsearch/elasticsearch:8.11.4` | Search engine |

### Resource Requirements

OpenMetadata is a resource-intensive stack due to the JVM-based server, Elasticsearch, and Airflow ingestion:
- **Estimated RAM**: ~3-4 GB total (Elasticsearch 1 GB heap + Server JVM 1 GB heap + Airflow)
- **Startup time**: ~2-3 minutes (Java + Elasticsearch initialization)
- Recommended for `cax31` or larger server types

### Credentials

| Credential | Source |
|------------|--------|
| Username | Your admin email (stored in Infisical as `OPENMETADATA_USERNAME`) |
| Password | Auto-generated (stored in Infisical as `OPENMETADATA_PASSWORD`) |

### Usage

1. Enable the OpenMetadata service in the Control Plane
2. Wait ~3-5 minutes for initial startup (Java + Elasticsearch + migration)
3. Access `https://openmetadata.<domain>`
4. Login with credentials from Infisical
5. Start adding data connectors (Settings > Services) to catalog your data sources

### Connecting Data Sources

From OpenMetadata UI, go to **Settings > Services** to add connectors:

| Connector Type | Examples |
|---------------|----------|
| **Databases** | PostgreSQL (`postgres:5432`), MySQL, Snowflake |
| **Dashboards** | Metabase, Grafana, Superset |
| **Pipelines** | Airflow, Prefect, Kestra |
| **Messaging** | Redpanda/Kafka (`redpanda:9092`) |

Internal services use Docker network hostnames (e.g., `postgres`, `redpanda`).

> ✅ **Auto-configured:** Admin account is automatically created during deployment with your admin email. The default password is changed to a generated password stored in Infisical.
