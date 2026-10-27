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

### The AI assistant is off, and turning it on is harder than it looks

This stack leaves `AI_ENABLED=false`. The obvious reason is the default endpoint: upstream points `AI_ENDPOINT` at a hosted third-party API, so switching the assistant on without overriding it sends contract content off the server — schema, ownership and service-level detail, and on a teaching stack a student's coursework.

The less obvious reason is where the configuration ends up. The image's `CMD` writes those variables into `config.json` **inside nginx's html root** (`/usr/share/nginx/html/config.json`), so the file is served like any other asset:

```
GET https://datacontract-editor.<domain>/config.json
```

**`AI_API_KEY` is therefore not a secret.** It is readable by anyone who can load the editor — on this stack, everyone on the Cloudflare Access allow-list. Never put `LITELLM_MASTER_KEY` there: [litellm.md](./litellm.md) calls it a root credential, and it can mint keys, change models and log into the UI as admin.

And the endpoint has to be one the **browser** can reach, because this is a single-page app — the request leaves the visitor's browser, not the server. `http://litellm:4000` is a Docker network name and resolves nowhere outside the host, so an in-stack endpoint simply does not work here.

What is left if you want the assistant:

- `AI_ENDPOINT=https://litellm.<domain>/v1/chat/completions` — the public hostname, which exists
- `AI_API_KEY` = a LiteLLM **virtual key** scoped to one model with a budget and an expiry ([litellm.md](./litellm.md)), never the master key, and accepting that everyone with Access can read it
- …and then a cross-origin request from `datacontract-editor.<domain>` to `litellm.<domain>` has to pass Cloudflare Access, whose per-service applications carry no CORS configuration in this repository

That last point is why the flag is off rather than documented as a recipe: the pieces exist, the path does not, and a documented recipe that fails at the preflight is worse than none.

Other documented variables: `AI_PROVIDER`, `AI_AUTH_HEADER` (`bearer` or `api-key`), `SCHEMA_URL`, `CUSTOMIZATION_CONFIG` (a path to a mounted `customization.yaml`), and `CONFIG_JSON` — which replaces the generated file with one you mount, and is the only way to keep a value out of the generated JSON.

### The Tests tab points at this stack's own API

Upstream hardcodes `tests.enabled` to `true` and ships `api.datacontract.com` as the default test server, so **Run Test** worked out of the box and sent the contract to a third party — no flag to switch on, no warning. This stack sets `TESTS_SERVER_URL` to its own [datacontract-api](./datacontract-api.md) instead.

The button will most likely error there, because the request is cross-origin from the browser to a hostname behind Cloudflare Access and the API wants an `x-api-key` the editor cannot send. That is the intended state while the gap is open: a failing test button rather than a quiet upload. [datacontract-api.md](./datacontract-api.md) has the three reasons and what closing them would take.

Validation, preview and the Diagram/Form/YAML views are unaffected — they run in the browser and need no server at all.

### Why there is no `strict_host_check`

Port 4173 is Vite's `preview` default, so this stack looks exactly like the case that flag exists for — a dev server that rejects the tunnel's `Host` header with `Blocked request. This host is not allowed.`

It is not that case. The image's final stage is `nginx:alpine-slim`, and its `nginx.conf` is `listen 4173;` with no `server_name` and an SPA fallback. nginx does not validate `Host`, so the flag would add a header rewrite nothing needs. The 11 MB image size is the other tell: there is no Node in it.

### Related

- [datacontract-api](./datacontract-api.md) — tests the contracts this editor writes
- [Soda](./soda.md) — data quality checks in SodaCL
- [OpenMetadata](./openmetadata.md) — catalogue, lineage and quality for the same assets
- [Apicurio Registry](./apicurio.md) — adjacent but different: versions Avro/Protobuf schemas, not ODCS contracts
