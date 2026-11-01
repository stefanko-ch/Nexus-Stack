---
title: "Langflow"
---

## Langflow

![Langflow](https://img.shields.io/badge/Langflow-7528FC?logo=langchain&logoColor=white)

**Visual builder for LLM flows, RAG pipelines and agents**

Langflow draws an LLM application as a flow: models, prompts, retrievers, vector stores and tools are components on a canvas, wired by their inputs and outputs. A flow runs in the built-in playground or as an API endpoint. It is the hands-on way to see how a RAG pipeline or an agent fits together before writing one in code.

| Setting | Value |
|---------|-------|
| Default Port | `7860` (bound to `127.0.0.1` on the host) |
| Suggested Subdomain | `langflow` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | Superuser, generated per deployment — see below |
| Persistence | `/mnt/nexus-data/langflow`, backed up to R2 |
| Website | [langflow.org](https://www.langflow.org) |
| Source | [GitHub](https://github.com/langflow-ai/langflow) |

### Using the rest of the stack

Langflow's components reach the AI stacks on `app-network` by service name:

| Component | URL |
|---|---|
| Ollama (local models, embeddings) | `http://ollama:11434` |
| Qdrant | `http://qdrant:6333` (API key from Infisical → `qdrant`) |
| Chroma | `http://chroma:8000` |
| Weaviate | `http://weaviate:8080` |
| LiteLLM (OpenAI-compatible) | `http://litellm:4000` |

Langflow blocks connector URLs that resolve to private addresses (its SSRF protection), and every container here has one. The compose file therefore allows exactly these five hostnames with `LANGFLOW_SSRF_ALLOWED_HOSTS`. Any other in-cluster service has to be added there first.

### Login

Cloudflare Access is the outer gate. Langflow then asks for its own login, a superuser created on first start:

- **Username:** the stack user's email (on a class stack, the student's), else `ADMIN_EMAIL`
- **Password:** generated per deployment

Both are in Infisical, folder `langflow`, as `LANGFLOW_USERNAME` and `LANGFLOW_PASSWORD`. Sign-up is disabled, and so is the superuser CLI inside the container.

Langflow sets the password only when it creates the user. An existing data directory keeps the password it was created with, so after a full `destroy-all` and a fresh deploy the restored data and the new password would not match.

### Persistence

Flows, the SQLite database, uploaded files and the secret-key file live in `LANGFLOW_CONFIG_DIR=/app/langflow`. The database path is set explicitly with `LANGFLOW_DATABASE_URL`, because Langflow 1.13's default puts `langflow.db` inside its Python package, in the container's writable layer, where a teardown would lose it. The directory is bind-mounted from `/mnt/nexus-data/langflow` and owned by the image's user (`1000:0`). The rebuild teardown stops Langflow and copies the directory to R2; the next spin-up restores it.

`LANGFLOW_SECRET_KEY` is set explicitly rather than left to the file Langflow would generate: it encrypts the API keys stored in flows, and a changed key makes them unreadable.

### Telemetry

`DO_NOT_TRACK=true`.

### Health

`GET /health` (curl, inside the container). It reports that the server is up; it does not check the database.
