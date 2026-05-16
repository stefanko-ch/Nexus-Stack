---
title: "pgAdmin"
---

## pgAdmin

![pgAdmin](https://img.shields.io/badge/pgAdmin-336791?logo=postgresql&logoColor=white)

**PostgreSQL administration and development platform**

pgAdmin is the most popular and feature-rich Open Source administration and development platform for PostgreSQL. Features include:
- Graphical query builder and SQL editor
- Database object browser and editor
- Visual explain plans for query optimization
- Server dashboard with monitoring
- Backup and restore functionality
- User and permission management
- Support for PostgreSQL 10+ and all PostgreSQL extensions

| Setting | Value |
|---------|-------|
| Default Port | `5050` |
| Suggested Subdomain | `pgadmin` |
| Public Access | No (database administration) |
| Website | [pgadmin.org](https://www.pgadmin.org) |
| Source | [GitHub](https://github.com/pgadmin-org/pgadmin4) |

### Usage

1. Access pgAdmin at `https://pgadmin.<domain>`
2. Login with credentials from Infisical (`PGADMIN_USERNAME` / `PGADMIN_PASSWORD`)
3. **Pre-configured server:** The "Nexus PostgreSQL" server appears automatically in the left sidebar
4. Click on the server — it connects directly. **No password prompt.**

> ✅ **Auto-configured:** Both the admin account AND the Postgres connection (username `nexus-postgres` + password) are pre-configured. One click to connect.

### How the auto-connect works

At spin-up time, `src/nexus_deploy/service_env.py::_render_pgadmin` writes a `pgpass` sidecar file next to the compose file: `stacks/pgadmin/pgpass`, containing one line in standard libpq pgpass format:

```text
postgres:5432:postgres:nexus-postgres:<actual-postgres-password-from-infisical>
```

The compose file bind-mounts this as `/pgpass:ro` inside the pgAdmin container, and `servers.json` references it via `PassFile: /pgpass`. pgAdmin reads the password from there on every connect — no prompt, no copy-paste from Infisical.

#### Security note

- The pgpass file lives only on the server at `/opt/docker-server/stacks/pgadmin/pgpass`, accessible exclusively via SSH (Cloudflare Tunnel + key auth, no public port).
- pgAdmin itself is behind Cloudflare Access (email OTP) + a pgAdmin master password (`PGADMIN_PASSWORD` from Infisical) — anyone who could read the auto-connect password from inside pgAdmin could already retrieve it from Infisical (same access policy).
- No net additional exposure compared to manual password entry; just one less manual step.

#### Caveat: existing volumes

pgAdmin loads `servers.json` **only on the first container start with an empty `pgadmin-data` volume**. If you already have a deployment from before this change, the old "Nexus PostgreSQL" entry with `Username: postgres` is still in the volume. To pick up the corrected config, either:

- **Wipe the volume** (loses any other server configs you added): `ssh nexus "docker volume rm pgadmin_pgadmin-data"` then re-spin.
- **Manually fix in pgAdmin UI:** Right-click "Nexus PostgreSQL" → Properties → Connection tab → Username = `nexus-postgres`, Password file = `/pgpass` → Save.
