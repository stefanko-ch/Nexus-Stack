# `examples/`

Sample code that ships with Nexus-Stack and lands automatically in every freshly-provisioned user stack. The convention is intentionally narrow so contributors don't need to learn a new system every time they add a new starter file.

## What lives here

| Subtree | Purpose | Auto-seeded? |
|---|---|---|
| [`workspace-seeds/`](./workspace-seeds/) | Files that get committed into the user's Forgejo workspace repo on every spin-up | **Yes** — copied 1:1 by the orchestrator's seed phase after the workspace repo is created |

For now there is only `workspace-seeds/`. If we ever ship reference material that is *not* meant to land in the workspace repo (e.g. contributor recipes for adding a new stack), it gets a sibling directory like `examples/contributing/` and an explicit "**not** auto-seeded" note.

## How `workspace-seeds/` maps to the workspace repo

The directory layout under `workspace-seeds/` mirrors the **`nexus_seeds/`** subtree of the workspace Forgejo repo. Every path you have under `workspace-seeds/<...>` lands at `nexus_seeds/<...>` in the workspace repo (the prefix added in #501 to keep Nexus-Stack-managed files visually separated from user-managed content at the repo root):

Source tree under `examples/workspace-seeds/`:

```
examples/workspace-seeds/
├── kestra/
│   ├── flows/
│   │   ├── r2-taxi-pipeline.yaml          (NYC Yellow-Taxi parquet → R2 → DuckDB stats)
│   │   ├── http-fetch-to-r2.yaml          (single HTTP endpoint → R2 with date/hour partitioning)
│   │   └── parallel-http-fetch-to-r2.yaml (fan-out variant: multiple URLs in parallel → R2)
│   └── workflows/                  (when added — helper files: scripts, configs, SQL templates)
├── marimo/
│   ├── _nexus_spark.py             (Spark Connect helper — `from _nexus_spark import get_spark`)
│   ├── Getting_Started_PySpark.py  (seed Marimo notebook demonstrating PySpark + Spark SQL via Ibis)
│   ├── Getting_Started_DuckDB.py   (seed Marimo notebook walking through DuckDB: in-memory queries, remote parquet over httpfs, mo.sql native cells)
│   └── NYC_Taxi_Pipeline.py        (seed Marimo notebook: NYC TLC bootstrap to Hetzner S3 + Spark analytics — mirror of Kestra's r2-taxi-pipeline)
├── prefect/
│   ├── prefect.yaml                (deployment manifest — `pull:` re-clones workspace repo per run, no schedule by convention)
│   ├── requirements.txt            (boto3 + duckdb + httpx, installed at run-time by the worker)
│   └── flows/
│       └── nyc_green_taxi_pipeline.py  (NYC Green-Taxi parquet → R2 → DuckDB stats — Prefect counterpart to Kestra's r2-taxi-pipeline)
├── notebooks/                      (when added — Jupyter / code-server, .ipynb)
├── scripts/                        (when added — code-server, ad-hoc execution)
├── dbt/                            (when added — code-server, manual `dbt`)
└── sql/                            (when added — DuckDB, Trino, ClickHouse)
```

Mapping: every file `examples/workspace-seeds/<path>` is seeded to `nexus_seeds/<path>` in the workspace Forgejo repo (`nexus-<slug>-workspace/nexus_seeds/<path>`). For example:

- `examples/workspace-seeds/kestra/flows/r2-taxi-pipeline.yaml` → `nexus-<slug>-workspace/nexus_seeds/kestra/flows/r2-taxi-pipeline.yaml`
- `examples/workspace-seeds/notebooks/foo.ipynb` → `nexus-<slug>-workspace/nexus_seeds/notebooks/foo.ipynb`

The `nexus_seeds/` prefix keeps Nexus-Stack-managed files visually separated from the user's own course material at the workspace-repo root (introduced in #501; pre-existing repos that still have files at the root level continue to work but those files are orphaned — see migration notes below).

`system.flow-sync` (registered by the orchestrator's kestra-register phase) then syncs `nexus_seeds/kestra/flows/` into Kestra under target namespace `nexus-tutorials` with `includeChildNamespaces: true` — so `nexus_seeds/kestra/flows/r2-taxi-pipeline.yaml` lands at `nexus-tutorials.r2-taxi-pipeline`, and any future subdir like `nexus_seeds/kestra/flows/sub1/foo.yaml` extends to `nexus-tutorials.sub1.foo`.

This means any file you drop under `workspace-seeds/<dir>/<name>` will appear in every user's workspace at `nexus_seeds/<dir>/<name>` after the next Initial Setup. No code change, no new path.

### Migration note for pre-#501 workspace repos

Workspace repos created before #501 was merged have seed files at the repo root (`kestra/`, `marimo/`). Those root-level files are NOT auto-deleted on upgrade — `build_folder` (the Forgejo seed pusher) is create-only and the migration would risk overwriting user edits. After the upgrade:

- The new seeds appear at `nexus_seeds/<dir>/<file>` (e.g. `nexus_seeds/kestra/flows/r2-taxi-pipeline.yaml`).
- The old root-level copies become orphaned: Kestra's `system.flow-sync` only scans `nexus_seeds/kestra/flows/` now, and notebook stacks should be updated to look under `nexus_seeds/marimo/` etc.
- Operators can manually delete the orphaned root-level directories (`kestra/`, `marimo/`) when the team is ready.

## Subdirectory conventions

Top-level folders under `workspace-seeds/` are split in two:

- **Per-stack folders** (e.g. `kestra/`) — used when the seeded material is unambiguously tied to one Nexus-Stack and that stack expects to find it at a stack-specific path. Today only `kestra/` qualifies; other stacks are added in the same shape if/when the same need arises.
- **Per-consumer-type folders** (e.g. `notebooks/`, `dbt/`, `sql/`) — used when the same files are consumed by *several* stacks (notebooks are read by Jupyter + Marimo + code-server; SQL is run by DuckDB + Trino + ClickHouse). Promoting these into a single owning-stack folder would force a misleading attribution.

Stick to these names so the various services pick the files up correctly:

| Folder | Consumed by | What goes here |
|---|---|---|
| `kestra/flows/` | Kestra (via `system.flow-sync`, registered by the orchestrator) | Flow definitions in YAML. Files at `nexus_seeds/kestra/flows/<id>.yaml` register under namespace `nexus-tutorials`; subdirectories extend the namespace (`nexus_seeds/kestra/flows/sub1/<id>.yaml` → `nexus-tutorials.sub1`). |
| `kestra/workflows/` | Kestra (via `system.git-sync`, registered by the orchestrator) | Helper files referenced by flows: Python scripts, SQL templates, configs. **Not** flow definitions. |
| `marimo/` | Marimo (cloned from the workspace repo into `/app/notebooks/<repo>/nexus_seeds/marimo/`) | Marimo notebooks (plain `.py` files using `marimo.App` + `@app.cell`) plus the `_nexus_spark.py` helper that wires `SparkSession.builder.remote("sc://spark-connect:15002")`. Per-stack folder because Marimo's `.py` notebook format is incompatible with Jupyter `.ipynb` and the helper module is Marimo-specific. |
| `prefect/` | Prefect worker — TWO distinct clones: (a) the worker container's STARTUP `git clone` in `stacks/prefect/docker-compose.yml:88-89` populates `/flows/$REPO_NAME/` (only on first launch when the dir is absent — this is what the operator's `prefect deploy` reads); (b) the `pull:` step inside the seeded `prefect.yaml` reclones into a fresh tmpdir at flow-RUN time, but only for ALREADY-REGISTERED deployments. | Per-stack folder with the deployment manifest at `nexus_seeds/prefect/prefect.yaml` (operator runs `cd nexus_seeds/prefect && prefect deploy` to register the seeded deployments), `requirements.txt` (installed at run-time by `pip_install_requirements`), and `flows/<flow_name>.py` (the entrypoint files referenced from `prefect.yaml`'s `deployments:` block). |
| `notebooks/` | Jupyter, code-server (cloned from the workspace repo) | `.ipynb` notebooks (Jupyter) or `.py` scripts (code-server). NOT for Marimo notebooks — those go in `marimo/`. |
| `scripts/` | code-server, ad-hoc execution | Shell or Python helpers reused across notebooks. |
| `dbt/` | code-server, manual `dbt` invocation | A normal dbt project tree (`dbt_project.yml`, `models/`, etc.). |
| `sql/` | DuckDB, Trino, ClickHouse — anywhere SQL gets pasted | Stand-alone SQL files. |

If a new stack needs its own per-stack folder, add it under `workspace-seeds/<stack>/` and list it here. If a new consumer-type folder is needed (multiple stacks share it), add it as a top-level peer of `notebooks/` / `scripts/`.

## How seeding works

The orchestrator's `_phase_seed` (in `src/nexus_deploy/orchestrator.py`, delegating to `run_seed_for_repo` in `src/nexus_deploy/seeder.py`), after the workspace repo exists, walks every file under `examples/workspace-seeds/`, base64-encodes it, and POSTs it to the internal Forgejo API (`http://localhost:3202/api/v1/repos/<owner>/<repo>/contents/<path>`, accessed via SSH from the runner) with the relative path. `<owner>` is the Forgejo admin in the default workspace-repo case, or the user's Forgejo username in the GH_MIRROR_REPOS+user-fork case (`workspace_coords.py` resolves this and the pipeline passes it as `FORGEJO_REPO_OWNER`).

- HTTP **201/200** → file created. Counted as `SEEDED`.
- HTTP **422** → file already exists. Counted as `SKIPPED`. **Existing files are never overwritten** — user edits persist across re-deploys.
- Anything else → `FAILED`, logged as a warning.

Because seeds use `POST` (create-only) instead of `PUT` (upsert), the seed step is safe to re-run after every spin-up. The trade-off: when you publish a new version of a seed file in a Nexus-Stack release, users who already have the file get the old version. If you need to push an updated example, give it a new filename or version-suffix it.

## Rules for seeded files

### 1. No schedule triggers in seeded flows

Seeded Kestra flows under `workspace-seeds/kestra/flows/` **must not** declare `triggers:` blocks of type `Schedule` (cron) or any other auto-firing trigger.

**Why:**
- A seeded flow lands on every user stack.
- A schedule trigger then fires on N user stacks, multiplying upstream load (CloudFront downloads, Databricks Free-Edition quota burn, Redpanda traffic, R2 egress) by the cohort size.
- Examples are *teaching artifacts*. Users press **Execute** in the Kestra UI to run them; they shouldn't run silently in the background.

What's allowed instead:
- A `Webhook` trigger that requires explicit invocation. Fine.
- No `triggers:` block at all. Run manually from the UI.

If you genuinely need a system-level scheduled flow (e.g. a periodic data refresh that the platform itself depends on), don't put it under `workspace-seeds/`. Register it directly in `src/nexus_deploy/kestra.py` the way `system.flow-sync` is registered today — that's infrastructure, not a learning sample, and lives outside this directory.

### 2. Reference Infisical-managed secrets only via `{{ secret('NAME') }}`

The orchestrator's kestra-secret-sync phase (`src/nexus_deploy/secret_sync.py`) syncs every Infisical secret into Kestra on each spin-up: the values are base64-encoded and written as `SECRET_<NAME>=<base64>` env-var entries into a delimited block in `stacks/kestra/.env` (look for `BEGIN nexus-secret-sync` in the rendered remote script), then Kestra is `--force-recreate`d so its `EnvVarSecretProvider` picks them up at startup. Reference them in flows as `{{ secret('R2_ACCESS_KEY') }}`, `{{ secret('FORGEJO_TOKEN') }}`, etc. Never hardcode credentials in seed files — this directory is public on GitHub.

### 3. Idempotent if executed multiple times

A user may hit **Execute** on a seeded flow more than once. Ensure the flow either: detects pre-existing state and skips work (`if exists then continue`), or is naturally repeatable (overwriting outputs is fine). Don't accumulate side-effects on each run.

### 4. Filename suggests intent

Use kebab-case file names that convey what the example does at a glance: `r2-taxi-pipeline.yaml`, `databricks-warehouse-query.yaml`, `bluesky-firehose-ingest.yaml`. The flow's `id` field can match the filename minus `.yaml` for consistency.

## Adding a new example

1. Decide which subdirectory under `workspace-seeds/` it belongs in (table above). Stack-specific Kestra material → `kestra/flows/` (lands in namespace `nexus-tutorials`). Multi-consumer material → top-level `notebooks/` / `scripts/` / etc.
2. Add the file at the right relative path, e.g. `workspace-seeds/kestra/flows/redpanda-produce-consume.yaml` (lands in Kestra namespace `nexus-tutorials`) or `workspace-seeds/notebooks/exploring-r2.ipynb`.
3. Read the rules above.
4. Open a PR. CI doesn't validate the seeds at build time — but `.github/copilot-instructions.md` carries the no-schedule-trigger rule, so Copilot will flag PRs that violate it.
5. After merge, the next spin-up will land the file in every user's workspace repo. Existing users who already have files in the same path keep their version.

## What this directory is *not*

- **Not a place for one-off experiments.** Anything here ships to every user forever (until they delete it). Use a personal branch or your own Forgejo repo for throwaway experiments.
- **Not a substitute for documentation.** The companion docs at `docs/tutorials/` explain *why* and *how*; the examples are *what* you actually run. Keep both in sync when you add either.
- **Not a place for production-style infrastructure flows.** Those live in `src/nexus_deploy/kestra.py` (registered directly) or in a future `stacks/` extension.
