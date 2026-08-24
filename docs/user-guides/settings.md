---
title: "Settings"
description: "Server info, auto-teardown schedule, and notification preferences"
order: 7
---

# Settings

![Top of the Settings page, showing the start of the Infrastructure Information block](./assets/settings-header.png)

The Settings page is split into four blocks: **Infrastructure Information** (read-only), **Scheduled Teardown**, **Lifecycle**, and **Email Notifications**.

## Infrastructure Information

Read-only facts about the current deployment.

![Infrastructure Information block listing read-only deployment facts: server type, location, domain, last spin-up and teardown timestamps, and uptime](./assets/settings-infrastructure-info.png)

| Field | Description |
|-------|-------------|
| **Server Type** | Hetzner server model (e.g. `cx43`) |
| **Location** | Hetzner datacenter code — EU options: `hel1` (Helsinki), `fsn1` (Falkenstein), `nbg1` (Nuremberg); US option: `ash` (Ashburn) |
| **Domain** | Your root domain |
| **Last Spin Up** | Timestamp of the most recent spin-up |
| **Last Teardown** | Timestamp of the most recent teardown |
| **Uptime** | Time elapsed since last spin-up |

To change server type or location, edit `config.tfvars` and re-deploy — the Control Plane can't change these on the fly.

## Scheduled Teardown

The cron worker can auto-teardown your stack on a daily schedule so you don't pay for an idle server overnight.

![Scheduled Teardown block with the enable toggle, next teardown countdown, remaining daily extensions, and a Delay Teardown by 4 Hours button](./assets/settings-scheduled-teardown.png)

- **Toggle** — Enable or disable the automatic daily teardown.
- **Next teardown** — Shows the scheduled time and how much time is remaining.
- **Extensions remaining** — How many times you can still delay teardown today (resets at UTC midnight).
- **Delay Teardown by 4 Hours** — Pushes the next teardown back by 4 hours. Useful when you're mid-session. Limited to 3 extensions per UTC day by default.

> If your admin has set `allow_disable_auto_shutdown = false`, the toggle is visible but locked — you can still use the delay button.

## Lifecycle

How your stack is torn down at night and brought back the next day. Both
options stop the server, which is where nearly all the saving comes from. They
differ in what survives, how long the spin-up takes, and — slightly — in cost:
Snapshot keeps disk images, and Hetzner bills those by used space. Measured on
a real stack that is roughly 10 GB used, two retained snapshots come to a
little under 30 cents a month. Small against a server, but not zero.

- **Rebuild** — Destroy everything and rebuild from a clean Ubuntu image each
  time. Container images are pulled fresh, so stacks tracking `:latest` stay
  current. What survives is only what the R2 backup covers: Gitea, Dify,
  HedgeDoc, Planka and Metabase. Anything else — tables you created in
  Postgres, dashboards you built in Grafana, Kestra run history, notebooks you
  have not committed — is gone the next morning.
- **Snapshot** — Take a disk snapshot before destroying the server and restore
  from it. Everything on the server survives, across all stacks, and the boot
  is faster because the system does not reinstall itself. In exchange the
  container images age: they stay at whatever was pulled when the snapshot line
  started. There is no refresh button yet — switching to Rebuild for one cycle
  is currently the only way to pull newer images, and that costs you everything
  the R2 backup does not cover.

The block always names the mode currently in use and what it means, so you can
read the setting even when you cannot change it.

> **Only the stack administrator can change this.** For everyone else the
> toggle is greyed out. Switching to Rebuild also asks for confirmation,
> because it cannot be undone: the next teardown regenerates every service
> password, and existing snapshots can no longer be restored after that.

Committing your work to the workspace repository is worth doing either way. The
repository lives in Gitea, which is backed up under both options — it is the
one place your work is safe regardless of which mode the stack is on.

## Email Notifications

![Email Notifications block with independent toggles for the Shutdown Warning Email and the Stack Online Email](./assets/settings-email-notifications.png)

Two email notifications can be toggled independently:

- **Shutdown Warning Email** — Sent before the scheduled daily teardown as a heads-up.
- **Stack Online Email** — Sent when the stack is back online after a spin-up.

Both are sent via Resend using the API key configured during setup. If emails aren't arriving, check the Secrets page — `RESEND_API_KEY` should be under the global folder.
