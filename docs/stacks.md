# 📦 Available Stacks

This document provides detailed information about all available Docker stacks in Nexus-Stack.

## Docker Image Versions

Images are pinned to **major versions** where supported for automatic security patches while avoiding breaking changes. Versions are defined in [`tofu/image-versions.tfvars`](../tofu/image-versions.tfvars).

| Service | Image | Tag | Strategy |
|---------|-------|-----|----------|
| CloudBeaver | `dbeaver/cloudbeaver` | `24` | Major |
| Grafana | `grafana/grafana` | `12` | Major |
| Prometheus | `prom/prometheus` | `v3` | Major |
| Loki | `grafana/loki` | `3` | Major |
| Promtail | `grafana/promtail` | `3` | Major |
| cAdvisor | `gcr.io/cadvisor/cadvisor` | `v0.56` | Minor |
| Node Exporter | `prom/node-exporter` | `v1` | Major |
| Portainer | `portainer/portainer-ce` | `2` | Major |
| Uptime Kuma | `louislam/uptime-kuma` | `2` | Major |
| n8n | `n8nio/n8n` | `1` | Major |
| Kestra | `kestra/kestra` | `v1` | Major |
| Infisical | `infisical/infisical` | `v0.155.5` | Exact ¹ |
| Metabase | `metabase/metabase` | `v0.58.x` | Minor |
| Mailpit | `axllent/mailpit` | `v1` | Major |
| IT-Tools | `corentinth/it-tools` | `latest` | Latest ² |
| Excalidraw | `excalidraw/excalidraw` | `latest` | Latest ² |
| Marimo | `ghcr.io/marimo-team/marimo` | `latest-sql` | Latest ² |
| Redpanda | `redpandadata/redpanda` | `v24.3` | Minor |
| Redpanda Console | `redpandadata/console` | `v2.8` | Minor |
| Superset | `apache/superset` | `4.1.1` | Exact |
| Nginx (Info) | `nginx` | `alpine` | Rolling |

¹ No major version tags available, requires manual updates.  
² Only `latest` tags published, no semantic versions available.

**Strategies:**
- **Major** (e.g., `:12`) - Auto-patches, manual major upgrades only
- **Minor** (e.g., `:v0.58`) - Auto-patches within minor version
- **Exact** (e.g., `:v0.155.5`) - Full control, manual all updates
- **Latest** - Always newest version (when no semver available)

**To upgrade**: Edit the version in `tofu/image-versions.tfvars` and run Spin-Up.

---

## CloudBeaver

![CloudBeaver](https://img.shields.io/badge/CloudBeaver-3776AB?logo=dbeaver&logoColor=white)

**Web-based database management tool**

CloudBeaver is an open-source cloud database management tool built on DBeaver. It provides a web-based interface for managing databases without installing any software. Features include:
- Support for 30+ databases (PostgreSQL, MySQL, SQL Server, Oracle, etc.)
- SQL editor with syntax highlighting and auto-completion
- Visual query builder for non-SQL users
- Data export in multiple formats (CSV, JSON, XML)
- Role-based access control
- Connection management and sharing

| Setting | Value |
|---------|-------|
| Default Port | `8978` |
| Suggested Subdomain | `cloudbeaver` |
| Public Access | No (database credentials) |
| Website | [dbeaver.com/cloudbeaver](https://dbeaver.com/cloudbeaver/) |
| Source | [GitHub](https://github.com/dbeaver/cloudbeaver) |

---

## IT-Tools

![IT-Tools](https://img.shields.io/badge/IT--Tools-5D5D5D?logo=homeassistant&logoColor=white)

**Collection of handy online tools for developers**

A comprehensive collection of 80+ tools for developers, including:
- Encoders/Decoders (Base64, URL, JWT, etc.)
- Converters (JSON ↔ YAML, Unix timestamp, etc.)
- Generators (UUID, Hash, Password, etc.)
- Network tools (IPv4/IPv6 subnets, MAC lookup, etc.)
- Text utilities (Lorem ipsum, text diff, etc.)

| Setting | Value |
|---------|-------|
| Default Port | `8080` |
| Suggested Subdomain | `it-tools` |
| Public Access | Optional (works both ways) |
| Website | [it-tools.tech](https://it-tools.tech) |
| Source | [GitHub](https://github.com/CorentinTh/it-tools) |

---

## Excalidraw

![Excalidraw](https://img.shields.io/badge/Excalidraw-6965DB?logo=excalidraw&logoColor=white)

**Virtual whiteboard for sketching hand-drawn diagrams**

A collaborative whiteboard tool that lets you create beautiful hand-drawn like diagrams. Features include:
- Hand-drawn style graphics
- Real-time collaboration
- Export to PNG, SVG, or JSON
- Libraries of shapes and icons
- End-to-end encryption for collaboration

| Setting | Value |
|---------|-------|
| Default Port | `8082` |
| Suggested Subdomain | `draw` or `excalidraw` |
| Public Access | Recommended for sharing |
| Website | [excalidraw.com](https://excalidraw.com) |
| Source | [GitHub](https://github.com/excalidraw/excalidraw) |

---

## Portainer

![Portainer](https://img.shields.io/badge/Portainer-13BEF9?logo=portainer&logoColor=white)

**Docker container management UI**

A lightweight management UI that allows you to easily manage your Docker environments:
- Container management (start, stop, restart, logs)
- Image management (pull, build, delete)
- Volume and network management
- Stack deployment with Docker Compose
- User access control

| Setting | Value |
|---------|-------|
| Default Port | `9090` (→ internal 9000) |
| Suggested Subdomain | `portainer` |
| Public Access | **Never** (always protected) |
| Website | [portainer.io](https://www.portainer.io) |
| Source | [GitHub](https://github.com/portainer/portainer) |

> ✅ **Auto-configured:** Admin account is automatically created during deployment. Use `make secrets` to view the credentials.

---

## Uptime Kuma

![Uptime Kuma](https://img.shields.io/badge/Uptime%20Kuma-5CDD8B?logo=uptimekuma&logoColor=white)

**A fancy self-hosted monitoring tool**

A beautiful, self-hosted monitoring tool similar to "Uptime Robot":
- Monitor uptime for HTTP(s), TCP, Ping, DNS, and more
- Fancy reactive dashboard
- Notifications via Telegram, Discord, Slack, Email, and 90+ services
- Multi-language support
- Status page with incident management

| Setting | Value |
|---------|-------|
| Default Port | `3001` |
| Suggested Subdomain | `uptime-kuma` |
| Public Access | Optional (status page can be public) |
| Website | [uptime.kuma.pet](https://uptime.kuma.pet) |
| Source | [GitHub](https://github.com/louislam/uptime-kuma) |

> ✅ **Auto-configured:** Admin account is automatically created and monitors for all enabled services are added during deployment. Use `make secrets` to view the credentials.

---

## Info

![Info](https://img.shields.io/badge/Info-00D4AA?logo=nginx&logoColor=white)

**Landing page with dynamic service overview dashboard**

A beautiful, cyberpunk-styled landing page that dynamically displays all your Nexus services:
- **Dynamically generated** from `config.tfvars` during deployment
- Shows enabled services as "Online", disabled services as "Disabled"
- Animated grid background with scanline effect
- Direct links to all enabled services
- Service statistics (total, active, protected)
- Responsive design for mobile

| Setting | Value |
|---------|-------|
| Default Port | `8090` |
| Suggested Subdomain | `info` |
| Public Access | Optional (can be your landing page) |
| Technology | nginx:alpine serving static HTML |

> ℹ️ **Note:** The info page is regenerated on every `make up` deployment. It reads your service configuration from `config.tfvars` and shows the current state of all services.

---

## Infisical

![Infisical](https://img.shields.io/badge/Infisical-000000?logo=infisical&logoColor=white)

**Open-source secret management platform**

A modern, developer-friendly alternative to HashiCorp Vault:
- Beautiful, intuitive UI
- No unsealing required (unlike Vault)
- Environment variables sync to your apps
- Team collaboration with RBAC
- Audit logs for compliance
- Native integrations (Kubernetes, Docker, CI/CD)

| Setting | Value |
|---------|-------|
| Default Port | `8070` |
| Suggested Subdomain | `infisical` |
| Public Access | **Never** (always protected) |
| Website | [infisical.com](https://infisical.com) |
| Source | [GitHub](https://github.com/Infisical/infisical) |

> ✅ **Auto-configured:** Admin account is automatically created during deployment. A "Nexus Stack" project is created with all generated passwords pre-loaded. Use `make secrets` to view the credentials.

> ℹ️ **Note:** Secrets are auto-generated on first deployment (encryption key, auth secret). These are stored in `stacks/infisical/.env`.

---

## Grafana

![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)

**Full observability stack with Prometheus, Loki & dashboards**

A complete monitoring and observability solution including:
- **Grafana** - Beautiful dashboards and visualization
- **Prometheus** - Metrics collection and alerting
- **Loki** - Log aggregation (like Prometheus, but for logs)
- **Promtail** - Ships Docker container logs to Loki
- **cAdvisor** - Container metrics (CPU, memory, network, disk)
- **Node Exporter** - Host-level metrics (CPU, RAM, disk, network)

| Setting | Value |
|---------|-------|
| Default Port | `3100` (→ internal 3000) |
| Suggested Subdomain | `grafana` |
| Public Access | **Never** (always protected) |
| Website | [grafana.com](https://grafana.com) |
| Source | [GitHub](https://github.com/grafana/grafana) |

### Pre-configured Dashboards

The stack comes with three ready-to-use dashboards:

| Dashboard | Description |
|-----------|-------------|
| **Docker Overview** | Container CPU, memory, network I/O, and disk usage |
| **Loki Logs** | Real-time log viewing and filtering for all containers |
| **Node Exporter** | Host metrics including CPU, memory, disk, and network |

### Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Containers │────▶│  Promtail   │────▶│    Loki     │
│   (logs)    │     │             │     │             │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
┌─────────────┐     ┌─────────────┐            │
│  cAdvisor   │────▶│ Prometheus  │            │
│  (metrics)  │     │             │────────────┼──────▶ Grafana
└─────────────┘     └──────┬──────┘            │
                           │                   │
┌─────────────┐            │                   │
│Node Exporter│────────────┘                   │
│(host stats) │                                │
└─────────────┘                                │
```

> ✅ **Auto-configured:** Admin password is set via environment variables during deployment. Dashboards and datasources are pre-provisioned. Use `make secrets` to view the credentials.

---

## Kestra

![Kestra](https://img.shields.io/badge/Kestra-6047EC?logo=kestra&logoColor=white)

**Modern workflow orchestration for data pipelines & automation**

A powerful, event-driven workflow orchestration platform for building data pipelines, ETL processes, and infrastructure automation:
- Declarative YAML workflows
- Event-driven triggers (cron, webhooks, file, message queues)
- 400+ plugins (AWS, GCP, Azure, databases, APIs)
- Real-time execution monitoring
- Built-in code editor with live preview
- Docker-in-Docker task execution

| Setting | Value |
|---------|-------|
| Default Port | `8085` (→ internal 8080) |
| Suggested Subdomain | `kestra` |
| Public Access | **Never** (always protected) |
| Website | [kestra.io](https://kestra.io) |
| Source | [GitHub](https://github.com/kestra-io/kestra) |

> ✅ **Auto-configured:** Admin account (Basic Auth) is automatically configured during deployment. Use `make secrets` to view the credentials.

### Architecture

The stack includes:
- **Kestra** - Main workflow engine with web UI
- **PostgreSQL** - Database for workflow state and metadata

> ℹ️ **Note:** Admin credentials are auto-generated. Use `make secrets` to view them.

---

## n8n

![n8n](https://img.shields.io/badge/n8n-EA4B71?logo=n8n&logoColor=white)

**Workflow automation tool - automate anything**

n8n is a free and source-available workflow automation tool that allows you to connect anything to everything. Features include:
- 400+ integrations (Slack, GitHub, Google, databases, APIs, etc.)
- Visual workflow builder with drag & drop
- Self-hostable with full data ownership
- Custom JavaScript/Python code nodes
- Webhook triggers and scheduled workflows
- AI-powered workflow suggestions

| Setting | Value |
|---------|-------|
| Default Port | `5678` |
| Suggested Subdomain | `n8n` |
| Public Access | No (workflows may contain sensitive data) |
| Authentication | Basic Auth (auto-configured) |
| Website | [n8n.io](https://n8n.io) |
| Source | [GitHub](https://github.com/n8n-io/n8n) |

> ✅ **Auto-configured:** Admin account (Basic Auth) is automatically configured during deployment. Use `make secrets` to view the credentials.

---

## Metabase

![Metabase](https://img.shields.io/badge/Metabase-509EE3?logo=metabase&logoColor=white)

**Open-source business intelligence and analytics tool**

Metabase is an easy-to-use, open-source business intelligence tool that lets you ask questions about your data. Features include:
- Ask questions in plain English or SQL
- Create beautiful dashboards with drag & drop
- Connect to 20+ data sources (PostgreSQL, MySQL, MongoDB, etc.)
- Share insights with your team
- Schedule automated reports via email/Slack
- Embed charts in other applications

| Setting | Value |
|---------|-------|
| Default Port | `3000` |
| Suggested Subdomain | `metabase` |
| Public Access | No (contains business data) |
| Website | [metabase.com](https://www.metabase.com) |
| Source | [GitHub](https://github.com/metabase/metabase) |

> ✅ **Auto-configured:** Admin account is automatically created during deployment. Use `make secrets` to view the credentials.

---

## Superset

![Superset](https://img.shields.io/badge/Superset-20A6C9?logo=apachesuperset&logoColor=white)

**Enterprise-ready BI platform with SQL Lab and interactive dashboards**

Apache Superset is a modern, enterprise-ready business intelligence platform. It's fast, lightweight, and designed for data exploration and visualization. Features include:
- SQL Lab for advanced SQL queries
- 40+ database connectors (PostgreSQL, MySQL, Snowflake, BigQuery, etc.)
- Rich visualizations and interactive dashboards
- Role-based access control (RBAC)
- Custom CSS themes and white-labeling
- Async query execution with caching
- Alerts and scheduled reports

| Setting | Value |
|---------|-------|
| Default Port | `8088` |
| Suggested Subdomain | `superset` |
| Public Access | No (contains business data) |
| Website | [superset.apache.org](https://superset.apache.org) |
| Source | [GitHub](https://github.com/apache/superset) |

### Components

Superset runs as a multi-container stack:

| Container | Purpose |
|-----------|---------|
| `superset` | Main web application (Gunicorn) |
| `superset-db` | PostgreSQL for metadata storage |
| `superset-redis` | Redis for caching and Celery broker |
| `superset-worker` | Celery worker for async tasks |
| `superset-init` | One-time initialization (migrations, admin user) |

> ✅ **Auto-configured:** Admin account is automatically created during deployment. Use `make secrets` to view the credentials.

---

## Marimo

![Marimo](https://img.shields.io/badge/Marimo-1C1C1C?logo=python&logoColor=white)

**Reactive Python notebook with SQL support**

Marimo is a reactive Python notebook that's reproducible, git-friendly, and deployable as apps. Features include:
- Reactive execution - cells auto-update when dependencies change
- Git-friendly - notebooks stored as pure Python files
- SQL support - built-in DuckDB for data analysis
- Interactive UI elements - sliders, buttons, tables
- Deploy as web apps or scripts
- No hidden state - what you see is what you run

| Setting | Value |
|---------|-------|
| Default Port | `2718` |
| Suggested Subdomain | `marimo` |
| Public Access | No (contains notebooks/code) |
| Website | [marimo.io](https://marimo.io) |
| Source | [GitHub](https://github.com/marimo-team/marimo) |

---

## Redpanda

![Redpanda](https://img.shields.io/badge/Redpanda-E4405F?logo=redpanda&logoColor=white)

**Kafka-compatible streaming platform**

Redpanda is a Kafka-compatible streaming data platform that is simpler, faster, and more cost-effective than Apache Kafka. Features include:
- 10x faster than Kafka with lower latency
- No JVM, no ZooKeeper dependencies
- 100% Kafka API compatible
- Built-in Schema Registry and HTTP Proxy
- Single binary deployment
- WebAssembly data transforms

| Setting | Value |
|---------|-------|
| Default Port (Admin) | `9644` |
| Kafka Port | `9092` |
| Schema Registry Port | `8081` |
| Suggested Subdomain | `redpanda` |
| Public Access | No (streaming infrastructure) |
| Website | [redpanda.com](https://redpanda.com) |
| Source | [GitHub](https://github.com/redpanda-data/redpanda) |

---

## Redpanda Console

![Redpanda Console](https://img.shields.io/badge/Redpanda_Console-E4405F?logo=redpanda&logoColor=white)

**Web UI for Redpanda/Kafka management**

Redpanda Console is a developer-friendly web UI for managing and debugging your Kafka/Redpanda workloads. Features include:
- Browse topics, partitions, and messages
- View consumer groups and their lag
- Manage schemas in Schema Registry
- Execute ksqlDB queries
- Monitor cluster health and performance
- Produce and consume test messages

| Setting | Value |
|---------|-------|
| Default Port | `8180` |
| Suggested Subdomain | `redpanda-console` |
| Public Access | No (cluster management) |
| Website | [redpanda.com](https://redpanda.com) |
| Source | [GitHub](https://github.com/redpanda-data/console) |

---

## Enabling a Stack

To enable any stack, add it to your `tofu/config.tfvars`:

```hcl
services = {
  # ... existing services ...
  
  uptime-kuma = {
    enabled   = true
    subdomain = "uptime-kuma"    # → https://uptime-kuma.yourdomain.com
    port      = 3001        # Must match docker-compose port
    public    = false       # false = requires login
  }
}
```

Then deploy via **Spin Up** workflow in GitHub Actions or through the Control Plane.

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

### 2. Add to services.tfvars

Add to `tofu/services.tfvars`:

```hcl
services = {
  # ... existing services ...
  
  my-app = {
    enabled     = true
    subdomain   = "my-app"     # → https://my-app.yourdomain.com
    port        = 8090         # Must match docker-compose port
    public      = false        # false = requires login, true = public
    description = "My awesome application"
  }
}
```

### 3. Deploy

Run the **Spin Up** workflow via GitHub Actions or use the Control Plane.

That's it! OpenTofu automatically creates:
- ✅ DNS record
- ✅ Tunnel ingress route
- ✅ Cloudflare Access application
- ✅ Access policy (email-based auth)

---

## Disabling Services

Services can be disabled via the **Control Plane** web interface, or by setting `enabled = false` in `services.tfvars`.

When disabled:
1. DNS record is removed from Cloudflare
2. Tunnel ingress route is removed
3. Cloudflare Access application and policy are removed
4. Docker container is stopped
5. Stack folder is deleted from the server

The service is completely cleaned up - no orphaned resources.

