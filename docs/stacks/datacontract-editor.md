---
title: "Data Contract Editor"
---

## Data Contract Editor

![Data Contract Editor](https://img.shields.io/badge/Data_Contract_Editor-1E293B?logoColor=white)

**Write what a dataset promises, before anything enforces it**

A data contract states a dataset's schema, its owners, its quality guarantees and its service levels — in a file, reviewable like code. This editor writes them in the [Open Data Contract Standard](https://github.com/bitol-io/open-data-contract-standard) (ODCS) 3.2.0, the Linux Foundation specification maintained by the Bitol project, and lets you move between a form, a visual model and the raw YAML while it validates as you type.

It is the step before [Soda](./soda.md): describe the contract here, then let a check enforce it. And the step before [datacontract-api](./datacontract-api.md), which tests the contract against real data.

| Setting | Value |
|---------|-------|
| Host Port | `4173` |
| Suggested Subdomain | `datacontract-editor` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [github.com/datacontract/datacontract-editor](https://github.com/datacontract/datacontract-editor) |
| Docker image | [`datacontract/editor`](https://hub.docker.com/r/datacontract/editor), pinned |
| Persistence | None — nothing to restore, nothing to lose |
| Licence | MIT |

### Nothing to persist

The image is nginx serving a built single-page app: no database, no backend, no volume. A contract lives wherever you put it — the workspace repository, a Kestra flow, your laptop — not inside this container. That is why the stack has no `s3_restore` target and no `mem_limit` worth arguing about (128 MB).

The practical consequence: **save your work somewhere**. Closing the tab is closing the editor.

### The AI assistant is off, on purpose

The image ships an optional AI assistant, and this stack leaves `AI_ENABLED=false`. The reason is its default endpoint: upstream points `AI_ENDPOINT` at a hosted third-party API, so switching the assistant on without overriding it sends contract content off the server — schema, ownership and service-level detail, and on a teaching stack a student's coursework.

If you want it, point it at the stack's own LiteLLM proxy instead:

```yaml
environment:
  - AI_ENABLED=true
  - AI_ENDPOINT=http://litellm:4000/v1/chat/completions
  - AI_API_KEY=${LITELLM_MASTER_KEY}
  - AI_MODEL=gpt-4o
```

`litellm` is reachable over `app-network`, and its key is in Infisical under `/litellm` like any other service credential. Then the assistant runs against a model you chose, through a proxy you control.

Other documented variables: `AI_AUTH_HEADER` (`bearer` or `api-key`) and `CUSTOMIZATION_CONFIG`, a path to a mounted `customization.yaml`.

### Why there is no `strict_host_check`

Port 4173 is Vite's `preview` default, so this stack looks exactly like the case that flag exists for — a dev server that rejects the tunnel's `Host` header with `Blocked request. This host is not allowed.`

It is not that case. The image's final stage is `nginx:alpine-slim`, and its `nginx.conf` is `listen 4173;` with no `server_name` and an SPA fallback. nginx does not validate `Host`, so the flag would add a header rewrite nothing needs. The 11 MB image size is the other tell: there is no Node in it.

### Related

- [datacontract-api](./datacontract-api.md) — tests the contracts this editor writes
- [Soda](./soda.md) — data quality checks in SodaCL
- [OpenMetadata](./openmetadata.md) — catalogue, lineage and quality for the same assets
- [Apicurio Registry](./apicurio.md) — adjacent but different: versions Avro/Protobuf schemas, not ODCS contracts
