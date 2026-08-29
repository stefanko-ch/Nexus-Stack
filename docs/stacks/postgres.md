---
title: "PostgreSQL"
---

## PostgreSQL

![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?logo=postgresql&logoColor=white)

**Powerful open-source relational database (internal-only)**

PostgreSQL is a powerful, open-source object-relational database system with over 35 years of active development. This stack provides a standalone PostgreSQL server accessible only within the Docker network.

**Important:** This service has **no web UI** and **no external access**. It runs only on the internal Docker network.

| Setting | Value |
|---------|-------|
| Internal Port | `5432` |
| External Access | **None** (internal-only) |
| Default User | `postgres` |
| Default Database | `postgres` |
| Website | [postgresql.org](https://www.postgresql.org) |
| Source | [GitHub](https://github.com/postgres/postgres) |

### Version

`postgres:18-alpine` — the current stable major, supported until
November 2030.

⚠️ **This stack previously ran 16-alpine, and not on purpose.** Until
[#715](https://github.com/stefanko-ch/Nexus-Stack/issues/715), nineteen
stacks declared an unprefixed `postgres` support-image key. `tofu output
image_versions` merges every stack's `support_images` into one flat map
with support images **last**, and Terraform's `merge()` gives the later
argument precedence — so `IMAGE_POSTGRES` resolved to whichever of the
nineteen the merge landed on (`postgres:16-alpine`, from windmill) and
overrode this stack's own image. The compose reads
`${IMAGE_POSTGRES:-postgres:18-alpine}`, so the declaration never reached
the container.

With the keys prefixed, `IMAGE_POSTGRES` is this service's own image
again. It went to 18 rather than the 17 it had been declaring, because
the fix forces one migration either way and 17 would have meant a second
one later.

**If your volume was initialised under an older major, the container will
refuse to start.** PostgreSQL does not read a data directory written by a
previous major version:

```text
FATAL:  database files are incompatible with server
DETAIL: The data directory was initialized by PostgreSQL version 16,
        which is not compatible with this version 18.
```

Two ways out, both deliberate rather than automatic:

- **Dump and restore** — `pg_dump` from a container on the old major,
  start 18, restore. The only option that keeps the data.
- **Start fresh** — remove the volume if the contents are disposable.

That refusal depends on one thing worth stating, because it does not hold
everywhere: **the data directory must be at the same path before and after
the bump.** This stack has always set
`PGDATA=/var/lib/postgresql/data/pgdata` explicitly, so the old cluster and
the new server look at the same place and the mismatch is caught.

A stack that gains an explicit `PGDATA` *as part of* moving to 18 — which is
required there, since the image default moved outside the mount — relocates
the directory in the same step. The new server never sees the old cluster,
so it does not refuse: it initialises an empty one and comes up healthy,
with the previous data sitting unused beside it. Quieter, and worse.
[#734](https://github.com/stefanko-ch/Nexus-Stack/issues/734) proposes the
preflight that would catch that case too.

Stacks that bring their own database are unaffected: each now has its own
`IMAGE_*` variable, derived from its `support_images` key, and keeps the
version it already ran. The suffix follows the key rather than a fixed
pattern — `IMAGE_KESTRA_POSTGRES` for the key `kestra-postgres`,
`IMAGE_LAKEKEEPER_DB` for `lakekeeper-db` — because the orchestrator
renders `IMAGE_<KEY>` with hyphens as underscores, uppercased.

Those versions are spread across 14 through 17 and are a separate question
from this stack — notably Infisical, still on **14**, which reaches end of
life on 2026-11-12 (#731).

### Access Methods

PostgreSQL is accessible via:

1. **pgAdmin or Adminer** (Web UIs)
   - Enable `pgadmin` or `adminer` stack
   - Connect to `postgres:5432`

2. **From other Docker containers**
   - Connection string: `postgresql://postgres:<password>@postgres:5432/postgres`
   - Get password from Infisical (`POSTGRES_PASSWORD`)

3. **Via SSH Tunnel** (for local tools like DBeaver, DataGrip)
   ```bash
   ssh -L 5432:postgres:5432 nexus
   # Then connect to localhost:5432
   ```

4. **Via Wetty** (terminal access)
   - Enable `wetty` stack
   - Run: `docker exec -it postgres psql -U postgres`

### Creating Databases and Users

```bash
# Via Wetty or SSH
docker exec -it postgres psql -U postgres

-- Create a new database
CREATE DATABASE myapp;

-- Create a new user
CREATE USER myapp_user WITH PASSWORD 'secure_password';

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE myapp TO myapp_user;
```

> 🔒 **Security:** PostgreSQL is not exposed to the internet. All access is via internal Docker network or SSH tunnel.
