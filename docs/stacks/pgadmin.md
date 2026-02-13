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
4. Click on the server and enter the password from Infisical (`POSTGRES_PASSWORD`)
   - Username is pre-configured as `postgres` (from `POSTGRES_USERNAME` in Infisical)
   - You only need to enter the password
5. The password is saved for future logins

> ✅ **Auto-configured:** Both the admin account and PostgreSQL server connection (including username) are pre-configured. You only need to enter the PostgreSQL password once.
