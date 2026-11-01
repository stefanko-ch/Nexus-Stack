---
title: "Memgraph"
---

## Memgraph

![Memgraph](https://img.shields.io/badge/Memgraph-FB6E00?logo=memgraph&logoColor=white)

**In-memory graph database with the MAGE algorithm library and Memgraph Lab**

Memgraph is a Cypher-compatible graph database that keeps the graph in memory, built for graph analytics and streaming graphs. This stack runs the MAGE image, so graph algorithms are callable straight from Cypher, and Memgraph Lab as the web UI for queries and graph visualisation.

| Setting | Value |
|---------|-------|
| Default Port | `3010` — Memgraph Lab (bound to `127.0.0.1` on the host) |
| Bolt | `bolt://memgraph:7687`, inside `app-network` only |
| Suggested Subdomain | `memgraph` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | `nexus-memgraph`, password generated per deployment |
| Persistence | `/mnt/nexus-data/memgraph`, backed up to R2 |
| Website | [memgraph.com](https://memgraph.com) |
| Source | [GitHub](https://github.com/memgraph/memgraph) |

### Memgraph next to Neo4j

[Neo4j](neo4j.md) is the classic disk-based graph store. Memgraph is the one for analysing a graph: with MAGE, `CALL pagerank.get()`, community detection (`community_detection.get()`), betweenness centrality and shortest paths run in the database, and Memgraph can consume Kafka or Redpanda topics into the graph. Both speak Cypher and Bolt, so the same client libraries work for either.

### Connecting

**Memgraph Lab** (the stack URL): choose **New connection → Memgraph instance**. Host `memgraph` and port `7687` are pre-filled. Set *Authentication* to *Username/password*, then enter `nexus-memgraph` and the password from Infisical, folder `memgraph` (`MEMGRAPH_PASSWORD`). Memgraph documents no way to pre-fill the credentials. *Connect now* under Quick Connect reports "Memgraph not detected", because it tries without credentials and this database requires them.

Lab opens the Bolt connection from its own backend: the browser only talks to Lab (`POST /auth/login`), so Lab reaches `memgraph:7687` inside the network and nothing Bolt-related has to cross the tunnel. Checked locally with 3.14.1. Lab's Logs view uses Memgraph's monitoring WebSocket (7444), which this stack does not publish.

**From a notebook** (Neo4j's driver works too):

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://memgraph:7687", auth=("nexus-memgraph", "<MEMGRAPH_PASSWORD>"))
```

Bolt is not published on the host: 7687 there belongs to Neo4j, and Bolt cannot cross the HTTPS tunnel as a plain hostname.

### Authentication

Memgraph creates `nexus-memgraph` from `MEMGRAPH_USER` / `MEMGRAPH_PASSWORD` on the first start with an empty data directory, and keeps an existing user unchanged. The deploy refuses to start Memgraph without a password, because with no user at all Memgraph accepts every connection.

### Memory

The graph lives in memory. The container is limited to 2 GB and Memgraph's own `--memory-limit` to 1536 MiB, so a query that outgrows it fails with an error instead of the container being killed. Raise both together for larger course datasets. Memgraph Lab has 512 MB.

### Persistence

Snapshots and the write-ahead log live in `/var/lib/memgraph`, bind-mounted from `/mnt/nexus-data/memgraph` and owned by the image's user (`101:103`). Memgraph writes a snapshot on shutdown by default, and the rebuild teardown stops it before copying the directory to R2, so the next spin-up loads the whole graph.

### Telemetry

`--telemetry-enabled=false`.

### Health

The image has no curl or wget, so the probe opens a TCP connection to Bolt. It shows that Memgraph is listening, not that a login works. Lab's probe requests its start page with Node.
