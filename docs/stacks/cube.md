---
title: "Cube"
---

## Cube

![Cube](https://img.shields.io/badge/Cube-FF6492?logoColor=white)

**Semantic layer — one definition of a metric, served to every tool**

Superset, Metabase and Evidence each carry their own idea of what "revenue" means. Three definitions drift three ways, and the first sign is usually two dashboards disagreeing in a meeting. Cube holds the definition once and serves it over SQL, REST and GraphQL, so the tools stop owning the arithmetic.

| Setting | Value |
|---------|-------|
| Host Port | `4001` (the container keeps Cube's own default `4000`; the host side is shifted because LiteLLM already binds `4000`) |
| Suggested Subdomain | `cube` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [cube.dev](https://cube.dev) |
| Source | [GitHub](https://github.com/cube-js/cube) |
| Docker images | [`cubejs/cube`](https://hub.docker.com/r/cubejs/cube) + [`cubejs/cubestore`](https://hub.docker.com/r/cubejs/cubestore), pinned in lockstep |
| Data source | The shared `postgres` stack |
| Data model | `stacks/cube/model/` in this repository, mounted read-only |

### The two containers

| Container | Role |
|---|---|
| `cube` | The SQL, REST and GraphQL APIs |
| `cube-store` | Cube's own storage layer: cache, query queue, and materialised pre-aggregations |

`cube-store` is not optional, and that is upstream's position rather than a guess: *"While Cube can operate with in-memory cache and queue storage, there're multiple parts of Cube which require Cube Store in production mode."*

### There is no Playground, and that is deliberate

Cube's Playground — the click-together UI most tutorials start with — is served only in development mode. Upstream is explicit about what that mode is:

> "Development mode is an authentication bypass … switches off JWT verification on the REST (JSON) and GraphQL APIs."
>
> "Use it only on a local development machine, never in production."

Running it here would mean any container on `app-network` could query the API with no token at all, on a server that also hosts CI. Cloudflare Access guards the browser route and never sees in-cluster traffic, so it would not help.

So this stack runs with `CUBEJS_DEV_MODE=false`. What you get instead is a token-authenticated API and a data model that lives in version control. To click a model together, run Cube on your laptop in development mode — which is exactly what upstream recommends it for; `stacks/cube/model/README.md` has the one-line command.

### Authoring the data model

The model is `stacks/cube/model/*.yml` **in this repository**, mounted read-only into the container. `stack-sync` copies it to the server on every spin-up.

1. Add or edit a `.yml` file under `stacks/cube/model/`.
2. Commit it — a metric definition is reviewed like any other change.
3. Spin up. Cube reads the model when its container starts.

`example.yml` shows the shape and is commented out on purpose: it references a table that does not exist on a fresh stack, and Cube refuses to start when a model points at a missing one.

Nothing here needs backing up, and a teardown loses nothing: the semantic layer is in git, not in a volume.

### Querying it

The API expects a JWT signed with `CUBE_API_SECRET`, which OpenTofu generates and publishes to Infisical under `/cube`. Mint one wherever you like — from code-server, for example:

```python
import jwt, datetime  # PyJWT

token = jwt.encode(
    {"exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)},
    "<CUBE_API_SECRET from Infisical>",
    algorithm="HS256",
)
```

Then:

```bash
curl -H "Authorization: $TOKEN" \
  "https://cube.YOUR_DOMAIN/cubejs-api/v1/load?query={\"measures\":[\"orders.revenue\"]}"
```

BI tools connect to the **SQL API** with the same secret. The token is not a login — Cube has no user management, and Cloudflare Access is what keeps people out of the browser route.

### What survives a teardown

| | Where | Survives |
|---|---|---|
| Data model | `stacks/cube/model/` in git | yes — it is never only on the server |
| Cache, queue, pre-aggregations | `cube-store-data` volume | no, and deliberately: all of it is derived from the warehouse and rebuilds itself |

### Why `cube-store` is amd64-only, and what that means

Every other image in this catalogue is multi-arch. `cubejs/cubestore` publishes **amd64 only** for its release tags (there is a separate `-arm64v8` build tag and `-non-avx` variants for CPUs without AVX).

Nexus-Stack has run on x86 `cx43` servers since 2026-05, so this satisfies the requirement in `CLAUDE.md` — the image must support `linux/amd64`. Two practical consequences:

- a contributor on Apple Silicon cannot run `cube-store` locally without emulation;
- Cube Store needs AVX. Hetzner's Intel instances have it; on a CPU without it the container fails at startup rather than degrading quietly, and the `-non-avx` tags exist for exactly that case.

### Rehearsed before it shipped

Both containers were run locally against a probe PostgreSQL on 2026-09-23, with the stack's own compose file. Two defects turned up that no test would have caught:

| Check | Result |
|---|---|
| `cube` starts with an effectively empty model directory | `🚀 Cube API server (1.7.42) is listening on 4000`, `/cubejs-api/v1/meta` → `{"cubes":[]}` |
| Request with no token | **403** `{"error":"Authorization header isn't set"}` |
| Token signed with the wrong secret | **403** `{"error":"Invalid token"}` |
| Token signed with `CUBE_API_SECRET` | **200** |
| Healthcheck | first draft used `curl`; the image has **neither curl nor wget**, so the container sat permanently `unhealthy` with `curl: not found`. Now probed with `node`, and the container reports `healthy` |
| Cube Store's data | first draft mounted the volume at `/cube/data` while the default data directory is `/cube/.cubestore`, so the metastore lived in the container layer and a recreate would have discarded it. `CUBESTORE_DATA_DIR` is now declared, and the volume holds the state |

What is still untested is a spin-up on a real server, which is what settles whether the tunnel, Access and the shared Postgres behave as expected.

### Configuration

| Variable | Source | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | the shared `postgres` stack's secret | Cube's connection to the warehouse (`CUBEJS_DB_PASS`) |
| `CUBE_API_SECRET` | `random_password.cube_api_secret` → Infisical `/cube` | signs and verifies API tokens |

Both are guarded at render time: if either is empty, the deploy stops with a message naming the missing value rather than starting a semantic layer that cannot reach the warehouse it exists to describe.

### Related

- [Superset](./superset.md), [Metabase](./metabase.md), [Evidence](./evidence.md) — the tools that consume the model
- [PostgreSQL](./postgres.md) — the data source
- [code-server](./code-server.md) — ships dbt, which is where the tables Cube describes usually come from
