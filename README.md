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

## Available Stacks

![IT-Tools](https://img.shields.io/badge/IT--Tools-5D5D5D?logo=homeassistant&logoColor=white)
![Excalidraw](https://img.shields.io/badge/Excalidraw-6965DB?logo=excalidraw&logoColor=white)
![Portainer](https://img.shields.io/badge/Portainer-13BEF9?logo=portainer&logoColor=white)
![Uptime Kuma](https://img.shields.io/badge/Uptime%20Kuma-5CDD8B?logo=uptimekuma&logoColor=white)
![Infisical](https://img.shields.io/badge/Infisical-000000?logo=infisical&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)
![Hoppscotch](https://img.shields.io/badge/Hoppscotch-201718?logo=hoppscotch&logoColor=white)
![Kafka-UI](https://img.shields.io/badge/Kafka--UI-000000?logo=apachekafka&logoColor=white)
![Kestra](https://img.shields.io/badge/Kestra-6047EC?logo=kestra&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-EA4B71?logo=n8n&logoColor=white)
![Marimo](https://img.shields.io/badge/Marimo-1C1C1C?logo=python&logoColor=white)
![Mailpit](https://img.shields.io/badge/Mailpit-F36F21?logo=maildotru&logoColor=white)
![Metabase](https://img.shields.io/badge/Metabase-509EE3?logo=metabase&logoColor=white)
![Meltano](https://img.shields.io/badge/Meltano-512EFF?logo=meltano&logoColor=white)
![Redpanda](https://img.shields.io/badge/Redpanda-E4405F?logo=redpanda&logoColor=white)
![Redpanda Connect](https://img.shields.io/badge/Redpanda%20Connect-E4405F?logo=redpanda&logoColor=white)
![Redpanda Datagen](https://img.shields.io/badge/Redpanda%20Datagen-E4405F?logo=redpanda&logoColor=white)
![CloudBeaver](https://img.shields.io/badge/CloudBeaver-3776AB?logo=dbeaver&logoColor=white)
![Mage](https://img.shields.io/badge/Mage-6B4FBB?logo=mage&logoColor=white)
![MinIO](https://img.shields.io/badge/MinIO-C72E49?logo=minio&logoColor=white)
![Wetty](https://img.shields.io/badge/Wetty-000000?logo=gnubash&logoColor=white)
![Info](https://img.shields.io/badge/Info-00D4AA?logo=nginx&logoColor=white)

| Stack | Description | Website |
|-------|-------------|--------|
| **IT-Tools** | Collection of handy online tools for developers | [it-tools.tech](https://it-tools.tech) |
| **Excalidraw** | Virtual whiteboard for sketching hand-drawn diagrams | [excalidraw.com](https://excalidraw.com) |
| **Portainer** | Docker container management UI | [portainer.io](https://www.portainer.io) |
| **Uptime Kuma** | A fancy self-hosted monitoring tool | [uptime.kuma.pet](https://uptime.kuma.pet) |
| **Infisical** | Open-source secret management platform | [infisical.com](https://infisical.com) |
| **Grafana** | Full observability stack with Prometheus, Loki & dashboards | [grafana.com](https://grafana.com) |
| **Hoppscotch** | Open-source API testing platform (Postman alternative) | [hoppscotch.io](https://hoppscotch.io) |
| **Kafka-UI** | Modern web UI for Apache Kafka / Redpanda management | [kafka-ui.provectus.io](https://docs.kafka-ui.provectus.io/) |
| **Kestra** | Modern workflow orchestration for data pipelines & automation | [kestra.io](https://kestra.io) |
| **n8n** | Workflow automation tool - automate anything | [n8n.io](https://n8n.io) |
| **Marimo** | Reactive Python notebook with SQL support | [marimo.io](https://marimo.io) |
| **Mailpit** | Email & SMTP testing tool - catch and inspect emails | [mailpit.axllent.org](https://mailpit.axllent.org) |
| **Metabase** | Open-source business intelligence and analytics tool | [metabase.com](https://www.metabase.com) |
| **Meltano** | Open-source data integration platform for building modular data pipelines | [meltano.com](https://meltano.com) |
| **Redpanda** | Kafka-compatible streaming platform with Console UI | [redpanda.com](https://redpanda.com) |
| **Redpanda Connect** | Declarative data streaming framework for real-time pipelines | [redpanda.com](https://redpanda.com) |
| **Redpanda Datagen** | Test data generator for Redpanda topics | [redpanda.com](https://redpanda.com) |
| **CloudBeaver** | Web-based database management tool | [dbeaver.com/cloudbeaver](https://dbeaver.com/cloudbeaver/) |
| **Mage** | Modern data pipeline tool for ETL/ELT workflows | [mage.ai](https://mage.ai) |
| **MinIO** | S3-compatible object storage for data lakes & backups | [min.io](https://min.io) |
| **Wetty** | Web-based SSH terminal - access server terminal from any browser | [GitHub](https://github.com/butlerx/wetty) |
| **Info** | Landing page with service overview dashboard | — |

→ See [docs/stacks.md](docs/stacks.md) for detailed stack documentation and how to add new services.

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
| [Stacks](docs/stacks.md) | Available services and how to add new ones |
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
