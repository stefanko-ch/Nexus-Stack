# Nexus-Stack

![Nexus-Stack](docs/images/Nexus-Logo-BlackWhite.png)

![GitHub License](https://img.shields.io/github/license/stefanko-ch/Nexus-Stack)
![GitHub issues](https://img.shields.io/github/issues/stefanko-ch/Nexus-Stack)
![GitHub pull requests](https://img.shields.io/github/issues-pr/stefanko-ch/Nexus-Stack)
![GitHub last commit](https://img.shields.io/github/last-commit/stefanko-ch/Nexus-Stack)

![OpenTofu](https://img.shields.io/badge/OpenTofu-FFDA18?logo=opentofu&logoColor=black)
![Hetzner](https://img.shields.io/badge/Hetzner-D50C2D?logo=hetzner&logoColor=white)
![Cloudflare](https://img.shields.io/badge/Cloudflare-F38020?logo=cloudflare&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)
![GitHub](https://img.shields.io/badge/GitHub-181717?logo=github&logoColor=white)
![Resend](https://img.shields.io/badge/Resend-000000?logo=resend&logoColor=white)

🚀 **One-command deployment: Hetzner server + Cloudflare Tunnel + Docker - fully automated via GitHub Actions.**

> ⚠️ **Disclaimer:** This project is currently under active development. Use at your own risk. While care has been taken to ensure security, you are responsible for reviewing the code and understanding what it does before running it.

> 📋 **Deployment Method:** This project uses **GitHub Actions exclusively**. Local deployment is not supported as it bypasses the Control Plane architecture.

## What This Does

### Infrastructure
- **Hetzner Cloud Server** - ARM-based (cax11/cax31) running Ubuntu 24.04
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

→ See the **[Setup Guide](docs/setup-guide.md)** for complete installation instructions.

After deployment you'll have:
- `https://control.yourdomain.com` - Control Plane to manage infrastructure
- `https://info.yourdomain.com` - Service dashboard with credentials

### Quick Start Flow

```mermaid
flowchart LR
    subgraph prep ["1. Preparation"]
        A[Fork Repository] --> B[Create Accounts]
        B --> B1[Hetzner]
        B --> B2[Cloudflare]
        B --> B3[Resend]
        B --> B4[Docker Hub - Optional]
    end

    subgraph config ["2. Configuration"]
        B1 & B2 & B3 --> C[Generate API Tokens]
        C --> D[Add GitHub Secrets]
    end

    subgraph deploy ["3. Deploy"]
        D --> E[Run Initial Setup]
        E --> F[Control Plane Ready]
        F --> G[Services Running]
    end

    subgraph access ["4. Access"]
        G --> H[Login via Email OTP]
        H --> I[Use Services]
    end
```

## Available Stacks (49)

![Adminer](https://img.shields.io/badge/Adminer-34567C?logo=adminer&logoColor=white)
![CloudBeaver](https://img.shields.io/badge/CloudBeaver-3776AB?logo=dbeaver&logoColor=white)
![ClickHouse](https://img.shields.io/badge/ClickHouse-FFCC00?logo=clickhouse&logoColor=black)
![code-server](https://img.shields.io/badge/code--server-007ACC?logo=visualstudiocode&logoColor=white)
![Dify](https://img.shields.io/badge/Dify-1677FF?logoColor=white)
![Draw.io](https://img.shields.io/badge/Draw.io-F08705?logo=diagramsdotnet&logoColor=white)
![Excalidraw](https://img.shields.io/badge/Excalidraw-6965DB?logo=excalidraw&logoColor=white)
![Filestash](https://img.shields.io/badge/Filestash-2B3A67?logo=files&logoColor=white)
![Garage](https://img.shields.io/badge/Garage-59C6A6?logo=amazons3&logoColor=white)
![Git Proxy](https://img.shields.io/badge/Git_Proxy-009639?logo=nginx&logoColor=white)
![Gitea](https://img.shields.io/badge/Gitea-609926?logo=gitea&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)
![Hoppscotch](https://img.shields.io/badge/Hoppscotch-201718?logo=hoppscotch&logoColor=white)
![Info](https://img.shields.io/badge/Info-00D4AA?logo=nginx&logoColor=white)
![Infisical](https://img.shields.io/badge/Infisical-000000?logo=infisical&logoColor=white)
![IT-Tools](https://img.shields.io/badge/IT--Tools-5D5D5D?logo=homeassistant&logoColor=white)
![Jupyter](https://img.shields.io/badge/Jupyter-F37726?logo=jupyter&logoColor=white)
![Kafka-UI](https://img.shields.io/badge/Kafka--UI-000000?logo=apachekafka&logoColor=white)
![Kestra](https://img.shields.io/badge/Kestra-6047EC?logo=kestra&logoColor=white)
![LakeFS](https://img.shields.io/badge/LakeFS-00B4D8?logo=git&logoColor=white)
![Mage](https://img.shields.io/badge/Mage-6B4FBB?logo=mage&logoColor=white)
![Mailpit](https://img.shields.io/badge/Mailpit-F36F21?logo=maildotru&logoColor=white)
![Marimo](https://img.shields.io/badge/Marimo-1C1C1C?logo=python&logoColor=white)
![Meltano](https://img.shields.io/badge/Meltano-512EFF?logo=meltano&logoColor=white)
![Metabase](https://img.shields.io/badge/Metabase-509EE3?logo=metabase&logoColor=white)
![MinIO](https://img.shields.io/badge/MinIO-C72E49?logo=minio&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-EA4B71?logo=n8n&logoColor=white)
![NocoDB](https://img.shields.io/badge/NocoDB-1F2937?logo=nocodb&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-000000?logo=ollama&logoColor=white)
![OpenMetadata](https://img.shields.io/badge/OpenMetadata-7147E8?logoColor=white)
![pgAdmin](https://img.shields.io/badge/pgAdmin-336791?logo=postgresql&logoColor=white)
![Portainer](https://img.shields.io/badge/Portainer-13BEF9?logo=portainer&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?logo=postgresql&logoColor=white)
![Prefect](https://img.shields.io/badge/Prefect-024DFD?logo=prefect&logoColor=white)
![Quickwit](https://img.shields.io/badge/Quickwit-FF6B6B?logo=quickwit&logoColor=white)
![Redpanda](https://img.shields.io/badge/Redpanda-E4405F?logo=redpanda&logoColor=white)
![Redpanda Connect](https://img.shields.io/badge/Redpanda%20Connect-E4405F?logo=redpanda&logoColor=white)
![Redpanda Datagen](https://img.shields.io/badge/Redpanda%20Datagen-E4405F?logo=redpanda&logoColor=white)
![RustFS](https://img.shields.io/badge/RustFS-B7410E?logo=rust&logoColor=white)
![S3 Manager](https://img.shields.io/badge/S3_Manager-2E7D32?logo=amazons3&logoColor=white)
![SeaweedFS](https://img.shields.io/badge/SeaweedFS-4CAF50?logo=amazons3&logoColor=white)
![Soda](https://img.shields.io/badge/Soda-6C47FF?logo=database&logoColor=white)
![Spark](https://img.shields.io/badge/Apache_Spark-E25A1C?logo=apachespark&logoColor=white)
![Trino](https://img.shields.io/badge/Trino-DD00A1?logo=trino&logoColor=white)
![Uptime Kuma](https://img.shields.io/badge/Uptime%20Kuma-5CDD8B?logo=uptimekuma&logoColor=white)
![Wetty](https://img.shields.io/badge/Wetty-000000?logo=gnubash&logoColor=white)
![Wiki.js](https://img.shields.io/badge/Wiki.js-1976D2?logo=wikidotjs&logoColor=white)
![Windmill](https://img.shields.io/badge/Windmill-3B82F6?logo=windowsterminal&logoColor=white)
![Woodpecker CI](https://img.shields.io/badge/Woodpecker_CI-4CAF50?logo=woodpeckerci&logoColor=white)

| Stack | Description | Website |
|-------|-------------|--------|
| **Adminer** | Lightweight database management tool (supports PostgreSQL, MySQL, SQLite, etc.) | [adminer.org](https://www.adminer.org) |
| **CloudBeaver** | Web-based database management tool | [dbeaver.com/cloudbeaver](https://dbeaver.com/cloudbeaver/) |
| **ClickHouse** | Fast columnar database for real-time analytics and OLAP queries | [clickhouse.com](https://clickhouse.com) |
| **code-server** | VS Code in the browser for remote development | [coder.com](https://coder.com) |
| **Dify** | AI workflow builder for LLM applications, RAG pipelines, and agents | [dify.ai](https://dify.ai) |
| **Draw.io** | Flowchart and diagramming tool for technical diagrams | [diagrams.net](https://www.diagrams.net) |
| **Excalidraw** | Virtual whiteboard for sketching hand-drawn diagrams | [excalidraw.com](https://excalidraw.com) |
| **Filestash** | Web-based file manager with S3/FTP/SFTP/WebDAV backend support | [filestash.app](https://www.filestash.app) |
| **Garage** | Lightweight S3-compatible object storage for self-hosting | [garagehq.deuxfleurs.fr](https://garagehq.deuxfleurs.fr) |
| **Git Proxy** | Public Git HTTPS proxy for external tools (Databricks, Git Desktop) | — |
| **Gitea** | Self-hosted Git service with pull requests, code review, and CI/CD | [gitea.com](https://about.gitea.com) |
| **Grafana** | Full observability stack with Prometheus, Loki & dashboards | [grafana.com](https://grafana.com) |
| **Hoppscotch** | Open-source API testing platform (Postman alternative) | [hoppscotch.io](https://hoppscotch.io) |
| **Info** | Landing page with service overview dashboard | — |
| **Infisical** | Open-source secret management platform | [infisical.com](https://infisical.com) |
| **IT-Tools** | Collection of handy online tools for developers | [it-tools.tech](https://it-tools.tech) |
| **Jupyter** | Interactive PySpark notebook platform with Spark SQL support and cluster connectivity | [jupyter.org](https://jupyter.org) |
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
| **pgAdmin** | PostgreSQL administration and development platform | [pgadmin.org](https://www.pgadmin.org) |
| **Portainer** | Docker container management UI | [portainer.io](https://www.portainer.io) |
| **PostgreSQL** | Powerful open-source relational database (internal-only, no web UI) | [postgresql.org](https://www.postgresql.org) |
| **Prefect** | Modern Python-native workflow orchestration for data pipelines | [prefect.io](https://www.prefect.io) |
| **Quickwit** | Cloud-native search engine for log management and analytics | [quickwit.io](https://quickwit.io) |
| **Redpanda** | Kafka-compatible streaming platform with Console UI | [redpanda.com](https://redpanda.com) |
| **Redpanda Connect** | Declarative data streaming framework for real-time pipelines | [redpanda.com](https://redpanda.com) |
| **Redpanda Datagen** | Test data generator for Redpanda topics | [redpanda.com](https://redpanda.com) |
| **RustFS** | Rust-based S3-compatible object storage (MinIO alternative) | [rustfs.com](https://rustfs.com) |
| **S3 Manager** | Web-based S3 bucket browser and manager for Hetzner Object Storage | [GitHub](https://github.com/cloudlena/s3manager) |
| **SeaweedFS** | Distributed object storage with Filer UI and S3 API | [seaweedfs.com](https://seaweedfs.com) |
| **Soda** | Data quality testing with SodaCL checks (CLI-only, no web UI) | [soda.io](https://www.soda.io) |
| **Spark** | Distributed data processing engine (Master + Worker cluster) | [spark.apache.org](https://spark.apache.org) |
| **Trino** | Distributed SQL query engine for querying data across multiple sources | [trino.io](https://trino.io) |
| **Uptime Kuma** | A fancy self-hosted monitoring tool | [uptime.kuma.pet](https://uptime.kuma.pet) |
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
gh workflow run initial-setup.yaml -f enabled_services="grafana,n8n,portainer"
```

→ See [docs/setup-guide.md](docs/setup-guide.md) for configuration details.

## Architecture

```mermaid
flowchart TB
    subgraph GH ["GitHub"]
        Actions["GitHub Actions"]
        Secrets["Secrets"]
    end

    subgraph CF ["Cloudflare"]
        DNS["DNS"]
        Access["Zero Trust Access"]
        Tunnel["Tunnel"]
        Pages["Control Plane"]
        D1[("D1 Database")]
        R2[("R2 State")]
    end

    subgraph HZ ["Hetzner Cloud"]
        FW["Firewall (0 ports)"]
        Server["Ubuntu 24.04 ARM"]
        Agent["cloudflared"]
        subgraph Docker ["Docker Containers"]
            Infisical & Grafana & n8n & More["..."]
        end
    end

    Actions -->|Deploy| Server
    Actions -->|State| R2
    Pages --> D1
    DNS --> Tunnel
    Tunnel --> Agent
    Agent --> Docker
    Access -.->|Protects| Tunnel
```

## Security

This setup achieves **zero open ports** after deployment:

1. During initial setup, SSH (port 22) is temporarily open
2. OpenTofu installs the Cloudflare Tunnel via SSH
3. After tunnel is running, SSH port is **automatically closed** via Hetzner API
4. All future SSH access goes through Cloudflare Tunnel

**Result:** No attack surface. All traffic flows through Cloudflare.

> **Firewall Management:** For TCP-based services (Kafka, PostgreSQL, MinIO S3 API), the Control Plane provides a Firewall Management page to selectively open ports. DNS A records are created pointing directly to the server IP (`proxied = false`). All firewall rules are automatically reset on every Teardown for security.

```mermaid
flowchart LR
    User(["User"]) --> DNS["DNS Lookup"]
    DNS --> Edge["Cloudflare Edge"]
    Edge --> Auth{"Cloudflare Access"}
    Auth -->|"Not authenticated"| OTP["Email OTP"]
    OTP --> Auth
    Auth -->|"Authenticated"| Tunnel["Tunnel"]
    Tunnel --> Agent["cloudflared"]
    Agent --> Container["Docker Service"]
    Container --> Response(["Response"])
```

- Services are protected by Cloudflare Access (email OTP)
- Set `public = true` in config if you want a service publicly accessible

## Documentation

| Document | Description |
|----------|-------------|
| [Setup Guide](docs/setup-guide.md) | Complete installation and configuration |
| [Control Plane Guide](docs/control-plane.md) | How to use the Control Plane web interface |
| [Stacks](docs/stacks/README.md) | Available services and how to add new ones |
| [Contributing](docs/CONTRIBUTING.md) | How to contribute to the project |

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
