---
title: "Windmill"
---

## Windmill

![Windmill](https://img.shields.io/badge/Windmill-3B82F6?logo=windowsterminal&logoColor=white)

**Open-source workflow engine for scripts, workflows, and UIs**

Windmill is a developer platform that turns scripts into production-grade workflows, UIs, and endpoints. It features a built-in code editor with LSP autocomplete and supports Python, TypeScript, Go, Bash, SQL, and more.

**Features:**
- **Script editor** - Built-in code editor with LSP autocomplete for Python, TypeScript, Go, Bash, SQL
- **Workflow builder** - Visual DAG editor for composing scripts into multi-step workflows
- **App builder** - Create custom UIs with drag-and-drop components backed by scripts
- **Schedules and triggers** - Cron schedules, webhooks, and event-driven triggers
- **Approval flows** - Human-in-the-loop steps with approval/rejection gates
- **Error handling** - Retries, error handlers, and recovery steps

| Setting | Value |
|---------|-------|
| Default Port | `8200` |
| Suggested Subdomain | `windmill` |
| Public Access | No (Cloudflare Access protected) |
| Default Enabled | No |
| Website | [windmill.dev](https://www.windmill.dev) |
| Source | [GitHub](https://github.com/windmill-labs/windmill) |

**Architecture (5 containers):**

| Container | Image | Purpose |
|-----------|-------|---------|
| `windmill` | `ghcr.io/windmill-labs/windmill:1.624.0` | API server + web UI (MODE=server) |
| `windmill-worker` | `ghcr.io/windmill-labs/windmill:1.624.0` | Default job executor |
| `windmill-worker-native` | `ghcr.io/windmill-labs/windmill:1.624.0` | Native lightweight workers (8 workers) |
| `windmill-lsp` | `ghcr.io/windmill-labs/windmill-lsp:latest` | LSP code intelligence for editor |
| `windmill-db` | `postgres:18-alpine` | Dedicated PostgreSQL database |

**Credentials:**
- Email: Your configured admin email (`$ADMIN_EMAIL`)
- Password: Auto-generated (stored in Infisical)

> ✅ **Auto-configured:** Admin user is automatically created during deployment with your admin email and a generated password. Credentials are available in Infisical.

**Internal connection (from other services):**
- PostgreSQL: `windmill-db:5432` (user: `nexus-windmill`, database: `windmill`)

## PostgreSQL 18

Windmill's database runs `postgres:18-alpine`, matching what upstream ships in its own compose file.

Under the default `rebuild` lifecycle this needs no action: the database is not in the S3 persistence set, so it is recreated from Windmill's own migrations on every spin-up.

⚠️ **Under the `snapshot` lifecycle an existing data directory carries
over physically, and the outcome is quieter than it looks.** This bump
introduced an explicit `PGDATA` at the same time, which relocates the data
directory. PostgreSQL 18 therefore does **not** find the old cluster and does
**not** refuse to start: it initialises a fresh, empty one at the new path and
comes up healthy, leaving the previous cluster in the volume untouched and
unused.

That is *not* the classic `database files are incompatible with server`
refusal described in [postgres.md](./postgres.md#version) — that one only
happens when the path is unchanged across the bump. Here it cannot, because
the path is part of what changed. [#734](https://github.com/stefanko-ch/Nexus-Stack/issues/734)
proposes the preflight that would make this loud.
