---
title: "Flowise"
---

## Flowise

![Flowise](https://img.shields.io/badge/Flowise-4F46E5?logo=langchain&logoColor=white)

**Visual builder for LLM chatflows and agents**

Flowise builds LLM applications from nodes on a canvas — chat models, prompts, document loaders, splitters, vector stores, memory, tools and agents — and serves each chatflow as an embeddable chat widget or an API endpoint. Next to [Langflow](langflow.md) it is the lighter, more catalogue-driven of the two: most flows are a handful of ready nodes rather than custom code.

| Setting | Value |
|---------|-------|
| Default Port | `3011` on the host (bound to `127.0.0.1`), `3000` in the container |
| Suggested Subdomain | `flowise` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | Owner account, generated per deployment — see below |
| Database | Dedicated PostgreSQL (`flowise-db`) |
| Persistence | Database dump + `/mnt/nexus-data/flowise`, both backed up to R2 |
| Website | [flowiseai.com](https://flowiseai.com) |
| Source | [GitHub](https://github.com/FlowiseAI/Flowise) |

### Using the rest of the stack

| Node | URL |
|---|---|
| Ollama (chat models, embeddings) | `http://ollama:11434` — Flowise joins Ollama's `ollama-internal` network |
| LiteLLM (OpenAI-compatible) | `http://litellm:4000` |
| Qdrant | `http://qdrant:6333` (API key from Infisical → `qdrant`) |
| Chroma | `http://chroma:8000` |
| Weaviate | `http://weaviate:8080` |

### Login

Flowise has no setting that creates an owner. In the open-source edition the first registration becomes owner of the only organisation, and every later registration is refused with "You can only have one organization". The `flowise-init` container makes that first registration as soon as Flowise answers:

- **Email:** the stack user's email (on a class stack, the student's), else `ADMIN_EMAIL`
- **Password:** generated per deployment

Both are in Infisical, folder `flowise`, as `FLOWISE_USERNAME` and `FLOWISE_PASSWORD`. `flowise-init` runs again on every spin-up, finds the owner, reports `owner already exists` and exits 0. Any other answer fails it loudly.

Flowise requires a lower- and upper-case letter, a digit and a special character in a password; the generated one always has them.

The restored database keeps the account it was registered with, so the rebuild teardown excludes the password from its destroy, and Infisical keeps matching it.

### Why PostgreSQL, not SQLite

Flowise defaults to SQLite. On 3.1.4 that crashes the server at startup — `TypeError: this.db.exec is not a function` in the SQLite session store — on amd64 and arm64 alike. With `DATABASE_TYPE=postgres` it starts, and a dedicated database is this repository's convention anyway.

### Persistence

Two parts that belong together:

- **The database** (flows, credentials, users): dumped with `pg_dump` on teardown and restored on spin-up.
- **`/mnt/nexus-data/flowise`** (owned by `1000:1000`): the credential encryption key, the generated JWT and session secrets, uploads and logs. Copied to R2 with the stack stopped.

A restored database needs the encryption key it was written with, which is why both are covered.

### Telemetry

`DISABLE_FLOWISE_TELEMETRY=true`. Flowise only creates its PostHog client when `POSTHOG_PUBLIC_API_KEY` is set, and it is not.

### Health

`GET /api/v1/ping` (curl, inside the container).
