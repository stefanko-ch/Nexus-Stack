---
title: "Kestra and Forgejo Flow Sync"
description: "How flow definitions are synced in both directions between Kestra and the Forgejo workspace repository"
order: 10
---

# Kestra ↔ Forgejo bi-directional flow sync


When the `kestra` service is enabled the orchestrator registers three system-namespace flows that sync flow definitions between Kestra and the user's Forgejo workspace repository.

## Two-namespace model

Flows live in two distinct Kestra namespaces, each tied to a separate path in the Forgejo workspace:

| Kestra namespace | Forgejo path in workspace | Meaning |
|---|---|---|
| `nexus-tutorials.*` | `nexus_seeds/kestra/flows/` | **Seeded reference flows** shipped by Nexus-Stack. Read-mostly from the student's perspective. NEVER pushed back from the UI (would corrupt the upstream tutorial baseline). |
| `my-flows.*` | `kestra/flows/` | **Student's own work** — clones of seeded flows, new flows. UI-edits in this namespace auto-push to Git every 10 min. |

The `nexus_seeds/` prefix is reserved for Nexus-Stack-shipped content; user-authored flows live at the repo root under `kestra/flows/` to make the ownership distinction visible at a glance in the Forgejo workspace tree.

## The three system flows

| Flow | Direction | Trigger | Purpose |
|---|---|---|---|
| `system.git-sync` | Forgejo → Kestra | once at spin-up | Pulls namespace files (SQL, scripts, queries) from `nexus_seeds/kestra/workflows/` into Kestra's namespace storage |
| `system.flow-sync` | Forgejo → Kestra | once at spin-up | Two tasks in one flow: `sync-seeds` pulls `nexus_seeds/kestra/flows/` → `nexus-tutorials.*`; `sync-user` pulls `kestra/flows/` → `my-flows.*`. Both `delete: true`, separate namespaces ensure no interference. |
| `system.flow-export` | Kestra → Forgejo | every 10 minutes | Pushes `my-flows.*` only to `kestra/flows/`. Excludes `nexus-tutorials.*` (protects seeds) and `system.*` (echo-prevention). |

## Design rationale

**Pull direction (`git-sync` + `flow-sync`) runs only at spin-up, not on a schedule.** The previous form (`cron: */15`) caused two distinct problems:

1. **Silent overwrite of UI edits.** `SyncFlows` with `delete: true` reconciles Kestra's target namespaces to whatever is in Git every tick. A student editing a flow in the Kestra UI had a 15-minute window before their changes vanished — invisible data loss, no error log.
2. **Ping-pong with the export direction.** A pull running on a 15-min schedule combined with a push running on any schedule would chase each other's commits.

**Steady-state source of truth:**
- For *in-session edits in `my-flows.*`* → the Kestra UI (auto-pushed to Forgejo via `flow-export`).
- For *cross-stack restore* → Forgejo (the persistence-bucket snapshot covers Kestra's Postgres DB; `flow-sync` re-hydrates Kestra at the next spin-up from Forgejo as canonical source).
- For *seeded tutorial flows in `nexus-tutorials.*`* → Git is canonical (the upstream Nexus-Stack repo seeded them). UI-edits there are preserved via DB-snapshot but **not** via Git, and `flow-sync` at the next spin-up will reconcile them away. The copy-before-edit workflow exists to avoid this.

## Loop diagram

```
                  ┌─────────────────────────────────────────┐
                  │  Nexus-Stack repo (upstream)            │
                  │  examples/workspace-seeds/kestra/flows/ │
                  └────────────────┬────────────────────────┘
                                   │
                                   ▼  (POSTed by _phase_seed at first deploy)
                  ┌─────────────────────────────────────────┐
                  │  Forgejo workspace                      │
                  │  ├── nexus_seeds/kestra/flows/  (seeds) │◀──┐
                  │  └── kestra/flows/             (user)   │   │
                  └────────────────┬───────────────┬────────┘   │
                                   │               ▲           │
                  [Spin-up: flow-sync, 2 tasks]   │           │
                                   │               │           │
                                   ▼               │           │
                  ┌─────────────────────────────────────────┐  │
                  │  Kestra                                 │  │
                  │  ├── nexus-tutorials.*  (read-mostly)   │  │
                  │  └── my-flows.*         (UI-editable)  ─┼──┘
                  │                          every 10 min,  │
                  │                          via flow-export │
                  └─────────────────────────────────────────┘
```

## `flow-export` specifics

- **Cadence:** `cron: "*/10 * * * *"` (every 10 minutes). A stack crash loses at most ~10 minutes of student work in `my-flows.*`. Faster (every 5 min) would multiply commits + R2 egress for marginal recovery; slower (hourly) would lose unacceptable amounts.
- **Source namespace:** `my-flows` only. The PushFlows plugin has no exclude-list, so positive-only namespace scoping is the only way to (a) prevent the exporter from pushing itself (`system.*` echo-loop) AND (b) protect `nexus-tutorials.*` seeds from getting overwritten with student edits.
- **`delete: false`:** a UI-side delete does *not* propagate to Git. To permanently delete a `my-flows.*` flow, the operator commits the removal directly in the Forgejo workspace; the next `flow-sync` (at next spin-up) drops it from Kestra.
- **Commit identity:** `Kestra Auto-Export <kestra@nexus-stack.local>` (synthetic, never a real user). The Forgejo push log still attributes the push to whoever owns the admin token, but Git blame stays clean.
- **Conflict behaviour:** `REJECTED_NONFASTFORWARD` is fail-loud — visible as an execution failure in the Kestra UI, manually resolvable by an operator. Happens when someone commits directly to the workspace between two export ticks.

## What students see in the Forgejo workspace

Two directories under the workspace:

```
<workspace-root>/
├── nexus_seeds/
│   └── kestra/
│       ├── flows/                         ← seeded tutorial flows
│       │   └── nexus-tutorials/
│       │       └── r2-taxi-pipeline.yml
│       └── workflows/                     ← namespace files (SQL/scripts)
└── kestra/
    └── flows/                             ← student's own auto-exported flows
        └── my-flows/
            └── r2-taxi-experiment.yml     ← auto-commit every ~10 min
```

The `system/` directory is **never** in either tree — those flows are infrastructure (regenerated per deploy).

See [user-guides/kestra-flow-editing.md](../user-guides/kestra-flow-editing.md) for the recommended student-side workflow (copy a seeded flow into `my-flows` before editing).
