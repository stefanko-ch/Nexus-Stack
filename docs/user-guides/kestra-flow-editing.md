---
title: "Editing Kestra flows"
description: "How to make edits to Kestra flows that survive a stack restart — the copy-before-edit rule"
order: 9
---

# Editing Kestra flows

Nexus-Stack syncs your Kestra flows bi-directionally with your Forgejo workspace fork. Two distinct namespaces live in Kestra, each tied to a separate directory in your fork:

| Kestra namespace | Forgejo path in your fork | Meaning |
|---|---|---|
| `nexus-tutorials.*` | `nexus_seeds/kestra/flows/` | **Seeded tutorial flows.** Shipped by Nexus-Stack as reference material. Read-mostly — your UI edits here are **not** auto-saved to Git. |
| `my-flows.*` | `kestra/flows/` | **Your own work.** Edits in this namespace auto-export to your Forgejo fork every 10 minutes. |

## The golden rule: copy seeded flows into `my-flows` before editing

The seeded `nexus-tutorials.*` flows are the same for every student who deploys Nexus-Stack. They are not your personal workspace — they are the upstream-distributed tutorial baseline. If you edit one in-place in the Kestra UI:

- **During the current session** (until the next spin-up): your edit is live in Kestra's DB and you can run it.
- **At the next spin-up**: `system.flow-sync` reconciles the `nexus-tutorials.*` namespace back to whatever is in `nexus_seeds/kestra/flows/` (i.e. the upstream-distributed version). Your in-place edit is **reverted**.
- Your edit is **not** captured in Git either — `flow-export` deliberately excludes `nexus-tutorials.*` so it cannot corrupt the upstream tutorial baseline.

**Net outcome:** in-place edits to `nexus-tutorials.*` flows do NOT survive a spin-up cycle. To make your changes permanent, **copy the seeded flow into the `my-flows` namespace first.**

### How to copy a seeded flow

1. Open the seeded flow in the Kestra UI, e.g. `nexus-tutorials.r2-taxi-pipeline`.
2. Open the YAML view → copy the entire source.
3. Create a new flow with:
   - `id:` something fresh, e.g. `r2-taxi-experiment-v1`
   - `namespace: my-flows` (the only auto-exported namespace)
4. Paste the body, save.

Your flow is now `my-flows.r2-taxi-experiment-v1`. The next `system.flow-export` run (within 10 min) commits it to `kestra/flows/my-flows/r2-taxi-experiment-v1.yml` in your Forgejo fork.

### Why "copy" instead of just "edit in place"?

| Benefit | What it means |
|---|---|
| Original tutorial stays intact | Reference material always available. After three weeks of editing, you can still see the unmodified starting point. |
| Reset is one delete away | Don't like your changes? Delete your copy → original (in `nexus-tutorials.*`) is untouched. |
| Multiple iterations | `r2-taxi-experiment-v1`, `r2-taxi-experiment-v2`, ... typical "draft → improve → final" workflow without losing earlier versions. |
| Clean Git history | Your fork's commit log shows what's yours (`my-flows/...`) vs the seeded baseline (`nexus_seeds/...`). |
| Predictable spin-up behavior | Your flow is in Git after the next export tick; the next spin-up's `flow-sync` re-hydrates it. |

## Round-trip across spin-ups

```
[10:03] Edit my-flows.r2-taxi-experiment-v1 in Kestra UI
            │
            ▼ (next */10 tick: 10:10)
[10:10] flow-export pushes kestra/flows/my-flows/r2-taxi-experiment-v1.yml to Forgejo
            │
            ▼  (at some point: stack teardown)
[Teardown] R2 snapshot captures the fork incl. your flow file
            │
            ▼  (next spin-up — could be 5 min or 5 weeks later)
[Spin-up] flow-sync's sync-user task pulls kestra/flows/ → my-flows.* namespace
            │
            ▼
[Kestra UI shows my-flows.r2-taxi-experiment-v1, exactly as you left it]
```

## Deleting a flow

The `flow-export` task uses `delete: false`, meaning a UI-side delete does **not** rewrite Git history. The flow file stays in your fork. The next `flow-sync` at spin-up will pull it back.

To permanently delete a `my-flows.*` flow:

1. Delete it in the Kestra UI (immediate effect, but only until next spin-up).
2. Open your Forgejo fork, navigate to `kestra/flows/my-flows/<flow-id>.yml`, click **Delete file**, commit the deletion.
3. At the next spin-up, `flow-sync`'s `sync-user` task with `delete: true` will reconcile the deletion: Kestra removes the flow.

To "reset to upstream" a seeded flow you accidentally edited in `nexus-tutorials.*`: just trigger `system.flow-sync` manually from the UI. The seeded original wins (Git is canonical for that namespace).

## What about the `system.*` flows?

Three flows live in the `system` namespace:

- `system.git-sync` (pulls namespace files at spin-up)
- `system.flow-sync` (pulls both seed + user flows at spin-up — two tasks in one flow)
- `system.flow-export` (pushes `my-flows.*` to Git every 10 min)

These are **infrastructure** — regenerated per deploy by Nexus-Stack itself. They are **never** pushed to your Forgejo fork (echo-prevention). Don't edit them in the UI — your edits would be silently overwritten on the next spin-up. They're not part of your workspace.

## When your `my-flows.*` edits aren't appearing in the Forgejo fork

If you don't see a recent UI edit in the fork:

1. **Check the cadence.** `flow-export` runs every 10 min on the `:00`, `:10`, `:20`... ticks. If you edited at `:08`, wait until `:10`, or trigger `system.flow-export` from the Kestra UI manually for an immediate push.
2. **Check the namespace.** Only flows in `my-flows.*` get exported. A flow in `nexus-tutorials.*` (the seeded namespace) or any other custom namespace won't be pushed. Move the flow to `my-flows.*` to make it persistent.
3. **Check the execution log.** Open `system.flow-export` in the Kestra UI → Executions tab. A `FAILED` execution with `REJECTED_NONFASTFORWARD` means someone (or you, via the Forgejo web UI) committed to the fork between two export ticks and the export couldn't fast-forward. Resolve by pulling the conflicting commit into your local edit and re-running the export.

## See also

- [admin-guides/setup-guide.md](../admin-guides/setup-guide.md#kestra--forgejo-bi-directional-flow-sync) — the bi-directional sync design + cadence rationale + loop diagram
