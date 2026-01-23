# 📦 Available Stacks

This document provides detailed information about all available Docker stacks in Nexus-Stack.

## Docker Image Versions

Images are pinned to **major versions** where supported for automatic security patches while avoiding breaking changes. Versions are defined in [`services.yaml`](../services.yaml).

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
| Mage | `mageai/mageai` | `latest` | Latest ² |
| MinIO | `minio/minio` | `latest` | Latest ² |
| Marimo | `ghcr.io/marimo-team/marimo` | `latest-sql` | Latest ² |
| Redpanda | `redpandadata/redpanda` | `v24.3` | Minor |
| Redpanda Console | `redpandadata/console` | `v2.8` | Minor |
| Redpanda Connect | `redpandadata/connect` | `latest` | Latest ² |
| Redpanda Datagen | `redpandadata/connect` | `latest` | Latest ² |
| Nginx (Info) | `nginx` | `alpine` | Rolling |

¹ No major version tags available, requires manual updates.  
² Only `latest` tags published, no semantic versions available.

**Strategies:**
- **Major** (e.g., `:12`) - Auto-patches, manual major upgrades only
- **Minor** (e.g., `:v0.58`) - Auto-patches within minor version
- **Exact** (e.g., `:v0.155.5`) - Full control, manual all updates
- **Latest** - Always newest version (when no semver available)

**To upgrade**: Edit the version in `services.yaml` and run Spin-Up.

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

## Mage

![Mage](https://img.shields.io/badge/Mage-6B4FBB?logo=mage&logoColor=white)

**Modern data pipeline tool for ETL/ELT workflows**

Mage is a modern replacement for Airflow, designed for building, running, and managing data pipelines. Features include:
- Hybrid development environment (notebooks + IDE)
- Built-in orchestration with scheduling and triggers
- Native integrations for data sources (SQL, APIs, cloud storage)
- Real-time and batch pipeline support
- Version control friendly with code-first approach
- Beautiful UI for monitoring and debugging

| Setting | Value |
|---------|-------|
| Default Port | `6789` |
| Suggested Subdomain | `mage` |
| Public Access | No (contains data pipelines) |
| Website | [mage.ai](https://mage.ai) |
| Source | [GitHub](https://github.com/mage-ai/mage-ai) |

> ✅ **Auto-configured:** Admin account is automatically created during deployment using your `user_email`. Use `make secrets` to view the credentials.

---

## MinIO

![MinIO](https://img.shields.io/badge/MinIO-C72E49?logo=minio&logoColor=white)

**High-performance S3-compatible object storage**

MinIO is a high-performance, S3-compatible object storage system designed for large-scale data infrastructure. Features include:
- Amazon S3 API compatible
- High performance for both streaming and throughput
- Distributed mode for high availability
- Lambda-compatible event notifications
- Encryption (at rest and in transit)
- Perfect for data lakes, ML models, backups

| Setting | Value |
|---------|-------|
| Default Port | `9001` (Console), `9000` (API) |
| Suggested Subdomain | `minio` |
| Public Access | No (storage infrastructure) |
| Website | [min.io](https://min.io) |
| Source | [GitHub](https://github.com/minio/minio) |

> ✅ **Auto-configured:** Root user (admin) is automatically created during deployment. Use `make secrets` to view the credentials.

### Usage

Access MinIO Console at `https://minio.<domain>` to:
- Create buckets
- Upload/download objects
- Manage access policies
- Configure lifecycle rules

**S3 API Access:**
- **Console UI**: `https://minio.<domain>` (accessible via Cloudflare Tunnel)
- **S3 API**: `http://localhost:9000` (cluster/localhost only - not exposed via tunnel)

For S3 API access from external applications, use the Console UI or SSH tunnel. Direct S3 API exposure via Cloudflare Tunnel is not configured by default for security reasons.

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

## Redpanda Connect

![Redpanda Connect](https://img.shields.io/badge/Redpanda_Connect-E4405F?logo=redpanda&logoColor=white)

**Declarative data streaming framework for real-time pipelines**

Redpanda Connect (formerly Benthos) is a high-performance stream processor that makes building data pipelines simple. Features include:
- Declarative YAML configuration
- Hundreds of connectors (Kafka, PostgreSQL, S3, HTTP, etc.)
- Built-in data transformation with Bloblang
- Stateless and easy to scale
- Real-time and batch processing
- Prometheus metrics endpoint

| Setting | Value |
|---------|-------|
| Default Port | `4195` |
| Suggested Subdomain | `redpanda-connect` |
| Public Access | No (data pipelines) |
| Website | [redpanda.com](https://redpanda.com) |
| Docs | [docs.redpanda.com/redpanda-connect](https://docs.redpanda.com/redpanda-connect/) |
| Source | [GitHub](https://github.com/redpanda-data/connect) |

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `/ready` | Health check endpoint |
| `/metrics` | Prometheus metrics |
| `/version` | Version information |

### Configuration

The pipeline configuration is in `stacks/redpanda-connect/config.yaml`. By default, a simple HTTP echo pipeline is configured. Replace with your own pipeline configuration.

Example pipeline to stream from Redpanda to stdout:
```yaml
input:
  kafka:
    addresses: ["redpanda:9092"]
    topics: ["my-topic"]
    consumer_group: "my-consumer"

output:
  stdout: {}
```

---

## Redpanda Datagen

![Redpanda Datagen](https://img.shields.io/badge/Redpanda_Datagen-E4405F?logo=redpanda&logoColor=white)

**Test data generator for Redpanda topics**

A separate stack for generating realistic test data into Redpanda topics. Uses Redpanda Connect with a pre-configured data generation pipeline. Enable this service via the Control Panel when you need test data - disable it when not needed to avoid overhead.

| Setting | Value |
|---------|-------|
| Default Port | `4196` |
| Suggested Subdomain | `redpanda-datagen` |
| Public Access | No (test data generator) |
| Target Topic | `test-events` |
| Message Rate | 1 message/second |

### Generated Data Format

The datagen produces realistic e-commerce event data:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:30:00Z",
  "user_id": 4523,
  "event_type": "purchase",
  "amount": 249,
  "metadata": {
    "browser": "Chrome",
    "country": "DE"
  }
}
```

### Event Types

| Event | Description |
|-------|-------------|
| `click` | User clicked on an element |
| `view` | User viewed a page |
| `purchase` | User made a purchase (includes amount) |
| `signup` | User signed up |

### Usage

1. **Enable** the `redpanda-datagen` service in the Control Panel
2. **View data** in Redpanda Console at the `test-events` topic
3. **Disable** when done testing to stop data generation

> ℹ️ **Note:** Data generation runs continuously while the service is enabled (1 msg/sec). Disable via Control Panel when not needed.

---

## Wetty

![Wetty](https://img.shields.io/badge/Wetty-000000?logo=gnubash&logoColor=white)

**Web-based SSH terminal**

A terminal over HTTP/HTTPS that allows you to access your server via a web browser. Provides a full terminal experience without requiring SSH client software.

**Features:**
- **Browser-based SSH** - Access server terminal from any device with a web browser
- **No SSH client needed** - Useful for environments where SSH client installation is restricted
- **Full terminal experience** - Complete terminal functionality in your browser
- **Cloudflare Access protected** - Secure access via email OTP authentication
- **Public key authentication only** - No password authentication for enhanced security
- **Short session duration** - Cloudflare Access sessions expire after 1 hour for enhanced security
- **Core service** - Always enabled, cannot be disabled

**Security Features:**
- ✅ **Public key authentication only** - `SSHAUTH=publickey` prevents password-based logins
- ✅ **Cloudflare Access** - Email OTP required before accessing Wetty interface
- ✅ **Short session duration** - Cloudflare Access sessions expire after 1 hour (enhanced security)
- ✅ **Rate limiting** - Cloudflare Access provides built-in rate limiting
- ✅ **HTTPS only** - All traffic encrypted via Cloudflare Tunnel
- ✅ **No direct SSH exposure** - SSH daemon only accessible via localhost

**Use cases:**
- Quick terminal access without setting up SSH clients
- Educational demos and teaching server management
- Access from devices where SSH client installation is restricted
- Fallback terminal access method via browser
- Emergency access when SSH client is unavailable

| Setting | Value |
|---------|-------|
| Default Port | `3002` |
| Suggested Subdomain | `wetty` |
| Public Access | **Never** (always protected) |
| Default Enabled | **No** (enable via Control Plane when needed) |
| Authentication | Public key only (no passwords) |
| Cloudflare Access Session | 1 hour (re-authentication required) |
| Website | [GitHub](https://github.com/butlerx/wetty) |
| Source | [GitHub](https://github.com/butlerx/wetty) |

> ✅ **Auto-configured:** Wetty connects to the server's SSH daemon using public key authentication only. Users must have their SSH public key configured on the server (same as regular SSH access).

> 🔒 **Security:** Wetty is configured with `SSHAUTH=publickey` to prevent password-based authentication. Only users with SSH keys configured on the server can access the terminal.

> 💡 **Usage:** Enable Wetty via the Control Plane when you need browser-based terminal access. It's disabled by default to reduce attack surface.

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
- ✅ DNS record
- ✅ Tunnel ingress route
- ✅ Cloudflare Access application
- ✅ Access policy (email-based auth)

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

