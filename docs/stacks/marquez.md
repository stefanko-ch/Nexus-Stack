---
title: "Marquez"
description: "OpenLineage reference backend — data lineage across the orchestrators in the stack"
---

# Marquez

![Marquez](https://img.shields.io/badge/Marquez-1F5C99?logo=apacheairflow&logoColor=white)

Marquez is the reference implementation of [OpenLineage](https://openlineage.io),
an open standard for describing what a data job read and wrote. It collects
those events and builds a graph you can query: this Kestra flow wrote that
table, which fed this dbt model, which backs that Superset dashboard.

It is the answer to two questions nothing else in this stack can answer:

- **Where did this table come from?** Walk the graph backwards through every
  job that touched it.
- **What breaks if I change it?** Walk forwards to every downstream dataset
  and dashboard.

## Configuration

| Setting | Value |
|---|---|
| Subdomain | `marquez.<your-domain>` |
| Host port | `3210` → container `3000` (web UI) |
| API | `http://marquez:5000` — internal only, on `app-network` |
| Admin port | `5001` — internal only, serves `/healthcheck` |
| Public | No — Cloudflare Access (email OTP) |
| Database | Dedicated PostgreSQL 16, not shared with any other stack |
| Search | Dedicated OpenSearch 2.19, internal only |

### Containers

| Container | Role |
|---|---|
| `marquez` | Dropwizard API. Ingests OpenLineage events, runs Flyway migrations on boot. |
| `marquez-web` | Serves the React UI **and** proxies `/api` to the backend, so the browser never contacts the API directly. |
| `marquez-db` | PostgreSQL holding the lineage graph. |
| `marquez-opensearch` | Backs fuzzy full-text search. Name and namespace search work without it, against PostgreSQL. |

Only `marquez-web` publishes a host port. The API stays on the internal
network because the producers that write to it — Kestra, Dagster, Spark —
all run in the same stack.

## Credentials

There is no user login. Marquez ships no user management; the Cloudflare
Access gate in front of the subdomain is the only authentication layer, the
same model [Lakekeeper](./lakekeeper.md) uses.

Two secrets are generated, both in Infisical under the `marquez` folder,
and neither is an account you sign in with:

| Secret | Used by |
|---|---|
| `MARQUEZ_DB_USERNAME` / `MARQUEZ_DB_PASSWORD` | the lineage PostgreSQL |
| `MARQUEZ_OPENSEARCH_USERNAME` / `MARQUEZ_OPENSEARCH_PASSWORD` | this stack's own OpenSearch |

The OpenSearch username is `admin` rather than a `nexus-` name, because
OpenSearch compiles that account name in and offers no way to change it
through configuration — the reasoning is in
[the OpenSearch stack doc](./opensearch.md#why-the-username-is-admin-and-not-nexus-opensearch).

The OpenSearch password is one of the few in this project generated with
special characters at all, and it is restricted to the three-character set
`-_.`. OpenSearch has validated `OPENSEARCH_INITIAL_ADMIN_PASSWORD`
since 2.12 and refuses to start without at least one uppercase letter, one
lowercase letter, one digit and one special character. The generator is
restricted to `-`, `_` and `.` so the value still means nothing to a shell,
a compose `.env` parser or a YAML scalar — which is why every other password
here avoids special characters in the first place.

## Sending lineage

Each of these already exists in the stack. Point them at
`http://marquez:5000` — that hostname resolves on `app-network`.

**Dagster** emits OpenLineage natively:

```python
# dagster.yaml
resources:
  openlineage:
    config:
      url: "http://marquez:5000"
```

**Spark** through the listener JAR:

```python
spark = (
    SparkSession.builder
    .config("spark.extraListeners", "io.openlineage.spark.agent.OpenLineageSparkListener")
    .config("spark.openlineage.transport.type", "http")
    .config("spark.openlineage.transport.url", "http://marquez:5000")
    .config("spark.openlineage.namespace", "nexus")
    .getOrCreate()
)
```

**dbt** through the wrapper from `openlineage-dbt`:

```bash
export OPENLINEAGE_URL=http://marquez:5000
export OPENLINEAGE_NAMESPACE=nexus
dbt-ol run
```

**Anything else** can POST the event directly, which is all the wrappers
above ultimately do:

```bash
curl -X POST http://marquez:5000/api/v1/lineage \
  -H 'Content-Type: application/json' \
  -d '{
        "eventType": "COMPLETE",
        "eventTime": "2026-01-01T00:00:00.000Z",
        "run":   {"runId": "d46e465b-d358-4d32-83d4-df660ff614dd"},
        "job":   {"namespace": "nexus", "name": "my-job"},
        "inputs":  [{"namespace": "nexus", "name": "raw.orders"}],
        "outputs": [{"namespace": "nexus", "name": "mart.orders"}],
        "producer": "https://example.com/my-tool"
      }'
```

A dataset appears in the UI as soon as one event names it. You do not
register anything in advance.

## Deliberate limitations

**The shipped config replaces the image's own.** `config/marquez.yml` is
bind-mounted and selected through `MARQUEZ_CONFIG`. The image's bundled
`marquez.dev.yml` hardcodes `user: marquez` / `password: marquez` and
substitutes only the database host and port from the environment, so there
is no way to reach the `nexus-` account convention or a generated password
without replacing the file. Keep the two in sync when bumping the image
version.

**amd64 only.** `marquezproject/marquez` publishes no arm64 manifest. The
servers have run x86 (`cx43`) since 2026-05, so this costs nothing in
deployment; it does mean the image needs emulation if you pull it onto an
Apple Silicon laptop to inspect it by hand.

## Debugging

```bash
# Is the API healthy? (admin port, not the application port)
ssh nexus "docker exec marquez wget -qO- http://localhost:5001/healthcheck"

# Did the migrations run?
ssh nexus "docker logs marquez 2>&1 | grep -i flyway"

# What has been recorded so far?
ssh nexus "docker exec marquez wget -qO- http://localhost:5000/api/v1/namespaces"

# Database reachable?
ssh nexus "docker exec marquez-db pg_isready -U nexus-marquez -d marquez"
```

A UI that loads but shows no data usually means no producer has sent an
event yet — check the emitting side rather than Marquez.

## Related

- [Issue #601](https://github.com/stefanko-ch/Nexus-Stack/issues/601) — the request this stack came from
- [OpenLineage](https://openlineage.io) — the standard
- [Dagster](./dagster.md), [Kestra](./kestra.md), [Spark](./spark.md) — producers already in the stack
- [OpenMetadata](./openmetadata.md) — catalog and discovery, complementary rather than overlapping: it describes what a dataset *is*, Marquez records what *happened* to it
