---
title: "Server Resize"
description: "Upgrade or downgrade the Hetzner server type (e.g. cpx32 → cpx42) for an existing Nexus-Stack deployment"
order: 2
---

# Server Resize Guide

This guide explains how to change the Hetzner server type on an existing Nexus-Stack deployment — typically an **upgrade** when you outgrow the current size (Kestra + JVM stacks running tight on RAM, slow spin-up due to limited vCPUs), or a **downgrade** to save cost during idle periods.

> **Nexus-Stack's workflows don't support in-place server-type changes.** Hetzner itself can change a server's type via the Cloud Console, but the OpenTofu IaC path the spin-up / teardown workflows use treats a type change as a destroy-and-recreate. A resize via Nexus-Stack therefore always means: tear down → re-create with new type. The workflow below makes that round-trip safe.

---

## When to use which path

| Situation | Path |
|---|---|
| Stack is running, want to change type | **Teardown → resize → spin-up** (Path A) |
| Stack is already torn down (e.g. scheduled teardown ran overnight) | **Resize → spin-up** (Path B — skip the teardown step) |
| Total reset wanted (forget all D1 state + Cloudflare resources) | **Destroy → resize → initial-setup** (Path C) |

The decision tree is about how much state you want to preserve:

- **Path A + B preserve state via two different mechanisms.** R2 snapshots hold the per-stack data — Postgres dumps, Gitea repos, dbt state, code-server volume; spin-up restores those onto the new server. D1 (the Control Plane database with your enabled-stack toggles and scheduled-teardown config) is preserved separately because teardown only destroys Hetzner-side infrastructure and leaves the Control Plane (Pages + Worker + D1) running untouched.
- **Path C wipes** the Hetzner server + Cloudflare resources + Control Plane (D1 + Pages + Worker). R2 buckets (Tofu state + snapshots + data) are **preserved by default** — pass `-f delete_data=DESTROY` if you also want those gone (see "About R2 buckets after destroy-all" below).

---

## Current configuration check

Before you change anything, see what the deployment thinks it's using:

```bash
# Runs against your own fork's repo by default — works from inside the
# repo checkout. If your shell isn't in the checkout, add
# `--repo <your-org>/<your-fork>` explicitly.
gh variable list 2>&1 | grep -i SERVER
```

Expected output:
```
SERVER_LOCATION fsn1    2026-03-30T18:36:00Z
SERVER_TYPE     cpx32   2026-05-06T18:47:24Z
```

If you see `SERVER_PREFERENCES` instead (comma-separated list), the deployment uses the capacity-selection workflow that picks the first available type from a preference list — different update path, see "Variant: SERVER_PREFERENCES" below.

---

## Available Hetzner types

Common Nexus-Stack choices:

| Type | vCPU | RAM | Disk | Monthly | Notes |
|---|---|---|---|---|---|
| `cx32` | 4 (Intel) | 8 GB | 80 GB | ~€7.50 | Cheapest viable |
| `cpx32` | 4 (AMD) | 8 GB | 160 GB | ~€12.49 | AMD, faster single-core than cx32 |
| `cx43` | 8 (Intel) | 16 GB | 160 GB | ~€19.49 | Project default since 2026-05 |
| `cpx42` | 8 (AMD) | 16 GB | 240 GB | ~€24.49 | AMD equivalent of cx43, more disk |
| `cx53` | 16 (Intel) | 32 GB | 320 GB | ~€34.49 | For heavy multi-tenant / large JVM loads |

For the full canonical list see [setup-guide.md](setup-guide.md#optional-repository-variables) — Hetzner also has `cax*` ARM variants but Nexus-Stack switched permanently away from ARM in 2026-05 for two reasons: (a) EU ARM capacity has been unavailable for an extended period, and (b) Hetzner's pricing flipped — ARM is now **~40% more expensive** than equivalent x86 (was ~50% cheaper at project start). See [the project's CLAUDE.md](https://github.com/stefanko-ch/Nexus-Stack/blob/main/CLAUDE.md) for the rationale. Stick to `cx*` / `cpx*` unless you have a specific reason to revisit ARM.

---

## Path A — Teardown → resize → spin-up

Use when the stack is currently running and you want to change type without losing any data.

```bash
# 1. Snapshot + tear down. The workflows default NEXUS_S3_PERSISTENCE
#    to "true" when the repo secret is unset, so the snapshot step
#    runs automatically. Only worry if you've EXPLICITLY set the secret
#    to "false" — in that case the teardown skips the snapshot and
#    data does not survive.
gh workflow run teardown.yml && sleep 3 && gh run watch

# 2. Update the server type repo variable
gh variable set SERVER_TYPE --body "cpx42"

# 3. Spin up with the new type. Will restore your data from the
#    R2 snapshot taken in step 1
gh workflow run spin-up.yml && sleep 3 && gh run watch
```

**What's preserved:** Gitea repos, Postgres data (Metabase dashboards, Kestra flows, CloudBeaver connections, etc.), dbt state, code-server volume — anything that's in the R2 snapshot.

**What's NOT preserved:** in-memory state from the moment of teardown (e.g. an in-flight Kestra execution gets cancelled). Plan resize windows accordingly.

---

## Path B — Resize → spin-up (already torn down)

Use when teardown has already run (scheduled teardown, manual teardown last night, etc.) — skip the first step:

```bash
# Update server type repo variable
gh variable set SERVER_TYPE --body "cpx42"

# Spin up
gh workflow run spin-up.yml && sleep 3 && gh run watch
```

Same data-preservation guarantees as Path A — the R2 snapshot from the last teardown gets restored onto the new server.

---

## Path C — Destroy → resize → initial-setup (full reset)

Use when you want to **completely reset** the deployment: not just the server, but also the Control Plane (D1 database with enabled-services state), Cloudflare resources (DNS, Tunnel, Access apps), and Pages/Worker. R2 buckets (Tofu state + snapshots + data) are preserved by default so the next `initial-setup` can pick up snapshot history — see "About R2 buckets after destroy-all" below for full-wipe semantics.

```bash
# 1. Full destroy
gh workflow run destroy-all.yml -f confirm=DESTROY && sleep 3 && gh run watch

# 2. Update server type
gh variable set SERVER_TYPE --body "cpx42"

# 3. Initial setup — NOT spin-up, because the Control Plane needs to
#    be rebuilt before any stack can be deployed. Initial-setup
#    creates the Control Plane and then automatically triggers spin-up.
gh workflow run initial-setup.yaml && sleep 3 && gh run watch
```

Duration: ~10-15 minutes (D1 database re-created + OpenTofu apply on new server + Cloudflare setup + automatic spin-up; R2 buckets reused from before).

### What comes back automatically

| Automatically | Manual step after |
|---|---|
| New Hetzner server (with the resized type) | Re-enable optional stacks in the Control Plane — the enabled-state lives in D1, which was wiped |
| Cloudflare Tunnel + DNS + Access | – |
| Control Plane (Pages + Worker + D1) — re-created fresh | – |
| Infisical (with **newly generated** secrets) | If you had **external** secrets (Databricks tokens, GitHub mirror tokens etc.), re-add them in Infisical |
| Core stacks: forgejo, gitea, grafana, infisical, portainer | Click "Spin Up" once you've toggled additional stacks |

### About R2 buckets after destroy-all

`destroy-all` deliberately **preserves all three R2 buckets** by default — the Tofu state bucket, the persistence (snapshot) bucket, and the data (datalake) bucket. The Tofu state file inside its bucket is stale after destroy but harmless: `init-r2-state.sh` reuses the bucket on the next `initial-setup`, and re-running `destroy-all` against a missing-server stack still works (RFC 0001 decision #6).

If you want to nuke the buckets too — fully reset including snapshot history — invoke `destroy-all` with the opt-in second flag:

```bash
gh workflow run destroy-all.yml \
  -f confirm=DESTROY \
  -f delete_data=DESTROY
```

That extra step deletes the persistence, data, and state buckets via the R2 S3 API. Once gone, snapshot history is unrecoverable — only do this if you really mean a fresh start. For a server-type resize you almost never want this; the bucket-preservation default is what lets the next `initial-setup` pick up where the old stack left off (DNS records re-applied, Cloudflare resources re-created, but all R2 buckets — Tofu state + snapshots + datalake — and the separate Hetzner Object Storage buckets retained).

---

## Variant: SERVER_PREFERENCES instead of SERVER_TYPE

If your deployment uses `SERVER_PREFERENCES` (the Hetzner capacity-selection workflow that picks across multiple types/regions), you change the **list** instead of a single type:

```bash
# Old:
# SERVER_PREFERENCES = cpx32:fsn1,cpx32:nbg1,cx32:fsn1
# New (cpx42 preferred, fall back to cx43 if cpx42 is out of capacity):
gh variable set SERVER_PREFERENCES --body "cpx42:fsn1,cpx42:nbg1,cx43:fsn1"
```

The capacity-selection step in spin-up picks the first `<type>:<location>` pair that has live capacity. Useful when a specific size is frequently sold out in your preferred region.

If `SERVER_TYPE` is also set, `SERVER_PREFERENCES` takes precedence — leave `SERVER_TYPE` alone or delete it (`gh variable delete SERVER_TYPE`) to avoid confusion.

---

## Verification after spin-up

Once spin-up finishes, confirm the server is actually the new type:

```bash
# Via SSH (uses Cloudflare Tunnel — see ssh-access.md)
ssh nexus "free -h; nproc; lsblk | head -3"
```

Expected for cpx42:
```
              total        used        free      shared  buff/cache   available
Mem:        15.5Gi       ...                                          ...
Swap:          0B
8                                          ← nproc
NAME    MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
sda       8:0    0   240G  0 disk           ← cpx42 disk size
└─sda1    8:1    0   240G  0 part /
```

You can also verify via the Hetzner Cloud Console: https://console.hetzner.cloud → Servers → your server → "Server Type" panel should show the new tier.

---

## Cost considerations

Resize itself is free (no Hetzner change-type fee), but the new type bills at its hourly rate from the moment of the new server's creation. If you're upgrading mid-month, plan for a partial month at the new rate.

If you frequently switch between types — for example "big during weekday classes, small at night and weekends" — use the **Scheduled Teardown** feature in the Control Plane (Settings → Scheduled Teardown) combined with `SERVER_TYPE` variable updates at the right times. The scheduler runs `teardown.yml` and re-deploys via `spin-up.yml`, so the Path-B flow applies automatically.

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Spin-up fails with "Server type … not available" | Hetzner is out of capacity for the requested type in the requested location | Switch to `SERVER_PREFERENCES` with multiple types/locations, or pick a different region (`SERVER_LOCATION=nbg1` or `hel1`) |
| Spin-up succeeds but data is missing | `NEXUS_S3_PERSISTENCE` was explicitly set to `"false"` (or some other non-`"true"` value) before the last teardown, so the snapshot step was skipped; OR snapshot ran but no snapshot exists in R2 for some other reason | Check the R2 snapshot bucket: `snapshots/latest.txt` must point to a real timestamp directory. Also verify the repo secret with `gh secret list` and look for `NEXUS_S3_PERSISTENCE` in the output; if missing entirely, the workflows default to `"true"` (data is preserved). Only an explicit `"false"` skips snapshotting. If `latest.txt` is empty, the data is unrecoverable from snapshots |
| Spin-up succeeds, server is new size, but it still feels slow right after | Stacks haven't fully restarted — Docker images cached, but containers booting takes a few minutes. Wait + check `ssh nexus "docker ps"` |
| Control Plane shows old enabled-stacks state | You ran Path A or B (D1 preserved) — that's expected. If you wanted a clean slate, you wanted Path C |
| Hetzner SSH key conflict after `destroy-all` + `initial-setup` | The old SSH key may still be registered in Cloudflare/Hetzner | See [troubleshooting.md](troubleshooting.md) |
