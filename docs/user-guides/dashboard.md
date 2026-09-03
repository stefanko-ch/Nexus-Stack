---
title: "Dashboard"
description: "Infrastructure status and the two big actions: spin up and tear down"
order: 2
---

# Dashboard

The Dashboard is the landing page of the Control Plane. It answers two questions at a glance:

1. **Is my stack up right now?**
2. **What can I do about it?**

## Version tag

The header shows the currently-deployed Nexus-Stack template version (e.g. `v0.51.1`). If a newer release exists upstream you can upgrade from the admin panel (not from the Control Plane itself).

![Control Plane header showing the deployed Nexus-Stack template version tag (e.g. v0.51.1)](./assets/dashboard-version-tag.png)

## Status panel

The coloured indicator at the top reflects the current state of your Hetzner infrastructure:

| Colour | Meaning |
|--------|---------|
| Green — **Deployed** | Server is running, Docker services are up, domain resolves |
| Amber — **Pending** | A workflow is in progress (spin-up, teardown, or initial setup) |
| Orange — **Torn down** | No server exists; nothing is running, nothing is being billed |
| Grey — **Unknown** | Status check failed; see [Monitoring](./monitoring.md) for details |

The panel re-polls automatically every few seconds, so you can keep it open while a workflow runs.

![Status panel in the orange "Torn down" state, indicating no server is running](./assets/dashboard-status-torn-down.png)

## Progress while a workflow runs

Spin-up and teardown used to be a black box: a spinner and "this usually takes 5-10 minutes". While one runs you now get a progress bar with the step it is on:

```text
◐  Spin Up is running                                      2m 14s   View in GitHub
   Step 19 of 37: Deploy stacks
   ████████████████░░░░░░░░░░░░░░░░
   ▸ Details
```

**Step N of M** counts the steps GitHub actually reports for this run, which is more than the workflow file declares — the runner adds its own `Set up job`, a `Post …` step for each action that has cleanup, and `Complete job`. They are counted and shown greyed out, so the numbers match what you see if you click **View in GitHub**. The list is read live: a step added to a workflow later appears here on its own, and the total can grow mid-run.

**Details** expands the full list, the same one GitHub shows:

| Mark | Meaning |
|------|---------|
| ✓ | Finished |
| ● | Running now |
| ○ | Not started |
| ⊘ | Skipped — a step whose `if:` condition did not apply |
| ✗ | Failed |

Each step shows how long it took, and its name links to that step in the GitHub log.

Two states worth recognising:

- **"Dispatched — waiting for GitHub to start the run"** — the click landed, but GitHub has not created the run yet. This takes a few seconds. The buttons stay disabled throughout, so a second click cannot start a second run.
- **A sliding bar instead of a percentage** — the run is queued for a runner, or a job has not reported its steps yet. There is nothing to count, so nothing is claimed.

When a run finishes, the bar stays: green at 100% for success, or red at the point it failed, with the failing step named and the list already expanded. It is **not** filled to 100% on failure — cleanup steps run after a failure, and filling the bar would suggest the work completed. Dismiss it, or start another run, to clear it.

## Action buttons

Two buttons, each tied to a GitHub Actions workflow:

![Spin Up and Teardown action buttons on the Dashboard](./assets/dashboard-action-buttons.png)

### ⚡ Spin Up

Starts `spin-up.yml` on your repo, which:
- Boots a Hetzner server
- Mounts the persistent volume
- Installs Docker + cloudflared
- Restarts all enabled services

Typical runtime: 3–5 minutes. Button stays disabled until the stack is fully torn down (can't spin up on top of a running server).

### 💤 Teardown

Starts `teardown.yml`, which:
- Stops and deletes the Hetzner server
- Detaches the volume (data preserved)
- Leaves DNS, tunnels, and Infisical in place so the next spin-up is fast

Cheap state: you pay only for the persistent volume (~€1/month).

## When buttons are disabled

The Control Plane will grey out actions that don't apply right now — e.g. **Spin Up** is disabled while the stack is already running or while a teardown is in flight. Hover the disabled button to see the reason.

## Active Stacks

Below the action buttons the Dashboard lists which services are currently active. Each row shows a service name that is enabled and running on the stack.

![Active Stacks list below the action buttons, showing the currently enabled and running services with a total count](./assets/dashboard-active-stacks.png)

The count ("3 stacks active") reflects services enabled in [Stacks](./stacks.md). Click a service row to open the service directly in a new tab.
