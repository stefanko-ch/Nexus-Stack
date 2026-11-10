---
title: "Website Documentation Sync"
description: "How documentation is synced from this repo to nexus-stack.ch"
order: 7
---

# Website Documentation Sync

Documentation in this repo is the **single source of truth** for [nexus-stack.ch](https://nexus-stack.ch). The website fetches all docs at build time — no content is duplicated between repos.

## How It Works

```
Nexus-Stack repo                          Cloudflare Workers Builds
┌─────────────────────────┐               ┌──────────────────┐
│ docs/stacks/*.md        │               │ fetch-docs.mjs   │
│ docs/user-guides/*.md   │ ──push to───> │ fetches docs     │
│ docs/admin-guides/*.md  │ ──main─────>  │ from GitHub,     │
│ docs/tutorials/*.md     │               │ then astro build │
│ services.yaml           │               └──────────────────┘
└─────────────────────────┘                        │
         │                                         │
         │ sync-docs-site.yml                      │
         │ (Cloudflare Deploy Hook)                │
         └────────────────────────────────────────>┘
              curl POST triggers rebuild
```

1. A push to `main` that changes `docs/`, `services.yaml`, or `README.md` triggers the `sync-docs-site.yml` workflow
2. The workflow calls the Cloudflare Deploy Hook via `curl -X POST`
3. Cloudflare Workers Builds runs `scripts/fetch-docs.mjs` (fetches docs from GitHub) then `astro build`
4. The updated site is deployed to the edge

## Content Mapping

| Content | Source | Website renders as |
|---------|--------|-------------------|
| `docs/concepts/*.md` | What the project is and how it is built | `/docs/concepts/[slug]` pages |
| `docs/stacks/*.md` | Stack documentation | `/docs/stacks/[slug]` pages. `overview.md` becomes the section's index page; `README.md` is not synced |
| `docs/user-guides/*.md` | End-user Control Plane guides | `/docs/guides/user-guides/[slug]` pages |
| `docs/admin-guides/*.md` | Operator / self-hoster guides | `/docs/guides/admin-guides/[slug]` pages |
| `docs/tutorials/**/*.md` | Tutorials and walkthroughs, one folder per topic | `/docs/tutorials/[topic]/[slug]` pages |
| `services.yaml` | Service metadata (ports, categories, descriptions) | Stack list, navigation, metadata |

### Images

| Asset folder | Synced to | Referenced from markdown as |
|--------------|-----------|----------------------------|
| `docs/assets/` | `public/docs-assets/` on the website | Absolute URL `/docs-assets/foo.png` |
| `docs/user-guides/assets/` | Next to the rendered `.md` files at `src/content/docs/docs/guides/user-guides/assets/` | Relative path `./assets/foo.png` |
| `docs/admin-guides/assets/` *(if added later)* | Next to the rendered `.md` files at `src/content/docs/docs/guides/admin-guides/assets/` | Relative path `./assets/foo.png` |

`docs/admin-guides/assets/` does not currently exist — admin guides have no screenshots today. The row above is the contract for when they do: drop images into that folder and `fetch-docs.mjs` picks them up automatically on the next sync.

**Always use markdown `![alt](./assets/foo.png)` — not HTML `<img>`.** Astro only processes images through its content pipeline when they're referenced via markdown syntax. HTML `<img>` tags pass through unchanged and 404 at runtime (the relative `./assets/` path resolves against the rendered page URL, not the source file's directory). See `CLAUDE.md` → "Documentation Image Syntax" for the full rule.

## Writing Documentation

### Stack Docs (`docs/stacks/`)

Each stack has a markdown file with a `title` frontmatter field:

```markdown
---
title: "Service Name"
---

## Service Name

(content)
```

The `description`, `category`, `port`, and other metadata come from `services.yaml` — don't duplicate them in frontmatter.

### Guides (`docs/user-guides/`, `docs/admin-guides/`)

User guides and admin guides use the same frontmatter — `title`, `description`, and `order`:

```markdown
---
title: "Setup Guide"
description: "Complete installation and configuration guide"
order: 1
---

(content)
```

The `order` field controls the navigation order within the guide's section on the website.

### Tutorials (`docs/tutorials/`)

Same format as general docs:

```markdown
---
title: "dlt"
description: "Ingest data from public APIs into Postgres using dlt"
order: 1
---

(content)
```

## Setup (Maintainer Only)

This section is only relevant for the repository owner. Forks do not need this setup — the sync workflow is skipped automatically.

### 1. Create a Cloudflare Deploy Hook

1. Go to Cloudflare Dashboard > Workers & Pages > `nexus-stack-ch` > Settings > Builds > Deploy Hooks
2. Create a hook:
   - **Name**: `nexus-stack-docs-sync`
   - **Branch**: `main`
3. Copy the generated URL

### 2. Add the Secret

1. Go to [Nexus-Stack repo settings > Secrets > Actions](https://github.com/stefanko-ch/Nexus-Stack/settings/secrets/actions)
2. Add a new secret:
   - **Name**: `WEBSITE_DEPLOY_HOOK`
   - **Value**: The Deploy Hook URL from step 1

### 3. Enable Website Sync

1. Go to [Nexus-Stack repo settings > Secrets and variables > Actions > Variables](https://github.com/stefanko-ch/Nexus-Stack/settings/variables/actions)
2. Add a new repository variable:
   - **Name**: `WEBSITE_SYNC_ENABLED`
   - **Value**: `true`

The sync workflow is gated on this variable. If it is missing or set to any other value, the job will be skipped.

## Fork Safety

The sync workflow is gated by three conditions that must all be true for it to run:

1. **Repository check** — `github.repository == 'stefanko-ch/Nexus-Stack'` in the job-level `if:`. This is the primary gate: forks have a different repository name, so the job is skipped entirely.
2. **Sync enabled** — `vars.WEBSITE_SYNC_ENABLED == 'true'` must be set as a repository variable. Not configured by default.
3. **Deploy hook configured** — `WEBSITE_DEPLOY_HOOK` secret must contain the Cloudflare Deploy Hook URL. The step fails if sync is enabled but the hook is missing.

Forks can safely ignore the `sync-docs-site.yml` workflow. The repository check alone prevents it from running.
