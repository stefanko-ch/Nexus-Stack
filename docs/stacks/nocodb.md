## NocoDB

![NocoDB](https://img.shields.io/badge/NocoDB-1F2937?logo=nocodb&logoColor=white)

**Open-source Airtable alternative that turns any database into a smart spreadsheet**

NocoDB turns any database into a smart spreadsheet with a modern web UI. Create tables, views, forms, and automations without code. All data is stored in a dedicated PostgreSQL database.

| Setting | Value |
|---------|-------|
| Default Port | `8091` (mapped from internal `8080`) |
| Suggested Subdomain | `nocodb` |
| Public Access | No (Cloudflare Access) |
| Website | [nocodb.com](https://nocodb.com) |
| Source | [GitHub](https://github.com/nocodb/nocodb) |

### Architecture

The stack includes:
- **NocoDB** - Web application (Airtable-like spreadsheet interface)
- **PostgreSQL** - Dedicated database for NocoDB metadata and user data

### Usage

1. Access at `https://nocodb.<domain>`
2. Default credentials:
   - Username: `admin_email` (from Infisical: `NOCODB_USERNAME`)
   - Password: From Infisical (`NOCODB_PASSWORD`)
3. Auto-setup creates the admin account on first deployment
4. Create bases, tables, views, forms, and automations

### Data Persistence

NocoDB stores all data in the PostgreSQL database and application data volume. The `nocodb-data` and `nocodb-db-data` Docker volumes are mounted to the Hetzner persistent volume, ensuring data survives teardown and spin-up.
