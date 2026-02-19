# Available Stacks

This document provides an overview of all available Docker stacks in Nexus-Stack. Click on any stack name to see detailed documentation.

## Docker Image Versions

Images are pinned to **major versions** where supported for automatic security patches while avoiding breaking changes. Versions are defined in [`services.yaml`](../../services.yaml).

| Service | Image | Tag | Strategy |
|---------|-------|-----|----------|
| Adminer | `adminer` | `latest` | Latest ² |
| CloudBeaver | `dbeaver/cloudbeaver` | `24` | Major |
| ClickHouse | `clickhouse/clickhouse-server` | `25.8.16.34` | Exact ¹ |
| code-server | `codercom/code-server` | `latest` | Latest ² |
| Draw.io | `jgraph/drawio` | `latest` | Latest ² |
| Grafana | `grafana/grafana` | `12` | Major |
| Hoppscotch | `hoppscotch/hoppscotch` | `latest` | Latest ² |
| Prometheus | `prom/prometheus` | `v3` | Major |
| Loki | `grafana/loki` | `3` | Major |
| Promtail | `grafana/promtail` | `3` | Major |
| cAdvisor | `gcr.io/cadvisor/cadvisor` | `v0.56` | Minor |
| Node Exporter | `prom/node-exporter` | `v1` | Major |
| Portainer | `portainer/portainer-ce` | `2` | Major |
| Uptime Kuma | `louislam/uptime-kuma` | `2` | Major |
| n8n | `n8nio/n8n` | `1` | Major |
| OpenMetadata Server | `docker.getcollate.io/openmetadata/server` | `1.6.6` | Exact ¹ |
| OpenMetadata Ingestion | `docker.getcollate.io/openmetadata/ingestion` | `1.6.6` | Exact ¹ |
| Elasticsearch (OpenMetadata) | `docker.elastic.co/elasticsearch/elasticsearch` | `8.11.4` | Exact ¹ |
| PostgreSQL (OpenMetadata DB) | `postgres` | `16-alpine` | Major |
| Kafka-UI | `provectuslabs/kafka-ui` | `latest` | Latest ² |
| Kestra | `kestra/kestra` | `v1` | Major |
| Infisical | `infisical/infisical` | `v0.155.5` | Exact ¹ |
| Metabase | `metabase/metabase` | `v0.58.x` | Minor |
| Mailpit | `axllent/mailpit` | `v1` | Major |
| IT-Tools | `corentinth/it-tools` | `latest` | Latest ² |
| Jupyter PySpark | `quay.io/jupyter/pyspark-notebook` | `python-3.13` | Minor |
| Excalidraw | `excalidraw/excalidraw` | `latest` | Latest ² |
| Filestash | `machines/filestash` | `latest` | Latest ² |
| Garage | `dxflrs/garage` | `v2.2.0` | Minor |
| Garage WebUI | `khairul169/garage-webui` | `latest` | Latest ² |
| Git Proxy | `nginx` | `alpine` | Latest ² |
| Gitea | `gitea/gitea` | `1.23` | Major |
| PostgreSQL (Gitea DB) | `postgres` | `16-alpine` | Major |
| LakeFS | `treeverse/lakefs` | `1.73.0` | Exact ¹ |
| Mage | `mageai/mageai` | `latest` | Latest ² |
| MinIO | `minio/minio` | `latest` | Latest ² |
| NocoDB | `nocodb/nocodb` | `0.301.2` | Exact ¹ |
| PostgreSQL (NocoDB DB) | `postgres` | `16-alpine` | Major |
| Ollama | `ollama/ollama` | `0.15.1` | Exact ¹ |
| Open WebUI | `ghcr.io/open-webui/open-webui` | `v0.8.3` | Exact ¹ |
| RustFS | `rustfs/rustfs` | `1.0.0-alpha.82` | Exact ¹ |
| S3 Manager | `cloudlena/s3manager` | `latest` | Latest ² |
| Marimo | `ghcr.io/marimo-team/marimo` | `latest-sql` | Latest ² |
| Meltano | `meltano/meltano` | `v4.0` | Minor |
| PostgreSQL (Meltano DB) | `postgres` | `16-alpine` | Major |
| PostgreSQL (Standalone) | `postgres` | `17-alpine` | Major |
| pgAdmin | `dpage/pgadmin4` | `9` | Major |
| Prefect | `prefecthq/prefect` | `3-latest` | Major |
| PostgreSQL (Prefect DB) | `postgres` | `16-alpine` | Major |
| Dify API | `langgenius/dify-api` | `1.13.0` | Exact ¹ |
| Dify Web | `langgenius/dify-web` | `1.13.0` | Exact ¹ |
| Dify Sandbox | `langgenius/dify-sandbox` | `0.2.12` | Exact ¹ |
| Dify Plugin Daemon | `langgenius/dify-plugin-daemon` | `0.5.3-local` | Exact ¹ |
| Weaviate (Dify) | `semitechnologies/weaviate` | `1.27.0` | Exact ¹ |
| PostgreSQL (Dify DB) | `postgres` | `15-alpine` | Major |
| Redis (Dify) | `redis` | `6-alpine` | Major |
| SSRF Proxy (Dify) | `ubuntu/squid` | `latest` | Latest ² |
| Quickwit | `quickwit/quickwit` | `0.8.1` | Exact ¹ |
| SeaweedFS | `chrislusf/seaweedfs` | `3.82` | Minor |
| Redpanda | `redpandadata/redpanda` | `v24.3` | Minor |
| Redpanda Console | `redpandadata/console` | `v2.8` | Minor |
| Redpanda Connect | `redpandadata/connect` | `latest` | Latest ² |
| Redpanda Datagen | `redpandadata/connect` | `latest` | Latest ² |
| Soda Core | `soda-core-arm64` | `3.3.7` | Exact ³ |
| Spark Master | `nexus-spark` | `4.1.1-python3.13` | Exact ³ |
| Spark Worker | `nexus-spark` | `4.1.1-python3.13` | Exact ³ |
| Trino | `trinodb/trino` | `479` | Exact ¹ |
| Wiki.js | `requarks/wiki` | `2.5.306` | Exact ¹ |
| PostgreSQL (Wiki.js DB) | `postgres` | `16-alpine` | Major |
| Woodpecker Server | `woodpeckerci/woodpecker-server` | `v3.13.0` | Exact ¹ |
| Woodpecker Agent | `woodpeckerci/woodpecker-agent` | `v3.13.0` | Exact ¹ |
| Windmill | `ghcr.io/windmill-labs/windmill` | `1.624.0` | Exact ¹ |
| Windmill LSP | `ghcr.io/windmill-labs/windmill-lsp` | `latest` | Latest ² |
| PostgreSQL (Windmill DB) | `postgres` | `16-alpine` | Major |
| Nginx (Info) | `nginx` | `alpine` | Rolling |

¹ No major version tags available, requires manual updates.
² Only `latest` tags published, no semantic versions available.
³ Custom build (official image doesn't support ARM64).

**Strategies:**
- **Major** (e.g., `:12`) - Auto-patches, manual major upgrades only
- **Minor** (e.g., `:v0.58`) - Auto-patches within minor version
- **Exact** (e.g., `:v0.155.5`) - Full control, manual all updates
- **Latest** - Always newest version (when no semver available)

**To upgrade**: Edit the version in `services.yaml` and run Spin-Up.

---

## Stack Documentation

| Stack | Description | Docs |
|-------|-------------|------|
| **Adminer** | Lightweight database management tool | [adminer.md](adminer.md) |
| **Apache Spark** | Distributed data processing engine | [spark.md](spark.md) |
| **CloudBeaver** | Web-based database management tool | [cloudbeaver.md](cloudbeaver.md) |
| **ClickHouse** | Columnar database for real-time analytics | [clickhouse.md](clickhouse.md) |
| **code-server** | VS Code in the browser | [code-server.md](code-server.md) |
| **Dify** | AI workflow builder for LLM applications | [dify.md](dify.md) |
| **Draw.io** | Flowchart and diagramming tool | [drawio.md](drawio.md) |
| **Excalidraw** | Virtual whiteboard for diagrams | [excalidraw.md](excalidraw.md) |
| **Filestash** | Web-based file manager | [filestash.md](filestash.md) |
| **Garage** | S3-compatible object storage | [garage.md](garage.md) |
| **Git Proxy** | Public Git HTTPS proxy | [git-proxy.md](git-proxy.md) |
| **Gitea** | Self-hosted Git service | [gitea.md](gitea.md) |
| **Grafana** | Observability stack with dashboards | [grafana.md](grafana.md) |
| **Hoppscotch** | API testing platform | [hoppscotch.md](hoppscotch.md) |
| **Info** | Landing page with service overview | [info.md](info.md) |
| **Infisical** | Secret management platform | [infisical.md](infisical.md) |
| **IT-Tools** | Developer tools collection | [it-tools.md](it-tools.md) |
| **Jupyter PySpark** | Interactive PySpark notebook | [jupyter.md](jupyter.md) |
| **Kafka-UI** | Kafka/Redpanda management UI | [kafka-ui.md](kafka-ui.md) |
| **Kestra** | Workflow orchestration | [kestra.md](kestra.md) |
| **LakeFS** | Git-like version control for data lakes | [lakefs.md](lakefs.md) |
| **Mage** | Data pipeline tool | [mage.md](mage.md) |
| **Mailpit** | Email and SMTP testing | [mailpit.md](mailpit.md) |
| **Marimo** | Reactive Python notebook | [marimo.md](marimo.md) |
| **Meltano** | Data integration platform | [meltano.md](meltano.md) |
| **Metabase** | Business intelligence tool | [metabase.md](metabase.md) |
| **MinIO** | S3-compatible object storage | [minio.md](minio.md) |
| **n8n** | Workflow automation tool | [n8n.md](n8n.md) |
| **NocoDB** | Airtable alternative (smart spreadsheet) | [nocodb.md](nocodb.md) |
| **Ollama + Open WebUI** | Local LLM inference with chat interface | [ollama.md](ollama.md) |
| **OpenMetadata** | Metadata management platform | [openmetadata.md](openmetadata.md) |
| **pgAdmin** | PostgreSQL administration tool | [pgadmin.md](pgadmin.md) |
| **Portainer** | Docker container management UI | [portainer.md](portainer.md) |
| **PostgreSQL** | Relational database | [postgres.md](postgres.md) |
| **Prefect** | Python workflow orchestration | [prefect.md](prefect.md) |
| **Quickwit** | Cloud-native log search engine | [quickwit.md](quickwit.md) |
| **Redpanda** | Kafka-compatible streaming platform | [redpanda.md](redpanda.md) |
| **Redpanda Console** | Redpanda web UI | [redpanda-console.md](redpanda-console.md) |
| **Redpanda Connect** | Stream processing framework | [redpanda-connect.md](redpanda-connect.md) |
| **Redpanda Datagen** | Test data generator | [redpanda-datagen.md](redpanda-datagen.md) |
| **RustFS** | Rust-based S3-compatible storage | [rustfs.md](rustfs.md) |
| **S3 Manager** | S3 bucket browser | [s3manager.md](s3manager.md) |
| **SeaweedFS** | Distributed object storage | [seaweedfs.md](seaweedfs.md) |
| **Soda Core** | Data quality testing | [soda.md](soda.md) |
| **Trino** | Distributed SQL query engine | [trino.md](trino.md) |
| **Uptime Kuma** | Self-hosted monitoring tool | [uptime-kuma.md](uptime-kuma.md) |
| **Wetty** | Web-based SSH terminal | [wetty.md](wetty.md) |
| **Wiki.js** | Wiki platform | [wikijs.md](wikijs.md) |
| **Windmill** | Developer workflow engine | [windmill.md](windmill.md) |
| **Woodpecker CI** | CI/CD pipeline | [woodpecker-ci.md](woodpecker-ci.md) |

---

## Firewall Management (External TCP Access)

The Control Plane includes a **Firewall Management** page that allows opening specific TCP ports on the Hetzner firewall for direct external access from clients like Databricks.

### Why?

By default, Nexus-Stack uses a "Zero Entry" security model where all ports are closed and all traffic flows through the Cloudflare Tunnel. However, the tunnel only supports HTTP/SSH protocols. Services like Kafka, PostgreSQL, and MinIO S3 API use TCP protocols that cannot be routed through the tunnel.

### How It Works

1. Open the **Firewall** page in the Control Plane
2. Toggle the ports you need (e.g., Kafka 9092, PostgreSQL 5432, MinIO S3 9000)
3. Optionally restrict source IPs (e.g., Databricks IP ranges)
4. Click **Spin Up** to apply changes

OpenTofu creates inbound Hetzner firewall rules and DNS A records pointing directly to the server IP (`proxied = false`, bypassing Cloudflare proxy).

### Available TCP Ports

| Service | Port | DNS Record | Protocol |
|---------|------|------------|----------|
| **Garage** (S3 API) | 3900 | `garage-s3.<domain>` | S3/HTTP |
| **LakeFS** (S3 Gateway) | 8000 | `s3.lakefs.<domain>` | S3/HTTP |
| **MinIO** (S3 API) | 9000 | `s3.<domain>` | S3/HTTP |
| **PostgreSQL** | 5432 | `postgres.<domain>` | PostgreSQL |
| **RedPanda** (Kafka) | 9092 | `redpanda.<domain>` | Kafka |
| **RedPanda** (Schema Registry) | 8081 | `redpanda-schema-registry.<domain>` | HTTP |
| **RustFS** (S3 API) | 9003 | `rustfs-s3.<domain>` | S3/HTTP |
| **SeaweedFS** (S3 API) | 8333 | `seaweedfs-s3.<domain>` | S3/HTTP |

### Connection Examples

```bash
# RedPanda Kafka (from Databricks or any Kafka client)
redpanda.yourdomain.com:9092

# RedPanda Schema Registry
curl http://redpanda-schema-registry.yourdomain.com:8081/subjects

# PostgreSQL
psql -h postgres.yourdomain.com -p 5432 -U postgres

# MinIO S3 API
aws s3 ls --endpoint-url http://s3.yourdomain.com:9000
```

### Security

- **Auto-Reset on Teardown:** All firewall rules are automatically reset (`enabled = 0`) when the infrastructure is torn down. Ports must be explicitly re-opened after each Spin Up.
- **Source IP Restriction:** Each rule supports optional source IP/CIDR restriction. Open to all (`0.0.0.0/0`) if not specified.
- **Service Authentication:** All exposed services have their own auth (PostgreSQL passwords, Kafka SASL, MinIO access keys).
- **fail2ban:** Installed on the server, provides brute-force protection for opened ports.
- **Pre-defined Ports Only:** Only ports defined in `services.yaml` under `tcp_ports` can be opened. No arbitrary port numbers.

---

## Enabling a Stack

Service enable/disable state is managed at runtime via Cloudflare D1 and exposed through the Control Plane. You generally do **not** need to edit any OpenTofu variable files to turn services on or off.

There are two primary ways to enable a stack:

1. **During initial setup**
   - Run the `initial-setup` GitHub Actions workflow.
   - Use the workflow inputs to select which stacks should be enabled on first deployment.
   - Complete the workflow, then run the **Spin Up** workflow to deploy.

2. **After setup via the Control Plane**
   - Open the Control Plane web UI.
   - Go to the services section.
   - Enable or disable individual stacks using the provided toggles.
   - The enabled/disabled state is stored in Cloudflare D1 and will be applied on the next **Spin Up**.

The `services.yaml` file defines service metadata (subdomain, port, description, image, etc.), but **not** the enabled/disabled state. That state is managed exclusively through D1 / the Control Plane.

---

## Adding New Services

Adding a new service requires **2 steps**:

### 1. Create the Docker Compose stack

```bash
mkdir -p stacks/my-app
```

Create `stacks/my-app/docker-compose.yml`:
```yaml
services:
  my-app:
    image: my-app-image:latest
    container_name: my-app
    restart: unless-stopped
    ports:
      - "8090:80"  # Pick an unused port
    networks:
      - app-network

networks:
  app-network:
    external: true
```

### 2. Add to services.yaml

Add to `services.yaml` (in project root):

```yaml
services:
  # ... existing services ...

  my-app:
    subdomain: "my-app"         # → https://my-app.yourdomain.com
    port: 8090                  # Must match docker-compose port
    public: false               # false = requires login, true = public
    description: "My awesome application"
    image: "myorg/my-app:latest"
```

> **Note:** No `enabled` field needed - runtime state is managed by D1 (Control Plane).

### 3. Deploy

Run the **Spin Up** workflow via GitHub Actions or use the Control Plane.

That's it! OpenTofu automatically creates:
- DNS record
- Tunnel ingress route
- Cloudflare Access application
- Access policy (email-based auth)

---

## Disabling Services

Services can be disabled via the **Control Plane** web interface. The enabled/disabled state is stored in Cloudflare D1 - not in the `services.yaml` file.

When disabled:
1. DNS record is removed from Cloudflare
2. Tunnel ingress route is removed
3. Cloudflare Access application and policy are removed
4. Docker container is stopped
5. Stack folder is deleted from the server

The service is completely cleaned up - no orphaned resources.
