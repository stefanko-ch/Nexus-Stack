---
title: "Stacks"
description: "Enable, disable, and open individual Docker services"
order: 3
---

# Stacks

Your Nexus-Stack ships with a large catalogue of Docker services, grouped into categories (Data Engineering, ML/AI, Dev Tools, …). The **Stacks** page is where you turn them on, turn them off, and click through to their web UIs.

![Stacks page header showing Docker services grouped into categories with controls to manage and open them](./assets/stacks-header.png)

## Grid vs List

The **Grid** view (default) shows one card per category, with the number of stacks in it and how many are running or disabled. Click a card to open the category and see its stacks as tiles.

![Stacks page in Grid view: one card per category, each with its stack count and a running vs. disabled count](./assets/stacks-grid-view.png)

The **List** view is one flat table of every stack — better for searching by name or browsing all stacks at once.

![Stacks page in List view: a table of every stack with a status dot, its name, category, URL and toggle](./assets/stacks-list-view.png)

Toggle between the two with the **Grid / List** buttons in the top right.

## Enabling and disabling a stack

Each tile on a category page has three controls (the List view has the same toggle in each row):

- **Toggle** — On/Off. Enabling triggers a GitHub Actions workflow that runs `docker compose up -d` for that stack. Disabling runs `docker compose down` and removes the container (volumes stay).
- **Open** — Opens the service's web UI in a new tab. Links to the stack's subdomain (e.g. `https://grafana.<your-domain>`).
- **Website link** — bottom left, the project's own website (e.g. `grafana.com`).

Toggling a stack takes 10–60 seconds depending on image size. The tile spins during the operation.

## Search

Press `/` (or click the search box) and type. Matches on stack name, description, and image tag. Press `Enter` to switch to the List view with the same filter applied.

![Stacks search box with a term typed in: the grid keeps only the categories that contain a match, and each count shows the matches in it](./assets/stacks-search.png)

## Core stacks

A small set of services are marked **core** and cannot be disabled:

- **Forgejo** — Git server used by several integrations
- **Grafana** — monitoring and observability
- **Infisical** — secrets store
- **Portainer** — container dashboard, the first stop when a service misbehaves
- **SFTPGo** — browser for the deployment's object storage

Core stacks are shown with a **CORE** badge and their toggle is locked.

![The Core Infrastructure category page: each tile carries a CORE badge and a locked toggle, showing that the service cannot be disabled](./assets/stacks-core-badge.png)

## Proven stacks

A few more stacks carry a **PROVEN** badge: code-server, Kestra, Marimo and Spark. They are the ones courses run on, and they are promised to work on every release, across a teardown and restore. Issues about them are fixed first. Unlike core stacks, you can switch them on and off like any other.

Click **Proven only** at the top of the Stacks page to list just these; it switches to the List view, and switching back to Grid clears the filter. Every other stack is *best-effort*: available, but not tested before each release. See [what each tier promises](../concepts/stacks.md#what-each-tier-promises).

## What happens when you disable a stack

- The Docker container is stopped and removed
- Docker volumes with data (databases, object storage) are preserved
- DNS and Cloudflare Tunnel routes stay in place (so re-enabling is instant)
- The stack's Cloudflare Access application stays (authentication rules persist)

Re-enabling triggers a GitHub Actions workflow in the background that runs `docker compose up -d` against the same volume — you get your data back.
