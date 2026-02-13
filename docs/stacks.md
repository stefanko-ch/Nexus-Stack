# 📦 Available Stacks

This document provides detailed information about all available Docker stacks in Nexus-Stack.

## Docker Image Versions

Images are pinned to **major versions** where supported for automatic security patches while avoiding breaking changes. Versions are defined in [`services.yaml`](../services.yaml).

| Service | Image | Tag | Strategy |
|---------|-------|-----|----------|
| Adminer | `adminer` | `latest` | Latest ² |
| CloudBeaver | `dbeaver/cloudbeaver` | `24` | Major |
| ClickHouse | `clickhouse/clickhouse-server` | `25.8.16.34` | Exact ¹ |
| code-server | `codercom/code-server` | `latest` | Latest ² |
| Draw.io | `jgraph/drawio` | `29` | Major |
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
| NocoDB | `nocodb/nocodb` | `0.301.2` | Minor |
| PostgreSQL (NocoDB DB) | `postgres` | `16-alpine` | Major |
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
| RustFS | `rustfs/rustfs` | `1.0.0-alpha.82` | Exact ¹ |
| S3 Manager | `cloudlena/s3manager` | `latest` | Latest ² |
| Marimo | `ghcr.io/marimo-team/marimo` | `latest-sql` | Latest ² |
| Meltano | `meltano/meltano` | `v4.0` | Minor |
| PostgreSQL (Meltano DB) | `postgres` | `16-alpine` | Major |
| PostgreSQL (Standalone) | `postgres` | `17-alpine` | Major |
| pgAdmin | `dpage/pgadmin4` | `9` | Major |
| Prefect | `prefecthq/prefect` | `3-latest` | Major |
| PostgreSQL (Prefect DB) | `postgres` | `16-alpine` | Major |
| Quickwit | `quickwit/quickwit` | `0.8.1` | Minor |
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

## Adminer

![Adminer](https://img.shields.io/badge/Adminer-34567C?logo=adminer&logoColor=white)

**Lightweight database management tool**

Adminer is a full-featured database management tool written in a single PHP file. Despite its small size, it supports a wide range of databases and provides essential features for database administration. Features include:
- Support for PostgreSQL, MySQL, SQLite, MS SQL, Oracle, MongoDB, and more
- SQL query editor with syntax highlighting
- Table structure viewer and editor
- Data import/export (SQL, CSV)
- User and permission management
- Lightweight alternative to phpMyAdmin or pgAdmin

| Setting | Value |
|---------|-------|
| Default Port | `8888` |
| Suggested Subdomain | `adminer` |
| Public Access | No (database access) |
| Website | [adminer.org](https://www.adminer.org) |
| Source | [GitHub](https://github.com/vrana/adminer) |

### Usage

1. Access Adminer at `https://adminer.<domain>`
2. Login page shows pre-filled connection details:
   - **System**: PostgreSQL (select if not pre-selected)
   - **Server**: `postgres` (pre-filled)
   - **Username**: From Infisical (`POSTGRES_USERNAME`)
   - **Password**: From Infisical (`POSTGRES_PASSWORD`)
   - **Database**: `postgres` (or leave empty to see all databases)
3. Click "Login"

> ℹ️ **Note:** Server hostname is pre-configured as `postgres`. Get username and password from Infisical - you need to enter them on each login (Adminer doesn't save credentials).

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

## ClickHouse

![ClickHouse](https://img.shields.io/badge/ClickHouse-FFCC00?logo=clickhouse&logoColor=black)

**Fast, open-source columnar database for real-time analytics**

ClickHouse is a column-oriented database management system for online analytical processing (OLAP). It provides sub-second query performance on billions of rows with SQL support.

| Setting | Value |
|---------|-------|
| Default Port | `8123` (HTTP/Play UI) |
| Native TCP Port | `9004` (for external clients) |
| Suggested Subdomain | `clickhouse` |
| Public Access | No |
| Website | [clickhouse.com](https://clickhouse.com) |
| Source | [GitHub](https://github.com/ClickHouse/ClickHouse) |

### Configuration

- **Admin user:** `nexus-clickhouse` (auto-configured via environment variables)
- **Admin password:** Auto-generated by OpenTofu, stored in Infisical as `CLICKHOUSE_PASSWORD`
- **Play UI:** Built-in web interface for interactive SQL queries at the HTTP port
- **Native TCP:** Port 9004 for external clients (DBeaver, DataGrip, clickhouse-client)

### Usage

1. Enable the service in Control Plane
2. Access `https://clickhouse.YOUR_DOMAIN` for the Play UI
3. Login with credentials from Infisical
4. Connect external clients to `YOUR_SERVER:9004` using native protocol

---

## code-server

![code-server](https://img.shields.io/badge/code--server-007ACC?logo=visualstudiocode&logoColor=white)

**VS Code in the browser**

Run VS Code on a remote server and access it through the browser. Provides a consistent development environment accessible from any device. Features include:
- Full VS Code experience in the browser
- Extension marketplace support
- Integrated terminal
- Git integration
- Multi-language support

| Setting | Value |
|---------|-------|
| Default Port | `8100` |
| Suggested Subdomain | `code` |
| Public Access | No (development environment) |
| Website | [coder.com](https://coder.com) |
| Source | [GitHub](https://github.com/coder/code-server) |

### Usage

1. Enable the code-server service in the Control Plane
2. Access `https://code.YOUR_DOMAIN`
3. Authentication is handled by Cloudflare Access (no additional password)
4. Files are persisted in a Docker volume (`code-server-data`)

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

## Jupyter PySpark

![Jupyter](https://img.shields.io/badge/Jupyter-F37726?logo=jupyter&logoColor=white)

**Interactive PySpark notebook platform with Spark SQL support and cluster connectivity**

JupyterLab with PySpark pre-configured to connect to the Apache Spark cluster. Supports Python notebooks, PySpark DataFrames, and Spark SQL via `%%sparksql` magic cells. Features include:
- PySpark pre-installed with Spark cluster connectivity
- Spark SQL magic cells (`%%sparksql`) auto-loaded on startup
- JupyterLab interface with file browser and terminal
- Hetzner Object Storage (S3) integration for data access
- Gitea integration with `jupyterlab-git` (auto-clones workspace repo)
- Markdown and LaTeX rendering

| Setting | Value |
|---------|-------|
| Default Port | `8087` |
| Suggested Subdomain | `jupyter` |
| Public Access | No (development environment) |
| Website | [jupyter.org](https://jupyter.org) |
| Source | [GitHub](https://github.com/jupyter/jupyter) |

### Kernel Selection

Jupyter provides two kernels:

| Kernel | Description |
|--------|-------------|
| **PySpark (Spark Cluster)** | Auto-creates a SparkSession connected to the cluster. `spark` and `sc` variables are immediately available. |
| **Python 3 (ipykernel)** | Plain Python kernel without auto-Spark. Use this for non-Spark notebooks. |

When creating a new notebook, select **PySpark (Spark Cluster)** to get automatic Spark connectivity. The kernel prints `SparkSession ready (master: spark://spark-master:7077)` on startup.

### Spark Integration

When the Spark stack is enabled, the PySpark kernel automatically connects to `spark://spark-master:7077`. When Spark is not enabled, it falls back to `local[*]` mode (runs Spark locally within the container).

**With PySpark kernel (auto-configured):**
```python
# spark and sc are already available - no setup needed
spark.sql("SELECT 1 as test").show()
```

**Spark SQL magic cell:**
```
%%sparksql
SELECT 'hello spark' as greeting
```

**S3 access (Hetzner Object Storage):**
```python
df = spark.read.csv("s3a://your-bucket/path/file.csv")
```

### Usage

1. Enable the Jupyter service in the Control Plane
2. Access `https://jupyter.YOUR_DOMAIN`
3. Select the **PySpark (Spark Cluster)** kernel when creating a notebook
4. Authentication is handled by Cloudflare Access (token auth disabled)
5. Notebooks are persisted in a Docker volume (`jupyter-data`)
6. PySpark and `sparksql-magic` are pre-installed; Spark SQL is auto-loaded

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

## Filestash

![Filestash](https://img.shields.io/badge/Filestash-2B3A67?logo=files&logoColor=white)

**Web-based file manager with S3/FTP/SFTP/WebDAV backend support**

Filestash is a modern file manager that makes data accessible from anywhere via a web browser. Features include:
- S3, FTP, SFTP, WebDAV, and many more backend support
- Clean, responsive web interface
- Image and document previews
- File sharing with links
- Full-text search across files
- Collaborative features

| Setting | Value |
|---------|-------|
| Default Port | `8334` |
| Suggested Subdomain | `filestash` |
| Public Access | No (file access) |
| Website | [filestash.app](https://www.filestash.app) |
| Source | [GitHub](https://github.com/mickael-kerjean/filestash) |

### Auto-configured S3 Backend

When Hetzner Object Storage credentials are configured (via GitHub Secrets), Filestash is automatically pre-configured with an S3 connection:

| Setting | Value |
|---------|-------|
| Connection Name | Hetzner Storage |
| Bucket | `nexus-<resource-prefix>` (shared bucket) |
| Endpoint | Hetzner Object Storage |

### Usage

1. Access Filestash at `https://filestash.<domain>`
2. Login to admin console at `/admin` with credentials from Infisical (`FILESTASH_ADMIN_PASSWORD`)
3. S3 backend is pre-configured (if Hetzner credentials exist)
4. Start browsing and uploading files

> ✅ **Auto-configured:** Admin password is automatically set via bcrypt hash. S3 backend is pre-configured when Hetzner Object Storage credentials are available. Use `make secrets` to view the admin password.

> **Note:** Only `latest` Docker image tag is available - no semantic versioning published.

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

## pgAdmin

![pgAdmin](https://img.shields.io/badge/pgAdmin-336791?logo=postgresql&logoColor=white)

**PostgreSQL administration and development platform**

pgAdmin is the most popular and feature-rich Open Source administration and development platform for PostgreSQL. Features include:
- Graphical query builder and SQL editor
- Database object browser and editor
- Visual explain plans for query optimization
- Server dashboard with monitoring
- Backup and restore functionality
- User and permission management
- Support for PostgreSQL 10+ and all PostgreSQL extensions

| Setting | Value |
|---------|-------|
| Default Port | `5050` |
| Suggested Subdomain | `pgadmin` |
| Public Access | No (database administration) |
| Website | [pgadmin.org](https://www.pgadmin.org) |
| Source | [GitHub](https://github.com/pgadmin-org/pgadmin4) |

### Usage

1. Access pgAdmin at `https://pgadmin.<domain>`
2. Login with credentials from Infisical (`PGADMIN_USERNAME` / `PGADMIN_PASSWORD`)
3. **Pre-configured server:** The "Nexus PostgreSQL" server appears automatically in the left sidebar
4. Click on the server and enter the password from Infisical (`POSTGRES_PASSWORD`)
   - Username is pre-configured as `postgres` (from `POSTGRES_USERNAME` in Infisical)
   - You only need to enter the password
5. The password is saved for future logins

> ✅ **Auto-configured:** Both the admin account and PostgreSQL server connection (including username) are pre-configured. You only need to enter the PostgreSQL password once.

---

## Prefect

![Prefect](https://img.shields.io/badge/Prefect-024DFD?logo=prefect&logoColor=white)

**Modern Python-native workflow orchestration for data pipelines and automation.**

| Detail | Value |
|--------|-------|
| Port | `4200` |
| Subdomain | `prefect.<domain>` |
| Source | [GitHub](https://github.com/PrefectHQ/prefect) |

### Architecture

Prefect runs as 4 containers:

| Container | Purpose |
|-----------|---------|
| `prefect` | API server + web UI |
| `prefect-services` | Background services (scheduler, triggers, events) |
| `prefect-worker` | Local flow executor (work pool: `local-pool`) |
| `prefect-db` | Dedicated PostgreSQL database |

### Usage

1. Enable the Prefect service in the Control Plane
2. Access `https://prefect.<domain>` to open the Prefect UI
3. Create flows using Python and deploy them via the API
4. The local worker automatically picks up flow runs from the `local-pool` work pool

### Connecting from Other Services

Services running on the same Docker network can connect to Prefect using:

```
PREFECT_API_URL=http://prefect:4200/api
```

> No authentication required - Cloudflare Access provides email OTP protection at the network level.

---

## PostgreSQL

![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?logo=postgresql&logoColor=white)

**Powerful open-source relational database (internal-only)**

PostgreSQL is a powerful, open-source object-relational database system with over 35 years of active development. This stack provides a standalone PostgreSQL server accessible only within the Docker network.

**Important:** This service has **no web UI** and **no external access**. It runs only on the internal Docker network.

| Setting | Value |
|---------|-------|
| Internal Port | `5432` |
| External Access | **None** (internal-only) |
| Default User | `postgres` |
| Default Database | `postgres` |
| Website | [postgresql.org](https://www.postgresql.org) |
| Source | [GitHub](https://github.com/postgres/postgres) |

### Access Methods

PostgreSQL is accessible via:

1. **pgAdmin or Adminer** (Web UIs)
   - Enable `pgadmin` or `adminer` stack
   - Connect to `postgres:5432`

2. **From other Docker containers**
   - Connection string: `postgresql://postgres:<password>@postgres:5432/postgres`
   - Get password from Infisical (`POSTGRES_PASSWORD`)

3. **Via SSH Tunnel** (for local tools like DBeaver, DataGrip)
   ```bash
   ssh -L 5432:postgres:5432 nexus
   # Then connect to localhost:5432
   ```

4. **Via Wetty** (terminal access)
   - Enable `wetty` stack
   - Run: `docker exec -it postgres psql -U postgres`

### Creating Databases and Users

```bash
# Via Wetty or SSH
docker exec -it postgres psql -U postgres

-- Create a new database
CREATE DATABASE myapp;

-- Create a new user
CREATE USER myapp_user WITH PASSWORD 'secure_password';

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE myapp TO myapp_user;
```

> 🔒 **Security:** PostgreSQL is not exposed to the internet. All access is via internal Docker network or SSH tunnel.

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

## Git Proxy

![Git Proxy](https://img.shields.io/badge/Git_Proxy-009639?logo=nginx&logoColor=white)

**Public HTTPS Git access for external tools (Databricks, CI/CD)**

Nginx reverse proxy that forwards Git HTTPS requests to Gitea. Provides public Git clone/push/pull access for external tools without exposing the Gitea Web UI.

| Setting | Value |
|---------|-------|
| Default Port | `3201` (-> internal 80) |
| Suggested Subdomain | `git` |
| Public Access | Yes (no Cloudflare Access) |

### How It Works

```
External tools ──HTTPS──> git.<domain> (PUBLIC)
                               │ (Cloudflare Tunnel)
                         Nginx (:3201)
                               │ (proxy_pass)
                         Gitea (:3000) (PRIVATE)
```

- External tools (Databricks) use `https://git.<domain>/<user>/<repo>.git` with Gitea PAT
- Internal services (Jupyter, etc.) use `http://gitea:3000` directly via Docker network
- Gitea Web UI at `https://gitea.<domain>` remains private (Cloudflare Access OTP)

### Usage with Databricks

1. Create a Personal Access Token (PAT) in Gitea
2. In Databricks, add Git Credentials: select "GitHub" provider, use Gitea username + PAT
3. Clone repos via: `https://git.<domain>/<user>/<repo>.git`

---

## Gitea

![Gitea](https://img.shields.io/badge/Gitea-609926?logo=gitea&logoColor=white)

**Self-hosted Git service with pull requests, code review, and CI/CD**

A lightweight, self-hosted Git hosting solution that provides:
- Pull requests and code review
- Issue tracking and project management
- CI/CD via Gitea Actions
- Repository mirroring from GitHub
- HTTPS access via Cloudflare Tunnel

| Setting | Value |
|---------|-------|
| Default Port | `3200` (-> internal 3000) |
| Suggested Subdomain | `gitea` |
| Public Access | No |
| Website | [gitea.com](https://about.gitea.com) |
| Source | [GitHub](https://github.com/go-gitea/gitea) |

> ✅ **Auto-configured:** Admin account is automatically created during deployment. Credentials are stored in Infisical under the `gitea` tag.

### Architecture

The stack includes:
- **Gitea** - Git service (Web UI + API)
- **Git Proxy** - Nginx reverse proxy for public Git HTTPS access (separate stack)
- **PostgreSQL** - Database for users, issues, PRs, and metadata

### Shared Workspace Repo

During deployment, a shared workspace repo named `nexus-<domain>-gitea` is automatically created. This repo is auto-cloned into the following services:

| Service | Clone Location | Method |
|---------|---------------|--------|
| Jupyter | `/home/jovyan/work/<repo>` | Entrypoint + jupyterlab-git |
| Marimo | `/app/notebooks/<repo>` | Entrypoint clone |
| code-server | `/home/coder/<repo>` | Entrypoint clone (opens as workspace) |
| Meltano | `/project/<repo>` | Entrypoint clone |
| Prefect | `/flows/<repo>` (worker) | Entrypoint clone |
| Kestra | Git sync flow | `plugin-git` SyncNamespaceFiles (every 15 min) |

### Persistent Storage

Gitea stores repository data and its database on a **persistent Hetzner Cloud Volume** that survives teardown:
- Git repositories: `/mnt/nexus-data/gitea/repos`
- LFS objects: `/mnt/nexus-data/gitea/lfs`
- PostgreSQL data: `/mnt/nexus-data/gitea/db`

The volume size is configurable via `persistent_volume_size` (default: 10 GB, minimum: 10 GB).

On **teardown**: Volume and all data are preserved.
On **spin-up**: Existing data is automatically reattached. Gitea resumes with all repositories and metadata intact.
On **destroy-all**: Volume is permanently deleted.

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

## Hoppscotch

![Hoppscotch](https://img.shields.io/badge/Hoppscotch-201718?logo=hoppscotch&logoColor=white)

**Open-source API testing platform (Postman alternative)**

Hoppscotch is a lightweight, open-source API development ecosystem that offers a fast and beautiful interface for testing APIs. Features include:
- REST, GraphQL, WebSocket, and SSE support
- Team collaboration with shared workspaces
- Collections and environments management
- Pre-request and post-request scripts
- Authentication helpers (OAuth, Basic, Bearer, API Key)
- Request history and favorites
- Import/export with Postman, OpenAPI, and HAR formats

| Setting | Value |
|---------|-------|
| Default Port | `3003` |
| Suggested Subdomain | `hoppscotch` |
| Admin Path | `/admin` |
| Public Access | No (API testing tool) |
| Website | [hoppscotch.io](https://hoppscotch.io) |
| Source | [GitHub](https://github.com/hoppscotch/hoppscotch) |

### Architecture

The stack includes:
- **Hoppscotch AIO** - All-in-one container with frontend, backend, and admin
- **PostgreSQL** - Database for users, teams, and collections

### Authentication

Hoppscotch uses email magic links for authentication by default. No OAuth configuration is required.

> ℹ️ **Note:** This stack uses the official AIO (All-In-One) container which includes the main app, admin dashboard, and API backend in a single container.

---

## Kafka-UI

![Kafka-UI](https://img.shields.io/badge/Kafka--UI-000000?logo=apachekafka&logoColor=white)

**Modern web UI for Apache Kafka / Redpanda management**

Kafka-UI is a free, open-source web UI for monitoring and managing Apache Kafka and Redpanda clusters. Features include:
- Multi-cluster management in one place
- Topic creation and configuration
- Real-time message browsing with filtering
- Consumer group monitoring with lag tracking
- Schema Registry support (Avro, JSON Schema, Protobuf)
- KSQL DB integration
- Live message tailing
- Topic data comparison

| Setting | Value |
|---------|-------|
| Default Port | `8181` |
| Suggested Subdomain | `kafka-ui` |
| Public Access | No (cluster management) |
| Website | [kafka-ui.provectus.io](https://docs.kafka-ui.provectus.io/) |
| Source | [GitHub](https://github.com/provectus/kafka-ui) |

### Pre-configured Connection

Kafka-UI is automatically configured to connect to the Redpanda cluster:
- **Bootstrap Servers:** `redpanda:9092`
- **Schema Registry:** `http://redpanda:8081`

> Dynamic configuration is enabled - you can add additional clusters via the UI settings.

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

## NocoDB

![NocoDB](https://img.shields.io/badge/NocoDB-1F2937?logo=nocodb&logoColor=white)

**Open-source Airtable alternative**

NocoDB turns any database into a smart spreadsheet with a modern web UI. Unlike read-only BI tools, NocoDB lets you create, edit, and manage data directly through multiple view types. Features include:
- Grid, Gallery, Kanban, Form, and Calendar views
- REST API auto-generated for every table
- Webhooks and automations
- Role-based access control
- File attachments and rich field types
- Import from CSV, Excel, and Airtable

| Setting | Value |
|---------|-------|
| Default Port | `8091` |
| Suggested Subdomain | `nocodb` |
| Public Access | No (may contain sensitive data) |
| Authentication | Admin account auto-configured |
| Website | [nocodb.com](https://nocodb.com) |
| Source | [GitHub](https://github.com/nocodb/nocodb) |

> ✅ **Auto-configured:** Admin account is automatically configured during deployment with the project admin email. Credentials available in Infisical.

---

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

## Meltano

![Meltano](https://img.shields.io/badge/Meltano-512EFF?logo=meltano&logoColor=white)

**Open-source CLI data integration platform for building modular data pipelines**

Meltano is a modular, open-source data integration platform that allows data teams to build, test, and deploy custom data pipelines. It is a CLI-only tool (the web UI was removed in Meltano v3.0). Features include:
- Modular architecture with Singer protocol support
- 500+ pre-built data connectors (Tap/Target plugins)
- dbt integration for transformations
- Version control friendly with Git-based configs
- State management for incremental loading
- Job scheduling and orchestration via CLI

| Setting | Value |
|---------|-------|
| Internal Only | Yes (CLI access only) |
| Database | PostgreSQL 16 |
| Website | [meltano.com](https://meltano.com) |
| Source | [GitHub](https://github.com/meltano/meltano) |

### Architecture

The stack includes:
- **Meltano** - CLI application (runs as long-lived container)
- **PostgreSQL** - Database for metadata storage

### Configuration

Meltano uses PostgreSQL for metadata storage. All project data (pipelines, schedules, logs) is persisted in the `meltano-data` volume.

### Getting Started

Meltano is accessible via CLI only. You have two options to access the Meltano CLI:

**Option 1: Web-based Terminal (Wetty)**

1. Access Wetty at `https://wetty.<domain>` (requires Cloudflare Access login)
2. In the web terminal, run Meltano commands:

```bash
docker exec -it meltano meltano --help
```

**Option 2: SSH Access**

1. Connect via SSH (see [SSH Access Guide](../docs/ssh-access.md))
2. Run Meltano commands:

```bash
ssh nexus
docker exec -it meltano meltano --help
```

**Common Meltano Commands:**

```bash
# Initialize a new project
docker exec -it meltano meltano init my-project

# List available commands
docker exec -it meltano meltano --help

# Add an extractor (tap) - e.g., CSV files, APIs, databases
docker exec -it meltano meltano add extractor tap-csv

# Add a loader (target) - e.g., PostgreSQL, S3, Data Warehouse
docker exec -it meltano meltano add loader target-postgres

# Run a pipeline (extract + load)
docker exec -it meltano meltano run tap-csv target-postgres

# Schedule a pipeline (runs automatically)
docker exec -it meltano meltano schedule add my-pipeline \
  --extractor tap-csv \
  --loader target-postgres \
  --interval '@daily'

# View logs
docker exec -it meltano meltano logs
```

> **Note:** Meltano has no web UI since v3.0. All interaction is via the CLI through Wetty or SSH.

---

## Soda Core

![Soda](https://img.shields.io/badge/Soda-6C47FF?logo=database&logoColor=white)

**CLI-based data quality testing tool using SodaCL checks**

Soda Core is an open-source data quality tool that uses SodaCL (Soda Checks Language) to define and run data quality checks against your databases. Features include:
- YAML-based check definitions (SodaCL)
- Support for PostgreSQL, MySQL, Snowflake, BigQuery, and more
- Schema validation and freshness checks
- Row count, missing value, and duplicate detection
- Custom SQL-based quality checks
- Over 25 built-in metrics

| Setting | Value |
|---------|-------|
| Internal Only | Yes (CLI access only) |
| Database | PostgreSQL 16 |
| Website | [soda.io](https://www.soda.io) |
| Source | [GitHub](https://github.com/sodadata/soda-core) |

### Architecture

The stack includes:
- **Soda Core** - CLI application (runs as long-lived container, custom-built for ARM64)
- **PostgreSQL** - Database for test data and quality checks

> **Note:** Soda Core uses a custom Dockerfile because the official `sodadata/soda-core` image doesn't support ARM64 architecture (required for cax31 servers).

### Configuration

Soda requires two types of YAML configuration files in the `/workspace` directory:

**1. Data Source Configuration (`configuration.yml`):**
```yaml
data_source soda_postgres:
  type: postgres
  host: soda-db
  port: "5432"
  username: soda
  password: ${SODA_DB_PASSWORD}
  database: soda
```

**2. Check Definitions (`checks.yml`):**
```yaml
checks for my_table:
  - row_count > 0
  - missing_count(column_name) = 0
  - duplicate_count(id) = 0
  - schema:
      fail:
        when required column missing: [id, name, created_at]
  - freshness(created_at) < 1d
```

### Getting Started

Soda Core is accessible via CLI only. You have two options:

**Option 1: Web-based Terminal (Wetty)**

1. Access Wetty at `https://wetty.<domain>` (requires Cloudflare Access login)
2. In the web terminal, run Soda commands:

```bash
docker exec -it soda soda --help
```

**Option 2: SSH Access**

1. Connect via SSH (see [SSH Access Guide](../docs/ssh-access.md))
2. Run Soda commands:

```bash
ssh nexus
docker exec -it soda soda --help
```

**Common Soda Commands:**

```bash
# Check Soda version
docker exec -it soda soda --version

# Test connection to a data source
docker exec -it soda soda test-connection \
  -d soda_postgres \
  -c /workspace/configuration.yml

# Run a scan against the Soda PostgreSQL database
docker exec -it soda soda scan \
  -d soda_postgres \
  -c /workspace/configuration.yml \
  /workspace/checks.yml

# Run a scan with verbose output
docker exec -it soda soda scan \
  -d soda_postgres \
  -c /workspace/configuration.yml \
  /workspace/checks.yml -V
```

> **Note:** Soda Core has no web UI. All interaction is via the CLI through Wetty or SSH. Database credentials are available in Infisical.

---

## Apache Spark

![Spark](https://img.shields.io/badge/Apache_Spark-E25A1C?logo=apachespark&logoColor=white)

**Distributed data processing engine with standalone cluster (Master + Worker)**

Apache Spark provides a unified analytics engine for large-scale data processing. This stack runs a standalone cluster with one master and one worker node, pre-configured with Hetzner Object Storage (S3) access.

| Setting | Value |
|---------|-------|
| Default Port | `8088` (Master Web UI) |
| Cluster Port | `7077` (internal only) |
| Suggested Subdomain | `spark` |
| Public Access | No (cluster management) |
| Website | [spark.apache.org](https://spark.apache.org) |
| Source | [GitHub](https://github.com/apache/spark) |

### Architecture

| Container | Image | Purpose |
|-----------|-------|---------|
| `spark-master` | `nexus-spark:4.1.1-python3.13` | Cluster manager + Web UI (port 8088) |
| `spark-worker` | `nexus-spark:4.1.1-python3.13` | Task executor (connects to master on 7077) |

> **Custom image:** The official `apache/spark:4.1.1` ships Python 3.10 (Ubuntu 22.04), but Jupyter uses Python 3.13. PySpark requires matching Python versions between driver and executors. The custom Dockerfile installs Python 3.13 via deadsnakes PPA and adds `hadoop-aws` + AWS SDK v2 JARs for S3A filesystem support.

```
                    ┌─────────────────────┐
                    │  Jupyter PySpark     │
                    │  %%sparksql magic    │
                    └────────┬────────────┘
                             │ spark://spark-master:7077
              ┌──────────────┴──────────────┐
              │                             │
     ┌────────┴────────┐          ┌─────────┴────────┐
     │  Spark Master   │          │  Spark Worker    │
     │  UI: port 8088  │          │  (no external UI)│
     └────────┬────────┘          └─────────┬────────┘
              │                             │
              └──────────────┬──────────────┘
                             │ S3 (hadoop-aws)
                    ┌────────┴────────┐
                    │ Hetzner Object  │
                    │ Storage (S3)    │
                    └─────────────────┘
```

### Configuration

- **Worker cores:** Configurable via `SPARK_WORKER_CORES` (default: 2)
- **Worker memory:** Configurable via `SPARK_WORKER_MEMORY` (default: 3g)
- **S3 access:** Pre-configured via `SPARK_HADOOP_fs_s3a_*` environment variables when Hetzner Object Storage credentials are available

### Resource Limits

Docker resource limits prevent Spark from consuming all server resources:

| Container | CPU Limit | Memory Limit | CPU Reserved | Memory Reserved |
|-----------|-----------|-------------|-------------|-----------------|
| `spark-master` | 1 | 1 GB | 0.25 | 256 MB |
| `spark-worker` | 2 | 4 GB | 0.5 | 512 MB |
| **Total** | **3** | **5 GB** | **0.75** | **768 MB** |

On a cax31 (8 vCPU, 16 GB RAM) this leaves 5 CPU and 11 GB RAM for other services.

### Usage

1. Enable the Spark service in the Control Plane
2. Access the Master Web UI at `https://spark.YOUR_DOMAIN` to monitor the cluster
3. The Web UI shows registered workers, running applications, and completed jobs
4. Use Jupyter PySpark to submit jobs to the cluster (auto-configured)

### Connecting from Jupyter

When both Spark and Jupyter are enabled, Jupyter automatically connects to the cluster:

```python
from pyspark.sql import SparkSession
spark = SparkSession.builder \
    .master("spark://spark-master:7077") \
    .getOrCreate()

# Run a query
spark.sql("SELECT 1 as test").show()
```

> No configuration needed - `SPARK_MASTER` is automatically set to `spark://spark-master:7077` when the Spark stack is enabled.

---

## Trino

![Trino](https://img.shields.io/badge/Trino-DD00A1?logo=trino&logoColor=white)

**Distributed SQL query engine for federated data access**

Trino is a fast, distributed SQL query engine that can query data across multiple sources (ClickHouse, PostgreSQL, MySQL, S3, and more) without moving data. Run a single SQL query that joins data from different databases.

| Setting | Value |
|---------|-------|
| Default Port | `8060` (mapped from container 8080) |
| Suggested Subdomain | `trino` |
| Public Access | No |
| Website | [trino.io](https://trino.io) |
| Source | [GitHub](https://github.com/trinodb/trino) |

### Configuration

- **Authentication:** None (Cloudflare Access provides authentication)
- **Dynamic catalogs:** Enabled via `CATALOG_MANAGEMENT=dynamic` - add new data sources at runtime
- **Pre-configured catalogs:**
  - `clickhouse` - connects to ClickHouse on the same server (if enabled)
  - `postgresql` - connects to PostgreSQL on the same server (if enabled)

### Usage

1. Enable the service in Control Plane
2. Access `https://trino.YOUR_DOMAIN` for the Web UI
3. Run SQL queries across connected data sources:
   ```sql
   -- Query ClickHouse data
   SELECT * FROM clickhouse.default.my_table LIMIT 10;

   -- Query PostgreSQL data
   SELECT * FROM postgresql.public.users LIMIT 10;

   -- Join across data sources
   SELECT u.name, e.event_type
   FROM postgresql.public.users u
   JOIN clickhouse.default.events e ON u.id = e.user_id;
   ```

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

## RustFS

![RustFS](https://img.shields.io/badge/RustFS-B7410E?logo=rust&logoColor=white)

**Rust-based S3-compatible object storage (MinIO alternative)**

RustFS is a high-performance object storage system written in Rust, designed as a drop-in replacement for MinIO. Features include:
- Amazon S3 API compatible (~94.7% compatibility)
- Built-in web console for bucket and object management
- Multipart uploads and object versioning
- Apache 2.0 license (vs MinIO's AGPLv3)

| Setting | Value |
|---------|-------|
| Default Port | `9003` (Console), `9002` (S3 API) |
| Suggested Subdomain | `rustfs` |
| Public Access | No (storage infrastructure) |
| Website | [rustfs.com](https://rustfs.com) |
| Source | [GitHub](https://github.com/rustfs/rustfs) |

> ✅ **Auto-configured:** Root credentials are automatically created during deployment. Use `make secrets` to view them.

> **Note:** RustFS is in active/alpha development. For production workloads, consider MinIO or SeaweedFS.

### Usage

Access RustFS Console at `https://rustfs.<domain>` to:
- Create buckets
- Upload/download objects
- Manage access policies

**S3 API Access:**
- **Console UI**: `https://rustfs.<domain>` (accessible via Cloudflare Tunnel)
- **S3 API**: Port `9002` (configurable via firewall rules for external access)

---

## S3 Manager

![S3 Manager](https://img.shields.io/badge/S3_Manager-2E7D32?logo=amazons3&logoColor=white)

**Web-based S3 bucket browser and manager for Hetzner Object Storage**

S3 Manager is a lightweight web UI written in Go for managing S3-compatible object storage. It connects to Hetzner Object Storage and provides:
- List all buckets in an account
- Create and delete buckets
- List, upload, download, and delete objects

| Setting | Value |
|---------|-------|
| Default Port | `8086` |
| Suggested Subdomain | `s3manager` |
| Public Access | No (behind Cloudflare Access) |
| Website | [GitHub](https://github.com/cloudlena/s3manager) |

> ✅ **Auto-configured:** S3 credentials are automatically injected from Hetzner Object Storage variables during deployment.

### Usage

Access S3 Manager at `https://s3manager.<domain>` to:
- Browse existing buckets and their contents
- Upload and download files
- Create new buckets
- Delete objects and buckets

No application-level login is required — authentication is handled by Cloudflare Access.

---

## SeaweedFS

![SeaweedFS](https://img.shields.io/badge/SeaweedFS-4CAF50?logo=amazons3&logoColor=white)

**Distributed object storage with S3-compatible API**

SeaweedFS is a lightweight distributed object storage system with S3 API compatibility. All components (master, volume, filer, S3 gateway) run in a single container. Features include:
- S3-compatible API with versioning and multipart uploads
- Master dashboard for cluster monitoring
- Very lightweight (~500MB RAM)
- Filer for POSIX-like file access

| Setting | Value |
|---------|-------|
| Ports | `8888` (Filer UI), `9333` (Master UI), `8333` (S3 API) |
| Subdomains | `seaweedfs` (Filer), `seaweedfs-manager` (Master) |
| Public Access | No (storage infrastructure) |
| Website | [seaweedfs.com](https://seaweedfs.com) |
| Source | [GitHub](https://github.com/seaweedfs/seaweedfs) |

> ✅ **Auto-configured:** S3 credentials are automatically created during deployment. Use `make secrets` to view them.

### URLs

| URL | Purpose |
|-----|---------|
| `https://seaweedfs.<domain>` | **Filer Web UI** - File browser with upload capability |
| `https://seaweedfs-manager.<domain>` | **Master UI** - Cluster statistics and monitoring |

### Usage

**Filer Web UI** (`https://seaweedfs.<domain>`):
- Upload and download files via browser
- Navigate directory structure
- Create folders and manage files

**Master UI** (`https://seaweedfs-manager.<domain>`):
- View cluster topology and volume allocation
- Monitor storage usage and health
- Read-only dashboard for statistics

**S3 API** (Port `8333`):
- Use S3-compatible tools (AWS CLI, Cyberduck, etc.)
- Credentials available in Infisical

---

## Garage

![Garage](https://img.shields.io/badge/Garage-59C6A6?logo=amazons3&logoColor=white)

**Lightweight S3-compatible object storage for self-hosting**

Garage is an S3-compatible distributed object storage service designed for self-hosting. It runs on minimal hardware (even Raspberry Pi) and uses a separate web UI. Features include:
- S3-compatible API (core operations)
- Designed for unreliable networks and consumer hardware
- Extremely lightweight resource usage
- Third-party web UI via garage-webui
- Can scale from single-node to multi-node cluster

| Setting | Value |
|---------|-------|
| Default Port | `3909` (Web UI), `3900` (S3 API), `3903` (Admin API) |
| Suggested Subdomain | `garage` |
| Public Access | No (storage infrastructure) |
| Website | [garagehq.deuxfleurs.fr](https://garagehq.deuxfleurs.fr) |
| Source | [Gitea](https://git.deuxfleurs.fr/Deuxfleurs/garage) |

> ✅ **Auto-configured:** Admin token and layout are automatically configured during deployment.

### Architecture

| Container | Purpose |
|-----------|---------|
| `garage` | S3 API + Admin API + RPC |
| `garage-webui` | Third-party web UI for bucket management |

### Usage

Access Garage Web UI at `https://garage.<domain>` to:
- Create and manage buckets
- Create S3 access keys
- View cluster health

**S3 API Access:**
- **Web UI**: `https://garage.<domain>` (accessible via Cloudflare Tunnel)
- **S3 API**: Port `3900` (configurable via firewall rules for external access)

---

## LakeFS

![LakeFS](https://img.shields.io/badge/LakeFS-00B4D8?logo=git&logoColor=white)

**Git-like version control for data lakes**

LakeFS provides Git-like version control for data stored in object storage. Features include:
- Branch, commit, merge, and diff for data
- S3-compatible gateway for transparent access
- Built-in web UI for repository management
- Zero-copy branching (no data duplication)
- Automatic repository creation based on backend type

| Setting | Value |
|---------|-------|
| Default Port | `8000` (Web UI + API + S3 Gateway) |
| Suggested Subdomain | `lakefs` |
| Public Access | No (data management) |
| Website | [lakefs.io](https://lakefs.io) |
| Source | [GitHub](https://github.com/treeverse/lakeFS) |

> **Note:** LakeFS is a version control layer for object storage. It can use **Hetzner Object Storage** (recommended for production) or **local filesystem** (development/testing).

### Storage Backend Configuration

**Option 1: Hetzner Object Storage (Recommended for Production)**

1. Create S3 credentials in [Hetzner Cloud Console](https://console.hetzner.cloud):
   - Navigate to **Storage** → **Object Storage** → **S3 Credentials**
   - Generate new credentials and save the **Access Key** and **Secret Key**

2. Add to **GitHub Secrets**:
   ```
   HETZNER_OBJECT_STORAGE_ACCESS_KEY = <your-access-key>
   HETZNER_OBJECT_STORAGE_SECRET_KEY = <your-secret-key>
   ```

3. Deploy - LakeFS automatically configures Hetzner S3 as backend

**Option 2: Local Filesystem (Automatic Fallback)**

If Hetzner Object Storage credentials are not configured, LakeFS automatically falls back to local filesystem storage. No additional configuration needed, but:
- ⚠️ Data is stored on server disk
- ⚠️ Data is lost on teardown
- ✅ Suitable for development/testing

**What's Automated:**
- Bucket creation (if using Hetzner S3)
- LakeFS admin user creation
- Default repository creation (`hetzner-object-storage` for S3, `local-storage` for local)
- Backend configuration (S3 or local filesystem)

### Architecture

| Container | Purpose |
|-----------|---------|
| `lakefs` | Web UI + API server + S3 gateway |
| `lakefs-db` | Dedicated PostgreSQL for metadata |

### Access Methods

LakeFS uses a **single port (8000)** for all services, but separates them via DNS:

**1. Web UI (via Cloudflare Tunnel):**
- URL: `https://lakefs.<domain>`
- Access: Protected by Cloudflare Access (email OTP)
- Use for: Browser-based repository management

**2. S3 Gateway (direct TCP access):**
- URL: `s3://s3.lakefs.<domain>:8000` or `http://s3.lakefs.<domain>:8000`
- Access: Direct server connection (requires firewall rule enabled in Control Plane)
- Use for: External tools (Databricks, Spark, DuckDB, Python boto3)

LakeFS routes requests based on the `Host` header:
- `lakefs.<domain>` → Web UI/API
- `s3.lakefs.<domain>` → S3 Gateway

### Usage

**Web UI Setup:**
1. Access LakeFS at `https://lakefs.<domain>`
2. On first launch, create an admin user via the setup wizard
3. Create a repository pointing to the auto-created bucket
4. Use branches for data experimentation, merge when ready

**S3 Gateway Access (requires firewall rule):**
```python
# Python example with boto3
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='http://s3.lakefs.your-domain.com:8000',
    aws_access_key_id='<your-lakefs-access-key>',
    aws_secret_access_key='<your-lakefs-secret-key>'
)

# List repositories
s3.list_buckets()
```

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

## Wiki.js

![Wiki.js](https://img.shields.io/badge/Wiki.js-1976D2?logo=wikidotjs&logoColor=white)

**Open-source wiki and knowledge base platform**

Wiki.js is a powerful wiki platform with Markdown editor, visual editor (WYSIWYG), multi-language support, full-text search, and Git-based storage. All content is stored in a dedicated PostgreSQL database and persists across teardown/spin-up cycles.

| Setting | Value |
|---------|-------|
| Default Port | `3005` |
| Suggested Subdomain | `wiki` |
| Public Access | No (Cloudflare Access) |
| Website | [js.wiki](https://js.wiki) |
| Source | [GitHub](https://github.com/Requarks/wiki) |

### Usage

1. Access at `https://wiki.<domain>`
2. Default credentials:
   - Username: `user_email` (from Infisical: `WIKIJS_USERNAME`)
   - Password: From Infisical (`WIKIJS_PASSWORD`)
3. Auto-setup creates the admin account on first deployment
4. Create pages using Markdown or the visual editor
5. Data persists in PostgreSQL across teardown/spin-up cycles

### Data Persistence

Wiki.js stores all content (pages, assets, settings) in the PostgreSQL database. The `wikijs-db-data` Docker volume is mounted to the Hetzner persistent volume, ensuring data survives teardown and spin-up.

---

## Windmill

![Windmill](https://img.shields.io/badge/Windmill-3B82F6?logo=windowsterminal&logoColor=white)

**Open-source workflow engine for scripts, workflows, and UIs**

Windmill is a developer platform that turns scripts into production-grade workflows, UIs, and endpoints. It features a built-in code editor with LSP autocomplete and supports Python, TypeScript, Go, Bash, SQL, and more.

**Features:**
- **Script editor** - Built-in code editor with LSP autocomplete for Python, TypeScript, Go, Bash, SQL
- **Workflow builder** - Visual DAG editor for composing scripts into multi-step workflows
- **App builder** - Create custom UIs with drag-and-drop components backed by scripts
- **Schedules and triggers** - Cron schedules, webhooks, and event-driven triggers
- **Approval flows** - Human-in-the-loop steps with approval/rejection gates
- **Error handling** - Retries, error handlers, and recovery steps

| Setting | Value |
|---------|-------|
| Default Port | `8200` |
| Suggested Subdomain | `windmill` |
| Public Access | No (Cloudflare Access protected) |
| Default Enabled | No |
| Website | [windmill.dev](https://www.windmill.dev) |
| Source | [GitHub](https://github.com/windmill-labs/windmill) |

**Architecture (5 containers):**

| Container | Image | Purpose |
|-----------|-------|---------|
| `windmill` | `ghcr.io/windmill-labs/windmill:1.624.0` | API server + web UI (MODE=server) |
| `windmill-worker` | `ghcr.io/windmill-labs/windmill:1.624.0` | Default job executor |
| `windmill-worker-native` | `ghcr.io/windmill-labs/windmill:1.624.0` | Native lightweight workers (8 workers) |
| `windmill-lsp` | `ghcr.io/windmill-labs/windmill-lsp:latest` | LSP code intelligence for editor |
| `windmill-db` | `postgres:16-alpine` | Dedicated PostgreSQL database |

**Credentials:**
- Email: Your configured admin email (`$ADMIN_EMAIL`)
- Password: Auto-generated (stored in Infisical)

> ✅ **Auto-configured:** Admin user is automatically created during deployment with your admin email and a generated password. Credentials are available in Infisical.

**Internal connection (from other services):**
- PostgreSQL: `windmill-db:5432` (user: `nexus-windmill`, database: `windmill`)

---

## Woodpecker CI

![Woodpecker CI](https://img.shields.io/badge/Woodpecker_CI-4CAF50?logo=woodpeckerci&logoColor=white)

**Lightweight Docker-native CI/CD engine with pipeline-as-code**

Woodpecker CI is a simple, container-native continuous integration engine forked from Drone CI. Pipelines are defined in `.woodpecker.yml` files in your Git repositories and executed inside Docker containers.

**Features:**
- **Pipeline-as-code** - Define CI/CD pipelines in `.woodpecker.yml` files alongside your code
- **Docker-native** - Each pipeline step runs in its own container
- **Multi-forge support** - Integrates with GitHub, Gitea, GitLab, Bitbucket, and Forgejo
- **Lightweight** - Minimal resource usage compared to Jenkins or GitLab CI
- **Matrix builds** - Run pipeline variants across multiple configurations
- **Secrets management** - Built-in secret storage for pipeline credentials

| Setting | Value |
|---------|-------|
| Default Port | `8084` |
| Suggested Subdomain | `woodpecker` |
| Public Access | No (Cloudflare Access protected) |
| Default Enabled | No |
| Website | [woodpecker-ci.org](https://woodpecker-ci.org) |
| Source | [GitHub](https://github.com/woodpecker-ci/woodpecker) |

**Architecture (2 containers):**

| Container | Image | Purpose |
|-----------|-------|---------|
| `woodpecker-server` | `woodpeckerci/woodpecker-server:v3.13.0` | Web UI, API, and pipeline coordination |
| `woodpecker-agent` | `woodpeckerci/woodpecker-agent:v3.13.0` | Pipeline executor (runs Docker containers) |

**Authentication (auto-configured via Gitea):**
Woodpecker uses OAuth from Gitea for authentication. There is no built-in user/password system. The deploy script automatically creates a Gitea OAuth application and configures Woodpecker with the credentials. Log in via your Gitea account.

> **Dependency:** Woodpecker requires Gitea. If Woodpecker is enabled without Gitea, Gitea is auto-enabled during deployment.

**Data persistence:**
Woodpecker uses SQLite by default. The database is stored in the `woodpecker-server-data` Docker volume on the Hetzner persistent volume, ensuring data survives teardown and spin-up.

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

Terraform creates inbound Hetzner firewall rules and DNS A records pointing directly to the server IP (`proxied = false`, bypassing Cloudflare proxy).

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

