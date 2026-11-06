---
title: "Bytebase"
---

## Bytebase

![Bytebase](https://img.shields.io/badge/Bytebase-5B4FE9?logoColor=white)

**Database schema changes as reviewed, versioned work**

Bytebase brings code review to database changes. A change is a plan of SQL statements:
- SQL review rules check it before it runs (naming, a missing `WHERE`, a dropped column and more);
- it rolls out per environment;
- it is recorded with its author, so every schema has a history.

Bytebase manages PostgreSQL, MySQL, ClickHouse, MongoDB and more, so the databases already running here can be added as instances.

| Setting | Value |
|---------|-------|
| Default Port | `8113` (bound to `127.0.0.1` on the host) |
| Suggested Subdomain | `bytebase` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | The stack user's email, password generated per deployment |
| Persistence | Dedicated PostgreSQL (`bytebase-db`) in a Docker volume |
| Website | [bytebase.com](https://www.bytebase.com) |
| Source | [GitHub](https://github.com/bytebase/bytebase) |

### Login

The first account to sign up becomes the workspace admin. So that this is never a stranger, `bytebase-init` claims it on the first start with the stack user's email (or `admin_email` if no user is configured) and a generated password, Infisical folder `bytebase`, key `BYTEBASE_PASSWORD`. It also turns off Bytebase's metric collection.

On every later start it logs in instead and stops if the password no longer matches. The claim races anyone who opens the page in the seconds after Bytebase becomes healthy, so `bytebase-init` polls every second. If someone does sign up first, the generated account becomes a member, the settings change is refused with 403, and `bytebase-init` exits with a message saying so. The smoke check reports an init container that exits non-zero. Resetting `bytebase-db` lets the next start claim the admin again.

**Further sign-ups stay open.** Turning them off is a paid feature (`FEATURE_DISALLOW_SELF_SERVICE_SIGNUP` is a TEAM feature), so anyone who reaches the page can create an account. Bytebase makes such accounts workspace members, not admins, and only people on the Cloudflare Access whitelist reach the page at all.

### Adding a database

In Bytebase, **Instances → Add instance**, then use the host and port inside `app-network`:

| Database | Host | Port | Credentials |
|---|---|---|---|
| Shared PostgreSQL | `postgres` | `5432` | Infisical folder `postgres` |
| ClickHouse | `clickhouse` | `9000` | Infisical folder `clickhouse` |
| StarRocks (MySQL protocol) | `starrocks` | `9030` | Infisical folder `starrocks` |

### Persistence

Projects, plans and instance definitions live in `bytebase-db`, a PostgreSQL 17 in the `bytebase-db-data` volume.

- **`rebuild` (default): the data does not survive a teardown.** Bytebase is not in the R2 backup list. The next spin-up claims the admin again with a freshly generated password.
- **`snapshot`: the data survives**, because the whole disk is imaged.
