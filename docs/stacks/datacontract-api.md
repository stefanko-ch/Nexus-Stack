---
title: "Data Contract API"
---

## Data Contract API

![Data Contract API](https://img.shields.io/badge/Data_Contract_API-0F766E?logoColor=white)

**Does the data actually keep the promise the contract makes?**

The [Data Contract CLI](https://cli.datacontract.com/) checks a dataset against its ODCS contract: column types, nullability, uniqueness, row counts, freshness. It speaks Postgres, Trino, Iceberg, S3, Kafka, DuckDB, MySQL, Oracle, SQL Server, Snowflake, Databricks and BigQuery — which is most of what this stack already runs, so a contract can be tested against the warehouse next door rather than against a copy of it.

This is the other half of [datacontract-editor](./datacontract-editor.md): the editor writes the contract, this tests it.

| Setting | Value |
|---------|-------|
| Host Port | `4242` |
| Suggested Subdomain | `datacontract-api` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [cli.datacontract.com](https://cli.datacontract.com/) |
| Docker image | [`datacontract/cli`](https://hub.docker.com/r/datacontract/cli), pinned |
| API key | Infisical, `/datacontract/DATACONTRACT_API_KEY` |
| Persistence | None |
| Licence | MIT |

### Two ways to use one container

The container runs the API server, and because the CLI lives in the same image, both are available.

**From the browser** — `/` is a Swagger UI. Paste a contract, pick a server, run the test. Every request needs the API key as an `x-api-key` header; the Swagger UI has a field for it.

| Endpoint | Does |
|---|---|
| `GET /` | Swagger UI |
| `GET /openapi.json` | OpenAPI 3.1 document |
| `POST /test` | Runs the contract's tests against a server |
| `POST /export` | Converts a contract to another format (`?format=sql`, …) |
| `POST /changelog` | Lists what changed between two contract versions |
| `POST /breaking` | Grades those changes and returns `is_breaking` |

**From the shell** — the same pattern as the [Soda](./soda.md) stack. The container has a `datacontract-api-data` volume mounted at `/workspace`, which is also its working directory, so a contract has somewhere to live while you test it:

```bash
ssh nexus
docker cp contract.yaml datacontract-api:/workspace/
docker exec -it datacontract-api datacontract lint contract.yaml
docker exec -it datacontract-api datacontract test --server production contract.yaml
```

That volume is deliberately **not** in `s3_restore.standard_targets()`: it does not survive a rebuild teardown. It is a working surface, not storage — contracts belong in the workspace repository, where they are versioned and reviewed.

### The API key is not optional, and here is why

The stack sets `DATACONTRACT_CLI_API_ALLOW_PRIVATE_NETWORK=true`. That is the whole point of running the tool next to the data — a contract has to be testable against `postgres`, `trino`, `lakekeeper` and `minio`, all of which are private addresses on `app-network`.

It also means the service is, by design, something that will make requests to internal addresses on a caller's behalf. Cloudflare Access covers the public hostname; it does not cover the Docker network, where every other stack can reach port 4242 directly. So the key is what stands between the endpoints and any container on that network: a missing `x-api-key` is `401`, a wrong one `403`.

The deploy fails rather than starting without it. `src/nexus_deploy/service_env.py` raises if `DATACONTRACT_API_KEY` is empty, with a message pointing at `tofu apply` — because the alternative is a container that comes up looking healthy and answers `POST /test` to anything that asks.

### Credentials for the systems under test

Data source credentials arrive as `DATACONTRACT_<SOURCE>_*` environment variables, or per-request as `datacontract-*` headers. Neither is on disk in the container.

For a contract against the shared Postgres, the per-request header form keeps the stack's own `.env` free of a second copy of the warehouse password — the value is already in Infisical under `/postgres`.

### Connecting the editor to this service

The editor has a `TESTS_SERVER_URL` variable that points at this API, and its `tests.enabled` is hardcoded to `true` upstream. It is not wired up here, and the reason is worth recording rather than rediscovering:

- The editor is a single-page app, so the request comes from the **visitor's browser**, not from the editor's container. The URL therefore has to be the public `https://datacontract-api.<domain>`, not an `app-network` name.
- That hostname sits behind Cloudflare Access, and a cross-origin request to it from `datacontract-editor.<domain>` needs CORS configuration that this repository's per-service Access applications do not carry.
- And every endpoint here requires an `x-api-key` header. The editor has no variable for one — and if it had, the value would land in its browser-readable `config.json` ([datacontract-editor.md](./datacontract-editor.md)), which would hand the key to everyone who can open the editor.

So the two stacks are used side by side rather than wired together: write in the editor, test in the Swagger UI or over `docker exec`. Closing that gap means solving the CORS question and finding somewhere for the key that is not a public file — neither is a line of configuration.

### Related

- [datacontract-editor](./datacontract-editor.md) — writes the contracts this tests
- [Soda](./soda.md) — the other CLI-shaped quality tool, same `docker exec` pattern
- [OpenMetadata](./openmetadata.md) — catalogues the same assets; ODCS import/export needs a version bump ([#919](https://github.com/stefanko-ch/Nexus-Stack/issues/919))
