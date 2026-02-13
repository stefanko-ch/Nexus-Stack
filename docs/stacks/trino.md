## Trino

![Trino](https://img.shields.io/badge/Trino-DD00A1?logo=trino&logoColor=white)

**Distributed SQL query engine for federated data access**

Trino is a fast, distributed SQL query engine that can query data across multiple sources (ClickHouse, PostgreSQL, MySQL, S3, and more) without moving data. Run a single SQL query that joins data from different databases.

| Setting | Value |
|---------|-------|
| Default Port | `8060` (mapped from container 8080) |
| Suggested Subdomain | `trino` |
| Public Access | No |
| Website | [trino.io](https://trino.io) |
| Source | [GitHub](https://github.com/trinodb/trino) |

### Configuration

- **Authentication:** None (Cloudflare Access provides authentication)
- **Dynamic catalogs:** Enabled via `CATALOG_MANAGEMENT=dynamic` - add new data sources at runtime
- **Pre-configured catalogs:**
  - `clickhouse` - connects to ClickHouse on the same server (if enabled)
  - `postgresql` - connects to PostgreSQL on the same server (if enabled)

### Usage

1. Enable the service in Control Plane
2. Access `https://trino.YOUR_DOMAIN` for the Web UI
3. Run SQL queries across connected data sources:
   ```sql
   -- Query ClickHouse data
   SELECT * FROM clickhouse.default.my_table LIMIT 10;

   -- Query PostgreSQL data
   SELECT * FROM postgresql.public.users LIMIT 10;

   -- Join across data sources
   SELECT u.name, e.event_type
   FROM postgresql.public.users u
   JOIN clickhouse.default.events e ON u.id = e.user_id;
   ```
