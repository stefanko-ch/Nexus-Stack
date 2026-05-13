---
title: "Chroma"
---

## Chroma

![Chroma](https://img.shields.io/badge/Chroma-F87171?logo=databricks&logoColor=white)

**Developer-friendly embedding (vector) database for LLM / RAG pipelines**

Chroma is an open-source vector database designed for LLM applications. You store text + embeddings, then run similarity queries to retrieve the top-k most relevant chunks for a prompt — the workhorse store behind most LangChain / LlamaIndex tutorials. Single-process Python server with HTTP REST API, file-based persistence (DuckDB + Parquet under the hood). Features include:

- Embedded or HTTP-server modes (we run HTTP-server in this stack)
- File-backed persistence — collections survive container restarts
- REST API at `/api/v2/...` and a Python client (`pip install chromadb`)
- Pairs naturally with [Crawl4AI](crawl4ai.md) (scrape → embed → index) and [Big-AGI](big-agi.md) / Dify (retrieve → augment prompt)

| Setting | Value |
|---------|-------|
| Default Port | `8099` (mapped to internal 8000) |
| Suggested Subdomain | `chroma` |
| Public Access | No (protected by Cloudflare Access) |
| Persistence | Local Docker volume `chroma_data` (see Persistence section below) |
| Website | [trychroma.com](https://www.trychroma.com) |
| Source | [GitHub](https://github.com/chroma-core/chroma) |

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

Or REST directly (curl, Postman, Hoppscotch):

```bash
curl https://chroma.<domain>/api/v2/heartbeat
# → {"nanosecond heartbeat": 1715583600123456789}
```

### Persistence

Data is stored in the Docker volume `chroma_data` mounted at `/chroma/chroma`. It **survives**:
- Container restarts (`docker compose restart`)
- Spin-up cycles where the Hetzner server isn't recreated
- `docker compose down` / `up` (volumes are not removed by default)

It does **NOT survive**:
- `gh workflow run teardown.yml` — the Hetzner server is destroyed and the volume goes with it
- `gh workflow run destroy-all.yml` — same, plus the Cloudflare side is wiped too

Cross-teardown persistence to R2 is **opt-in per stack** in [src/nexus_deploy/s3_restore.py](../../src/nexus_deploy/s3_restore.py) (the hard-coded `rsync_targets` tuple, currently only `gitea-*` and `dify-*`). Chroma is intentionally not in that list — for workshop / classroom use, rebuilding embeddings per session is part of the demo. If you operate Chroma as a long-running RAG store and want cross-teardown durability, add it explicitly there in a deliberate code-change PR.

### Authentication

Chroma ships built-in basic-auth and token-auth providers, but they're disabled in this stack (`CHROMA_SERVER_AUTHN_PROVIDER` unset). Cloudflare Access fronts the API — the email-OTP gate authenticates the human, and the HTTPS-only Tunnel keeps the traffic confidential. For a single-operator / classroom setup that's sufficient.

If you need finer-grained access control (per-collection token auth, etc.), flip the relevant `CHROMA_SERVER_AUTHN_*` env vars in [stacks/chroma/docker-compose.yml](../../stacks/chroma/docker-compose.yml) and re-spin-up.

### Telemetry

`ANONYMIZED_TELEMETRY=FALSE` is set by default. Upstream Chroma sends anonymized usage stats by default; we turn it off for the self-hosted scenario where the operator typically doesn't want any outbound calls. Flip it back to `TRUE` if you want to contribute usage data to the project.
