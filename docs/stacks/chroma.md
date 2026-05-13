---
title: "Chroma"
---

## Chroma

![Chroma](https://img.shields.io/badge/Chroma-F87171?logo=databricks&logoColor=white)

**Developer-friendly embedding (vector) database for LLM / RAG pipelines**

Chroma is an open-source vector database designed for LLM applications. You store text + embeddings, then run similarity queries to retrieve the top-k most relevant chunks for a prompt — the workhorse store behind most LangChain / LlamaIndex tutorials. Single container, HTTP REST API, file-based persistence on a local volume. Features include:

- Embedded or HTTP-server modes (we run HTTP-server in this stack)
- File-backed persistence — collections survive container restarts
- REST API at `/api/v2/...` and a Python client (`pip install chromadb`)
- Pairs naturally with [Crawl4AI](crawl4ai.md) (scrape → embed → index) and [Big-AGI](big-agi.md) / Dify (retrieve → augment prompt)

| Setting | Value |
|---------|-------|
| Default Port | `8099` (mapped to internal 8000) |
| Suggested Subdomain | `chroma` |
| Public Access | No (protected by Cloudflare Access) |
| Persistence | Local Docker volume (compose key `chroma_data`; see Persistence section for the project-prefixed on-disk name) |
| Website | [trychroma.com](https://www.trychroma.com) |
| Source | [GitHub](https://github.com/chroma-core/chroma) |

### Browser entry point

Chroma is API-only — it has no landing page at `/` and Chroma returns 404 there. To make the URL Just Work for browser users, the **Control Plane "Open Chroma" button** links to `https://chroma.<domain>/docs/` directly (Chroma's bundled Swagger UI) instead of the bare root.

This is driven by an optional **`landing_path`** field on the service's `services.yaml` entry:

```yaml
chroma:
  ...
  landing_path: "/docs/"   # API-only — Chroma has no UI at /, but /docs/ serves Swagger
```

The Control Plane's `stackUrl()` helper reads this from the `/api/services` response and appends it to the base URL when building the click target. Operators who type the bare URL into the browser address bar still see Chroma's 404 — that's expected — but anyone using the Control Plane's UI lands on Swagger directly.

Direct API calls (`/api/v2/...`, the Python client `chromadb.HttpClient(...)`) bypass `landing_path` and behave normally.

### Usage

From a Python client (most common):

```python
import chromadb
client = chromadb.HttpClient(host="chroma", port=8000)   # inside the Docker network
# from outside: chromadb.HttpClient(host="chroma.<domain>", port=443, ssl=True, headers={...CF Access JWT...})

collection = client.get_or_create_collection("notes")
collection.add(
    documents=["Nexus-Stack runs on Hetzner.", "Big-AGI is a multi-LLM web UI."],
    ids=["doc1", "doc2"],
)
print(collection.query(query_texts=["Where does Nexus-Stack run?"], n_results=1))
```

Or REST directly. Two paths, depending on where the client runs:

**From inside the Docker network** (e.g. a code-server terminal, a Kestra task, or another container) — no auth, just hit the internal host:

```bash
curl http://chroma:8000/api/v2/heartbeat
# → {"nanosecond heartbeat": 1715583600123456789}
```

**From outside the stack** (your laptop, an external CI job) — the request goes through Cloudflare Tunnel + Cloudflare Access. Browser users get the email-OTP login; programmatic clients need a service token. Generate one in your Zero Trust dashboard (**Access → Service Auth → Service Tokens**), bind it to the Chroma Access app, then:

```bash
curl https://chroma.<domain>/api/v2/heartbeat \
  --header "CF-Access-Client-Id: <token-id>.access" \
  --header "CF-Access-Client-Secret: <token-secret>"
```

A bare `curl https://chroma.<domain>/...` returns `302` to the Access login flow — that's expected, not a Chroma error.

### Persistence

Data is stored in a Docker named volume mounted at `/data` inside the container (Chroma 1.x's canonical persistence path — older 0.x docs sometimes show `/chroma/chroma`, which is stale and writes go to the container FS instead). The compose-file volume key is `chroma_data`, but Docker Compose prefixes it with the project name when it actually creates the volume on disk — so `docker volume ls` will show it as something like **`chroma_chroma_data`** (compose-file dir = project name by default), not as the bare `chroma_data`. When looking for the data directory or backing it up directly, use:

```bash
docker volume ls | grep chroma          # find the exact project-prefixed name
docker volume inspect <name>            # see the host path under .[].Mountpoint
                                        # typically /var/lib/docker/volumes/<name>/_data
```

It **survives**:
- Container restarts (`docker compose restart`)
- Spin-up cycles where the Hetzner server isn't recreated
- `docker compose down` / `up` (volumes are not removed by default)

It does **NOT survive**:
- `gh workflow run teardown.yml` — the Hetzner server is destroyed and the volume goes with it
- `gh workflow run destroy-all.yml` — same, plus the Cloudflare side is wiped too

Cross-teardown persistence to R2 is **opt-in per stack** in [src/nexus_deploy/s3_restore.py](../../src/nexus_deploy/s3_restore.py) (the hard-coded `rsync_targets` tuple, currently only `gitea-*` and `dify-*`). Chroma is intentionally not in that list — for workshop / classroom use, rebuilding embeddings per session is part of the demo. If you operate Chroma as a long-running RAG store and want cross-teardown durability, register the on-disk volume path (e.g. `/var/lib/docker/volumes/chroma_chroma_data/_data` — adjust the project prefix to match your local setup) explicitly there in a deliberate code-change PR. A cleaner alternative is to first switch this stack to a bind-mount under `/mnt/nexus-data/chroma/` and register that path — bind-mount paths are stable across hostnames whereas named-volume paths embed the Compose project name.

### Authentication

Chroma ships built-in basic-auth and token-auth providers, but they're disabled in this stack (`CHROMA_SERVER_AUTHN_PROVIDER` unset). Cloudflare Access fronts the API — the email-OTP gate authenticates the human, and the HTTPS-only Tunnel keeps the traffic confidential. For a single-operator / classroom setup that's sufficient.

If you need finer-grained access control (per-collection token auth, etc.), flip the relevant `CHROMA_SERVER_AUTHN_*` env vars in [stacks/chroma/docker-compose.yml](../../stacks/chroma/docker-compose.yml) and re-spin-up.

### Telemetry

`ANONYMIZED_TELEMETRY=false` is set by default. Upstream Chroma sends anonymized usage stats by default; we turn it off for the self-hosted scenario where the operator typically doesn't want any outbound calls. Flip it back to `true` if you want to contribute usage data to the project.
