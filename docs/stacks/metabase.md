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

**One-time caveat after this PR lands on an existing deployment:** the first spin-up after the bind-mount change starts Metabase against an EMPTY data dir (`/mnt/nexus-data/metabase/` didn't exist before). The previous `metabase_data` named-volume content is orphaned (not migrated automatically). Dashboards from before this change have to be migrated explicitly — `docker cp metabase:/metabase-data/...` does NOT work because once the running container has the new bind-mount attached, that path inside the container is the empty bind-mount, not the old data.

**Migration recipe (run BEFORE the first post-merge spin-up, or temporarily on an SSH session before deploying the new compose):**

```bash
# 1. Verify the old named volume still exists on the host.
ssh nexus "docker volume ls | grep metabase_data"

# 2. Stop the metabase container so nothing's writing while we copy.
ssh nexus "docker stop metabase"

# 3. Run a throwaway helper container that mounts the OLD named volume +
#    the NEW bind-mount side-by-side, then rsync the content across.
ssh nexus "docker run --rm \\
  -v metabase_data:/old-data:ro \\
  -v /mnt/nexus-data/metabase:/new-data \\
  alpine:latest \\
  sh -c 'cp -a /old-data/. /new-data/ && chown -R 2000:2000 /new-data'"

# 4. Now run the next spin-up — Metabase starts against the populated
#    bind-mount with all your historical dashboards intact.
```

If you skip the migration, dashboards are simply gone on first post-merge spin-up. The old `metabase_data` named volume stays on the host (unreferenced) until you manually `docker volume rm metabase_data`.
