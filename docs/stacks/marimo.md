---
title: "Marimo"
---

## Marimo

![Marimo](https://img.shields.io/badge/Marimo-1C1C1C?logo=python&logoColor=white)

**Reactive Python notebook with SQL + Spark Connect support**

Marimo is a reactive Python notebook that's reproducible, git-friendly, and deployable as apps. Features include:
- Reactive execution — cells auto-update when dependencies change
- Git-friendly — notebooks stored as pure Python files (no JSON, no merge hell)
- SQL support — built-in DuckDB for local analysis, Spark SQL via Ibis for cluster work
- Spark Connect pre-wired — talk to the cluster via `sc://spark-connect:15002`, no JDK or full pyspark in the client
- Interactive UI elements — sliders, buttons, tables
- Deploy as web apps or scripts
- No hidden state — what you see is what you run

| Setting | Value |
|---------|-------|
| Default Port | `2718` |
| Suggested Subdomain | `marimo` |
| Public Access | No (contains notebooks/code) |
| Image | `nexus-marimo:latest-sql-spark` (custom, see `stacks/marimo/Dockerfile`) |
| Website | [marimo.io](https://marimo.io) |
| Source | [GitHub](https://github.com/marimo-team/marimo) |

## Spark Integration (Spark Connect)

When the Spark stack is also enabled, Marimo can run PySpark workloads against the cluster via the Spark Connect endpoint. Topology:

```
Marimo container (Python 3.13, no JDK)
   │ pyspark[connect] + Arrow + gRPC
   ▼ sc://spark-connect:15002
spark-connect container (driver-JVM)
   │ spark://spark-master:7077
   ▼
spark-master + spark-worker (executors)
```

The Marimo container is a thin gRPC client — the driver-JVM lives in the dedicated `spark-connect` service. This means **1 GiB memory is plenty for Marimo**, even for jobs that move large DataFrames; the heavy work happens server-side and only Arrow batches stream back.

### Quickstart

Four seed notebooks ship under `nexus_seeds/marimo/` and land in `/app/notebooks/<repo>/` on **first** Marimo container launch. The seeds live in the Forgejo workspace repo, and Marimo's entrypoint runs the `git clone` when `FORGEJO_REPO_URL` is set in its env — see [`stacks/marimo/docker-compose.yml`](../../stacks/marimo/docker-compose.yml)). On a Marimo-only install without Forgejo you'll see an empty `/app/notebooks/` directory and need to author your own notebooks via the UI. With Forgejo enabled, open from `https://marimo.<your-domain>` and hit **Run all** on whichever seed matches what you're trying to learn:

> **Upgrade note:** Marimo's entrypoint only clones the workspace repo when `/app/notebooks/<repo>/.git` is **absent** ([`stacks/marimo/docker-compose.yml`](../../stacks/marimo/docker-compose.yml)). On an existing workspace where Marimo was already running before a new seed shipped, `gh workflow run spin-up.yml` won't pull the new file in automatically — the repo dir already exists. Either run `git pull` from inside the Marimo notebook UI's terminal, or wipe the `marimo_data` volume and let the first-launch clone re-fetch (loses any local notebook edits). The new seeds DO appear in fresh stack deployments.


- **`Getting_Started_PySpark.py`** — minimal "spin up a SparkSession via Spark Connect, run a job, render results" walkthrough. Start here.
- **`Getting_Started_DuckDB.py`** — DuckDB walkthrough that doesn't need the Spark stack at all: in-memory queries, `range()` synthetic data, remote parquet over `httpfs`, aggregate + window functions, Polars/Pandas/PyArrow conversion, and Marimo's native `mo.sql()` reactive cell. Useful as a single-node analytics baseline before reaching for Spark.
- **`Getting_Started_PostgREST.py`** — REST-API walkthrough over the shared `postgres` stack via the PostgREST stack: list / filter / order / paginate / POST / PATCH / DELETE / OpenAPI. Stdlib-only (`urllib.request`), hits the internal `http://postgrest:3000` so no Cloudflare Access detour. Requires the PostgREST stack enabled.
- **`NYC_Taxi_Pipeline.py`** — end-to-end bootstrap-to-S3 + Spark-analytics pattern using DuckDB for the upload step and Spark for the read+aggregate.

The minimal pattern is:

```python
from _nexus_spark import get_spark
spark = get_spark()
df = spark.createDataFrame([("a", 1), ("b", 2)], ["k", "v"])
df  # auto-rendered as paginated mo.ui.table.lazy
```

The `_nexus_spark` helper (also seeded into the workspace, at `nexus_seeds/marimo/_nexus_spark.py`) caches a single SparkSession across cells and notebooks within the same Python process — see its docstring for details.

### Spark SQL via Ibis

Marimo's `mo.sql(...)` cells are DuckDB-first; for Spark SQL you wire them through Ibis:

```python
import ibis
con = ibis.pyspark.connect(spark)
df.createOrReplaceTempView("employees")

high_earners = mo.sql(
    "SELECT department, AVG(salary) FROM employees GROUP BY 1",
    engine=con,
)
```

### S3 / Hetzner Object Storage

Hadoop S3A config (`fs.s3a.endpoint`, access key, secret key) is set on the **spark-connect server** side via env vars in `stacks/spark/docker-compose.yml`. The Marimo container also gets `HETZNER_S3_BUCKET` so notebooks can build `s3a://${HETZNER_S3_BUCKET}/...` paths. Setting Hadoop conf on the Marimo client side via `SparkSession.builder.config(...)` is a no-op for Connect — the remote driver doesn't see client-side conf.

### Gotcha: cancelling long Spark jobs

Marimo's red **Stop** button does NOT interrupt blocking gRPC calls. A long Spark query started from Marimo will keep running on the cluster even after Stop is pressed (upstream issue [marimo-team/marimo#3494](https://github.com/marimo-team/marimo/issues/3494)).

To kill a runaway query:

1. Open the Spark Master UI at `https://spark.<your-domain>`
2. Find the running app (`Running Applications` table)
3. Click the `(kill)` link next to it

The gRPC stream then fails back to Marimo, which surfaces a clean `MarimoInterrupt` and the cell can be re-run.

### Reactivity vs. Spark state

Marimo's reactive DAG re-runs cells when their upstream changes. The `spark` session is module-level cached in `_nexus_spark.py`, so multiple cells importing it share one Connect channel — Marimo never re-creates the session.

But: Marimo does NOT track mutations to attributes. `spark.conf.set("spark.sql.shuffle.partitions", "4")` from one cell will NOT cause downstream cells to re-execute. **Treat the SparkSession as immutable after build.** If you need a different config, call `_nexus_spark.stop_spark()` and then `get_spark()` again — that's an explicit reset.

## Infisical secrets

Secrets stored in Infisical are auto-synced into the Marimo container's env on every spin-up. Reference them in notebook cells exactly as named in Infisical:

```python
import os
access_key = os.environ["R2_ACCESS_KEY"]
```

The sync writes to a dedicated `.infisical.env` file (not `.env`) so secret keys can't accidentally collide with Compose's `${VAR}` interpolation. Multi-line values (e.g. PEM keys) are skipped with a warning — they need a different transport mechanism (mount-as-file). The mechanism lives in `src/nexus_deploy/secret_sync.py`, run by the orchestrator's `secret-sync marimo` phase.

## Memory limits

| Container | Limit | Why |
|---|---|---|
| `marimo` | 1 GiB | gRPC client only, no driver-JVM. Plenty unless you pull huge `.toPandas()` results. |
| `spark-connect` | 1.5 GiB | Driver-JVM for ALL Connect clients. Bump if multiple notebooks run heavy queries concurrently. |
| `spark-worker` | 4 GiB | Executor — same as Jupyter setup. |

If a query OOMs, increase `stacks/spark/docker-compose.yml`'s `spark-connect` `deploy.resources.limits.memory`, NOT the Marimo container's.
