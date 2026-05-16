---
title: "Kestra"
---

## Kestra

![Kestra](https://img.shields.io/badge/Kestra-6047EC?logo=kestra&logoColor=white)

**Modern workflow orchestration for data pipelines & automation**

A powerful, event-driven workflow orchestration platform for building data pipelines, ETL processes, and infrastructure automation:
- Declarative YAML workflows
- Event-driven triggers (cron, webhooks, file, message queues)
- 400+ plugins (AWS, GCP, Azure, databases, APIs)
- Real-time execution monitoring
- Built-in code editor with live preview
- Docker-in-Docker task execution

| Setting | Value |
|---------|-------|
| Default Port | `8085` (→ internal 8080) |
| Suggested Subdomain | `kestra` |
| Public Access | **Never** (always protected) |
| Website | [kestra.io](https://kestra.io) |
| Source | [GitHub](https://github.com/kestra-io/kestra) |

> ✅ **Auth:** Cloudflare Access (email OTP) gates the UI at the edge. Kestra's own Basic-Auth popup is **disabled** by default to avoid double-authentication — students authenticate once via the CF OTP and land directly in the UI. The `KESTRA_ADMIN_USER` / `KESTRA_ADMIN_PASSWORD` env vars are still rendered for forward-compat (Kestra EE / OIDC), but unused while basic-auth is off.

### Architecture

The stack includes:
- **Kestra** - Main workflow engine with web UI
- **PostgreSQL** - Database for workflow state and metadata

### Authentication & RBAC

| Layer | What it does |
|---|---|
| **Cloudflare Access** (edge) | Email OTP. No unauthenticated request ever reaches the container. Audit log of who authenticated lives in the CF dashboard. |
| **Kestra Basic-Auth** | **Disabled** by default — see `stacks/kestra/docker-compose.yml` for the rationale comment. Re-enable only if you want the single shared `KESTRA_ADMIN_USER` name to appear in Kestra's audit log (instead of `anon/system`), or once you've moved to Kestra Enterprise with SSO/OIDC. Basic-Auth in OSS Kestra is a single shared admin — **it does NOT give per-user attribution**; every student would log in as the same admin. Real per-user attribution requires EE + SSO. |
| **Kestra namespaces** | Flow-level access boundaries (`my-flows.*`, `nexus-tutorials.*`). Independent of who's logged in — used for organizing flows, not gating them. |
