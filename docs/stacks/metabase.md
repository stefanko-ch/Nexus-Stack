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

Metabase's internal H2/DB and all user-created artefacts (dashboards, questions, collections, pulses, alerts, user settings) live under `/metabase-data` inside the container, bind-mounted onto `/mnt/nexus-data/metabase/` on the host.

`/mnt/nexus-data/` itself is **ephemeral host storage** — it's NOT a persistent Hetzner Volume anymore (RFC 0001 cutover replaced the block volume with **R2 snapshot/restore**). For Metabase artefacts to actually survive a teardown + spin-up cycle, the path is registered in `src/nexus_deploy/s3_restore.py::standard_targets` as an rsync target alongside Forgejo and Dify:

1. **Teardown** rsyncs `/mnt/nexus-data/metabase/` → `snapshots/<timestamp>/metabase/data/` on R2 before `tofu destroy` runs.
2. **Spin-up** rsyncs the latest snapshot back into `/mnt/nexus-data/metabase/` BEFORE the metabase container starts.
3. **Container start** — Metabase opens the H2 DB pre-populated with all the previous session's dashboards.

**What survives:** normal `teardown` + `spin-up` cycles, `tofu destroy` + `tofu apply`, scheduled teardown/spin-up workflows. All use the same R2 snapshot/restore cycle.

**What does NOT survive:** `gh workflow run destroy-all.yml -f confirm=DESTROY` if the operator also explicitly wipes the R2 bucket. By default the workflow preserves R2 (so snapshots stay), but an explicit R2-deletion drops Metabase state along with everything else.

**One-time caveat after this PR lands on an existing deployment:** the first spin-up after the bind-mount change starts Metabase against an EMPTY data dir (`/mnt/nexus-data/metabase/` didn't exist before, and the R2 bucket has no `metabase/data/` snapshot yet). The previous `metabase_data` named-volume content is orphaned (not migrated automatically). Dashboards from before this change have to be migrated explicitly — `docker cp metabase:/metabase-data/...` does NOT work because once the running container has the new bind-mount attached, that path inside the container is the empty bind-mount, not the old data.

**Migration recipe (run BEFORE the first post-merge spin-up, on an SSH session against the live host):**

```bash
# 1. Find the actual volume name. Docker Compose prefixes named
#    volumes with the compose-project name, so the volume declared as
#    `metabase_data` in the old stacks/metabase/docker-compose.yml
#    typically lives on disk as `metabase_metabase_data` (or
#    `<projectname>_metabase_data` when --project-name overrides are
#    in use). Grep returns the exact host name:
ssh nexus "docker volume ls | grep metabase_data"
# Example output:  local   metabase_metabase_data

# 2. Stop the metabase container so nothing's writing while we copy.
ssh nexus "docker stop metabase"

# 3. Run a throwaway helper container that mounts BOTH the OLD named
#    volume (use the exact name from step 1, INCLUDING any compose-
#    project prefix — replace 'metabase_metabase_data' below with
#    whatever step 1 printed) AND the new bind-mount, then copy the
#    content across. Alpine is pinned to a specific version so this
#    recipe stays reproducible if alpine:latest moves to a newer
#    distro release.
ssh nexus "docker run --rm \\
  -v metabase_metabase_data:/old-data:ro \\
  -v /mnt/nexus-data/metabase:/new-data \\
  alpine:3.20 \\
  sh -c 'cp -a /old-data/. /new-data/ && chown -R 2000:2000 /new-data'"

# 4. Run the next spin-up — Metabase starts against the populated
#    bind-mount with all your historical dashboards intact. The first
#    teardown that follows pushes the populated state to R2, and from
#    then on the snapshot/restore cycle takes over automatically.
```

If you skip the migration, dashboards are simply gone on first post-merge spin-up. The old named volume (whatever step 1 printed — `metabase_metabase_data` in the typical case) stays on the host unreferenced until you manually `docker volume rm <name>`.
