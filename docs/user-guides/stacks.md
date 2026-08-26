---
title: "Stacks"
description: "Enable, disable, and open individual Docker services"
order: 3
---

# Stacks

Your Nexus-Stack ships with 60+ Docker services grouped into categories (Data Engineering, ML/AI, Dev Tools, …). The **Stacks** page is where you turn them on, turn them off, and click through to their web UIs.

![Stacks page header showing Docker services grouped into categories with controls to manage and open them](./assets/stacks-header.png)

## Grid vs List

The **Grid** view (default) groups services by category with a count of running and disabled stacks per group.

![Stacks page in Grid view with services grouped by category, each group showing a running vs. disabled count](./assets/stacks-grid-view.png)

The **List** view is a flat sortable table — better for searching by name or browsing all stacks at once.

![Stacks page in List view: a flat sortable table of every service with columns for name, subdomain, port, and toggle](./assets/stacks-list-view.png)

Toggle between the two with the **Grid / List** buttons in the top right.

## Enabling and disabling a stack

Each tile has three controls:

- **Toggle** — On/Off. Enabling triggers a GitHub Actions workflow that runs `docker compose up -d` for that stack. Disabling runs `docker compose down` and removes the container (volumes stay).
- **Open** — Opens the service's web UI in a new tab. Links to the stack's subdomain (e.g. `https://grafana.<your-domain>`).
- **Docs** — Per-stack documentation on nexus-stack.ch.

Toggling a stack takes 10–60 seconds depending on image size. The tile spins during the operation.

## Search

Press `/` (or click the search box) and type. Matches on stack name, description, and image tag. Press `Enter` to switch to the List view with the same filter applied.

![Stacks search box filtering the grid to services matching the typed term across name, description, and image tag](./assets/stacks-search.png)

## Core stacks

A small set of services are marked **core** and cannot be disabled:

- **Forgejo** — Git server used by several integrations
- **Grafana** — monitoring and observability
- **Infisical** — secrets store
- **Portainer** — container dashboard, the first stop when a service misbehaves

Core stacks are shown with a **CORE** badge and their toggle is locked.

![A stack tile marked with a CORE badge and a locked toggle, showing that the service cannot be disabled](./assets/stacks-core-badge.png)

## What happens when you disable a stack

- The Docker container is stopped and removed
- Docker volumes with data (databases, object storage) are preserved
- DNS and Cloudflare Tunnel routes stay in place (so re-enabling is instant)
- The stack's Cloudflare Access application stays (authentication rules persist)

Re-enabling triggers a GitHub Actions workflow in the background that runs `docker compose up -d` against the same volume — you get your data back.
