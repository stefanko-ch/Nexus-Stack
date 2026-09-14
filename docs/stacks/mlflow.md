---
title: "MLflow"
---

## MLflow

![MLflow](https://img.shields.io/badge/MLflow-0194E2?logo=mlflow&logoColor=white)

**Experiment tracking and model registry**

MLflow records what a training run used and what it produced: parameters, metrics, artifacts, and the models worth keeping. It is the piece the notebook stacks in here were missing — Jupyter, Marimo, Spark, Dagster, Prefect and Kestra all existed with nowhere to log to.

| Setting | Value |
|---------|-------|
| Host Port | `5001` (the container keeps MLflow's own default `5000`; the host side is shifted because Meltano already binds `5000`) |
| Suggested Subdomain | `mlflow` |
| Public Access | No (Cloudflare Access via email OTP) |
| Website | [mlflow.org](https://mlflow.org) |
| Source | [GitHub](https://github.com/mlflow/mlflow) |
| Docker image | Custom build from [`ghcr.io/mlflow/mlflow`](https://github.com/mlflow/mlflow/pkgs/container/mlflow) — see [Why a custom image](#why-a-custom-image) |
| Backing DB | Dedicated Postgres 17 (`mlflow-db` container) |
| Artifacts | Cloudflare R2 data bucket, under the `mlflow/` prefix |

### Where the two halves live

A run is split across two stores, and both outlive the server:

| | Where | Survives a teardown because |
|---|---|---|
| Experiments, params, metrics, registry | `mlflow-db` (Postgres 17) | `s3_restore` dumps and restores it, like Lakekeeper's catalogue |
| Artifacts — plots, CSVs, models | R2 under `mlflow/` | R2 is outside the server entirely |

Artifacts are **proxied**, not handed out. `--serve-artifacts` routes every upload and download through the tracking server, so a notebook needs no object-storage credentials of its own — only this container holds them. That is also why the client half is so small: it never speaks S3.

### Usage

1. Enable **MLflow** in the Control Plane → Spin Up.
2. Open `https://mlflow.YOUR_DOMAIN` → Cloudflare Access email OTP → the UI.
3. From a notebook, `MLFLOW_TRACKING_URI` is already set, so nothing needs configuring:

```python
import mlflow

mlflow.set_experiment("housing-prices")
with mlflow.start_run():
    mlflow.log_param("degree", 2)
    mlflow.log_metric("rmse", 0.41)
    mlflow.log_artifact("./fit.csv")
```

The seeded notebook `nexus_seeds/marimo/Getting_Started_MLflow.py` walks through the whole loop including reading an artifact back, and `nexus_seeds/marimo/_nexus_mlflow.py` is a helper with a cached client and an idempotent `experiment()`.

**Always the in-cluster URL** — `http://mlflow:5000`, note the container port rather than the host-published 5001. Two separate things break the public hostname, and the second is the one that will fool you; see [Host-header validation](#host-header-validation).

### Host-header validation

MLflow 3.x rejects requests whose `Host` header it was not told to expect:

```
403 Invalid Host header - possible DNS rebinding attack detected
```

There is no hint in that message about what to change. The stack therefore passes both names it must answer to:

```
--allowed-hosts "mlflow:5000,${MLFLOW_DOMAIN}"
```

Two traps worth knowing before you touch that line:

1. **Setting `--allowed-hosts` replaces the built-in default, it does not extend it.** The `--help` text reads *"Default allows: localhost (all ports)"*, which invites the opposite assumption. Measured with the flag set as above: `mlflow:5000` → 200, `boeser.host` → 403, and **`localhost:5000` → 403**. Anything that must reach this server belongs in the list explicitly.
2. **This is deliberately not solved with `strict_host_check`.** That flag rewrites the header inside the tunnel and exists for origins that offer no way to allow a hostname — Evidence regenerates its vite config on every start. MLflow offers one, so per `CLAUDE.md` the flag is the wrong reach here, and using it would switch off a protection that works.

If you add another client under a different name — a second tunnel hostname, a reverse proxy — add it to `--allowed-hosts` or it gets a flat 403 from a server that is otherwise healthy.

### Why a custom image

The official `ghcr.io/mlflow/mlflow` image cannot run this configuration. Measured on `v3.16.0`:

```
mlflow           3.16.0
SQLAlchemy       2.0.52
alembic          1.19.1
psycopg2         missing     <- needed for --backend-store-uri postgresql://
boto3            missing     <- needed for --artifacts-destination s3://
```

As published it can only reach SQLite and a local directory, neither of which survives a teardown. `stacks/mlflow/Dockerfile` adds the two drivers and nothing else.

Note the tag form while you are there: `ghcr.io/mlflow/mlflow:3.16.0` does not exist — upstream prefixes releases with `v`.

### No setup hook

Unlike Lakekeeper, which needs a bootstrap call and a warehouse created over its management API, MLflow migrates its own schema on first start. Measured against an empty database: 59 tables plus the `alembic_version` row, with no intervention. There is no entry in `_HOOK_REGISTRY` and none is needed.

### The client is `mlflow-skinny`, not `mlflow`

Marimo and Jupyter install the tracking client only:

| | Size on the Marimo image |
|---|---|
| `mlflow-skinny==3.16.0` | **+78 MB** |
| `mlflow==3.16.0` | +465 MB |

Full MLflow declares `scikit-learn<2` and `scipy<2` as hard dependencies and pulls in matplotlib besides, because it bundles the server and the model flavours' training-time requirements. A notebook needs none of that to log a run.

What you give up is the *training* side of the model flavours: `mlflow.sklearn` imports, but there is no scikit-learn to build a model with. Logging params, metrics, artifacts, tags and registry entries all work. If a notebook genuinely needs to fit a model, add `scikit-learn` to `stacks/marimo/Dockerfile` explicitly rather than swapping in full MLflow — that keeps the 400 MB visible instead of hiding it inside a transitive dependency.

### Auth model

Cloudflare Access (email OTP) gates the UI at the edge. MLflow's own basic auth (`--app-name basic-auth`) is **off**, the same model as Grafana, Forgejo, Infisical and Kestra: students authenticate once via the OTP and land in the UI rather than hunting a second password in Infisical.

**The trade-off is larger here than for its neighbours, and worth stating plainly.** With artifact proxying on, any container on `app-network` can not only write to any experiment but also push objects into the R2 bucket through this server. There is no per-experiment permission and no attribution — every run looks the same regardless of who logged it.

That is acceptable for a teaching deployment where the stacks are already a shared space. It is not acceptable if you put something in here you would mind a classmate overwriting. Turning basic auth on is possible, and costs a second login plus credentials in every client's environment.

### Secrets

| Infisical folder | Key | What it is |
|---|---|---|
| `mlflow` | `MLFLOW_DB_USERNAME` | `nexus-mlflow` — the Postgres role, not a login |
| `mlflow` | `MLFLOW_DB_PASSWORD` | generated by `random_password.mlflow_db_password` |

R2 credentials are not MLflow-specific; they come from the `r2-datalake` folder and reach this container through its `.env`.

### Persistence

- `mlflow-db` keeps its data at `/mnt/nexus-data/mlflow/db`, a bind mount rather than a named volume so the snapshot lifecycle images it along with the other stateful stacks.
- `s3_restore` carries a `PostgresDumpTarget` for `mlflow-db`, so the rebuild lifecycle dumps it on teardown and restores it on spin-up.
- Artifacts need no backup — they are already in R2.

Restoring only one half leaves either orphaned objects in R2 or an empty experiment list pointing at files that still exist.

### Upgrading

The version appears in **three** places that must move together:

1. `FROM ghcr.io/mlflow/mlflow:vX.Y.Z` in `stacks/mlflow/Dockerfile`
2. `image:` in `services.yaml`
3. the `${IMAGE_MLFLOW:-…}` fallback in `stacks/mlflow/docker-compose.yml`

`test_compose_fallbacks_match_the_declared_version` catches 2 against 3. **Nothing catches 1**, so a bumped `services.yaml` with a stale `FROM` produces an image labelled with a version it does not contain. Check it by hand.

The client pin in `stacks/marimo/Dockerfile` and the `pip install` line in `stacks/jupyter/docker-compose.yml` should track the server version, though MLflow's client and server are compatible across minor releases.

### Troubleshooting

- **`403 Invalid Host header`** — see [Host-header validation](#host-header-validation). The name you connected under is not in `--allowed-hosts`.

  This also bites when debugging from the server itself: `curl http://localhost:5001/api/2.0/mlflow/experiments/search` sends `Host: localhost:5001`, which is not on the list. Pass a name that is, rather than widening the list:

  ```bash
  curl -H "Host: mlflow:5000" http://localhost:5001/api/2.0/mlflow/experiments/search?max_results=5
  ```

  `/health` is exempt from the check and answers 200 under any name — measured, and it is why the container's own healthcheck works without `localhost` being allow-listed.
- **The UI loads but a notebook cannot connect** — check the notebook is using `http://mlflow:5000` and not the public hostname. The public one goes through Cloudflare Access, which answers an API client with an HTML login page.
- **`ModuleNotFoundError: No module named 'sklearn'`** — expected; the client is `mlflow-skinny`. See [The client is mlflow-skinny](#the-client-is-mlflow-skinny-not-mlflow).
- **Runs are there but artifacts 404** — the artifact half is R2. Check the spin-up log for the `mlflow` stack's `.env`: an empty `R2_BUCKET` leaves `--artifacts-destination s3:///mlflow`, which the server accepts at startup and fails on at upload time.
- **Postgres restart-loops on first start** — an empty `MLFLOW_DB_PASSWORD`. `_render_mlflow` aborts the deploy with a message pointing at the `tofu apply` and Infisical sync rather than letting this happen, so seeing it means the env file was written by something else.

### Related

- [MLflow documentation](https://mlflow.org/docs/latest/index.html) · [self-hosting guide](https://mlflow.org/docs/latest/self-hosting/architecture/tracking-server)
- [marimo.md](./marimo.md) and [jupyter.md](./jupyter.md) — the two notebook stacks wired to this one
- [lakekeeper.md](./lakekeeper.md) — the other stack that pairs a dedicated Postgres with R2. Pick Lakekeeper for *table* data you want to query from several engines; pick MLflow for the record of *how* a result was produced. They are not alternatives.
