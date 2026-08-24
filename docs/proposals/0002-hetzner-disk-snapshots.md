# RFC 0002 — Hetzner Disk Snapshots as a Second Lifecycle

**Status:** implemented (#649, #651, #653), not yet exercised end to end
**Supersedes:** nothing. Complements [RFC 0001](./0001-s3-persistence.md).

## tl;dr

Add a second teardown/spin-up pair that takes a Hetzner disk snapshot before destroying the server and restores from it on the next spin-up, selected per stack by a single D1 config value. The existing pair is untouched and remains the default.

The headline is speed, but the stronger argument is coverage: RFC 0001's R2 layer protects five stacks by name; a disk snapshot protects all of them.

## Motivation

### What the current cycle repeats

Every teardown destroys the whole stack; every spin-up rebuilds it from `ubuntu-24.04`. Most of that rebuild is work already done: patching Ubuntu, installing Docker, and pulling the same container images.

Measured across real workflow runs (May–August 2026):

| Phase | Duration | Share |
|---|---|---|
| Spin-up total | 3m49s – 9m47s | |
| of which `Deploy stacks` | 99–465 s | ~87% |
| of which cloud-init gate (cold) | 42–123 s | |
| of which `Apply infrastructure` | 9–21 s | |
| Teardown total | ~2 min | |

Within `Deploy stacks`, Docker image pulls are the single largest block. A cold/warm comparison of the same service set isolates it:

| | cold | warm | delta |
|---|---|---|---|
| cloud-init gate | 78 s | 14 s | −64 s |
| `Deploy stacks` | 257 s | 148 s | −109 s |

A restore skips both.

### The part that is not about speed

RFC 0001 moved persistence to R2 and, in doing so, made the covered set explicit and finite. `s3_restore.standard_targets()` lists Postgres dumps for gitea, dify, hedgedoc and planka, plus filesystem trees for those and metabase. Its own docstring states the consequence for everything else:

> Skipping this step means the stack's bind-mount under `/mnt/nexus-data/<stack>/` is purely ephemeral — present across container restarts on the same VM, gone the moment `tofu destroy` re-creates the host.

That is five stacks out of roughly seventy-six. A disk snapshot captures the whole root disk, which after RFC 0001's volume removal holds both the bind mounts and the Docker named volumes. It also requires no per-stack registration, so a new stack is protected by default rather than silently ephemeral until someone extends a list.

### What this is NOT

- **Not a replacement for RFC 0001.** R2 remains, runs first on every snapshot teardown, and is the recovery path whenever a snapshot is unavailable, epoch-mismatched or architecture-incompatible. It is also logically consistent (`pg_dump`) where a disk image is not, and portable where a snapshot is vendor- and architecture-locked.
- **Not the default.** Stacks stay on the rebuild pair until switched.
- **Not a backup.** Retention is two generations and the images live in the same Hetzner project as the server.

## Design

### Targeted destroy, not out-of-band deletion

```
tofu destroy -target=hcloud_server.main
```

The original sketch was to delete the server outside OpenTofu. Targeted destroy is better on three counts:

1. **Credentials survive.** All 81 `random_password` / `random_id` / `random_string` resources stay in state, so service credentials remain stable. A snapshot captures Postgres roles and app admin accounts as they were; restoring it against regenerated credentials produces a stack that boots and then authenticates nowhere.
2. **So does everything else that is free to keep.** Tunnel, tunnel config, every DNS record, every Access application and policy. The restored server's baked-in `cloudflared` config still matches, so that work is skipped too.
3. **State stays truthful.** An out-of-band delete leaves `hcloud_server.main` in state, where the partial-state guard in `pipeline.py` would then try to SSH to a server that no longer exists.

The one resource destroyed alongside the server is `cloudflare_record.firewall_tcp`, which depends on its IPv4 address. That is desirable rather than incidental: the address is about to be reassigned to another Hetzner customer, and an out-of-band delete would leave that unproxied A record live for the whole downtime window.

### Ordering is the safety property

1. R2 logical snapshot — first, while containers still run, since it needs `docker exec … pg_dump`
2. Power off, polled to `status=off` — Hetzner recommends it, and the graceful stop is what makes the captured Postgres directories trustworthy
3. `create_image`, waited to `available` — the action reaching `success` means the copy finished; only `available` means it can create a server
4. Mirror metadata to D1
5. **Only then** destroy
6. Prune older generations, keep 2 — after the new one is available, never before

### One config value, not two

`lifecycle_mode` is `rebuild` or `snapshot`, and both workflow filenames are derived from it. It was originally `legacy`, renamed because the pair is a permanent fallback rather than something deprecated; `schema.sql` migrates existing rows.

The first implementation used one key per workflow. That allows drift, and a half-applied switch is harmful rather than untidy: snapshot spin-up with rebuild teardown means the nightly untargeted destroy rotates every credential and orphans the snapshot it just made. Documenting "switch both together" is not the same as making the other case impossible.

Deriving the names rather than storing them also removes an injection surface: no database value reaches the GitHub API URL path.

### "Cannot tell" is not "there is none"

This rule appears in four places across the implementation, and it is the one most worth remembering:

| Situation | Answer | Action |
|---|---|---|
| No snapshot exists | definite | build fresh |
| Epoch mismatch | definite | build fresh |
| No `lifecycle_mode` row | definite | `rebuild` |
| Snapshot lookup failed | **unknown** | stop |
| `tofu init` failed | **unknown** | stop |
| D1 unreadable | **unknown** | dispatch nothing |

The asymmetry matters because the fallbacks are not neutral. Building fresh during an API outage discards a snapshot that may hold the only copy of most stacks' data. Defaulting to `rebuild` when the mode is unknown dispatches the *destructive* pair at a stack that may be on snapshots.

### Boot readiness

`user_data` is guarded by `/opt/docker-server/.image-provisioned` so a restored server does not repeat `apt-get upgrade` and the Docker install it already carries.

Readiness is signalled by `/run/nexus-setup-complete`, written by a small systemd unit ordered `After=docker.service`. Two properties matter:

- `/run` is tmpfs, so it is structurally impossible to capture in a disk image. The old marker `/opt/docker-server/.setup-complete` lives on the disk and is therefore *inside* every snapshot — a gate probing it would pass instantly, possibly before sshd and Docker were up.
- A systemd unit runs on **every** boot. cloud-init's `scripts-user` is PER_INSTANCE and does not re-run on a plain reboot, so a marker touched from `user_data` would be missing for the rest of the server's life after its first reboot — which breaks the warm spin-up, the common case.

The gate itself is unified rather than branched:

```bash
test -f /run/nexus-setup-complete \
  || { test -f /opt/docker-server/.setup-complete && systemctl is-active --quiet docker; }
```

This is monotonically safer for the rebuild path: it accepts everything the old gate accepted, plus requires Docker to be up. It can only wait longer, never pass earlier.

### `lifecycle.ignore_changes` on the server

```hcl
lifecycle {
  ignore_changes = [image, user_data, server_type, location]
}
```

Load-bearing, not tidiness. Without it a snapshot-restored server is one rebuild spin-up away from destruction: `spin-up.yml` supplies `ubuntu-24.04` and `select-capacity` rewrites `server_type`/`server_location`, so OpenTofu would plan a **replacement** of the live server. `image` and `user_data` are ForceNew, which makes it a silent data-loss path rather than a diff someone notices.

It costs nothing operationally: the documented resize flow is teardown → set `SERVER_TYPE` → spin-up, so the server is always created fresh with the new values.

## Known limits

**30 snapshots per Hetzner customer**, counted across every project, and a raisable default rather than a ceiling. At two retained generations that caps a fleet at roughly 15 stacks until raised — which is why this is opt-in per stack rather than a global switch. Splitting tenants across projects does not help; the count is per customer. The effective value is read from `NEXUS_SNAPSHOT_LIMIT` (repository variable `SNAPSHOT_LIMIT`) because it is account-specific and cannot be a constant in this repo.

**Disk-size ratchet.** A snapshot requires a target disk at least as large as its source. Restoring onto a larger tier makes the next snapshot larger, permanently excluding the smaller ones. Mitigated by the `--min-disk-gb` / `--arch` filters in capacity selection; reset by one `force_fresh` cycle.

**Architecture lock.** x86 snapshots restore only onto x86. Relevant if the project ever reverts to ARM, and a reason the R2 layer stays.

**Living outside Tofu state cuts both ways.** It is what lets a snapshot survive the `tofu destroy` in its own teardown, and equally what stops `destroy-all.yml` from removing it as a side effect. Handled by an explicit `snapshot-purge` step under the existing `delete_data=DESTROY` opt-in; the default lists what survives rather than deleting it, because an unrestorable image is still readable by hand and is the last recovery path after an accidental destroy-all.

**Cross-network-zone restore is unverified.** Keep snapshot preferences within one zone.

**Nothing has run end to end.** `skip_destroy=true` proved snapshot creation against the live stack on 2026-08-21 (72 s: 28 s power-off, 44 s create-and-available). The restore half has never executed. Five review rounds found eight genuine defects in this path before it ran once — the first real restore remains the test that matters.

## Code map

| Area | Where |
|---|---|
| Hetzner snapshot API | `src/nexus_deploy/hetzner_snapshot.py` |
| CLI subcommands | `src/nexus_deploy/__main__.py` (`server-poweroff`, `snapshot-create`, `snapshot-resolve`, `snapshot-prune`) |
| Restore constraints | `src/nexus_deploy/hetzner_capacity.py` (`fetch_server_types`, `filter_specs`) |
| Server + credential epoch | `tofu/stack/main.tf`, `tofu/stack/outputs.tf` |
| Workflows | `.github/workflows/teardown-snapshot.yml`, `spin-up-snapshot.yml` |
| Shared workflow steps | `.github/actions/nexus-bootstrap`, `.github/actions/nexus-config-tfvars` |
| Mode selection | `control-plane/functions/api/_utils/workflow-selection.js`, `control-plane/worker/src/index.js` |

Operator instructions live in [Snapshot Lifecycle](../admin-guides/snapshot-lifecycle.md).

## Open questions

1. Which server types actually satisfy the current snapshot's disk requirement? Needs one `/v1/server_types` query; determines whether the ratchet costs money.
2. Should pre-snapshot disk hygiene (`docker image prune`, `journalctl --vacuum`) be added? Deferred as a cost optimisation worth cents against an SSH dependency in the critical path.
3. Should `teardown.yml` and `destroy-all.yml` move onto the composite actions? Deliberately not done yet — a bug in a shared action would take every path down at once, so the actions are being proven on the newer workflows first.
