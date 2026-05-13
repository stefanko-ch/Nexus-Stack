# Nexus-Stack

![Nexus-Stack](docs/assets/Nexus-Logo-BlackWhite.png)

[![GitHub License](https://img.shields.io/github/license/stefanko-ch/Nexus-Stack)](https://github.com/stefanko-ch/Nexus-Stack/blob/main/LICENSE)
[![GitHub Issues](https://img.shields.io/github/issues/stefanko-ch/Nexus-Stack)](https://github.com/stefanko-ch/Nexus-Stack/issues)
[![GitHub Pull Requests](https://img.shields.io/github/issues-pr/stefanko-ch/Nexus-Stack)](https://github.com/stefanko-ch/Nexus-Stack/pulls)
[![GitHub Last Commit](https://img.shields.io/github/last-commit/stefanko-ch/Nexus-Stack)](https://github.com/stefanko-ch/Nexus-Stack/commits/main)
[![Tests](https://github.com/stefanko-ch/Nexus-Stack/actions/workflows/python-tests.yml/badge.svg)](https://github.com/stefanko-ch/Nexus-Stack/actions/workflows/python-tests.yml)
[![codecov](https://codecov.io/gh/stefanko-ch/Nexus-Stack/branch/main/graph/badge.svg)](https://codecov.io/gh/stefanko-ch/Nexus-Stack)

[![OpenTofu](https://img.shields.io/badge/OpenTofu-FFDA18?logo=opentofu&logoColor=black)](https://opentofu.org/)
[![Hetzner](https://img.shields.io/badge/Hetzner-D50C2D?logo=hetzner&logoColor=white)](https://www.hetzner.com/)
[![Cloudflare](https://img.shields.io/badge/Cloudflare-F38020?logo=cloudflare&logoColor=white)](https://www.cloudflare.com/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)](https://docs.github.com/actions)
[![GitHub](https://img.shields.io/badge/GitHub-181717?logo=github&logoColor=white)](https://github.com/)
[![Resend](https://img.shields.io/badge/Resend-000000?logo=resend&logoColor=white)](https://resend.com/)

🚀 **One-command deployment: Hetzner server + Cloudflare Tunnel + Docker - fully automated via GitHub Actions.**

> ⚠️ **Disclaimer:** This project is currently under active development. Use at your own risk. While care has been taken to ensure security, you are responsible for reviewing the code and understanding what it does before running it.

> 📋 **Deployment Method:** This project uses **GitHub Actions exclusively**. Local deployment is not supported as it bypasses the Control Plane architecture.

## What This Does

### Infrastructure
- **Hetzner Cloud Server** - x86 (default `cx43` in `hel1`, Intel-shared 8 vCPU / 16 GB RAM / 160 GB) running Ubuntu 24.04 — defaults switched permanently from ARM in 2026-05 because (a) Hetzner ARM EU capacity has been unavailable since 2026-01-22, and (b) Hetzner's 2025+ pricing flipped — ARM is now ~40% more expensive than the equivalent x86 spec. Smaller x86 alternatives (`cpx32` AMD 4-vCPU/8-GB, `cx32` Intel 4-vCPU/8-GB) and ARM (`cax*`) variants are supported via the `SERVER_TYPE` / `SERVER_LOCATION` repo variables for users who want to override the default — see [docs/admin-guides/setup-guide.md](docs/admin-guides/setup-guide.md#optional-repository-variables) for the canonical list
- **Cloudflare Tunnel** - All traffic routed through Cloudflare, zero open ports
- **Cloudflare Access** - Email OTP authentication for all services
- **Remote State** - OpenTofu state stored in Cloudflare R2

### Automation
- **Control Plane** - Web UI to manage infrastructure (spin up, teardown, services)
- **GitHub Actions** - Full CI/CD deployment without local tools
- **Scheduled Teardown** - Optional daily auto-shutdown to save costs (with configurable policy to prevent users from disabling it)
- **Email Notifications** - Credentials and status emails via Resend

### Security
- **Zero Entry** - Zero open ports = Zero attack surface
- **Firewall Management** - Open specific TCP ports for external access (Kafka, PostgreSQL, MinIO) via Control Plane, auto-reset on teardown
- **Service Tokens** - Headless SSH access for CI/CD
- **Secrets Management** - Centralized in Infisical with auto-provisioning

### Developer Experience
- **GitHub Actions Only** - No local tools required, fully automated deployment
- **Modular Stacks** - Enable/disable services via Control Plane
- **Auto-Setup** - Admin users created automatically with generated passwords
- **Info Page** - Dashboard with all service URLs and credentials

## Prerequisites

- **[Hetzner Cloud](https://console.hetzner.cloud/) account** - For the server
- **[Cloudflare](https://cloudflare.com) account** - Free tier is sufficient
- **[Resend](https://resend.com) account** - For email notifications (credentials, status updates)
- **A domain** - Must be [added to Cloudflare](https://developers.cloudflare.com/fundamentals/setup/manage-domains/add-site/) (Cloudflare manages DNS)
- **[Docker Hub](https://hub.docker.com) account** *(optional)* - Increases pull rate limits for Docker images

## Getting Started

→ See the **[Setup Guide](docs/admin-guides/setup-guide.md)** for complete installation instructions.

After deployment you'll have:
- `https://control.yourdomain.com` - Control Panel to manage services and view URLs

### Quick Start Flow

![Quick Start Flow](docs/assets/architecture-quickstart.svg)

## Available Stacks (65)

[![AKHQ](https://img.shields.io/badge/AKHQ-000000?logo=apachekafka&logoColor=white)](https://akhq.io)
[![Adminer](https://img.shields.io/badge/Adminer-34567C?logo=adminer&logoColor=white)](https://www.adminer.org)
[![Appsmith](https://img.shields.io/badge/Appsmith-F86A2E?logo=appsmith&logoColor=white)](https://appsmith.com)
[![Big-AGI](https://img.shields.io/badge/Big--AGI-FF6B35?logo=openai&logoColor=white)](https://github.com/enricoros/big-agi)
[![Budibase](https://img.shields.io/badge/Budibase-9981F5?logo=budibase&logoColor=white)](https://budibase.com)
[![CloudBeaver](https://img.shields.io/badge/CloudBeaver-3776AB?logo=dbeaver&logoColor=white)](https://dbeaver.com/cloudbeaver/)
[![ClickHouse](https://img.shields.io/badge/ClickHouse-FFCC00?logo=clickhouse&logoColor=black)](https://clickhouse.com)
[![code-server](https://img.shields.io/badge/code--server-007ACC?logo=visualstudiocode&logoColor=white)](https://coder.com)
[![Crawl4AI](https://img.shields.io/badge/Crawl4AI-1B6CA8?logo=googlechrome&logoColor=white)](https://github.com/unclecode/crawl4ai)
[![Dagster](https://img.shields.io/badge/Dagster-4F43DD?logo=dagster&logoColor=white)](https://dagster.io)
[![Debezium](https://img.shields.io/badge/Debezium-4E8CBF?logo=debezium&logoColor=white)](https://debezium.io)
[![Dify](https://img.shields.io/badge/Dify-1677FF?logoColor=white)](https://dify.ai)
[![Dinky](https://img.shields.io/badge/Dinky-1677FF?logo=apacheflink&logoColor=white)](https://www.dinky.org.cn/)
[![Draw.io](https://img.shields.io/badge/Draw.io-F08705?logo=diagramsdotnet&logoColor=white)](https://www.diagrams.net)
[![Excalidraw](https://img.shields.io/badge/Excalidraw-6965DB?logo=excalidraw&logoColor=white)](https://excalidraw.com)
[![Filestash](https://img.shields.io/badge/Filestash-2B3A67?logo=files&logoColor=white)](https://www.filestash.app)
[![Flink](https://img.shields.io/badge/Apache_Flink-E6526F?logo=apacheflink&logoColor=white)](https://flink.apache.org)
[![Garage](https://img.shields.io/badge/Garage-59C6A6?logo=amazons3&logoColor=white)](https://garagehq.deuxfleurs.fr)
[![Git Proxy](https://img.shields.io/badge/Git_Proxy-009639?logo=nginx&logoColor=white)](docs/stacks/git-proxy.md)
[![Gitea](https://img.shields.io/badge/Gitea-609926?logo=gitea&logoColor=white)](https://about.gitea.com)
[![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)](https://grafana.com)
[![Hoppscotch](https://img.shields.io/badge/Hoppscotch-201718?logo=hoppscotch&logoColor=white)](https://hoppscotch.io)
[![Infisical](https://img.shields.io/badge/Infisical-000000?logo=infisical&logoColor=white)](https://infisical.com)
[![IT-Tools](https://img.shields.io/badge/IT--Tools-5D5D5D?logo=homeassistant&logoColor=white)](https://it-tools.tech)
[![Jupyter](https://img.shields.io/badge/Jupyter-F37726?logo=jupyter&logoColor=white)](https://jupyter.org)
[![Kafdrop](https://img.shields.io/badge/Kafdrop-000000?logo=apachekafka&logoColor=white)](https://github.com/obsidiandynamics/kafdrop)
[![Kafka-UI](https://img.shields.io/badge/Kafka--UI-000000?logo=apachekafka&logoColor=white)](https://docs.kafka-ui.provectus.io/)
[![Kestra](https://img.shields.io/badge/Kestra-6047EC?logo=kestra&logoColor=white)](https://kestra.io)
[![LakeFS](https://img.shields.io/badge/LakeFS-00B4D8?logo=git&logoColor=white)](https://lakefs.io)
[![Mage](https://img.shields.io/badge/Mage-6B4FBB?logo=mage&logoColor=white)](https://mage.ai)
[![Mailpit](https://img.shields.io/badge/Mailpit-F36F21?logo=maildotru&logoColor=white)](https://mailpit.axllent.org)
[![Marimo](https://img.shields.io/badge/Marimo-1C1C1C?logo=python&logoColor=white)](https://marimo.io)
[![Meltano](https://img.shields.io/badge/Meltano-512EFF?logo=meltano&logoColor=white)](https://meltano.com)
[![Metabase](https://img.shields.io/badge/Metabase-509EE3?logo=metabase&logoColor=white)](https://www.metabase.com)
[![MinIO](https://img.shields.io/badge/MinIO-C72E49?logo=minio&logoColor=white)](https://min.io)
[![n8n](https://img.shields.io/badge/n8n-EA4B71?logo=n8n&logoColor=white)](https://n8n.io)
[![NocoDB](https://img.shields.io/badge/NocoDB-1F2937?logo=nocodb&logoColor=white)](https://nocodb.com)
[![Ollama](https://img.shields.io/badge/Ollama-000000?logo=ollama&logoColor=white)](https://ollama.com)
[![OpenMetadata](https://img.shields.io/badge/OpenMetadata-7147E8?logoColor=white)](https://open-metadata.org)
[![pg_ducklake](https://img.shields.io/badge/pg__ducklake-336791?logo=postgresql&logoColor=white)](https://pgducklake.select)
[![pgAdmin](https://img.shields.io/badge/pgAdmin-336791?logo=postgresql&logoColor=white)](https://www.pgadmin.org)
[![Portainer](https://img.shields.io/badge/Portainer-13BEF9?logo=portainer&logoColor=white)](https://www.portainer.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Prefect](https://img.shields.io/badge/Prefect-024DFD?logo=prefect&logoColor=white)](https://www.prefect.io)
[![Quickwit](https://img.shields.io/badge/Quickwit-FF6B6B?logo=quickwit&logoColor=white)](https://quickwit.io)
[![Redpanda](https://img.shields.io/badge/Redpanda-E4405F?logo=redpanda&logoColor=white)](https://redpanda.com)
[![Redpanda Connect](https://img.shields.io/badge/Redpanda%20Connect-E4405F?logo=redpanda&logoColor=white)](https://redpanda.com)
[![Redpanda Datagen](https://img.shields.io/badge/Redpanda%20Datagen-E4405F?logo=redpanda&logoColor=white)](https://redpanda.com)
[![RisingWave](https://img.shields.io/badge/RisingWave-0065FF?logoColor=white)](https://risingwave.com)
[![RustFS](https://img.shields.io/badge/RustFS-B7410E?logo=rust&logoColor=white)](https://rustfs.com)
[![S3 Manager](https://img.shields.io/badge/S3_Manager-2E7D32?logo=amazons3&logoColor=white)](https://github.com/cloudlena/s3manager)
[![SeaweedFS](https://img.shields.io/badge/SeaweedFS-4CAF50?logo=amazons3&logoColor=white)](https://seaweedfs.com)
[![SFTPGo](https://img.shields.io/badge/SFTPGo-2D3748?logo=files&logoColor=white)](https://sftpgo.com)
[![Sling](https://img.shields.io/badge/Sling-FF6B35?logo=data&logoColor=white)](https://slingdata.io)
[![Soda](https://img.shields.io/badge/Soda-6C47FF?logo=database&logoColor=white)](https://www.soda.io)
[![Spark](https://img.shields.io/badge/Apache_Spark-E25A1C?logo=apachespark&logoColor=white)](https://spark.apache.org)
[![Superset](https://img.shields.io/badge/Apache_Superset-20A6A4?logo=apachesuperset&logoColor=white)](https://superset.apache.org)
[![Telegraf](https://img.shields.io/badge/Telegraf-22ADF6?logo=influxdb&logoColor=white)](https://www.influxdata.com/time-series-platform/telegraf/)
[![Trino](https://img.shields.io/badge/Trino-DD00A1?logo=trino&logoColor=white)](https://trino.io)
[![Uptime Kuma](https://img.shields.io/badge/Uptime%20Kuma-5CDD8B?logo=uptimekuma&logoColor=white)](https://uptime.kuma.pet)
[![Vector](https://img.shields.io/badge/Vector-3B2F63?logo=vector&logoColor=white)](https://vector.dev)
[![Wetty](https://img.shields.io/badge/Wetty-000000?logo=gnubash&logoColor=white)](https://github.com/butlerx/wetty)
[![Wiki.js](https://img.shields.io/badge/Wiki.js-1976D2?logo=wikidotjs&logoColor=white)](https://js.wiki)
[![Windmill](https://img.shields.io/badge/Windmill-3B82F6?logo=windowsterminal&logoColor=white)](https://www.windmill.dev)
[![Woodpecker CI](https://img.shields.io/badge/Woodpecker_CI-4CAF50?logo=woodpeckerci&logoColor=white)](https://woodpecker-ci.org)

| Stack | Description | Website |
|-------|-------------|--------|
| **AKHQ** | Kafka/Redpanda management GUI for topics, consumer groups, schema registry, and Kafka Connect | [akhq.io](https://akhq.io) |
| **Adminer** | Lightweight database management tool (supports PostgreSQL, MySQL, SQLite, etc.) | [adminer.org](https://www.adminer.org) |
| **Appsmith** | Open-source low-code platform for building admin panels, dashboards, and internal tools | [appsmith.com](https://appsmith.com) |
| **Big-AGI** | Stateless multi-LLM web UI for OpenAI, Anthropic, and local LLM endpoints (browser-side state, no server DB) | [github.com/enricoros/big-agi](https://github.com/enricoros/big-agi) |
| **Budibase** | Open-source low-code platform for building internal tools and dashboards | [budibase.com](https://budibase.com) |
| **CloudBeaver** | Web-based database management tool | [dbeaver.com/cloudbeaver](https://dbeaver.com/cloudbeaver/) |
| **ClickHouse** | Fast columnar database for real-time analytics and OLAP queries | [clickhouse.com](https://clickhouse.com) |
| **code-server** | VS Code in the browser for remote development | [coder.com](https://coder.com) |
| **Crawl4AI** | LLM-friendly web crawler that returns clean Markdown for RAG ingestion (REST API + Playground UI) | [github.com/unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) |
| **Dagster** | Python-native data orchestration for data pipelines and Software-Defined Assets | [dagster.io](https://dagster.io) |
| **Debezium** | Change data capture - streams database changes to Redpanda/Kafka in real time | [debezium.io](https://debezium.io) |
| **Dify** | AI workflow builder for LLM applications, RAG pipelines, and agents | [dify.ai](https://dify.ai) |
| **Dinky** | Web-based Flink SQL IDE with auto-completion and job management | [dinky.org.cn](https://www.dinky.org.cn/) |
| **Draw.io** | Flowchart and diagramming tool for technical diagrams | [diagrams.net](https://www.diagrams.net) |
| **Excalidraw** | Virtual whiteboard for sketching hand-drawn diagrams | [excalidraw.com](https://excalidraw.com) |
| **Filestash** | Web-based file manager with S3/FTP/SFTP/WebDAV backend support | [filestash.app](https://www.filestash.app) |
| **Flink** | Distributed stream and batch processing engine (JobManager + TaskManager cluster) | [flink.apache.org](https://flink.apache.org) |
| **Garage** | Lightweight S3-compatible object storage for self-hosting | [garagehq.deuxfleurs.fr](https://garagehq.deuxfleurs.fr) |
| **Git Proxy** | Public Git HTTPS proxy for external tools (Databricks, Git Desktop) | [Documentation](docs/stacks/git-proxy.md) |
| **Gitea** | Self-hosted Git service with pull requests, code review, and CI/CD | [gitea.com](https://about.gitea.com) |
| **Grafana** | Full observability stack with Prometheus, Loki & dashboards | [grafana.com](https://grafana.com) |
| **Hoppscotch** | Open-source API testing platform (Postman alternative) | [hoppscotch.io](https://hoppscotch.io) |
| **Infisical** | Open-source secret management platform | [infisical.com](https://infisical.com) |
| **IT-Tools** | Collection of handy online tools for developers | [it-tools.tech](https://it-tools.tech) |
| **Jupyter** | Interactive PySpark notebook platform with Spark SQL support and cluster connectivity | [jupyter.org](https://jupyter.org) |
| **Kafdrop** | Lightweight Kafka/Redpanda web UI for browsing topics and consumer groups | [GitHub](https://github.com/obsidiandynamics/kafdrop) |
| **Kafka-UI** | Modern web UI for Apache Kafka / Redpanda management | [kafka-ui.provectus.io](https://docs.kafka-ui.provectus.io/) |
| **Kestra** | Modern workflow orchestration for data pipelines & automation | [kestra.io](https://kestra.io) |
| **LakeFS** | Git-like version control for data lakes (Hetzner Object Storage backend) | [lakefs.io](https://lakefs.io) |
| **Mage** | Modern data pipeline tool for ETL/ELT workflows | [mage.ai](https://mage.ai) |
| **Mailpit** | Email & SMTP testing tool - catch and inspect emails | [mailpit.axllent.org](https://mailpit.axllent.org) |
| **Marimo** | Reactive Python notebook with SQL support | [marimo.io](https://marimo.io) |
| **Meltano** | Open-source data integration platform (CLI-only, no web UI) | [meltano.com](https://meltano.com) |
| **Metabase** | Open-source business intelligence and analytics tool | [metabase.com](https://www.metabase.com) |
| **MinIO** | S3-compatible object storage for data lakes & backups | [min.io](https://min.io) |
| **n8n** | Workflow automation tool - automate anything | [n8n.io](https://n8n.io) |
| **NocoDB** | Open-source Airtable alternative - turn any database into a spreadsheet | [nocodb.com](https://nocodb.com) |
| **Ollama** | Local LLM inference with Open WebUI chat interface | [openwebui.com](https://openwebui.com) |
| **OpenMetadata** | Open-source metadata management for data discovery and governance | [open-metadata.org](https://open-metadata.org) |
| **pg_ducklake** | PostgreSQL with DuckLake extension - SQL-native lakehouse with S3 storage | [pgducklake.select](https://pgducklake.select) |
| **pgAdmin** | PostgreSQL administration and development platform | [pgadmin.org](https://www.pgadmin.org) |
| **Portainer** | Always-on Docker dashboard — first stop for inspecting a misbehaving container (logs, state, restart). Auto-deployed alongside Gitea/Grafana/Infisical | [portainer.io](https://www.portainer.io) |
| **PostgreSQL** | Powerful open-source relational database (internal-only, no web UI) | [postgresql.org](https://www.postgresql.org) |
| **Prefect** | Modern Python-native workflow orchestration for data pipelines | [prefect.io](https://www.prefect.io) |
| **Quickwit** | Cloud-native search engine for log management and analytics | [quickwit.io](https://quickwit.io) |
| **Redpanda** | Kafka-compatible streaming platform with Console UI | [redpanda.com](https://redpanda.com) |
| **Redpanda Connect** | Declarative data streaming framework for real-time pipelines | [redpanda.com](https://redpanda.com) |
| **Redpanda Datagen** | Test data generator for Redpanda topics | [redpanda.com](https://redpanda.com) |
| **RisingWave** | PostgreSQL-compatible streaming database for real-time materialized views | [risingwave.com](https://risingwave.com) |
| **RustFS** | Rust-based S3-compatible object storage (MinIO alternative) | [rustfs.com](https://rustfs.com) |
| **S3 Manager** | Web-based S3 bucket browser and manager for Hetzner Object Storage | [GitHub](https://github.com/cloudlena/s3manager) |
| **SeaweedFS** | Distributed object storage with Filer UI and S3 API | [seaweedfs.com](https://seaweedfs.com) |
| **SFTPGo** | SFTP/SCP server with R2 backend (file-protocol front door onto the datalake; WebDAV/FTPS supported upstream, disabled by default) | [sftpgo.com](https://sftpgo.com) |
| **Sling** | Lightweight CLI for database-to-database and file-to-database transfers | [slingdata.io](https://slingdata.io) |
| **Soda** | Data quality testing with SodaCL checks (CLI-only, no web UI) | [soda.io](https://www.soda.io) |
| **Spark** | Distributed data processing engine (Master + Worker cluster) | [spark.apache.org](https://spark.apache.org) |
| **Superset** | Modern data exploration and visualization platform with SQL Lab | [superset.apache.org](https://superset.apache.org) |
| **Telegraf** | Metrics collection agent with 300+ plugins (CLI-only, no web UI) | [influxdata.com](https://www.influxdata.com/time-series-platform/telegraf/) |
| **Trino** | Distributed SQL query engine for querying data across multiple sources | [trino.io](https://trino.io) |
| **Uptime Kuma** | A fancy self-hosted monitoring tool | [uptime.kuma.pet](https://uptime.kuma.pet) |
| **Vector** | High-performance observability pipeline for logs, metrics, and traces | [vector.dev](https://vector.dev) |
| **Wetty** | Web-based SSH terminal - access server terminal from any browser | [GitHub](https://github.com/butlerx/wetty) |
| **Wiki.js** | Open-source wiki and knowledge base with Markdown and visual editor | [js.wiki](https://js.wiki) |
| **Windmill** | Open-source workflow engine for scripts, workflows, and UIs | [windmill.dev](https://www.windmill.dev) |
| **Woodpecker CI** | Lightweight Docker-native CI/CD engine with pipeline-as-code | [woodpecker-ci.org](https://woodpecker-ci.org) |

→ See [docs/stacks/README.md](docs/stacks/README.md) for detailed stack documentation and how to add new services.

## Control Plane

Manage your Nexus-Stack infrastructure via web interface at `https://control.YOUR_DOMAIN`.

**Features:**
- ⚡ **Spin Up / Teardown** - Start and stop infrastructure with one click
- 🧩 **Services** - Enable/disable services dynamically
- ⏰ **Scheduled Teardown** - Auto-shutdown to save costs
- 📧 **Email Credentials** - Send login credentials to your inbox

## GitHub Actions Workflows

| Workflow | Description |
|----------|-------------|
| **Initial Setup** | One-time setup (Control Plane + Spin Up). Supports `enabled_services` parameter to pre-select services. |
| **Spin Up** | Re-create infrastructure after teardown |
| **Teardown** | Teardown infrastructure (keeps state) |
| **Destroy All** | Delete everything |
| **Cleanup Orphaned Resources** | Manual cleanup of orphaned Cloudflare resources |

**Pre-select services during Initial Setup:**
```bash
# Core services (Gitea, Grafana, Infisical, Portainer) are always enabled —
# pass any additional services you want active on the first spin-up.
gh workflow run initial-setup.yaml -f enabled_services="n8n,kestra"
```

→ See [docs/admin-guides/setup-guide.md](docs/admin-guides/setup-guide.md) for configuration details.

## Architecture

![Architecture Overview](docs/assets/architecture-overview.svg)

## Security

This setup achieves **zero open ports** after deployment:

1. During initial setup, SSH (port 22) is temporarily open
2. OpenTofu installs the Cloudflare Tunnel via SSH
3. After tunnel is running, SSH port is **automatically closed** via Hetzner API
4. All future SSH access goes through Cloudflare Tunnel

**Result:** No attack surface. All traffic flows through Cloudflare.

> **Firewall Management:** For TCP-based services (Kafka, PostgreSQL, MinIO S3 API), the Control Plane provides a Firewall Management page to selectively open ports. DNS A records are created pointing directly to the server IP (`proxied = false`). All firewall rules are automatically reset on every Teardown for security.

![Security Flow](docs/assets/architecture-security.svg)

- Services are protected by Cloudflare Access (email OTP)
- Set `public = true` in config if you want a service publicly accessible (bypasses Zero Trust)

## Documentation

| Document | Description |
|----------|-------------|
| [Setup Guide](docs/admin-guides/setup-guide.md) | Complete installation and configuration |
| [Control Plane Guide](docs/user-guides/control-plane.md) | How to use the Control Plane web interface |
| [Stacks](docs/stacks/README.md) | Available services and how to add new ones |
| [Contributing](docs/CONTRIBUTING.md) | How to contribute to the project |
| [Migration to Python](docs/admin-guides/migration-to-python.md) | `scripts/deploy.sh` → `nexus_deploy` package (completed Phase 4c via [issue #505](https://github.com/stefanko-ch/Nexus-Stack/issues/505) / [PR #535](https://github.com/stefanko-ch/Nexus-Stack/pull/535)) |

## How It Works

**Read the full story behind Nexus-Stack:**

**[Nexus-Stack: Your Data, Your Rules, Your Flow](https://stefanko-ch.medium.com/nexus-stack-your-data-your-rules-your-flow-46b29abc062d)**

For a detailed technical explanation of how this infrastructure works under the hood - including the Docker deployment on Hetzner and the Cloudflare Zero Trust Tunnel security setup - check out this article:

**[Secure Hetzner Docker Deployment via Cloudflare Zero Trust Tunnel](https://medium.com/@stefanko-ch/secure-hetzner-docker-deployment-via-cloudflare-zero-trust-tunnel-8f716c4631ce)**

## Project Website

Learn more about Nexus-Stack and explore the full documentation:

**[https://nexus-stack.ch/](https://nexus-stack.ch/)**

## License

[MIT](LICENSE)
