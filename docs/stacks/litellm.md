---
title: "LiteLLM Proxy"
---

## LiteLLM Proxy

![LiteLLM](https://img.shields.io/badge/LiteLLM-00BFFF?logo=openai&logoColor=white)

**Unified OpenAI-compatible proxy for 100+ LLM providers**

LiteLLM is a drop-in OpenAI-compatible proxy that forwards requests to ANY LLM provider — local Ollama (free, in-stack), OpenAI, Anthropic, Mistral, Groq, Cohere, Together, and 100+ others — based on the `model` parameter. Students write code against `openai.OpenAI(base_url="https://litellm.YOUR_DOMAIN/v1")` and the proxy routes each request to the right backend. The `/v1` suffix matches OpenAI's own SDK default (`https://api.openai.com/v1`) so the `openai-python` client appends paths like `/chat/completions` correctly.

| Setting | Value |
|---------|-------|
| Default Port | `4000` |
| Suggested Subdomain | `litellm` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [litellm.ai](https://www.litellm.ai) |
| Source | [GitHub](https://github.com/BerriAI/litellm) |
| Docker image | [`litellm/litellm-database`](https://hub.docker.com/r/litellm/litellm-database) (database variant for cost-tracking UI) |
| Backing DB | Dedicated Postgres 16 (`litellm-db` container) |

### Why this stack matters for a teaching environment

- **Single SDK, every model**: students learn `openai-python` ONCE and access GPT-4, Claude 3.5, Llama 3, Mistral Large — all via the same client
- **Free local inference**: `model="gpt-3.5-turbo"` routes to the in-stack Ollama by default → zero cost during workshops
- **Real-API access on demand**: operator adds OpenAI / Anthropic keys → students can request `model="claude-3-5-sonnet"` or `model="gpt-4o"` for production-grade output
- **Per-key budgets**: give each student an API key with a `$5/month` cap → no risk of a runaway loop blowing through the org budget
- **Cost dashboard at `/ui`**: see live spend per user, per project, per model

### Usage

1. Enable **LiteLLM** in the Control Plane → Spin Up
2. Open `https://litellm.YOUR_DOMAIN/ui` → CF Access OTP → LiteLLM UI login (username `admin` + master key as password)
3. Create per-student virtual keys under **Virtual Keys** → set monthly budget → share key
4. Student code:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://litellm.YOUR_DOMAIN/v1",  # matches OpenAI SDK's expected /v1 path prefix
    api_key="sk-..."  # the virtual key from step 3
)
response = client.chat.completions.create(
    model="gpt-3.5-turbo",  # routes to local Ollama
    messages=[{"role": "user", "content": "Explain RAG in one sentence"}],
)
```

### Adding more providers

The shipped `stacks/litellm/config.yaml.template` ships ONE route (`gpt-3.5-turbo` → Ollama). The generated `config.yaml` is gitignored and overwritten on every spin-up — edit the **template**, not the generated file. Two ways to add providers:

**Option A — UI (no redeploy):** `/ui → Models → + Add Model`. UI-added models persist in Postgres (`STORE_MODEL_IN_DB=true`) so they survive container restarts.

**Option B — config.yaml.template (committed):**

1. Add the entry to `stacks/litellm/config.yaml.template`. Example real-provider entries:

    ```yaml
    model_list:
      - model_name: gpt-4o
        litellm_params:
          model: openai/gpt-4o
          api_key: os.environ/OPENAI_API_KEY

      - model_name: claude-3-5-sonnet
        litellm_params:
          model: anthropic/claude-3-5-sonnet-20241022
          api_key: os.environ/ANTHROPIC_API_KEY

      - model_name: llama3-70b-groq
        litellm_params:
          model: groq/llama3-70b-8192
          api_key: os.environ/GROQ_API_KEY
    ```

2. **Wire the env var through TWO files** (the shipped compose does NOT pass provider keys by default — this is the operator step Copilot rightly flagged as missing):

   - In `stacks/litellm/docker-compose.yml`, add to the `litellm` service's `environment:` block:
     ```yaml
     OPENAI_API_KEY: ${OPENAI_API_KEY}
     ```
   - In the `.env` rendered by `nexus_deploy`, the value comes from either (a) a repo secret plumbed through `.github/workflows/spin-up.yml`'s `env:` block of the `python -m nexus_deploy run-pipeline` step + a matching field added to `_render_litellm` in `src/nexus_deploy/service_env.py`, OR (b) for a quick test, set the env var on the server before `docker compose up`.

3. Run **Spin Up** — the rendered `config.yaml` picks up the new template, the container has `OPENAI_API_KEY` available, LiteLLM routes `gpt-4o` requests to OpenAI.

### Auth model

- **Master key** (`LITELLM_MASTER_KEY`): admin bearer token for `/key/generate`, `/team/new`, model management, UI login as `admin`. Treat as root credential — rotate by `tofu apply` + `infisical sync` + spin-up
- **Virtual keys**: per-student / per-project keys generated through the UI or `/key/generate`. Each can have its own budget, allowed-models list, expiration date
- **Salt key** (`LITELLM_SALT_KEY`): hashes derived keys before storing in DB. Operator can rotate to invalidate ALL student-issued keys at once (e.g. after a workshop ends)

### Secrets

Generated by OpenTofu and pushed to Infisical under folder `/litellm`:

- `LITELLM_MASTER_KEY` — admin Bearer token (32 chars)
- `LITELLM_SALT_KEY` — DB hash salt (32 chars)
- `LITELLM_DB_PASSWORD` — Postgres password for the dedicated `litellm-db` container

All three must be non-empty or the deploy aborts (no silent auth-bypass).

### Ollama integration

The LiteLLM compose joins the external `ollama-internal` network so it can reach `http://ollama:11434` directly without going through the public CF Tunnel route — fast and private. **The Ollama stack MUST be enabled** for LiteLLM to start: the compose declares `external: true` + `name: ollama-internal` on that network, and Docker will refuse to start the LiteLLM container if the network doesn't exist (error: `network ollama-internal not found`).

If you want LiteLLM without Ollama (e.g. real-providers-only setup), you need TWO changes:

1. Remove the `ollama-internal` network declaration AND the `ollama-internal:` entry under `litellm.networks:` in `stacks/litellm/docker-compose.yml`
2. Remove the `gpt-3.5-turbo` → Ollama route from `stacks/litellm/config.yaml.template` (otherwise the proxy serves the model name but routes to an unreachable backend)

Removing just the config route without the network change still results in container start failure.

### Persistence

- `litellm-db-data` volume: cost tracking history, virtual keys, model list, team / user metadata

Included in the S3-persistence snapshot loop (`NEXUS_S3_PERSISTENCE=true`).

### Troubleshooting

- **All requests 401**: master key mismatch — check the bearer token your client sends matches `infisical secrets get LITELLM_MASTER_KEY --path=/litellm --plain`
- **`model not available`**: check `/ui → Models` — only models in the routing table are reachable. Add via UI (runtime) or edit `stacks/litellm/config.yaml.template` (committed) and re-deploy. The generated `stacks/litellm/config.yaml` is gitignored and overwritten on every spin-up.
- **High latency to OpenAI/Anthropic**: LiteLLM forwards synchronously — slow upstream = slow proxy. Look at `/ui → Logs` to see per-request timing
- **DB connection errors at startup**: `LITELLM_DB_PASSWORD` mismatch between the litellm container and the Postgres container env — usually means a previous deploy used a different password and the volume has the old one. `docker compose down -v` the stack to reset (loses cost history)

### Related

- [Issue tracker](https://github.com/BerriAI/litellm/issues) — very active project, frequent releases
- [Provider compatibility matrix](https://docs.litellm.ai/docs/providers) — what params drop / map for each backend
