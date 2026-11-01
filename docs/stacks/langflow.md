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

Langflow's components reach the AI stacks by service name — Ollama through the `ollama-internal` network it shares with LiteLLM (Ollama is on no other network), the rest on `app-network`:

| Component | URL |
|---|---|
| Ollama (local models, embeddings) | `http://ollama:11434` |
| Qdrant | `http://qdrant:6333` (API key from Infisical → `qdrant`) |
| Chroma | `http://chroma:8000` |
| Weaviate | `http://weaviate:8080` |
| LiteLLM (OpenAI-compatible) | `http://litellm:4000` |

Langflow's SSRF protection makes its built-in connectors refuse URLs that resolve to private addresses, and every container here has one. `LANGFLOW_SSRF_ALLOWED_HOSTS` lists these five hostnames as exceptions, so the connectors can reach them; another in-cluster service needs adding there before a built-in connector will call it. Public URLs are not affected. The list is a convenience for the built-in components, not an access boundary: a custom Python component runs on the server and can make any request it likes, and the superuser can write one.

### Login

Cloudflare Access is the outer gate. Langflow then asks for its own login, a superuser created on first start:

- **Username:** the stack user's email (on a class stack, the student's), else `ADMIN_EMAIL`
- **Password:** generated per deployment

Both are in Infisical, folder `langflow`, as `LANGFLOW_USERNAME` and `LANGFLOW_PASSWORD`. Sign-up is disabled, and so is the superuser CLI inside the container.

Langflow sets the password only when it creates the user, and the R2 restore brings an existing user back. The rebuild teardown therefore excludes the superuser password and `LANGFLOW_SECRET_KEY` from its destroy, so after a teardown and spin-up Infisical still holds the password the restored account has. `destroy-all` removes them like everything else; restoring old data into a fresh deploy afterwards would leave the two out of step.

### Persistence

Flows, the SQLite database, uploaded files and the secret-key file live in `LANGFLOW_CONFIG_DIR=/app/langflow`. The database path is set explicitly with `LANGFLOW_DATABASE_URL`, because Langflow 1.13's default puts `langflow.db` inside its Python package, in the container's writable layer, where a teardown would lose it. The directory is bind-mounted from `/mnt/nexus-data/langflow` and owned by the image's user (`1000:0`). The rebuild teardown stops Langflow and copies the directory to R2; the next spin-up restores it.

`LANGFLOW_SECRET_KEY` is set explicitly rather than left to the file Langflow would generate: it encrypts the API keys stored in flows, and a changed key makes them unreadable.

### Telemetry

`DO_NOT_TRACK=true`.

### Health

`GET /health` (curl, inside the container). It reports that the server is up; it does not check the database.
