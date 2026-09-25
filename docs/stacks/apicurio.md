---
title: "Apicurio Registry"
---

## Apicurio Registry

![Apicurio](https://img.shields.io/badge/Apicurio-CE1126?logoColor=white)

**The place a data platform keeps its contracts**

Avro, Protobuf and JSON Schema for the streaming side; OpenAPI, AsyncAPI and GraphQL for the service side. Apicurio versions them, groups them, and can refuse a new version that breaks the old one.

| Setting | Value |
|---------|-------|
| Host Port | `8110` (the proxy; the registry keeps its own `8080` inside) |
| Suggested Subdomain | `apicurio` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [apicur.io/registry](https://www.apicur.io/registry/) |
| Source | [GitHub](https://github.com/Apicurio/apicurio-registry) |
| Backing DB | Dedicated Postgres 17 (`apicurio-db`) |

### It does not replace Redpanda's schema registry

Redpanda already serves a Confluent-compatible schema registry, and `kafka-ui` is wired to it — measured: `redpanda:8081/subjects` answers `200`. Nothing about that changes.

What Apicurio adds is breadth and governance. Redpanda's registry is a Kafka sidecar for Avro and Protobuf; Apicurio keeps OpenAPI and AsyncAPI documents too, groups artifacts, and enforces compatibility rules on new versions. It is the right place for a contract that outlives one topic.

It also speaks the Confluent-compatible API at `/apis/ccompat/v7`, so a producer written against Redpanda's registry can be pointed here without code changes.

### Four containers, and why

| Container | Role |
|---|---|
| `apicurio-proxy` | nginx — the only published port; serves the UI and forwards `/apis` to the registry |
| `apicurio-ui` | the web UI, a separate image since 3.x |
| `apicurio` | the REST API |
| `apicurio-db` | its own PostgreSQL |

The proxy is not decoration. In 3.x the UI is a **single-page app**: it reads `REGISTRY_API_URL` when its container starts, writes it into `config.js`, and the *browser* then calls that URL. Measured on the running stack:

```js
const ApicurioRegistryConfig = {
    "artifacts": { "url": "https://apicurio.example.com/apis/registry/v3" },
    ...
};
```

So the API has to be reachable from outside. An in-cluster address fails in every browser; a second hostname would mean a second Access application and cross-origin calls that then need CORS configured on the registry. One nginx in front makes the UI and the API same-origin, and neither problem exists.

### Usage

1. Enable **Apicurio Registry** in the Control Plane → Spin Up.
2. Open `https://apicurio.YOUR_DOMAIN` → Cloudflare Access email OTP → the registry UI.
3. Register a schema from anywhere on `app-network`:

```bash
curl -X POST http://apicurio:8080/apis/registry/v3/groups/default/artifacts \
  -H 'Content-Type: application/json' \
  -d '{"artifactId":"orders-value","artifactType":"AVRO",
       "firstVersion":{"content":{"content":"{\"type\":\"record\",\"name\":\"Order\",\"fields\":[{\"name\":\"id\",\"type\":\"long\"}]}","contentType":"application/json"}}}'
```

4. The same artifact then appears under the Confluent-compatible API, which is what Kafka tooling reads:

```bash
curl http://apicurio:8080/apis/ccompat/v7/subjects
["orders-value"]
```

### Storage, and what survives

Apicurio offers in-memory storage, and upstream says plainly that **"all data is lost when the container image is restarted"**. Every spin-up recreates containers here, so that option would leave the registry empty exactly when somebody needed it. This stack uses the SQL variant against its own PostgreSQL.

The database directory is a bind mount under `/mnt/nexus-data/apicurio/db`, so it survives a snapshot lifecycle. A rebuild teardown destroys the server; whether the schemas should be dumped to R2 alongside Forgejo's and MLflow's is a decision worth making deliberately rather than by default — see `s3_restore.standard_targets()`.

### Authentication

None of its own — Apicurio 3.x supports OIDC, and this stack does not configure it. Cloudflare Access is the gate on the browser route, as with every other stack here. Anything on `app-network` can call the API directly, which is what makes the `curl` examples above work from a notebook.

### Related

- [Redpanda](./redpanda.md) — ships its own Confluent-compatible registry for Kafka topics
- [AKHQ](./akhq.md), [Kafka UI](./kafka-ui.md) — both can browse a schema registry
- [Hoppscotch](./hoppscotch.md) — for exercising the OpenAPI documents kept here
