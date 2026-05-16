---
title: "Metabase"
---

## Metabase

![Metabase](https://img.shields.io/badge/Metabase-509EE3?logo=metabase&logoColor=white)

**Open-source business intelligence and analytics tool**

Metabase is an easy-to-use, open-source business intelligence tool that lets you ask questions about your data. Features include:
- Ask questions in plain English or SQL
- Create beautiful dashboards with drag & drop
- Connect to 20+ data sources (PostgreSQL, MySQL, MongoDB, etc.)
- Share insights with your team
- Schedule automated reports via email/Slack
- Embed charts in other applications

| Setting | Value |
|---------|-------|
| Default Port | `3000` |
| Suggested Subdomain | `metabase` |
| Public Access | No (contains business data) |
| Website | [metabase.com](https://www.metabase.com) |
| Source | [GitHub](https://github.com/metabase/metabase) |

> ✅ **Auto-configured:** Admin account is automatically created during deployment. Credentials are available in Infisical.

### Data persistence

Metabase's internal H2/DB and all user-created artefacts (dashboards, questions, collections, pulses, alerts, user settings) are bind-mounted onto the persistent Hetzner Volume at `/mnt/nexus-data/metabase/`. They survive normal `teardown` + `spin-up` cycles — students who build dashboards across multiple class sessions keep their work.

**What does NOT survive:** `gh workflow run destroy-all.yml -f confirm=DESTROY` explicitly wipes `/mnt/nexus-data/`. That's the only path that drops Metabase state.

**One-time caveat after this PR lands on an existing deployment:** the first spin-up after the bind-mount change starts Metabase against an EMPTY data dir (`/mnt/nexus-data/metabase/` didn't exist before). The previous `metabase_data` named-volume content is orphaned (not migrated automatically). Dashboards from before this change need to be either re-created or migrated manually via `docker cp metabase:/metabase-data/...` if the old volume still exists on the host (check `docker volume ls | grep metabase`).
