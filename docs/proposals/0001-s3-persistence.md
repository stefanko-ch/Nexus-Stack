# RFC 0001 — S3-Backed Persistence (Cloudflare R2)

> **Naming note (superseded):** this RFC was written while Gitea held the
> internal forge role. Forgejo took that role over later; wherever this
> document says `gitea`/`gitea-db`, the running system now uses
> `forgejo`/`forgejo-db`, and the workspace repo is
> `nexus-<slug>-workspace`. The design itself is unchanged.
**Status:** Draft
**Author:** sk@stefanko.ch
**Date:** 2026-05-10 (rev. 2026-05-11 — storage provider switched from Hetzner Object Storage to Cloudflare R2)
**Target version:** v1.0.0 (breaking change)

## tl;dr

Replace the per-stack Hetzner Block Storage volume with **Cloudflare R2** as the canonical persistence layer. On `spinup`, restore from R2 to local SSD; on `teardown`, snapshot back to R2, then destroy infra. This eliminates the volume-location lock-in that today wedges every stack to a single Hetzner DC, surfaces dramatically during EU stock crunches (root cause of the 2026-05-10 Hetzner OOS incident).

**Why R2** (revised from earlier Hetzner Object Storage proposal): the project already uses R2 — the Tofu state backend lives in R2 (`scripts/init-r2-state.sh`, `tofu/backend.hcl`), the Cloudflare provider is already configured for DNS / Tunnel / Access. Adding an R2 *persistence* bucket per stack reuses the existing R2 token, the existing Cloudflare provider, and ships with no EU lock-in + zero egress fees. The Hetzner-Object-Storage path explored in the previous revision of this RFC would have introduced a parallel storage system, parallel credential handling, and a per-region egress cost when non-EU compute pulls the snapshot. R2 doesn't have any of those problems.

## Motivation

### The current wedge

Every Nexus-Stack instance has one persistent Hetzner Block Storage volume mounted at `/mnt/nexus-data/`. The volume is created once at control-plane setup and pinned to the location configured at the time (`server_location` in `tofu/control-plane/variables.tf` — current repo default is `hel1`, but the stacks affected by the 2026-05-10 incident were originally provisioned when the default was `fsn1`). On every spinup the server is provisioned and the existing volume is attached.

Hetzner enforces: **server and volume must be in the same location**. Volumes are **not migratable** between locations.

Today (2026-05-10) Hetzner Falkenstein went out of stock for every server type we tried (cx43, cpx41, cx42, cx52). Capacity exists at hel1, nbg1, ash, hil, sin — but no fsn1 volume can be attached to any of those. Result: 26 student stacks completely wedged for hours, no graceful fallback.

### The architectural fix

Move all persistent data to Cloudflare R2. Server local SSD becomes ephemeral cache. Spinup-anywhere becomes possible because the server has no location-locked dependency, AND because R2 is region-agnostic (single global namespace, automatic edge replication, zero egress fees — the server pulls the snapshot at full speed from wherever it landed).

### What this is NOT

- Not a backup solution (though it gets you one for free). Recovery from R2 is the *primary* path, not a fallback.
- Not Postgres-on-R2. Postgres needs POSIX semantics and stays on local SSD, but its **dump** lives on R2.
- Not a data-residency commitment beyond what R2 itself offers. R2 stores objects in the Cloudflare data centre closest to the bucket's selected jurisdiction. v1.0 sets the persistence bucket's `location` to `EEUR` (Cloudflare's "Eastern Europe" hint) as a **new explicit constraint** on this bucket — the project's existing R2 buckets (Tofu state, data-lake) don't set a jurisdiction and use R2's default. For the tutorial/class-stack data we ship, the EEUR pin is fine; if a future workload needs a stricter pinned-region guarantee, R2's jurisdiction API supports that natively. Operators may set `location` differently per their data-residency needs.

## Goals

1. **Eliminate Hetzner volume location lock-in.** A spinup must succeed in any Hetzner location that has compute stock — there's no more compute-location dependency on a specific volume's pin. R2 being region-agnostic with zero egress means non-EU compute (ash, hil, sin) is just as cheap as EU compute to pull the snapshot from — no cross-region surcharge to worry about (the worry that pushed the previous revision of this RFC toward EU-only as a default). Operators can keep `SERVER_PREFERENCES` EU-only for latency reasons, but the architecture itself doesn't push them in that direction.
2. **Preserve all student-visible state across teardown→spinup cycles** (Gitea repos, Postgres data, Dify uploads, Weaviate vectors).
3. **Atomic teardown.** A teardown that fails to upload to S3 must abort, not destroy infra. No "half-saved" state.
4. **Acceptable spinup overhead.** Adding S3-restore should not extend spinup beyond +5 minutes vs. today.
5. **Clean migration for existing 26 stacks.** No data loss; one-time evacuation script that runs against current volumes before they're decommissioned.

## Non-goals

- Real-time replication (streaming changes to S3 on every write). Snapshot-based suffices for the "scheduled teardown / class-end" pattern.
- Per-second RPO. RPO is "since last teardown" (typically nightly). Acceptable for a class environment.
- Encryption at rest beyond what R2 provides natively (R2 encrypts every object at rest with AES-256 by default; we don't add envelope encryption in v1).
- Migrating away from Postgres entirely. We keep the existing Postgres containers, just move their dump (not their live data) to S3.

## Current architecture

### Volume layout (today)

```
/mnt/nexus-data/                      ← Hetzner Volume (fsn1, immutable location)
├── gitea/
│   ├── repos/                         Git repos: nexus_seeds + student-pushed code
│   ├── lfs/                           Git LFS files
│   └── db/                            Gitea Postgres data dir
└── dify/
    ├── storage/                       Dify uploaded files (knowledge bases)
    ├── db/                            Dify Postgres data dir
    ├── weaviate/                      Vector DB files
    ├── plugins/                       Installed Dify plugins
    └── redis/                         Redis dump (ephemeral, regeneratable)
```

### Current spinup flow

```
1. select-capacity:  pick (server_type, location) honoring SERVER_PREFERENCES
2. tofu apply:       provision server + attach existing volume by ID
                     ← FAILS HERE if server.location ≠ volume.location
3. cloud-init:       mount volume at /mnt/nexus-data
4. compose-runner:   docker compose up (services bind-mount /mnt/nexus-data/...)
```

### Current teardown flow

```
1. tofu destroy:     server + tunnel + DNS + access apps
                     volume is RETAINED — but NOT via `lifecycle
                     { prevent_destroy = true }`. The mechanism is
                     simpler: the volume resource lives in the
                     `tofu/control-plane/` state, and the teardown
                     workflow only runs `tofu destroy` against
                     `tofu/stack/` (the per-spinup state file).
                     Since the volume isn't part of that state, it's
                     never considered for destruction.
```

The volume sits idle costing ~€0.50/month per stack until next spinup.

## Proposed architecture

### Storage layout

```
Cloudflare R2 (per-stack bucket, R2 jurisdiction set to EEUR — see Bucket
provisioning below; this is a new constraint on the persistence bucket,
not inherited from the existing Tofu-state bucket which uses R2's default
jurisdiction):
  s3://nexus-<class>-<user>-internal/
    ├── snapshots/
    │   ├── latest.txt                    ← single-line pointer to the active
    │   │                                   timestamp; updated only AFTER the
    │   │                                   verify gate passes
    │   └── <ISO8601-timestamp>/
    │       ├── manifest.json             ← slim metadata: stack, timestamp,
    │       │                               template version (rich per-
    │       │                               component checksums are a v1.1
    │       │                               extension; v1.0 trusts rclone's
    │       │                               per-object hash check for
    │       │                               integrity)
    │       ├── postgres/
    │       │   ├── gitea.dump.gz         ← pg_dump -F c | gzip (custom binary)
    │       │   └── dify.dump.gz
    │       ├── gitea/
    │       │   ├── repos/                ← rsync mirror (excluding .lock + db/)
    │       │   └── lfs/                  ← rsync mirror
    │       └── dify/
    │           ├── storage/              ← rsync mirror
    │           ├── weaviate/             ← rsync mirror
    │           └── plugins/              ← rsync mirror

Retention is enforced by R2's built-in object versioning + lifecycle
policy (30-day NoncurrentVersionExpiration on the ``snapshots/`` prefix
in v1.0). No dedicated ``_versioning/`` subdirectory; the prior diagram
inherited that note from the earlier Hetzner-Object-Storage revision and
was inaccurate.

Note: `gitea/db/` and `dify/db/` (Postgres data directories) and
`dify/redis/` (ephemeral cache) are **excluded** from the sync.
Postgres state is captured via `pg_dump` into the `postgres/`
directory above; Redis state is regeneratable on spinup. There's
no `--exclude` flag involved — the on-server bash in
`s3_persistence.py:render_snapshot_script` enforces the exclusion
structurally by only walking the explicitly-listed `RsyncTarget`
subdirectories (gitea/repos, gitea/lfs, dify/storage,
dify/weaviate, dify/plugins). Anything outside that list, db/ and
redis/ included, never reaches a rclone-sync call in the first
place. (An earlier RFC revision mentioned `rsync --exclude=…` here,
which was both the wrong tool name and an incorrect syntax — the
project uses `rclone sync` throughout.)

Server local SSD (ephemeral, recreated on every spinup):
  /var/lib/nexus-data/
    ├── gitea/                            ← restored from S3 on spinup (repos/, lfs/ only)
    ├── dify/                                                          (storage/, weaviate/, plugins/ only)
    └── postgres-bootstrap/               ← scratch dir for pg_restore (dump files staged here, then piped via gunzip | pg_restore)
```

`/mnt/nexus-data/` symlink points to `/var/lib/nexus-data/` for backward-compat with existing docker-compose paths.

### New spinup flow

```
1. select-capacity:    pick (type, location) — no volume constraint, full SERVER_PREFERENCES list valid
2. tofu apply:         provision server (no volume attachment).
                       The per-stack R2 bucket already exists from
                       control-plane setup (see "Code changes →
                       tofu/control-plane/main.tf" — the bucket
                       resource lives in control-plane state, not
                       stack state, so it's NOT created or
                       destroyed on each spinup/teardown cycle —
                       same lifecycle pattern as the volume it
                       replaces).
3. cloud-init / setup:
   a. mkdir -p /var/lib/nexus-data
   b. ln -sfn /var/lib/nexus-data /mnt/nexus-data    (back-compat symlink:
                                                      existing docker-compose
                                                      bind-mounts under
                                                      /mnt/nexus-data resolve to
                                                      the new SSD-local location
                                                      without docker-compose
                                                      changes)
   c. Read s3://<bucket>/snapshots/latest.txt → $TIMESTAMP
      (single-line pointer; first-time spinup → file missing →
      skip the rest of step 3 and proceed with empty data dirs)
   d. rclone sync s3://<bucket>/snapshots/$TIMESTAMP/gitea/repos    → /var/lib/nexus-data/gitea/repos
      rclone sync s3://<bucket>/snapshots/$TIMESTAMP/gitea/lfs      → /var/lib/nexus-data/gitea/lfs
      rclone sync s3://<bucket>/snapshots/$TIMESTAMP/dify/storage   → /var/lib/nexus-data/dify/storage
      rclone sync s3://<bucket>/snapshots/$TIMESTAMP/dify/weaviate  → /var/lib/nexus-data/dify/weaviate
      rclone sync s3://<bucket>/snapshots/$TIMESTAMP/dify/plugins   → /var/lib/nexus-data/dify/plugins
      rclone copy s3://<bucket>/snapshots/$TIMESTAMP/postgres/      → /tmp/nexus-restore/postgres/
      (each rsync goes against the explicit subdirectory under
      snapshots/<timestamp>/; db/ and redis/ are NOT in the
      snapshot so they're implicitly excluded)
   e. start docker compose for postgres containers (gitea-db, dify-db) on EMPTY data dirs
   f. gunzip -c /tmp/nexus-restore/postgres/gitea.dump.gz \
        | docker exec -i gitea-db pg_restore -U <user> -d gitea --no-owner --no-acl
   g. gunzip -c /tmp/nexus-restore/postgres/dify.dump.gz \
        | docker exec -i dify-db pg_restore -U <user> -d dify --no-owner --no-acl
4. compose-runner:     docker compose up for the rest of the stack
```

**Postgres dump format**: ``pg_dump -F c | gzip`` (custom binary
format, gzipped) on snapshot, ``gunzip | pg_restore`` on spinup.
Plain SQL output (``pg_dump -F p``) would only round-trip through
``psql``, which doesn't support the ``--clean --no-owner --no-acl``
options we use for cross-version restores. The implementation in
``s3_persistence.py:render_snapshot_script`` and
``render_restore_script`` uses the custom format end-to-end.

### New teardown flow (atomic)

```
1. pre-snapshot:       docker compose stop on app services (Gitea web,
                       Dify api/web) + Postgres exec CHECKPOINT to flush
                       WAL. We deliberately do NOT use `docker compose
                       pause` (cgroup-freezer SIGSTOP is hard-stop, not
                       drain — in-flight HTTP requests die mid-write).
                       The compose stop with default 10s timeout gives
                       app processes time to finish in-flight requests
                       and close DB connections cleanly.
2. dump postgres:
   a. docker exec gitea-db pg_dump -F c -U <user> <db> | gzip > /tmp/dumps/gitea.dump.gz
   b. docker exec dify-db  pg_dump -F c -U <user> <db> | gzip > /tmp/dumps/dify.dump.gz
3. rsync-to-s3 — every destination is **under the timestamped
   ``snapshots/<timestamp>/`` prefix** (matches the storage-layout
   section above; the bare ``s3://<bucket>/gitea/...`` form in
   earlier RFC revisions was a path-mismatch bug). Only the
   intended subdirectories — db/ and redis/ never reach S3:
   a. rclone sync /var/lib/nexus-data/gitea/repos    → s3://<bucket>/snapshots/<timestamp>/gitea/repos
   b. rclone sync /var/lib/nexus-data/gitea/lfs      → s3://<bucket>/snapshots/<timestamp>/gitea/lfs
   c. rclone sync /var/lib/nexus-data/dify/storage   → s3://<bucket>/snapshots/<timestamp>/dify/storage
   d. rclone sync /var/lib/nexus-data/dify/weaviate  → s3://<bucket>/snapshots/<timestamp>/dify/weaviate
   e. rclone sync /var/lib/nexus-data/dify/plugins   → s3://<bucket>/snapshots/<timestamp>/dify/plugins
   f. rclone copy /tmp/dumps/                        → s3://<bucket>/snapshots/<timestamp>/postgres/  (gitea.dump.gz, dify.dump.gz)
   g. rclone copyto manifest.json                    → s3://<bucket>/snapshots/<timestamp>/manifest.json
                                                            (slim — timestamp, stack, template_version; per-component
                                                             checksums deferred to v1.1, see Open Question 1)
4. verify:             rclone check --one-way per source (workdir + every rsync target's local_path)
   ✗ on mismatch:      ABORT — leave server up, alert operator, do NOT proceed to step 5 or 6
   ✓ on match:         proceed
5. point latest.txt:   rclone copyto $timestamp.txt → s3://<bucket>/snapshots/latest.txt
                                                            (single-line text file at the snapshots/ root, NOT
                                                             under any timestamped prefix — it's the cross-snapshot
                                                             pointer that restore reads to figure out which
                                                             snapshots/<timestamp>/ subtree to pull. This is the
                                                             atomic-promotion step — only happens AFTER verify
                                                             passed in step 4.)
6. tofu destroy:       server + tunnel + DNS + access apps (volume already gone; the per-stack R2
                                                            bucket stays — owned by control-plane state)
```

### Atomicity guarantees

- **Step 4 is the gate.** If verify fails for any reason (network blip, bucket permission, partial upload), the workflow stops. Server stays up; operator decides whether to retry teardown or troubleshoot.
- **No infrastructure destruction before verified S3 state.**
- **Idempotency:** re-running teardown after a partial failure replays steps 1–4. Step 4 short-circuits if hashes already match.

**About `rclone check`'s integrity guarantee.** The default
`rclone check` compares the per-object hash that rclone has for the
S3 backend — for R2 (S3-compatible API) that's the object ETag for
non-multipart uploads, or the etag-of-etags (an MD5-of-MD5s) for
multipart uploads.

**Multipart-threshold caveat.** An earlier draft of this section
claimed our typical files are "well under R2's multipart
threshold" and that ETag therefore equals MD5 end-to-end. That's
not generally true: rclone's S3 backend uses `--s3-upload-cutoff`
(default ~200 MiB) to decide when to multipart-upload, and the
default `--s3-chunk-size` is 5 MiB. Plenty of our objects —
Gitea LFS attachments, larger Postgres dumps, Dify uploads — can
land above 200 MiB, in which case ETag is the etag-of-etags and
NOT plain MD5 of the body.

What ``rclone check`` actually guarantees in that case:
*upload integrity* (every part uploaded matches what rclone
sent, and the assembled object's etag-of-etags matches rclone's
locally-computed etag-of-etags) — NOT strict content-equality
against the source bytes. That's still a strong property —
network corruption or partial-upload truncation get caught — but
it's weaker than "bit-for-bit equal to source." A deliberately
corrupted source could in theory hash-collide its way through
the etag-of-etags scheme; for our threat model (no adversarial
operator) we accept that.

**v1.0 acceptance.** We accept that the integrity guarantee in
the multipart case is "upload integrity," not "content equality
against source." v1.1 can tighten this by either: (a) pinning
``--s3-upload-cutoff`` high enough that all our objects stay
single-part (works for ≤200 MiB-ish; not for LFS or large Dify
uploads); (b) running ``rclone hashsum sha256 --download`` after
upload to round-trip every object; or (c) moving per-component
sha256 into ``manifest.json`` and verifying client-side on
restore (Open Question 1).

## Code changes

### Template (`stefanko-ch/Nexus-Stack`)

#### Tofu

| File | Change |
|---|---|
| `tofu/control-plane/main.tf` | Remove `hcloud_volume "persistent"` resource + outputs. Add a new `cloudflare_r2_bucket "persistence"` resource using the **existing** `cloudflare/cloudflare` provider (already configured for DNS / Tunnel / Access / Pages elsewhere in this file). Set the bucket's `location` to `EEUR` (Eastern Europe — Cloudflare's hint that constrains R2 storage replicas to EU geography). Note this is a **new** explicit constraint on the persistence bucket; the project's existing R2 buckets (Tofu state, data-lake) don't set a jurisdiction and rely on R2's default. Operators may set `location` differently per their data-residency needs. **Also configure object versioning + lifecycle** on this bucket — the cloudflare provider doesn't have a first-class lifecycle resource as of writing, so v1.0 ships these via a `null_resource` + `local-exec` against the S3 API (or via the migration shell script for the existing-stack evacuation phase) that turns on versioning and applies the 30-day `NoncurrentVersionExpiration` rule on the `snapshots/` prefix. The repo's other `minio_s3_bucket` resources today don't configure versioning/lifecycle — adding it for the persistence bucket is a new constraint that gets enforced separately from the bucket-create itself. No new provider plumbing required, no new credentials — the existing `CLOUDFLARE_API_TOKEN` already has the scopes needed. The bucket lives in **control-plane state** (not stack state), so it's created once at control-plane setup and survives every per-spinup teardown of `tofu/stack/` — same pattern as the volume it replaces. |
| `tofu/control-plane/variables.tf` | Remove `persistent_volume_size`. Add `s3_persistence_bucket_name`, `s3_persistence_endpoint`, `s3_persistence_region`. |
| `tofu/control-plane/outputs.tf` | Replace `persistent_volume_id` with `s3_persistence_credentials` (sensitive). |
| `tofu/stack/main.tf` | Remove `hcloud_volume_attachment "persistent"`. Add user-data / cloud-init pulling from S3 (or do it in `pipeline.py` instead — see below). |
| `tofu/stack/variables.tf` | Remove `persistent_volume_id`. |

#### `src/nexus_deploy/`

| File | Change |
|---|---|
| `setup.py` | Remove `mount_persistent_volume()`. Add `restore_from_s3()` that runs after server boot: rclone sync + pg_restore. |
| `pipeline.py` | Replace `_setup.mount_persistent_volume(...)` with `_setup.restore_from_s3(...)`. Add new phase `_phase_postgres_restore` that runs pg_restore before `_phase_compose_up`. |
| `compose_runner.py` | Replace bind-mount paths from `/mnt/nexus-data/...` to `/var/lib/nexus-data/...`, OR keep `/mnt/nexus-data` as symlink (decide based on whether `/mnt` is conventional in any tooling). |
| **NEW** `s3_persistence.py` | Module containing: `dump_postgres_to_s3()`, `rclone_sync_to_s3()`, `rclone_sync_from_s3()`, `verify_s3_snapshot()`, `write_manifest()`, `read_manifest()`. |
| **NEW** `teardown.py` (or extend existing teardown logic in `__main__.py`) | New phase ordering: **stop (graceful drain) → dump → sync → verify → tofu destroy**. Abort on verify failure. ``docker compose stop`` (not ``pause`` — see Risks table) with the default 10s timeout gives app processes time to finish in-flight requests and close DB connections cleanly. |

#### `services.yaml` / `stacks/`

| Stack | Change |
|---|---|
| `gitea` | Bind-mount path update only (or keep — if `/mnt/nexus-data` symlink stays). Optionally migrate Gitea LFS to native S3 backend (`[lfs] STORAGE_TYPE=minio`) — saves an rsync round-trip but adds Gitea config complexity. **Open Question.** |
| `dify` | Bind-mount path update only (or keep). Optionally migrate Dify storage to native S3 (`STORAGE_TYPE=s3` env var) — see Dify docs. **Open Question.** Weaviate stays local — no S3 backend mode. |
| All other stacks | No changes. Their docker-named-volumes were already ephemeral; the volume removal doesn't affect them. |

#### GitHub Actions workflows

| File | Change |
|---|---|
| `.github/workflows/spin-up.yml` | Remove `persistent_volume_id` extraction from control-plane outputs. The new pipeline phase pulls S3 credentials from Infisical instead. |
| `.github/workflows/teardown.yml` | Add pre-tofu-destroy phase: run `nexus_deploy.teardown` (the new module). Abort workflow if S3-verify fails. |
| `.github/workflows/destroy-all.yml` | Document that this now also deletes the S3 bucket contents (or doesn't — operator confirmation). |

#### Documentation

| File | Change |
|---|---|
| `CLAUDE.md` | Update "Adding New Stacks" — clarify which stacks need S3-aware persistence. |
| `docs/admin-guides/setup-guide.md` | Replace volume-creation step with S3 bucket creation. |
| `README.md` | Architecture diagram — server is now stateless, data lives in S3. |

### Education (`stefanko-ch/Nexus-Stack-for-Education`)

| File | Change |
|---|---|
| `nexus-admin/packages/shared/src/db/schema.ts` | Add `s3PersistenceBucket` to classes / users (or compute from naming convention). |
| `nexus-admin/packages/shared/src/operations/setup.ts` | Replace volume-creation API call with R2-bucket-creation call against Cloudflare's R2 API (or shell out to `scripts/init-s3-bucket.sh`). Reuses the project-wide R2 token already minted by `init-r2-state.sh` — no new credential to provision per fork. |
| `nexus-admin/packages/shared/src/operations/lifecycle.ts` | Remove volume-related preflight. |
| Admin UI | Class-create form: drop "Persistent Volume Size" field. **No region picker needed** — R2 is region-agnostic (single global namespace; the optional EEUR jurisdiction hint is set once in Tofu, not exposed to the operator UI). The earlier Hetzner-OS revision of this RFC proposed a fsn1/hel1/nbg1 picker; that's obsolete with the R2 switch. |

## Migration path for the 26 existing stacks

This is the riskiest part. Existing stacks have data on Hetzner volumes; we must move it to S3 without loss.

### Phase A: prepare (no breaking changes yet)

1. Pre-create per-stack R2 buckets (one-time admin action via the migration shell script or the new Tofu resource).
2. Push the R2 access credentials to each stack's Infisical secrets folder. v1.0 **reuses the project-wide R2 token** that already exists from `scripts/init-r2-state.sh`. **Security trade-off the operator must know about:** that token is account-scoped ("Workers R2 Storage Write" permissions across the whole account), so the same credential is what already protects the Tofu state bucket — and a compromise of any one stack would expose every other stack's persistence bucket (and the state bucket). For v1.0 we accept this because the alternative (a per-stack R2 token) would mean managing 26+ tokens against Cloudflare's 50-token-per-account limit, and the stacks already share trust via Infisical secret-sync. **v1.1 work:** introduce bucket-restricted tokens via Cloudflare's R2 token-permissions API (`bucket = nexus-<class>-<user>-internal`) and the `cloudflare_api_token` Tofu resource, so each stack only sees its own bucket. Tracked as Open Question 9 below.
3. Add `nexus_deploy.s3_persistence` module to template, but don't wire it into pipeline yet.

### Phase B: one-time evacuation

For each of the 26 existing stacks, run a manual evacuation workflow:

```
1. Spin up the stack (current behaviour, attaches volume)
2. Run `nexus-evacuate-volume-to-s3.yaml` — a one-shot GH workflow:
   a. docker compose stop on app services (Gitea web, Dify api/web) —
      same graceful-drain approach as the atomic teardown flow above.
      We deliberately do NOT use `docker compose pause` here either;
      cgroup-freezer SIGSTOP is hard-stop, not drain.
   b. dump postgres (gitea, dify) via `pg_dump -F c | gzip`
      into /tmp/dumps/<db>.dump.gz
   c. rsync exactly the same 5 subdirectories as the steady-state
      teardown flow above, into the snapshots/<timestamp>/
      prefix of the per-stack R2 bucket (NOT to the bucket root
      — earlier RFC revisions had this wrong):
      - /mnt/nexus-data/gitea/repos    → s3://<bucket>/snapshots/<timestamp>/gitea/repos
      - /mnt/nexus-data/gitea/lfs      → s3://<bucket>/snapshots/<timestamp>/gitea/lfs
      - /mnt/nexus-data/dify/storage   → s3://<bucket>/snapshots/<timestamp>/dify/storage
      - /mnt/nexus-data/dify/weaviate  → s3://<bucket>/snapshots/<timestamp>/dify/weaviate
      - /mnt/nexus-data/dify/plugins   → s3://<bucket>/snapshots/<timestamp>/dify/plugins
      gitea/db/ and dify/{db,redis}/ are NOT rsync'd (Postgres
      state lives under postgres/<db>.dump.gz; Redis is
      regeneratable).
   d. rclone copy /tmp/dumps/ → s3://<bucket>/snapshots/<timestamp>/postgres/
   e. write manifest.json into snapshots/<timestamp>/manifest.json
   f. verify via `rclone check --one-way` per source
   g. point s3://<bucket>/snapshots/latest.txt at the new timestamp
3. Operator confirms S3 contents look right
4. Stack stays up on volume (still using old code path)
```

Run for all 26 stacks during a maintenance window.

### Phase C: cutover (atomic per stack)

Per stack:

1. Teardown (current code path — preserves volume)
2. Update fork to new template version (S3-aware)
3. Spinup (new code path — restores from S3, ignores volume)
4. Verify functionality
5. Detach + delete the now-unused Hetzner volume

If anything goes wrong in step 3, roll back: spin up with the old template version, the volume is still there.

### Phase D: decommission

Once all 26 stacks are on the new code path and a few weeks have passed without regressions:

1. Delete the orphaned volumes (one-time cleanup script).
2. Remove the legacy `mount_persistent_volume` code path entirely from the template (clean removal in v1.0.0).

## Risks and open questions

### Risks

| Risk | Mitigation |
|---|---|
| **S3 upload fails mid-teardown** | Atomic 2-phase: verify before destroy. Operator manually resolves; never silently lose data. |
| **Spinup time becomes too long** | Profile per-stack data size; for large stacks (>5 GB) consider parallel rsync streams or streaming pg_restore. Document expected spinup time impact in setup guide. |
| **Postgres dump consistency** | `pg_dump` on a running DB takes a consistent snapshot at the moment the transaction begins. App-side: `docker compose stop` the Gitea web service / Dify api+web services (10s graceful drain) before `pg_dump` so no new writes land mid-snapshot. We deliberately do NOT use `docker compose pause` — that's a cgroup-freezer SIGSTOP, hard-kills in-flight requests. |
| **Weaviate corruption on incomplete restore** | Treat Weaviate as rebuildable from Dify-DB metadata if the dump is partial. Worst case: knowledge bases need re-indexing (slow but recoverable). |
| **Cloudflare R2 outage** | R2 has a single global namespace with automatic replication, but a control-plane outage at Cloudflare blocks both reads and writes. Today's design has a single Cloudflare dependency anyway (Tunnel, Access, DNS, Pages all depend on Cloudflare), so adding R2 doesn't expand the blast radius. If the project ever needs to be Cloudflare-independent, that's a separate concern outside this RFC. |
| **R2 ops free-tier exhaustion** | Class A ops (writes) capped at 1M/month free; we estimate ~780K/month at 26 stacks × ~10 teardowns each. Adding more classes pushes us over. Monitor via Cloudflare dashboard; switch billing on once usage approaches the cap (paid is $4.50 per million additional Class A ops — small absolute cost). |
| **Existing Class config breaks on upgrade** | Migration script; back-compat shim in tofu (`persistent_volume_id = 0` becomes the new normal). |

### Open questions

1. **Gitea LFS native backend vs. rsync.** Gitea natively supports S3 LFS storage. Switching to native saves an rsync of the LFS dir on every teardown but adds Gitea config to the deployment. Recommendation: **rsync in v1, migrate to native LFS-S3 in v1.1** once we know the rsync performance impact.

2. **Dify storage native S3 backend.** Dify supports `STORAGE_TYPE=s3`. Same trade-off as Gitea. Recommendation: **rsync in v1, migrate to native in v1.1**.

3. **Weaviate.** No native S3 mode. Always rsync. Document that weaviate restoration is best-effort and Dify can rebuild if needed.

4. **Bucket-per-stack vs. shared bucket with prefixes.** Per-stack is operationally cleaner (easy to delete on destroy-all, isolation, separate IAM scopes). Shared with `<stack>/<path>` prefixes saves the bucket-creation step but couples blast radius. Recommendation: **bucket-per-stack**.

5. **R2 Terraform provider support.** RESOLVED — the `cloudflare/cloudflare` provider has a first-class `cloudflare_r2_bucket` resource and is already configured in this repo for DNS / Tunnel / Access / Pages. The persistence bucket is just one more cloudflare resource per stack — no new provider, no new credentials. The shell scripts shipped in PR-1 of the implementation become migration tooling for the existing-stack evacuation phase, not the steady-state path.

6. **Snapshot retention.** v1.0 ships with **30-day NoncurrentVersionExpiration** as the safety net (rough ceiling on storage cost, no precise N-of-each control). At typical tutorial-stack sizes (~5 GB current copy, plus same again in noncurrent versions for the most recent ~30 days of teardown→spinup churn) this lands around ~5-10 GB/stack peak — see Cost analysis table for the per-stack monthly impact. The "last 7 daily + last 4 weekly" pattern is a v1.1 follow-up that needs either (a) Cloudflare R2 lifecycle support for tag-based rules — R2's S3 API exposes `PutBucketLifecycleConfiguration` but the rule shapes it accepts are a subset of AWS S3 (`Expiration`, `NoncurrentVersionExpiration`, prefix-filtered; *not* tag-filtered as of writing) — or (b) a separate cleanup cron that walks `snapshots/<timestamp>/` directories and deletes by ISO-8601 timestamp sort order. (b) is the more likely v1.1 implementation path.

7. **What happens to `destroy-all`?** ✅ **RESOLVED** — see Decision #6 above. The single canonical answer: **bucket preserved by default, opt-in delete via `CONFIRM_DELETE_DATA=DESTROY`**. (For historical traceability only — not the active recommendation — the original draft of this Q proposed the opposite default; that was abandoned in favour of the explicit-opt-in shape that mirrors the existing `destroy-all.yml -f confirm=DESTROY` pattern. The early-draft text has been removed to avoid confusion.)

8. **How to surface S3 latency in spinup logs.** Add a `_phase_s3_restore` log section showing per-directory transfer rate so the operator can spot regressions.

9. **Per-stack R2 token scoping (v1.1).** v1.0 reuses the existing account-scoped R2 token from `init-r2-state.sh`. v1.1 should mint a bucket-restricted token per stack (Cloudflare R2 supports `permission_groups` with `bucket = <name>` filtering as of late 2024). The cloudflare provider has a `cloudflare_api_token` resource that can do this in Tofu. The trade-off: 26+ tokens against Cloudflare's 50-token-per-account limit, which is why this is deferred — needs either a token-rotation strategy or moving Tofu state credentials to a different storage system to free up token slots.

## Phased rollout plan

### v1.0-rc.1 — code complete on a feature branch

- All template changes (tofu, src/nexus_deploy/, stacks, workflows)
- Migration script `evacuate-volume-to-s3.yaml` workflow
- Documentation updates
- Unit tests for `s3_persistence.py`
- Integration test: spin up a fresh stack on the feature branch, teardown, spinup again — verify no data loss

### v1.0-rc.2 — evacuation of pilot stack

- Pick 1 of the 26 (e.g. `stefan-hslu` or a Template Dev Stack)
- Run evacuation
- Cutover this stack to new code path
- Run for 24-48 h, verify nothing breaks

### v1.0-rc.3 — broader pilot

- Cutover 5 more stacks, monitor

### v1.0.0 — full cutover

- All 26 stacks migrated
- Old code path removed from template
- Release Please cuts v1.0.0

## Cost analysis (back-of-envelope)

Cloudflare R2 pricing (2026-05):
- **Free tier**: 10 GB storage + 1M Class A ops/month + 10M Class B ops/month
- **Above free tier**: $0.015 per GB/month storage, $4.50 per million Class A ops (writes), $0.36 per million Class B ops (reads)
- **Egress**: **$0 (zero) regardless of destination** — major advantage over both Hetzner Object Storage and AWS S3

Class-A ops counted: ``rclone sync`` writes (one PutObject per file) + ``rclone copyto`` for manifest + `latest.txt`. For a typical teardown
(~1000 small repo files + a handful of dump files + manifest) → ~1000 Class-A ops per teardown × 30 teardowns/month × 26 stacks = ~780K Class-A ops/month — comfortably inside the free 1M.

Class-B ops counted: ``rclone sync`` reads on spinup-restore — same magnitude as Class-A on teardown. ~780K Class-B ops/month — comfortably inside the free 10M.

Storage volume estimation under v1.0 retention (30-day expiration of noncurrent versions): each snapshot is roughly the size of the live data (~5 GB peak per typical stack). 30-day retention with ~10 teardowns/month per stack → ~55 GB peak per stack worst case (1 current + 10 noncurrent versions); typical usage churns far less so realistic average is closer to 5-10 GB/stack.

| Item | Today | Post-v1.0 (worst case) | Post-v1.0 (typical) |
|---|---|---|---|
| Hetzner volume (10 GB × 26 stacks) | €0.50 × 26 = €13/month | €0 | €0 |
| R2 storage (~55 GB worst / ~10 GB typical × 26 stacks = ~1430 GB / ~260 GB; first 10 GB free per *account* not per bucket) | €0 | ~$21/month | ~$3.75/month |
| R2 Class A + Class B ops | €0 | within free tier | within free tier |
| R2 egress (spinup pulls) | €0 | **$0** (R2 zero-egress) | **$0** |
| Increased spinup time (3-5 min × 30 spinups) | n/a | negligible | negligible |
| **Net** | **~€13/month** | **~$21/month** | **~$4/month** |

Wider considerations vs the previous Hetzner-Object-Storage proposal:

- **R2 is more expensive per GB** ($0.015/GB vs Hetzner €0.99/TB ≈ $0.001/GB). Pure storage cost is a wash at small data sizes; R2 pulls ahead on the operational story.
- **R2 has zero egress, which dominates** the moment a non-EU compute pull happens. Hetzner-Object-Storage charged €1.19/TB to the public internet — at 5 GB/spinup × 30 spinups = 150 GB/month egress, that would have been ~€0.18/month. Small absolute number, but a real operational caveat that pushed the previous RFC revision toward "EU-only compute by default". With R2 that caveat is gone.
- **R2 ops counted differently** — Class-A vs Class-B distinction (writes vs reads) is something Hetzner doesn't have. The 1M Class-A ops/month free-tier ceiling is generous for 26 stacks but worth tracking as the class grows.
- **Below free tier the cost is literally zero.** For pilot work or a smaller class (<10 GB total across all stacks) R2 is free.

## Decision points — RESOLVED 2026-05-11

1. **Storage provider:** ✅ **Cloudflare R2** (revised from the earlier Hetzner Object Storage choice). The project already uses R2 — the Tofu state backend lives in R2 (`scripts/init-r2-state.sh`, `tofu/backend.hcl`), and the `cloudflare/cloudflare` Tofu provider is already configured for DNS / Tunnel / Access / Pages. Reusing R2 for persistence means: same credentials, same provider, no new system to operate. R2 is also region-agnostic with zero egress fees — non-EU compute pulls the snapshot at no surcharge, which eliminates the EU-only-compute caveat that made the Hetzner-Object-Storage proposal awkward.
2. **Bucket scoping:** ✅ **Bucket-per-stack** — operational isolation, easy `destroy-all` cleanup, per-stack IAM scope.
3. **Bucket provisioning:** ✅ **Tofu via the existing `cloudflare/cloudflare` provider** (`cloudflare_r2_bucket` resource). The cloudflare provider is already in `providers.tf` for the project's DNS / Tunnel / Access / Pages resources, so a new `cloudflare_r2_bucket "persistence"` per stack stays in the established pattern. No additional providers, no additional credentials. The shell scripts shipped in PR-1 of the implementation series (`scripts/init-s3-bucket.sh`, `scripts/cleanup-s3-bucket.sh`) — originally framed for Hetzner-Object-Storage — are rewritten in PR-1 round-4 to use the Cloudflare API + `wrangler r2 bucket` pattern (same shape as the existing `scripts/init-r2-state.sh`). They remain as migration tooling for the existing 26 stacks during the evacuation phase, and as a manual-fallback path for operators not using Education's setup automation.
4. **Native S3 backends (Gitea LFS, Dify storage):** ✅ **Defer to v1.1** — v1.0 ships with rsync only. Removes one source of risk per release.
5. **Snapshot retention:** ✅ **30-day expiration of noncurrent versions** as the safety net for v1.0, configured via R2's built-in object-versioning + lifecycle policy. The precise "7 daily + 4 weekly" pattern still needs a separate cleanup script — v1.1 work.
6. **`destroy-all` behaviour:** ✅ **Opt-in delete** — bucket preserved by default, `--delete-data` flag (or workflow input) required to remove it. Same shape as the existing `confirm=DESTROY` confirmation.

## Estimated effort

- Architecture + RFC: 0.5 days (this document)
- Implementation (template-side): 3-5 days
- Implementation (Education-side): 1-2 days
- Migration scripts + evacuation workflow: 1-2 days
- Pilot rollout + monitoring: 2-3 days
- Full cutover: 1 day (mostly waiting for queue)
- Documentation: 1 day

**Total: ~10-15 working days end-to-end**, can be parallelised between template + Education.

## Appendix A — manifest.json schema

The v1.0 *rendered* manifest is slim — just stack identity and
timestamp — and relies on rclone's per-object hash check for
integrity. The richer per-component shape below is what the
Python-side `SnapshotManifest` + `manifest_for_components` helpers
produce; v1.1 may switch the rendered bash to emit this richer
form once we've measured the per-stack-size impact of computing
sha256 over multi-GB trees on the server.

```json
{
  "version": 1,
  "created_at": "2026-05-10T20:30:00Z",
  "stack": "nexus-stefan-hslu",
  "template_version": "v0.56.0",
  "components": {
    "gitea": {
      "repos_count": 12,
      "repos_size_bytes": 245760,
      "lfs_size_bytes": 0,
      "postgres_dump_bytes": 18432,
      "postgres_schema_version": "1.21.0"
    },
    "dify": {
      "storage_size_bytes": 1048576,
      "weaviate_size_bytes": 4194304,
      "plugins_count": 3,
      "postgres_dump_bytes": 32768
    }
  },
  "checksums": {
    "gitea/repos/": "sha256:...",
    "gitea/lfs/": "sha256:...",
    "postgres/gitea.dump.gz": "sha256:...",
    "dify/storage/": "sha256:...",
    "dify/weaviate/": "sha256:...",
    "dify/plugins/": "sha256:...",
    "postgres/dify.dump.gz": "sha256:..."
  }
}
```

Note: the `postgres/<db>.dump.gz` paths match the actual S3 object
layout from the teardown flow (custom-format `pg_dump` piped through
gzip, written under `postgres/` not under each app's subtree).

## Appendix B — example rclone config snippet

```ini
[cloudflare-r2]
type = s3
provider = Cloudflare
endpoint = https://<account_id>.r2.cloudflarestorage.com
access_key_id = <from-infisical>
secret_access_key = <from-infisical>
region = auto
acl = private
```

R2 uses ``region = auto`` (R2 is a single global namespace; the SDK
doesn't route based on region). The endpoint URL includes the
Cloudflare account ID, which the existing
``scripts/init-r2-state.sh`` already retrieves from the
``CLOUDFLARE_ACCOUNT_ID`` env var when it sets up the Tofu state
bucket.
