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
| `windmill-db` | `postgres:16-alpine` | Dedicated PostgreSQL database |

**Credentials:**
- Email: Your configured admin email (`$ADMIN_EMAIL`)
- Password: Auto-generated (stored in Infisical)

> ✅ **Auto-configured:** Admin user is automatically created during deployment with your admin email and a generated password. Credentials are available in Infisical.

**Internal connection (from other services):**
- PostgreSQL: `windmill-db:5432` (user: `nexus-windmill`, database: `windmill`)
