---
title: "Langfuse"
---

## Langfuse

![Langfuse](https://img.shields.io/badge/Langfuse-0A0A0A?logo=opentelemetry&logoColor=white)

**LLM observability: tracing, evaluations and prompt management**

Langfuse records what an LLM application actually did: every model call with its prompt, response, latency, token usage and cost, nested into traces you can step through. On top of that it offers scores and evaluations, datasets for experiments, and versioned prompt management.

| Setting | Value |
|---------|-------|
| Host Port | `3008` (the container keeps Langfuse's own default `3000`, which on the host belongs to Metabase) |
| Suggested Subdomain | `langfuse` |
| In-cluster URL | `http://langfuse:3000` (on `app-network`) |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [langfuse.com](https://langfuse.com) |
| Source | [GitHub](https://github.com/langfuse/langfuse) |
| Docker images | `langfuse/langfuse:3.225.7`, `langfuse/langfuse-worker:3.225.7` |
| Backing stores | Dedicated PostgreSQL 17, ClickHouse 26.3 LTS and Redis 7 |
| Blob storage | Cloudflare R2 data bucket, under the `langfuse/` prefix |

### What runs

| Container | Role | Memory limit |
|---|---|---|
| `langfuse` | Web UI and public API. Runs the PostgreSQL and ClickHouse migrations on every start, then the headless initialisation | 2 GiB |
| `langfuse-worker` | Consumes the ingestion queues and writes traces into ClickHouse; runs evaluations | 1.5 GiB |
| `langfuse-db` | PostgreSQL: users, organisations, projects, API keys, prompts | 512 MiB |
| `langfuse-clickhouse` | Traces, observations, scores | 2 GiB |
| `langfuse-redis` | Queues and caches | 384 MiB |

Together that is up to about 6.4 GiB, on a 16 GB server shared with every other enabled stack. Measured idle after start-up it is closer to 2 GiB. Enable it when you use it.

`langfuse-clickhouse` is not the [`clickhouse`](./clickhouse.md) stack, and the two do not share anything. That one is a general-purpose analytics database; this one holds a schema Langfuse owns and migrates itself.

Only `langfuse` joins `app-network`. The worker and the three stores sit on `langfuse-internal`, where nothing outside this stack can reach them.

### Usage

1. Enable **Langfuse** in the Control Plane → Spin Up.
2. Open `https://langfuse.YOUR_DOMAIN` → Cloudflare Access email OTP → the Langfuse login.
3. Sign in with the admin email and the password from Infisical (folder `langfuse`).

The first start creates, without anyone clicking through a wizard:

- an organisation **Nexus Stack** (id `nexus`),
- a project **Default** (id `nexus-default`),
- an API key pair for that project,
- the admin user, as owner of the organisation.

**Public sign-up is disabled** (`AUTH_DISABLE_SIGNUP=true`; a sign-up attempt answers `Sign up is disabled.`). Add further people from the organisation settings.

#### Sending traces

From a container on `app-network` — a notebook, a Kestra task, LiteLLM — use the in-cluster URL and the project key pair from Infisical:

```python
import os
from langfuse import Langfuse

langfuse = Langfuse(
    host="http://langfuse:3000",
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
)
```

Plain OpenTelemetry works too: the OTLP/HTTP endpoint is `http://langfuse:3000/api/public/otel`, authenticated with HTTP basic auth of `public_key:secret_key`.

**Not the public hostname.** `https://langfuse.YOUR_DOMAIN` sits behind Cloudflare Access, which answers an SDK with an HTML login page rather than an error the SDK understands. A client outside the server would need a Cloudflare Access service token; none is provisioned for this stack.

### Why Langfuse v3

Upstream's current major is v4. This stack pins **v3.225.7** on purpose, and the reason is compatibility rather than caution.

Langfuse v4's default write mode, `events_only`, rejects the legacy ingestion API. Measured on `4.36.0` with a `trace-create` event, the kind older SDKs send:

```
Event type "trace-create" is not accepted by /api/public/ingestion when
LANGFUSE_MIGRATION_V4_WRITE_MODE is events_only.
```

The Dify stack in this repository is on `1.13.0`, whose API declares `langfuse~=2.51.3` — exactly such a client. On v3, both the legacy API and OpenTelemetry ingestion were measured to work.

v4 does offer `dual` and `legacy` write modes that accept older clients, but its own upgrade guide says they will be removed in an upcoming major, and `dual` delays older SDKs' data by around fifteen minutes.

**v3 receives security patches until end of January 2027**, per upstream's v3-to-v4 upgrade guide. Moving to v4 before then is expected. Two things make it cheaper here than it would otherwise be:

- `langfuse-clickhouse` is already on 26.3, above v4's ClickHouse minimum of 25.12.
- On the rebuild lifecycle the databases are new on every spin-up (see [Persistence](#persistence)), so there is no data to migrate — the bump is the two image tags.

### Blob storage in R2

Langfuse needs S3-compatible storage for two things: every ingested event batch is written there before the worker processes it, and multimodal media (images, audio, attachments) lives there.

| Prefix | What |
|---|---|
| `langfuse/events/` | Raw ingestion payloads |
| `langfuse/media/` | Media referenced from traces |

The data bucket is shared — Lakekeeper, Unity Catalog and MLflow each own a prefix of their own — so Langfuse never writes outside `langfuse/`.

**Why R2 rather than a MinIO container in the stack.** Langfuse hands SDKs and browsers *presigned URLs* to upload and download media directly, so the storage endpoint must be reachable from outside the Docker network. R2's endpoint is. An in-stack MinIO would need a second public hostname, and that hostname would sit behind Cloudflare Access like every other, which a presigned upload cannot pass.

Langfuse builds its S3 client with `requestChecksumCalculation` and `responseChecksumValidation` set to `WHEN_REQUIRED` in its own code, so the `AWS_*_CHECKSUM_*` variables the MLflow stack sets are not needed here.

What has **not** been verified: media upload and preview against the live R2 bucket. The ingestion path was exercised end to end against S3-compatible storage locally, not against R2 itself. If media previews fail in the browser while traces work, check the browser console first: a CORS rejection from the R2 endpoint would point at the bucket's CORS rules, which this project does not manage. That is a candidate, not a diagnosis — it has not been observed.

### Auth model

Two layers, and both are on: Cloudflare Access at the edge, then Langfuse's own email-and-password login. Unlike MLflow, Langfuse cannot run without its own user management — traces belong to projects, and projects to organisations with members — so the second login is not optional.

API access uses the project key pair, not the admin password. Any container on `app-network` holding the key pair can write traces to the `Default` project and read them back.

### Secrets

Generated by OpenTofu in `tofu/stack/main.tf` and pushed to Infisical under folder `langfuse`:

| Key | What it is |
|---|---|
| `LANGFUSE_USERNAME` | The admin email — Langfuse signs in by email |
| `LANGFUSE_PASSWORD` | The admin password (`random_password.langfuse_admin`) |
| `LANGFUSE_PUBLIC_KEY` | Project API public key, `pk-lf-<uuid>` |
| `LANGFUSE_SECRET_KEY` | Project API secret key, `sk-lf-<uuid>` |
| `LANGFUSE_DB_USERNAME` / `LANGFUSE_DB_PASSWORD` | PostgreSQL role `nexus-langfuse` |
| `LANGFUSE_CLICKHOUSE_USERNAME` / `LANGFUSE_CLICKHOUSE_PASSWORD` | ClickHouse user `nexus-langfuse` |
| `LANGFUSE_REDIS_PASSWORD` | Redis `requirepass` |
| `LANGFUSE_NEXTAUTH_SECRET` | Signs session cookies |
| `LANGFUSE_SALT` | Salts hashed API keys |
| `LANGFUSE_ENCRYPTION_KEY` | 64 hex characters (`random_id.langfuse_encryption_key`, 32 bytes); upstream uses it to encrypt sensitive stored data |

R2 credentials are not Langfuse-specific; they come from the `r2-datalake` folder and reach the containers through the stack's `.env`, which is written with mode `0600`.

`_render_langfuse` in `src/nexus_deploy/service_env.py` refuses to write that file if any of the above is empty, if the encryption key is not 64 lower-case hex characters, if the admin email is empty, or if the R2 block is incomplete.

### Persistence

Langfuse is **not** in `s3_restore.standard_targets()`.

| Lifecycle | What survives a teardown |
|---|---|
| `rebuild` | Only the objects under `langfuse/` in R2. PostgreSQL, ClickHouse and Redis live in Docker named volumes on the server's disk and are destroyed with it. Every spin-up starts with an empty Langfuse, re-initialised with the current credentials. |
| `snapshot` | Everything: the named volumes are on the root disk, which the snapshot images. |

Two consequences worth knowing:

- **On `rebuild`, the event files in R2 outlive the traces that referenced them.** Nothing reads them again and nothing deletes them. They accumulate under `langfuse/events/` until removed by hand.
- **The initialiser never changes an existing user's password.** It creates the user only if the email is new. On `rebuild` the database is new each time, so the Infisical password always works. On `snapshot` the database comes back — if you change the admin password in the Langfuse UI, Infisical no longer knows it.

### ClickHouse memory

The `langfuse-clickhouse` container is limited to 2 GiB, and `stacks/langfuse/clickhouse-memory.xml` keeps ClickHouse well inside that:

| Setting | Value | Why |
|---|---|---|
| `max_server_memory_usage_to_ram_ratio` | `0.75` | ClickHouse reads the cgroup limit; measured, this yields a 1.5 GiB server cap under the 2 GiB limit, so a query fails with `MEMORY_LIMIT_EXCEEDED` before the kernel kills the server |
| `mark_cache_size` | 256 MiB | Upstream's default is sized for a dedicated server |
| `index_mark_cache_size` | 64 MiB | Same |
| `uncompressed_cache_size` | 0 | Off |

### Upgrading

The version appears in four places that must move together: `image` and `support_images.langfuse-worker` in `services.yaml`, and the two `${IMAGE_LANGFUSE…:-…}` fallbacks in `stacks/langfuse/docker-compose.yml`. `test_compose_fallbacks_match_the_declared_version` catches a mismatch between each pair; keep web and worker on the same version.

For v4, read upstream's v3-to-v4 upgrade guide first, and decide on a write mode before bumping — see [Why Langfuse v3](#why-langfuse-v3).

### Troubleshooting

- **`langfuse` keeps restarting, logs end in `JavaScript heap out of memory`** — the container's memory limit is below 2 GiB. Node sizes its heap from the cgroup limit, and at 1.5 GiB the web container crash-looped on start. Its healthcheck passes between crashes, so look at the restart count (`docker inspect langfuse --format '{{.RestartCount}}'`), not only the status.
- **Web healthy, worker `unhealthy`** — check `HOSTNAME: "0.0.0.0"` is still set. Without it the worker listens on the container's network address only and its loopback healthcheck is refused, while it otherwise works.
- **ClickHouse migrations fail on start** — check `CLICKHOUSE_CLUSTER_ENABLED` is still `false`. Upstream's default is `true`, which runs migrations `ON CLUSTER`, and upstream's configuration reference says to set it to `false` for a single-container setup like this one.
- **Login rejects the password from Infisical** — on the snapshot lifecycle, see [Persistence](#persistence): someone changed it in the UI.
- **An SDK reports HTML or a redirect instead of JSON** — it is using the public hostname. Use `http://langfuse:3000`.
- **Traces from an older SDK do not appear after a v4 upgrade** — the v4 default write mode rejects them; see [Why Langfuse v3](#why-langfuse-v3).

### Related

- [Langfuse self-hosting documentation](https://langfuse.com/self-hosting)
- [litellm.md](./litellm.md), [dify.md](./dify.md) — LLM stacks that can report to Langfuse; neither is wired to it yet
- [mlflow.md](./mlflow.md) — the other R2-backed stack with its own prefix. MLflow tracks ML training runs; Langfuse tracks LLM calls in a running application.
