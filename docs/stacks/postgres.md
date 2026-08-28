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

`postgres:17-alpine`, as `services.yaml` has always declared.

⚠️ **It did not always run that.** Until [#715](https://github.com/stefanko-ch/Nexus-Stack/issues/715), nineteen stacks
declared an unprefixed `postgres` support-image key. `tofu output
image_versions` merges every stack's `support_images` into one flat map
with support images **last**, and Terraform's `merge()` gives the later
argument precedence — so `IMAGE_POSTGRES` resolved to whichever of the
nineteen the merge landed on (`postgres:16-alpine`, from windmill) and
overrode this stack's own image. This compose reads
`${IMAGE_POSTGRES:-postgres:17-alpine}`, so it ran **16-alpine** while
every declaration said 17.

With the keys prefixed, `IMAGE_POSTGRES` is this service's own image again
and the stack runs 17. **If your volume was initialised under 16, the
container will refuse to start** — PostgreSQL does not read a data
directory from an older major version, and logs:

```text
FATAL:  database files are incompatible with server
DETAIL: The data directory was initialized by PostgreSQL version 16,
        which is not compatible with this version 17.
```

Two ways out, both deliberate rather than automatic:

- **Dump and restore** — `pg_dump` from a 16 container, start 17, restore.
  The only option that keeps the data.
- **Start fresh** — remove the volume if the contents are disposable.

Stacks that bring their own database are unaffected: each now has its own
`IMAGE_<STACK>_POSTGRES` and keeps the version it already ran.

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
