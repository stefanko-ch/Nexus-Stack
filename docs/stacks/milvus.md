---
title: "Milvus"
---

## Milvus

![Milvus](https://img.shields.io/badge/Milvus-00A1EA?logo=milvus&logoColor=white)

**Vector database**

Milvus stores embeddings in collections with scalar fields and searches them with approximate nearest-neighbour indexes such as HNSW, IVF and DiskANN. It also does hybrid search over dense vectors, sparse vectors and full text. Next to [Qdrant](qdrant.md), [Weaviate](weaviate.md) and [Chroma](chroma.md) it is the one designed for scale-out clusters; here it runs as one standalone node.

| Setting | Value |
|---------|-------|
| In-cluster | `milvus:19530` (gRPC for pymilvus, REST API under `/v2/vectordb`) |
| Login | `nexus-milvus`, with the admin role |
| Credentials | Password generated per deployment (Infisical folder `milvus`); root's password is in the same folder |
| Web UI | None — internal only, no subdomain |
| Persistence | Docker volume `milvus-data` |
| Licence | Apache-2.0 |
| Website | [milvus.io](https://milvus.io) |

### First steps

From a notebook, with [pymilvus](https://milvus.io/docs/install-pymilvus.md) (`pip install pymilvus`):

```python
from pymilvus import MilvusClient

client = MilvusClient(uri="http://milvus:19530", token="nexus-milvus:<MILVUS_PASSWORD>")
client.create_collection("demo", dimension=4)
client.insert("demo", [
    {"id": 1, "vector": [0.1, 0.2, 0.3, 0.4]},
    {"id": 2, "vector": [0.9, 0.8, 0.7, 0.6]},
])
client.search("demo", data=[[0.1, 0.2, 0.3, 0.4]], limit=1)  # id 1, distance 1.0
```

The same through the REST API:

```bash
curl -X POST http://milvus:19530/v2/vectordb/entities/search \
  -H "Authorization: Bearer nexus-milvus:<MILVUS_PASSWORD>" -H "Content-Type: application/json" \
  -d '{"collectionName": "demo", "data": [[0.1, 0.2, 0.3, 0.4]], "limit": 1}'
```

Tested through the REST API: a collection created, two vectors inserted and found by search, requests without a token or with a wrong password refused (`user hasn't authenticated`), the data kept across a restart. pymilvus was not tried here.

### One container, no MinIO

A Milvus cluster normally needs etcd for metadata and S3-compatible object storage, and many examples bundle MinIO. MinIO no longer publishes images, and the stack does not need it: it runs the setup of Milvus's own `standalone_embed.sh`.

- **Embedded etcd**, configured by `embedEtcd.yaml` in the stack directory. It listens inside the container only.
- **Local storage** (`COMMON_STORAGETYPE=local`) for segments and indexes.
- **RocksMQ** as the message log, also local. It is set explicitly, because the other standalone choice, Woodpecker, defaults to MinIO.

Like that script, the container runs with `seccomp:unconfined`: the embedded etcd and the storage layer use system calls Docker's default seccomp profile blocks.

### Authentication

Authentication is on. Root's password is seeded from `MILVUS_ROOT_PASSWORD` when the metadata is created on the first start. `milvus-init` then creates `nexus-milvus` with the admin role through the REST API; `curl` reads the `Authorization` header and the request bodies from files, so no password reaches an argument list. On later starts it checks that `nexus-milvus` still logs in.

Milvus's WebUI on the metrics port is read-only and has no login, so it is not published.

### Resources

The container limit is 3 GB. Milvus used about 110 MB with one small collection; indexes for real datasets need far more, roughly the size of the vectors in memory for HNSW. Milvus's own guide recommends 8 GB for a standalone node under load.

### Persistence

Vectors, indexes and the etcd metadata are in `milvus-data`.

- **`rebuild` (default): they do not survive a teardown.** Milvus is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
