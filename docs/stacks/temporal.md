---
title: "Temporal"
---

## Temporal

![Temporal](https://img.shields.io/badge/Temporal-000000?logo=temporal&logoColor=white)

**Durable workflow execution engine**

Temporal runs workflows written as ordinary code — Python, Go, Java, TypeScript, .NET — and records the result of every step in its database. A worker that crashes halfway through a workflow is replaced, and the workflow continues from the last completed step instead of starting over. Retries, timeouts, heartbeats and sleeps that last for days are features of the platform rather than code you write.

It sits next to Prefect, Dagster and Kestra on purpose, and it is not a fourth pipeline scheduler. Those decide *when* a pipeline runs. Temporal makes one long-running process *reliable*: a saga that must compensate when step four fails, an approval that waits a week for a human, a backfill that must survive the worker being restarted halfway through.

**The workflow is durable; the side effects are at-least-once.** Temporal records an activity as done only once its result is back, so an activity whose worker dies mid-call — or which times out, or fails and is retried — runs again. For anything with an external effect that must not repeat, such as charging a card or sending an email, pass an idempotency key to the external system (the workflow ID plus the activity ID is the usual choice), or give that activity a retry policy with a maximum of one attempt — which still does not rule out a repeat when a worker dies after the effect but before reporting it, which is why the key is the real fix.

| Setting | Value |
|---------|-------|
| Host Port | `8107` — the Web UI (container port `8080`; host `8080` belongs to IT-Tools) |
| gRPC frontend | `temporal:7233` on `app-network`; on the host, `127.0.0.1:7233` only |
| Suggested Subdomain | `temporal` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [temporal.io](https://temporal.io) |
| Source | [GitHub](https://github.com/temporalio/temporal) |
| Docker images | [`temporalio/server`](https://hub.docker.com/r/temporalio/server), [`temporalio/ui`](https://hub.docker.com/r/temporalio/ui), [`temporalio/admin-tools`](https://hub.docker.com/r/temporalio/admin-tools) |
| Backing DB | Dedicated Postgres 17 (`temporal-db` container) |

### What runs

| Container | Image | Lifetime | Job |
|---|---|---|---|
| `temporal-db` | `postgres:17-alpine` | long-running | Databases `temporal` (executions, history) and `temporal_visibility` (what the UI lists and filters) |
| `temporal-schema-setup` | `temporalio/admin-tools` | one-shot | Creates both databases if missing and applies schema migrations |
| `temporal` | `temporalio/server` | long-running | The server, all four roles (frontend, history, matching, worker) in one process |
| `temporal-create-namespace` | `temporalio/admin-tools` | one-shot | Creates the `default` namespace if it does not exist |
| `temporal-ui` | `temporalio/ui` | long-running | The Web UI |

The two one-shot containers show as *Exited (0)* in `docker ps -a` after every start. That is them having finished, not failed.

Start order is enforced with `depends_on` conditions, and each step waits for the previous one to **succeed**: database healthy → schema job exits 0 → server healthy → namespace job exits 0 → UI. A failing one-shot therefore makes `docker compose up` itself fail, and the deploy reports it, rather than a server starting against a half-built schema. Measured by running the schema job against a wrong password: it exits 1 on `password authentication failed for user "nexus-temporal"`, and `docker compose up -d` exits 1 with `service "temporal-schema-setup" didn't complete successfully: exit 1`.

### Why not `temporalio/auto-setup`

Most tutorials, and the old `temporalio/docker-compose` repository, use `temporalio/auto-setup`, which did schema setup and namespace creation inside the server container on every start. Upstream deprecated it in the Temporal v1.30.1 release notes — *"will no longer receive updates"* — and has published no tag beyond `1.29.x`; `temporalio/docker-compose` is archived. There is no `auto-setup` image for the version pinned here.

The replacement upstream now ships in [`temporalio/samples-server/compose`](https://github.com/temporalio/samples-server/tree/main/compose) is the plain server image plus the same two steps run from `admin-tools` beforehand. That is the shape of this stack; the scripts are in `stacks/temporal/scripts/`.

Both scripts are safe to run on every start, which is how they run. Measured against `admin-tools:1.32.0` by running the full schema sequence twice against one database: `create` on an existing database exits 0, `setup-schema -v 0.0` logs *"Current database schema version 1.19 is greater than initial schema version 0.0. Skip version upgrade"*, and `update-schema` finds zero updates. The namespace job checks with `describe` first, so an existing `default` namespace — including any retention you changed — is left alone.

### Usage

1. Enable **Temporal** in the Control Plane → Spin Up.
2. Open `https://temporal.YOUR_DOMAIN` → Cloudflare Access email OTP → the `default` namespace's workflow list.
3. Write a worker and start a workflow from any container on `app-network` — a Jupyter or Marimo notebook, a code-server terminal. The SDK is not preinstalled; `pip install temporalio` first.

```python
import asyncio
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker


@activity.defn
async def greet(name: str) -> str:
    return f"Hello, {name}"


@workflow.defn
class HelloWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        return await workflow.execute_activity(
            greet, name, start_to_close_timeout=timedelta(seconds=10)
        )


async def main() -> None:
    # The in-cluster address. Not the public hostname: that goes through
    # Cloudflare Access and carries HTTP, not gRPC.
    client = await Client.connect("temporal:7233", namespace="default")
    async with Worker(
        client, task_queue="hello", workflows=[HelloWorkflow], activities=[greet]
    ):
        result = await client.execute_workflow(
            HelloWorkflow.run, "Nexus", id="hello-1", task_queue="hello"
        )
        print(result)


asyncio.run(main())
```

In a notebook, where an event loop is already running, `await main()` in a cell instead of `asyncio.run(main())`.

The run then appears in the Web UI with its full event history — every scheduled activity, its result, and the retries if there were any.

#### From a worker on your laptop

The tunnel carries the Web UI over HTTPS; it does not carry gRPC. The frontend is published on the server's loopback interface instead, so an SSH port-forward reaches it:

```bash
ssh -N -L 7233:localhost:7233 nexus
```

Then connect a local worker to `localhost:7233`. The deploy itself uses `ssh -N -L` through the same Cloudflare-tunnelled SSH connection (`src/nexus_deploy/ssh.py`), so forwarding is available on this path.

### Auth model

**Temporal has no login in this deployment, on either interface.**

- **The Web UI** supports OIDC, which is off by default and not configured here. Cloudflare Access at the edge is the only gate — the same model as Lakekeeper, Marquez and MLflow.
- **The gRPC frontend** accepts every client. Anything that can reach `temporal:7233` — which means **every container on `app-network`** — can start, signal, query, reset and terminate any workflow in any namespace.

That is acceptable for a teaching deployment where the stacks are a shared space already. It is not a place for workflows whose execution someone else must not be able to interfere with. Temporal's own answer is mTLS on the frontend plus an authorizer; neither is set up here.

Two consequences are enforced in code rather than left to convention:

- `temporal` is in `NO_OWN_AUTH` in `tests/unit/test_stack_conventions.py`, so it can never be given `tcp_ports` (a Hetzner firewall rule) or `public: true`.
- Both published ports bind to `127.0.0.1` only, checked by `test_temporal_publishes_every_port_on_loopback_only`. cloudflared reaches the UI over localhost either way, and the firewall is then not the single thing between an unauthenticated frontend and the internet (#742).

The Web UI needs no hostname configured. It calls its own server on the origin it was loaded from, and its CSRF middleware only consults the CORS allow-list for cross-site requests. Measured against a local stack: a terminate request with `Host`/`Origin` set to a public hostname and `Sec-Fetch-Site: same-origin` returned 200 and closed the workflow; the same request marked `cross-site` from another origin returned 403.

### Secrets

| Infisical folder | Key | What it is |
|---|---|---|
| `temporal` | `TEMPORAL_DB_USERNAME` | `nexus-temporal` — the Postgres role, not a login |
| `temporal` | `TEMPORAL_DB_PASSWORD` | generated by `random_password.temporal_db_password` |

The password reaches the stack as `TEMPORAL_DB_PASSWORD` in `stacks/temporal/.env`, written with mode `0600` by `_render_temporal`, which aborts the deploy if the value is empty. The compose file additionally reads it as `${TEMPORAL_DB_PASSWORD:?…}`, so a hand-run `docker compose up` without the file refuses to start.

### Persistence

What survives a teardown depends on the lifecycle mode ([Lifecycle](../concepts/lifecycle.md)):

| Lifecycle | Workflow history, running workflows, namespaces |
|---|---|
| `rebuild` (default) | **Lost.** `temporal-db` is not among the `s3_restore` targets (`standard_targets()` in `src/nexus_deploy/s3_restore.py`), so every spin-up starts with an empty database. The schema job rebuilds the schema and the namespace job recreates `default`. |
| `snapshot` | **Kept.** `temporal-db` stores its data at `/mnt/nexus-data/temporal/db` on the server's disk, which the Hetzner snapshot images. |

Under `rebuild`, a workflow that is sleeping or waiting for a signal when the teardown runs does not resume afterwards — it no longer exists. Workers reconnect fine; they simply find nothing to do. Plan long waits accordingly, or switch the deployment to the snapshot lifecycle.

### Dynamic config

`stacks/temporal/dynamicconfig/dynamicconfig.yaml` sets one value, `limit.maxIDLength: 255`. The PostgreSQL schema declares `workflow_id` and the other identifier columns as `VARCHAR(255)`, while the server's own default limit is 1000; without the cap an ID between 256 and 1000 characters passes the frontend's validation and fails at the insert. Same value upstream's samples-server PostgreSQL compose uses.

The server re-reads the file every 60 seconds, so a change there needs no restart.

### Upgrading

Temporal Server is upgraded **one minor version at a time**, moving to the newest patch of the current minor first, with the schema migrated before the new server starts ([upgrade guide](https://docs.temporal.io/self-hosted-guide/upgrade-server)). Skipping a minor can leave older data unreadable.

Here the migration is automatic: `temporal-schema-setup` runs `update-schema` from the admin-tools image before `temporal` starts. That only works if the two move together, so bump in one change:

1. `image:` and the `temporal-admin-tools` support image in `services.yaml` — same version
2. the `${IMAGE_TEMPORAL:-…}` and both `${IMAGE_TEMPORAL_ADMIN_TOOLS:-…}` fallbacks in `stacks/temporal/docker-compose.yml`

`test_compose_fallbacks_match_the_declared_version` catches a fallback that disagrees with `services.yaml`. **Nothing checks that the server and admin-tools versions match each other** — check it by hand. The UI (`temporalio/ui`) has its own version line and can move independently.

Upstream does publish minor tags (`1.32`); exact tags are used because a moving tag would change the running version on a re-pull without anyone deciding to upgrade. Under `rebuild` the one-minor-at-a-time rule matters less — the database starts empty on every spin-up — but a deployment on the snapshot lifecycle carries its data forward and must respect it.

### Troubleshooting

- **`docker ps -a` shows `temporal-schema-setup` or `temporal-create-namespace` as Exited (0)** — expected; both are one-shot jobs.
- **Exited (1) on `temporal-schema-setup`** — read `docker logs temporal-schema-setup`. `password authentication failed` on a deployment using the snapshot lifecycle means the database on disk was initialised with a different password than the current one; Postgres only applies `POSTGRES_PASSWORD` on first init.
- **Exited (1) on `temporal-create-namespace`** — its log prints the last error from `temporal operator namespace create` after 30 attempts, two seconds apart.
- **`Namespace default is not found`** from an SDK — the namespace job did not run to completion; check its log as above.
- **An SDK cannot connect to `https://temporal.YOUR_DOMAIN`** — expected. That hostname serves the Web UI over HTTPS through Cloudflare Access. Workers use `temporal:7233` inside the stack, or the SSH forward from a laptop.
- **The spin-up smoke check reports `temporal` on port 7233 as not an HTTP service** — expected: the check sends plain HTTP to every published port, and 7233 speaks gRPC. Measured locally, not yet on a server: the check's `curl` against it connects and exits 1, which the step files under "listening, not an HTTP service" rather than as a failure. If a server run classifies it differently, the port is still fine as long as `temporal` is healthy in `docker ps`.

### Related

- [Temporal documentation](https://docs.temporal.io) · [Python SDK](https://docs.temporal.io/develop/python)
- [kestra.md](./kestra.md), [prefect.md](./prefect.md), [dagster.md](./dagster.md) — the pipeline orchestrators in the same category. Reach for those to schedule data pipelines; reach for Temporal when a single long-running process must survive failure and pick up where it stopped.
