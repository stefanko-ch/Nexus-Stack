---
title: Stacks Overview
description: All 60+ services available in Nexus Stack — with Docker image versions, categorized, and linked to upstream reference docs.
sidebar:
  order: 1
---

Nexus Stack ships with **60+ pre-configured services** that you can enable or disable individually via the Control Plane. Every stack runs in Docker behind a Cloudflare Tunnel — zero open ports, email-OTP authentication via Cloudflare Access.

:::tip
Each **stack name** links to its detailed reference doc in the Nexus-Stack repository: ports, default subdomain, public access policy, architecture diagram, and post-deployment notes. The **image column** shows the exact Docker image and version tag that Nexus Stack pins today — override it via the corresponding `IMAGE_*` environment variable in your deployment if you need a different tag.
:::

## How stacks work in Nexus Stack

A "stack" in Nexus Stack is a self-contained module that combines:

- A **Docker Compose file** describing one or more containers
- An **OpenTofu module** that wires up DNS, the Cloudflare Tunnel ingress rule, the Cloudflare Access policy, and Infisical secrets
- A **Control Plane registration** so you can enable/disable the service from the web UI

When you enable a stack, the Control Plane:

1. Pulls Docker images on the Hetzner server
2. Starts the containers
3. Creates a DNS record (`<stack>.yourdomain.com`)
4. Adds an ingress rule to the Cloudflare Tunnel
5. Creates a Cloudflare Access application gating the route by email OTP
6. Provisions secrets in Infisical and emails you the credentials

Disabling a stack reverses every one of those steps. Nothing is left behind on Cloudflare or Hetzner.

## Image pinning & updates

Every stack Docker Compose file uses an environment variable default pattern:

```yaml
image: ${IMAGE_GRAFANA:-grafana/grafana:11.6}
```

The tag shown in each table below is the value Nexus Stack ships with **right now** on `main`. Tags fall into three buckets:

- **Pinned exact version** (e.g. `clickhouse/clickhouse-server:25.8.16.34`, `treeverse/lakefs:1.73.0`) — reproducible, deterministic, what you want in production.
- **Pinned major (or major/minor)** (e.g. `gitea/gitea:1.23`, `redpandadata/redpanda:v24.3`) — gets patch updates on next `docker pull`, locked against major version surprises.
- **`:latest`** (e.g. `adminer:latest`, `corentinth/it-tools:latest`) — tracks upstream bleeding edge. Reserved for presentation-layer and dev tools that hold no persistent state, and for viewers over somebody else's state such as Kafka-UI and S3 Manager. No stateful stack is left on it.

You override any image via the matching `IMAGE_*` environment variable in your deployment — useful for pinning `:latest` stacks to a specific version, or for testing a pre-release tag.

Some images are maintained by Nexus Stack itself rather than pulled from a public registry. Most use the `nexus-*` prefix (e.g. `nexus-flink:1.20.1`, `nexus-spark:4.1.1-python3.13`, `nexus-dagster:1.12.21`, `nexus-dinky:1.2.5-flink1.20`, `nexus-sling:1.5.13`, `nexus-code-server:latest`). A small number of local-build variants use descriptive names without the prefix — most notably **`soda-core:3.3.7`**, where Soda's official image is x86-only and Nexus Stack ships a multi-arch rebuild via Python + pip. All of these Dockerfiles live in the Nexus-Stack repo, layer Python/Java dependencies on top of upstream base images, and are built on the Hetzner server during Initial Setup. They build correctly on both ARM (cax) and x86 (cpx) server types. Most get that for free from multi-arch base images; the two that download a pre-built binary — `nexus-sling` and the DuckDB CLI inside `nexus-code-server` — select the matching artefact at build time via `dpkg --print-architecture` / `uname -m`.

## Authentication

Every stack — except those explicitly marked as public — sits behind **Cloudflare Access** with an **email OTP** policy. When you visit a service URL:

1. Cloudflare intercepts the request at the edge
2. You enter your email; Cloudflare sends a one-time code
3. After verification, Cloudflare passes you through the tunnel to the Docker container

There are **no passwords stored on the server** for this layer. Application-level credentials (e.g. the Grafana admin user) are generated on first deploy and stored in **Infisical** — they're also emailed to you on initial setup.

## Public vs. private services

Some stacks make sense to expose without Cloudflare Access (a public wiki, a shared whiteboard, a Git proxy for external CI). To do that, set `public = true` in the stack config. Public services skip Cloudflare Access but **still go through the Cloudflare Tunnel** — your Hetzner server has no open ports either way.

A handful of stacks are marked **"always protected"** in their reference docs — Grafana, Infisical, Portainer, Kestra, Wetty. These can never be made public, even by accident, because they grant infrastructure-level access.

## Internal-only services

Some stacks have no web UI and exist purely to support other services. They are reachable from inside the Docker network only and don't even appear in the Control Plane service list as "open me":

- **PostgreSQL** — used as the storage backend by Wiki.js, Gitea, Metabase, Superset, Dagster, OpenMetadata, Soda, and several others
- **Telegraf** — metrics agent shipping data to Prometheus
- **Soda** / **Meltano** / **Sling** — CLI-only data tools without a web UI

You don't access them directly; you use them through their consumers.

## TCP services & firewall management

Cloudflare Tunnels handle HTTPS perfectly, but a few services need raw TCP access from the outside (Kafka clients, PostgreSQL drivers, MinIO S3 SDK clients). For those, the Control Plane offers a **Firewall Management** page where you can selectively open TCP ports on the Hetzner firewall. DNS A records are created pointing directly to the server IP (`proxied = false`), since Cloudflare doesn't proxy raw TCP. All firewall rules are **automatically reset on every Teardown** — there is no way to leave a port accidentally open.

---

## Streaming & messaging

| Stack | Image | Description |
|-------|-------|-------------|
| **[AKHQ](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/akhq.md)** | `tchiotludo/akhq:0.27.0` | Alternative Kafka/Redpanda management GUI with first-class support for the Schema Registry and Kafka Connect. Use it side-by-side with Redpanda Console if you manage Connect workers. |
| **[Debezium](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/debezium.md)** | `quay.io/debezium/connect:3.5.0` | Change data capture via Kafka Connect. Tails the PostgreSQL WAL (and MySQL/Mongo/SQL Server binlogs) and streams row-level changes into Redpanda topics — the standard way to get an event stream out of a boring OLTP database. |
| **[Kafdrop](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/kafdrop.md)** | `obsidiandynamics/kafdrop:4.2.0` | Minimalist read-only Kafka topic/consumer group viewer. Runs on ~100 MB RAM — the lightest option when you just need to peek at messages. |
| **[Kafka-UI](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/kafka-ui.md)** | `provectuslabs/kafka-ui:latest` | Provectus' open-source web UI for Kafka. Similar feature set to Redpanda Console and AKHQ — pick the one that matches your taste. |
| **[Redpanda](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/redpanda.md)** | `redpandadata/redpanda:v24.3` | Kafka API-compatible streaming platform written in C++ and Raft-based — same protocol as Kafka, no JVM, no ZooKeeper, lower tail latency. The data plane for every CDC and streaming pipeline in Nexus Stack. |
| **[Redpanda Connect](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/redpanda-connect.md)** | `redpandadata/connect:4.43.0` | Declarative stream-processing framework (formerly Benthos). YAML-defined pipelines with 200+ inputs/outputs/processors for real-time ETL, enrichment, and routing. |
| **[Redpanda Console](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/redpanda-console.md)** | `redpandadata/console:v2.8.0` | Modern web UI for browsing topics, consumer groups, schema registry, and ACLs. The recommended first-stop GUI if you're running Redpanda. |
| **[Redpanda Datagen](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/redpanda-datagen.md)** | `redpandadata/connect:4.43.0` | Synthetic test data generator for Redpanda topics. Handy for reproducing pipeline issues or load-testing downstream consumers without hitting production sources. |

## Databases

| Stack | Image | Description |
|-------|-------|-------------|
| **[Adminer](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/adminer.md)** | `adminer:latest` | Tiny single-file DB admin tool (one PHP file). Supports PostgreSQL, MySQL, SQLite, MSSQL, Oracle, and more. Ugly but extremely practical when you just want a SQL console now. |
| **[ClickHouse](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/clickhouse.md)** | `clickhouse/clickhouse-server:25.8.16.34` | Columnar OLAP database optimized for analytical queries over billions of rows. Typical pairing: a Debezium → Redpanda → ClickHouse CDC pipeline turning a transactional PostgreSQL into sub-second analytics. |
| **[CloudBeaver](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/cloudbeaver.md)** | `dbeaver/cloudbeaver:24` | DBeaver's web UI — full universal database IDE with ER diagrams, data editor, and SQL completion. The power-user choice for multi-engine work. |
| **[pgAdmin](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/pgadmin.md)** | `dpage/pgadmin4:9` | The PostgreSQL admin and query client, browser-based. Use this if you live in PostgreSQL; use Adminer or CloudBeaver if you need multi-engine access. |
| **[pg-ducklake](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/pg-ducklake.md)** | `postgres:17-alpine` + DuckDB extension | PostgreSQL with the DuckDB extension for analytical queries. Stores Parquet files on Hetzner Object Storage (S3) for columnar analytics alongside transactional workloads. Internal-only. |
| **[PostgreSQL](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/postgres.md)** | `postgres:17-alpine` | The default relational database used as the storage backend for many other stacks (Wiki.js, Gitea, Metabase, Superset, Dagster, OpenMetadata, Soda, Kestra). Internal-only — no public endpoint. |
| **[RisingWave](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/risingwave.md)** | `risingwavelabs/risingwave:v2.8.1` | PostgreSQL-wire-compatible streaming database. Write SQL `CREATE MATERIALIZED VIEW … FROM kafka_source`, get real-time results. Think "Flink SQL but you query it like Postgres". |

## Object storage

| Stack | Image | Description |
|-------|-------|-------------|
| **[Filestash](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/filestash.md)** | `machines/filestash@sha256:68171bf3…` | Web file manager with pluggable backends: S3, SFTP, FTP, WebDAV, Dropbox, Google Drive. Think "Google Drive UI for whichever storage you already own". |
| **[Garage](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/garage.md)** | `dxflrs/garage:v2.2.0` | Lightweight geo-distributed S3-compatible storage from the Deuxfleurs collective. Designed to run on heterogeneous nodes, e.g. a laptop + a VPS + a Raspberry Pi as one cluster. |
| **[LakeFS](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/lakefs.md)** | `treeverse/lakefs:1.73.0` | Git-like branches, commits, and merges for an S3 bucket. Enables "reproduce Tuesday's report" workflows by snapshotting the data lake state at each dbt run. Configured to use Hetzner Object Storage as the backing bucket. |
| **[MinIO](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/minio.md)** | `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z` | The reference open-source S3-compatible object store. Battle-tested, widely supported by every SDK that speaks S3, picked by default when in doubt. |
| **[RustFS](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/rustfs.md)** | `rustfs/rustfs:1.0.0-alpha.82` | Rust rewrite of MinIO's protocol surface. Lower RAM footprint and better tail latency; still pre-1.0 so treat it as experimental for production. |
| **[S3 Manager](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/s3manager.md)** | `cloudlena/s3manager:latest` | Simple web bucket browser. Preconfigured against the Hetzner Object Storage credentials from `.env`, so it works out of the box. |
| **[SeaweedFS](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/seaweedfs.md)** | `chrislusf/seaweedfs:3.82` | Distributed object store designed for billions of tiny files where MinIO struggles. Has its own Filer UI plus an S3 API compatibility layer. |
| **[SFTPGo](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/sftpgo.md)** | `drakkan/sftpgo:v2.7.1` | SFTP/SCP server with a web admin UI. Configured here with the R2 datalake bucket as its S3 backend, so external tools that only speak SFTP can read and write the same files the rest of the stack accesses via S3. SFTPGo also supports WebDAV and FTPS upstream, but Nexus-Stack disables both by default in the shipped compose. |

## Workflow orchestration & automation

| Stack | Image | Description |
|-------|-------|-------------|
| **[Dagster](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/dagster.md)** | `nexus-dagster:1.12.21` | Python orchestrator built around Software-Defined Assets and data lineage. Great fit for dbt + Python analytics stacks. Uses a Nexus-built image that layers your dependencies on top of the official base. |
| **[Kestra](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/kestra.md)** | `kestra/kestra:v1.0` | YAML-defined declarative workflow orchestration. Event-driven, plugin-rich, and language-agnostic. Pinned to the Kestra LTS track — the default image already bundles every official plugin (Databricks JDBC, Snowflake, Trino, Postgres, ~15 more). Always protected by Cloudflare Access — it touches every downstream system. |
| **[Mage](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/mage.md)** | `mageai/mageai:0.9.79` | Notebook-style data pipeline builder. A good middle ground if Dagster feels too abstract and Jupyter feels too loose. |
| **[n8n](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/n8n.md)** | `n8nio/n8n:1.123.75` | Fair-code workflow automation — Zapier/Make alternative with 400+ integrations and self-hostable license. The go-to tool for "when X happens, do Y" glue work. |
| **[Prefect](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/prefect.md)** | `prefecthq/prefect:3-latest` | Python-native orchestrator — flows are plain Python decorated with `@flow`. Deploys a Prefect Server, worker, and UI as separate containers. |
| **[Windmill](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/windmill.md)** | `ghcr.io/windmill-labs/windmill:1.624.0` | Developer-focused workflow and internal-tools platform. Write scripts in TypeScript/Python/Go/Bash, auto-generate forms, compose flows. Ships with an LSP container for in-browser autocomplete. |
| **[Woodpecker CI](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/woodpecker-ci.md)** | `woodpeckerci/woodpecker-server:v3.13.0` | Lightweight Docker-native CI/CD. Reads a `.woodpecker.yaml` and runs each step in a disposable container. Ships with a sibling **`woodpeckerci/woodpecker-agent:v3.13.0`** runner. Pairs naturally with Gitea for a fully self-hosted Git + CI setup. |

## Stream & batch processing

| Stack | Image | Description |
|-------|-------|-------------|
| **[Apache Flink](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/flink.md)** | `nexus-flink:1.20.1` | Distributed stream & batch processor. Deployed as a standalone cluster (JobManager + TaskManager). The Nexus-built image bundles Flink-Kafka, Flink-JDBC, and ARM-compatible connectors. |
| **[Apache Spark](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/spark.md)** | `nexus-spark:4.1.1-python3.13` | Distributed batch (+ streaming) processor, Master + Worker cluster. Nexus-built image includes PySpark, JupyterLab integration, and S3A connectors for MinIO/Hetzner Object Storage. |
| **[Dinky](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/dinky.md)** | `nexus-dinky:1.2.5-flink1.20` | Web IDE for Flink SQL with autocompletion, syntax highlighting, and one-click job submission to the Flink cluster above. Matching Flink version is baked into the image tag. |
| **[Meltano](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/meltano.md)** | `meltano/meltano:v4.0` | Open-source ELT built on Singer taps and targets. Version-controlled data integration with `meltano.yml`. CLI-only — runs jobs but exposes no web UI. |
| **[Sling](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/sling.md)** | `nexus-sling:1.5.13` | Lightweight CLI for database↔database and file↔database transfers. Think "rsync, but it speaks PostgreSQL, MySQL, S3, and CSV". CLI-only, no web UI. |

## BI, analytics & notebooks

| Stack | Image | Description |
|-------|-------|-------------|
| **[Apache Superset](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/superset.md)** | `apache/superset:6.0.0` | Power-user BI and data exploration with SQL Lab, 40+ chart types, and Jinja-templated dashboards. Fits the "data team wants real tooling" use case. |
| **[Budibase](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/budibase.md)** | `budibase/budibase:v3.43.0` | Low-code internal-tools builder. Drag-and-drop forms, tables, and auto-generated CRUD apps on top of your existing databases or APIs. |
| **[Jupyter](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/jupyter.md)** | `quay.io/jupyter/pyspark-notebook:python-3.13` | JupyterLab with PySpark preinstalled and pre-connected to the Spark cluster stack. The interactive data-exploration workhorse. |
| **[Marimo](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/marimo.md)** | `ghcr.io/marimo-team/marimo:latest-sql` | Modern Python notebook with reactive execution (change a cell and dependents re-run automatically) and built-in SQL cells. Notebooks are stored as plain `.py` files — git-friendly. |
| **[Metabase](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/metabase.md)** | `metabase/metabase:v0.60.6.2` | Friendly self-service BI — point at a database, get an ask-a-question-in-plain-English UI, build dashboards in minutes. Best fit for non-technical stakeholders. |
| **[NocoDB](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/nocodb.md)** | `nocodb/nocodb:0.301.2` | Airtable-style spreadsheet UI on top of any existing PostgreSQL or MySQL database. Turn a boring schema into a grid/kanban/form in one click. |
| **[Trino](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/trino.md)** | `trinodb/trino:479` | Distributed SQL query engine for federated queries. Join a PostgreSQL table with a Parquet file on S3 with a Hive table on MinIO in a single query. |

## Observability

| Stack | Image | Description |
|-------|-------|-------------|
| **[Dozzle](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/dozzle.md)** | `amir20/dozzle:v10.5.3` | Realtime Docker logs in the browser. The "no-SSH `docker logs -f`" — pick a container in the sidebar, stream its logs live, search/filter, open multiple in tabs. Subscribes to the Docker socket read-only. Stateless, ~30 MB image. |
| **[Grafana](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/grafana.md)** | `grafana/grafana:11.6` | The observability stack, bundled: Grafana + Prometheus + Loki + Promtail + cAdvisor + Node Exporter. Ships with pre-provisioned dashboards for Docker containers, Loki logs, and host metrics — working observability out of the box. Always protected. |
| **[Quickwit](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/quickwit.md)** | `quickwit/quickwit:0.8.1` | Rust-based log search engine, designed to store indexes on cheap object storage (S3/MinIO) instead of expensive SSD. Elasticsearch alternative when you have terabytes of logs you rarely query. |
| **[Telegraf](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/telegraf.md)** | `telegraf:1.38.2` | InfluxData's metrics agent with 300+ input plugins. CLI-only — runs in the background, no web UI. Complements the Grafana stack when you need something Node Exporter doesn't cover. |
| **[Uptime Kuma](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/uptime-kuma.md)** | `louislam/uptime-kuma:2` | A fancy self-hosted uptime monitor. Beautiful dashboards, Telegram/Slack/Discord alerts, public status pages. The reference "I need monitoring tonight" pick. |
| **[Vector](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/vector.md)** | `timberio/vector:0.54.0-alpine` | Ultra-fast observability pipeline in Rust — collect, transform, and route logs/metrics/traces. Think "unified Logstash + Fluentd + Telegraf at 10× the throughput". |

## Data quality & metadata

| Stack | Image | Description |
|-------|-------|-------------|
| **[OpenMetadata](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/openmetadata.md)** | `docker.getcollate.io/openmetadata/server:1.6.6` | Open-source metadata platform covering discovery, lineage, glossary, and data quality. Heavy — requires Elasticsearch + MySQL — but the right pick if you need a real data catalog. |
| **[Soda](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/soda.md)** | `soda-core:3.3.7` | Data quality testing framework. Write checks in SodaCL (a YAML DSL), run them from CI, break pipelines on failed quality thresholds. Local build via `python:3.11-slim` + pip (multi-arch). CLI-only. |

## AI / LLM

| Stack | Image | Description |
|-------|-------|-------------|
| **[Dify](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/dify.md)** | `langgenius/dify-api:1.13.0` | Visual builder for LLM apps, RAG pipelines, and agent workflows. Ships a sandbox runner, a plugin daemon, a web UI, and a Weaviate vector store as sibling containers — a full AI platform in a single stack. |
| **[Meilisearch](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/meilisearch.md)** | `getmeili/meilisearch:v1.43.1` | Lightning-fast Rust-based full-text search engine — sub-100ms typo-tolerant queries. Self-hosted Algolia. In RAG: pairs with Chroma for hybrid (keyword + vector) search; Crawl4AI scrapes → Meilisearch indexes → Big-AGI/Dify queries both. Auto-generated master key in Infisical (folder `meilisearch`, key `MEILISEARCH_MASTER_KEY`). |
| **[Ollama](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/ollama.md)** | `ollama/ollama:0.15.1` | Local LLM inference runtime bundled with **Open WebUI** (`ghcr.io/open-webui/open-webui:v0.8.3`) as the chat frontend. Pull `llama3`, `qwen2`, `mistral`, etc., and chat privately. Note: model size drives RAM — a 7B model needs ≥8 GB server. |

## Developer tools

| Stack | Image | Description |
|-------|-------|-------------|
| **[code-server](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/code-server.md)** | `nexus-code-server:latest` | VS Code in the browser. Nexus-built image preinstalls Python, Node, Docker CLI, and common language servers. Point it at a workspace volume and you have a full cloud IDE. |
| **[CyberChef](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/cyberchef.md)** | `mpepping/cyberchef:v10.24.0` | GCHQ's "Cyber Swiss Army Knife" — drag-and-drop ~400 operations into a recipe (encode/decode/hash/regex/crypto/compress/parse). The container serves static assets only; operations execute client-side in the browser (a small subset like DNS-over-HTTPS or HTTP request deliberately call out). Perfect for decoding JWTs, base64+gzip payloads, or live-demoing format conversions in class. |
| **[Git Proxy](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/git-proxy.md)** | `nginx:alpine` | Public HTTPS reverse proxy for Gitea, so external tools that can't do Cloudflare Access (Databricks, hosted CI, `git clone` from a random box) can still pull from your repos. |
| **[Gitea](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/gitea.md)** | `gitea/gitea:1.23` | Self-hosted Git with pull requests, code review, releases, and a built-in Actions runner. The GitHub-at-home experience. PostgreSQL is included as a sibling container. |
| **[Hoppscotch](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/hoppscotch.md)** | `hoppscotch/hoppscotch:2025.12.1` | Open-source API testing client. REST, GraphQL, WebSocket, SSE, MQTT. Postman alternative with collections, environments, and history. |
| **[IT-Tools](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/it-tools.md)** | `corentinth/it-tools:latest` | Collection of ~80 daily-dev utilities: JSON/YAML formatters, hash generators, JWT decoder, base64, regex tester, cron parser, and friends. |
| **[Mailpit](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/mailpit.md)** | `axllent/mailpit:v1.28` | SMTP sink + web UI for intercepting test emails. Point any app's SMTP at Mailpit and inspect every email it would have sent — indispensable for developing email flows. |
| **[Portainer](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/portainer.md)** | `portainer/portainer-ce:2.40.0` | Docker container management UI. Browse images, inspect volumes, tail logs, exec into containers. Always protected — it controls the entire Docker daemon. |
| **[Wetty](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/wetty.md)** | `wettyoss/wetty:latest` | SSH terminal in the browser. Always protected — it literally gives you a shell on the host. The emergency break-glass access path when something is wrong and you can't ssh from your laptop. |
| **[Wiki.js](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/wikijs.md)** | `requarks/wiki:2.5.306` | Modern wiki and knowledge base with Markdown, WYSIWYG, Git sync, and fine-grained ACLs. Run it privately for team docs or `public = true` for a real public wiki. |

## Diagrams & whiteboards

| Stack | Image | Description |
|-------|-------|-------------|
| **[Draw.io](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/drawio.md)** | `jgraph/drawio:latest` | Self-hosted Draw.io / diagrams.net for technical architecture diagrams. Saves locally in the browser by default — no upstream telemetry. |
| **[Excalidraw](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/excalidraw.md)** | `excalidraw/excalidraw:latest` | Virtual whiteboard with a deliberate hand-drawn aesthetic. Great for quick system-design sketches and workshops. Typically set to `public = true` so you can share board URLs without requiring Cloudflare Access on every viewer. |

## Secrets management

| Stack | Image | Description |
|-------|-------|-------------|
| **[Infisical](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/stacks/infisical.md)** | `infisical/infisical:v0.155.5` | Open-source secret management platform — the secrets store Nexus Stack uses *for itself*. Every other stack fetches its credentials from here at container startup. Always protected. |

---

## Choosing your stacks

You don't need to enable all 60. A typical setup is between 5 and 15 services. Some sensible starter combinations:

**Minimal data platform** — `postgres` · `metabase` · `grafana` · `portainer`
A relational database, a BI tool to query it, observability for the host, and a Docker UI to poke around. Roughly 2 GB RAM.

**Streaming pipeline** — `redpanda` · `redpanda-console` · `debezium` · `clickhouse` · `grafana`
Source-of-truth in PostgreSQL, change data capture into Redpanda via Debezium, materialized in ClickHouse, dashboards in Grafana. Around 4 GB RAM.

**Self-hosted dev environment** — `forgejo` · `forgejo-runner` · `code-server` · `woodpecker-ci` · `mailpit` · `portainer`
A full Git + CI + remote-IDE setup with email testing. Around 3 GB RAM.

**LLM playground** — `ollama` · `dify` · `postgres` · `portainer`
Local LLMs via Ollama, a workflow builder for RAG / agents via Dify. Heavy — comfortably runs on the default `cx43` (8 vCPU, 16 GB RAM); a smaller `cpx32` (4 vCPU, 8 GB) works only with a slim model selection.

**Data engineer's Swiss Army knife** — `redpanda` · `flink` · `dinky` · `postgres` · `clickhouse` · `grafana` · `kestra` · `jupyter`
Stream + batch processing, two databases, an orchestrator, a notebook, full observability. Around 6 GB RAM.

## Resource considerations

The default Hetzner server is **`cx43` (Intel-shared, 8 vCPU, 16 GB RAM, 160 GB SSD, x86) in `hel1` (Helsinki)** which handles 25–30 typical services comfortably. For lighter setups, switch to **`cpx32` (AMD, 4 vCPU, 8 GB)** or **`cx32` (Intel, 4 vCPU, 8 GB)** — the same fallbacks listed in [setup-guide.md](../admin-guides/setup-guide.md#optional-repository-variables) — to save cost; for heavier workloads, larger sizes are available via the **`SERVER_TYPE` GitHub repository variable** (Settings → Secrets and variables → Actions → Variables — see the setup-guide link for the full list of supported overrides). The Control Plane web UI displays the current value but doesn't let you edit it; changes go through the repo-variable + spin-up workflow. ARM (`cax`) variants are still supported via `SERVER_TYPE` but no longer the default — see the project README for the rationale.

Memory-hungry stacks to watch out for:

- **Apache Flink / Spark** — JVM-based, each TaskManager / Worker reserves 1+ GB
- **OpenMetadata** — requires Elasticsearch, MySQL, and the OpenMetadata server itself
- **Dify** — bundles a vector store, web app, API, plugin daemon, and worker
- **Ollama** — model size dictates RAM (a 7B model needs ~5 GB just for inference)
- **Superset / Metabase** — Java/Python web servers; ~500 MB each at idle

## Adding a new stack

Each stack is a self-contained module under [`stacks/`](https://github.com/stefanko-ch/Nexus-Stack/tree/main/stacks) in the Nexus-Stack repository. To contribute a new service:

1. Create a folder `stacks/<your-service>/`
2. Add a `docker-compose.yml` — use the `${IMAGE_YOURSERVICE:-upstream/image:tag}` pattern so the image can be overridden via env var
3. Add an OpenTofu module (DNS, tunnel ingress, Cloudflare Access policy, Infisical secret)
4. Register it in the Control Plane manifest
5. Add a doc file under `docs/stacks/<your-service>.md` following the template (tagline, settings table, architecture, credentials)
6. Open a PR

→ Full contribution guide: [CONTRIBUTING.md](https://github.com/stefanko-ch/Nexus-Stack/blob/main/docs/CONTRIBUTING.md)
