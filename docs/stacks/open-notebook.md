---
title: "Open Notebook"
---

## Open Notebook

![Open Notebook](https://img.shields.io/badge/Open_Notebook-111827?logo=jupyter&logoColor=white)

**Self-hosted NotebookLM alternative — ask questions about your own sources with local models**

Open Notebook collects sources — PDFs, web pages, text, audio — into notebooks and lets you ask questions about them, generate summaries and notes, and search across everything. With Ollama as the model provider nothing leaves the server.

| Setting | Value |
|---------|-------|
| Default Port | `8503` on the host (bound to `127.0.0.1`), `8502` in the container |
| Suggested Subdomain | `open-notebook` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | One shared password, generated per deployment |
| Database | SurrealDB sidecar (`open-notebook-db`) |
| Persistence | `/mnt/nexus-data/open-notebook`, backed up to R2 |
| Website / Source | [GitHub](https://github.com/lfnovo/open-notebook) |

### Login

Cloudflare Access is the outer gate. Open Notebook then asks for its own password — one shared password, no username — which also protects the REST API (`Authorization: Bearer <password>`). It is in Infisical, folder `open-notebook`, as `OPEN_NOTEBOOK_PASSWORD`. The deploy refuses to start Open Notebook without it, because Open Notebook without a password runs with authentication off and does not say so.

### Setting up models (once)

Open Notebook does not pull models and has no model until one is configured. In the UI, **Manage → Models**:

1. Add an **Ollama** credential with base URL `http://ollama:11434` (no API key). Open Notebook joins Ollama's `ollama-internal` network, so this resolves.
2. Assign a chat model and an embedding model, or use *Auto-assign Defaults*. The models must already exist in Ollama, for example:
   ```bash
   ssh nexus "docker exec ollama ollama pull llama3.2:3b"
   ssh nexus "docker exec ollama ollama pull mxbai-embed-large"
   ```

Alternatively use **OpenAI Compatible** with base URL `http://litellm:4000/v1` and a LiteLLM key. Credentials are stored encrypted with `OPEN_NOTEBOOK_ENCRYPTION_KEY`, which is generated per deployment and kept across a rebuild teardown so stored credentials stay readable.

Podcasts need a text-to-speech model, which Ollama does not provide; that feature stays unavailable without an external TTS provider.

### One hostname, one port

The image runs the Next.js UI (8502), the FastAPI API (5055) and a worker. Only the UI is published. `API_URL` is set to the stack's public URL, so the browser calls the API there and the UI forwards `/api` to the API inside the container. Left unset, the browser would try `<host>:5055`, which the tunnel does not route.

### Persistence

| Directory | Content |
|---|---|
| `/mnt/nexus-data/open-notebook/db` | SurrealDB's RocksDB files: notebooks, sources, notes, settings |
| `/mnt/nexus-data/open-notebook/data` | Uploaded files and caches |

The rebuild teardown stops the stack and copies both to R2. SurrealDB's user (`nexus-open-notebook`) and its password, like the encryption key, are kept across a rebuild teardown, because the restored database holds them. Checked locally: a notebook created through the API was still there after the containers were removed and recreated.

### Health

`GET /health` on the API (curl, inside the container). It turns green a few seconds before the API answers data requests: right after a start, a notebook list can come back empty once before it fills.
