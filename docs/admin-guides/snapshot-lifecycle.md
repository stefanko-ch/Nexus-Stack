---
title: "Snapshot Lifecycle"
description: "Restore the server from a Hetzner disk snapshot instead of rebuilding it, and how to get back if that goes wrong"
order: 6
---

# Snapshot Lifecycle

Nexus-Stack has two teardown/spin-up pairs. This guide covers the second one, when to use it, and — more importantly — how to get out of it.

| Mode | Teardown | Spin-up | What happens |
|---|---|---|---|
| `legacy` | `teardown.yml` | `spin-up.yml` | Destroy everything, rebuild from `ubuntu-24.04` |
| `snapshot` | `teardown-snapshot.yml` | `spin-up-snapshot.yml` | Snapshot the disk, destroy only the server, restore from the image |

**The default is `legacy`.** Nothing changes until you switch.

---

## Why you might want it

Two reasons, and the second is the stronger one.

**Speed.** Measured on real runs in August 2026, same service set:

| | cold (rebuild) | warm | difference |
|---|---|---|---|
| cloud-init gate | 78 s | 14 s | −64 s |
| `Deploy stacks` | 257 s | 148 s | −109 s |

A restore skips both: cloud-init takes a light path, and the Docker images are already on the disk. Roughly **3 minutes on a small service set**, scaling with the number of images. The cost lands on the teardown (~2 min → ~2.5 min), which runs unattended at 21:00.

**Data coverage.** The R2 persistence layer covers a hard-coded five-stack subset — Postgres dumps for gitea, dify, hedgedoc and planka, plus filesystem trees for those and metabase. Everything else is discarded on teardown. `s3_restore.standard_targets()` says so directly:

> Skipping this step means the stack's bind-mount under `/mnt/nexus-data/<stack>/` is purely ephemeral — present across container restarts on the same VM, gone the moment `tofu destroy` re-creates the host.

A disk snapshot captures the whole root disk, so **all ~76 stacks** survive a teardown rather than five. It also needs no per-stack maintenance, where the hard-coded list silently makes every new stack ephemeral until someone remembers to extend it.

---

## Switching a stack

Three steps, in this order. The third is not optional for a first switch — it is the only thing that proves the mechanism works before you rely on it.

### 1. Deploy the Control Plane

The scheduled-teardown Worker is deployed by Terraform. A Worker that predates this feature does not know the `lifecycle_mode` key at all, so the config change would have no effect on the nightly run.

```bash
gh workflow run setup-control-plane.yaml
```

### 2. Flip the mode

```bash
npx wrangler@4 d1 execute nexus-<domain-slug>-db --remote \
  --command "UPDATE config SET value = 'snapshot' WHERE key = 'lifecycle_mode'"
```

`<domain-slug>` is your domain with dots replaced by hyphens — for
`nexus-stack.ch` the database is `nexus-nexus-stack-ch-db`. Same convention as
the R2 buckets described in [Setup Guide](./setup-guide.md).

Valid values are `legacy` and `snapshot`. Anything else is refused — see [When the mode cannot be determined](#when-the-mode-cannot-be-determined).

**One key controls both workflows on purpose.** An earlier design had one key per workflow and it was wrong: a half-applied switch means snapshot spin-up with legacy teardown, and the legacy teardown runs an untargeted `tofu destroy` that regenerates every service credential — which orphans the snapshot it just produced.

### 3. Verify before relying on it

`teardown-snapshot.yml` takes a `skip_destroy` input that runs the whole sequence and then powers the server back on, destroying nothing:

```bash
gh workflow run teardown-snapshot.yml -f confirm=TEARDOWN -f skip_destroy=true
```

Cost: one power cycle. Check afterwards that the image appears in the Hetzner console with the `nexus_role`, `nexus_domain` and `nexus_epoch` labels, and that the stack came back up.

---

## Switching back

```bash
npx wrangler@4 d1 execute nexus-<domain-slug>-db --remote \
  --command "UPDATE config SET value = 'legacy' WHERE key = 'lifecycle_mode'"
```

That is the whole rollback. The legacy workflows were never modified and do not depend on anything the snapshot path added.

For a single run rather than a permanent switch, `spin-up-snapshot.yml` takes `force_fresh=true`, which ignores any snapshot and builds from `ubuntu-24.04`.

---

## What can go wrong

### The snapshot is refused and the stack rebuilds fresh

This is the **designed** behaviour, not a fault. A snapshot is only used when it is genuinely usable. It is skipped when:

- there is none yet (first spin-up after switching)
- it was pruned
- its credential epoch no longer matches
- its architecture or disk size cannot be satisfied by any available server type

In every case the spin-up falls back to a normal `ubuntu-24.04` build **with R2 restore enabled**, so the five R2-covered stacks keep their data. The other stacks come back empty — the same as the legacy path has always behaved.

The workflow log names the reason.

### The credential epoch stopped matching

Symptom: every spin-up rebuilds fresh, and the log says the snapshot was rejected on epoch.

Cause: the legacy `teardown.yml` ran at some point. Its untargeted `tofu destroy` destroys all 81 `random_password` / `random_id` / `random_string` resources, so every service credential is regenerated on the next spin-up. A snapshot taken before that holds Postgres roles and admin accounts with the old passwords; restoring it would produce a stack that boots and then authenticates nowhere.

The guard exists precisely to prevent that, so this is the mechanism working. The snapshot is dead, though — take a fresh one on the next teardown.

**Do not mix the two teardowns on one stack.** That is what `lifecycle_mode` being a single key is for.

### The restore cannot find a server type

Symptom: `select-capacity` reports that every preference was excluded, and the spin-up stops.

Cause: a Hetzner snapshot is architecture-locked and requires a target disk **at least as large** as the source server's. `DEFAULT_PREFERENCES` mixes disk sizes across tiers, so a snapshot taken on a large tier excludes the smaller ones.

This is a one-way ratchet: restore a 160 GB snapshot onto a 240 GB server and the *next* snapshot is 240 GB, permanently excluding 160 GB types.

Fixes, in order of preference:

1. Widen `SERVER_PREFERENCES` to include types that can host it
2. Run once with `force_fresh=true` to rebuild from the base image, which resets the ratchet

Do not trust the tier comments in `hetzner_capacity.py` for disk sizes — they were wrong once already. `fetch_server_types` reads the real values from the API at runtime.

### The snapshot limit is reached

Hetzner allows **30 snapshots across all projects** by default. Retention keeps 2 per stack, so a single project supports roughly 15 stacks before this bites. `snapshot-create` counts before creating and warns near the cap; it fails loudly naming foreign snapshots rather than deleting anything it does not own.

Ask Hetzner support to raise the limit, or reduce retention.

### When the mode cannot be determined

If D1 is unreachable, the binding is missing, or `lifecycle_mode` holds an unrecognised value, **nothing is dispatched**:

- the scheduled Worker skips that night's teardown and logs why
- the Control Plane API returns `503`

This is deliberate. "Cannot tell" is not "not configured": guessing would fall back to the legacy pair, which is the *destructive* one, and running it at a stack that is on snapshots would rotate every credential and orphan the snapshot. Skipping costs one more day of server time; guessing wrong costs the snapshot.

An **unconfigured** stack — no row at all — is a different case and resolves to `legacy` without complaint.

---

## Costs

Hetzner bills snapshots on **used** space, not the disk size, at roughly EUR 0.011–0.014 per GB per month. At two retained snapshots that is on the order of EUR 1–2 per month — small against the server, not zero.

Note the two figures are different and easy to confuse:

- `disk_size` — the source server's whole disk. Decides which types can host the image.
- `image_size` — compressed used space. What you pay for.

Both are reported by `snapshot-create` and `snapshot-resolve`.

---

## Related

- [Server Resize](./server-resize.md) — changing server type; interacts with the disk ratchet above
- [SSH Access](./ssh-access.md) — needed for the verification steps
- [Troubleshooting](./troubleshooting.md) — general operational issues
- `docs/proposals/0002-hetzner-disk-snapshots.md` — the design and why it looks like this
