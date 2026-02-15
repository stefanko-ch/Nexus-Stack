## Dify

![Dify](https://img.shields.io/badge/Dify-1677FF?logoColor=white)

**AI workflow builder for LLM applications, RAG pipelines, and agentic workflows**

Dify is a production-ready platform for building AI-powered applications with visual
workflow orchestration. It supports multi-model integration (OpenAI, Anthropic, local
models), RAG pipelines with vector database, code execution sandbox, and a plugin
ecosystem.

| Setting | Value |
|---------|-------|
| Default Port | `8501` |
| Suggested Subdomain | `dify` |
| Public Access | No (Cloudflare Access protected) |
| Default Enabled | No |
| Website | [dify.ai](https://dify.ai) |
| Source | [GitHub](https://github.com/langgenius/dify) |

### Architecture (11 containers)

| Container | Image | Purpose |
|-----------|-------|---------|
| `dify-api` | `langgenius/dify-api:1.13.0` | Backend API server |
| `dify-worker` | `langgenius/dify-api:1.13.0` | Celery async worker (MODE=worker) |
| `dify-worker-beat` | `langgenius/dify-api:1.13.0` | Celery beat scheduler |
| `dify-web` | `langgenius/dify-web:1.13.0` | Next.js frontend |
| `dify` | `nginx:alpine` | Reverse proxy (routes to web + api) |
| `dify-db` | `postgres:15-alpine` | Dedicated PostgreSQL database |
| `dify-redis` | `redis:6-alpine` | Cache and message broker |
| `dify-weaviate` | `semitechnologies/weaviate:1.27.0` | Vector database for RAG |
| `dify-sandbox` | `langgenius/dify-sandbox:0.2.12` | Code execution sandbox |
| `dify-ssrf-proxy` | `ubuntu/squid:latest` | SSRF protection proxy |
| `dify-plugin-daemon` | `langgenius/dify-plugin-daemon:0.5.3-local` | Plugin lifecycle management |

### Data Storage

All data is stored on the persistent Hetzner Cloud Volume at `/mnt/nexus-data/dify/`:

| Subdirectory | Content |
|-------------|---------|
| `db/` | PostgreSQL database (workflows, users, configuration) |
| `redis/` | Redis cache and job queue state |
| `storage/` | Uploaded files and documents for RAG |
| `weaviate/` | Vector embeddings for RAG pipelines |
| `plugins/` | Installed Dify plugins |

### Credentials

- **Email**: Your configured admin email (`$ADMIN_EMAIL`)
- **Password**: Auto-generated (stored in Infisical under `dify` tag)

Admin user is automatically created during deployment.

### LLM Provider Configuration

After deployment, configure LLM providers in the Dify UI:

1. Navigate to **Settings > Model Providers**
2. Add your API keys for desired providers (OpenAI, Anthropic, etc.)
3. Dify itself is free - costs come from the LLM provider APIs you configure
