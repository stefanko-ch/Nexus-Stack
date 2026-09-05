---
title: "Weaviate"
---

## Weaviate

![Weaviate](https://img.shields.io/badge/Weaviate-00C9A7?logo=weaviate&logoColor=white)

**Vector database with hybrid search — BM25 keyword scoring and vector similarity in one query**

Weaviate is a server-shaped vector database. Collections carry a schema, queries go over REST or GraphQL, and hybrid search blends keyword relevance with vector distance in a single call rather than making you merge two result sets yourself. Features include:

- Named collections with an explicit schema, not just untyped blobs
- Hybrid search — BM25 + vector, with a tunable `alpha` between them
- REST and GraphQL endpoints, plus Python, TypeScript and Go clients
- Filtered vector search: `where` clauses applied during the search, not after
- File-backed persistence on a local volume

### Why alongside Chroma

Both are vector stores and both stay. [Chroma](chroma.md) is the small, embedded-style option most tutorials start with — you add texts, you query, you are done. Weaviate is what a retrieval pipeline looks like once relevance has to be tuned: schema, hybrid scoring, filters that run inside the search. Comparing the two on the same corpus is the point of having both.

| Setting | Value |
|---------|-------|
| Default Port | `8101` (mapped to internal 8080) |
| Suggested Subdomain | `weaviate` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | None — see below |
| Persistence | Local Docker volume (compose key `weaviate_data`) |
| Website | [weaviate.io](https://weaviate.io) |
| Source | [GitHub](https://github.com/weaviate/weaviate) |

### No credentials, on purpose

Weaviate runs with `AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true`. The port is published only inside `app-network` and reachable from outside solely through the tunnel, behind Cloudflare Access — which is where authentication lives in this project.

Enabling Weaviate's own API-key auth would add a second secret in front of the same door, and one that every other stack on the network would then need handed to it. Nothing is gained; a key to distribute is lost.

The consequence is worth stating plainly: **any container on `app-network` can read and write every collection.** That is the same posture as Chroma and the shared Postgres, and it is a property of the network, not of Weaviate.

### There is a second Weaviate in this stack

[Dify](dify.md) bundles its own Weaviate as a support container
(`dify-weaviate`, pinned separately at `1.27.0`) and uses it internally for
its knowledge bases. That one is Dify's private store: it is not exposed,
not documented here, and not the instance this page describes.

The two never collide. Dify's image key is prefixed `dify-`, which is what
keeps `tofu output image_versions` from merging them into one — the rule
that #715 was opened for after nineteen stacks shared the key `postgres`.

### No vectorizer module

`DEFAULT_VECTORIZER_MODULE` is `none`, so the container computes no embeddings. Vectors come from the client.

That lets it pair with whatever is already deployed — [Ollama](ollama.md) for local models, [LiteLLM](litellm.md) as a gateway, or an external provider — instead of pinning one embedding model inside the database, where changing it would mean re-indexing.

`ENABLE_MODULES=""` alone does **not** turn the modules off. Measured on 1.34: with only that set, `/v1/meta` lists **39 active modules** — the API-based ones (`generative-anthropic`, `generative-aws`, and so on) are enabled by default. They download nothing, but each is an outbound integration this deployment never asked for. `API_BASED_MODULES_DISABLED=true` brings it to zero, and that is what the stack sets.

### Quick check

The tunnel hostname is behind Cloudflare Access, so an unauthenticated `curl` gets an Access page rather than JSON. Check from the server, where the port is bound to loopback:

```bash
ssh nexus "curl -s http://127.0.0.1:8101/v1/meta" | jq '.version'
```

Inside the stack, other containers reach it at `weaviate:8080` — the container port, not the published `8101`.

### Creating a collection

```python
import weaviate

client = weaviate.connect_to_custom(
    http_host="weaviate", http_port=8080, http_secure=False,
    grpc_host="weaviate", grpc_port=50051, grpc_secure=False,
)
client.collections.create("Documents")
```

Note the ports differ from the browser URL: in-cluster clients use 8080, and the gRPC channel is separate from the REST one.

### Health

The container's healthcheck probes `/v1/.well-known/ready`, which answers 200 when the node can serve queries and 503 while it is still starting.

The probe uses `wget`, not `curl`: this image ships no `curl`, verified with `command -v` inside it. A `curl` probe would have failed on every attempt while the service was perfectly healthy, which is the defect fixed for three other stacks in #783.
