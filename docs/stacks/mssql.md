---
title: "Microsoft SQL Server"
---

## Microsoft SQL Server

![SQL Server](https://img.shields.io/badge/SQL_Server-CC2927?logoColor=white)

**SQL Server 2025, Developer edition**

SQL Server on Linux with the full feature set of the Developer edition: T-SQL, stored procedures, columnstore indexes, temporal tables and change data capture. The Developer edition is licensed for development and test, not for production.

| Setting | Value |
|---------|-------|
| In-cluster | `mssql:1433` |
| Login | `nexus-mssql` (sysadmin) |
| Credentials | Password generated per deployment (Infisical folder `mssql`) |
| Web UI | None — internal only, no subdomain |
| Resources | 2 GB for SQL Server, 3 GB container limit |
| Persistence | Docker volume `mssql-data` |
| Website | [microsoft.com/sql-server](https://www.microsoft.com/sql-server) |

### Connecting

Any T-SQL client on `app-network` connects to `mssql:1433` as `nexus-mssql`. [CloudBeaver](cloudbeaver.md) and [Adminer](adminer.md) both support SQL Server.

From inside the container, on the server:

```bash
docker exec -it mssql /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U nexus-mssql
```

`sqlcmd` asks for the password (`MSSQL_PASSWORD` from Infisical), so it never appears on a command line. `-C` trusts the server's self-signed certificate.

### Accounts

`mssql-init` creates the `nexus-mssql` login with the sysadmin role on the first start. On later starts it resets that login's password to the generated one, so the value in Infisical stays right. The built-in `sa` gets its own generated password, which is not handed out.

### Telemetry and memory

Customer feedback (telemetry) is switched off in `mssql.conf` before the server starts; the log confirms `Software Usage Metrics is disabled`. `MSSQL_MEMORY_LIMIT_MB` caps SQL Server at 2 GB.

### Architecture

The image is published for `linux/amd64` only. The default servers are x86 (`cx43`), so it runs natively.

### Persistence

Databases are in `mssql-data`.

- **`rebuild` (default): they do not survive a teardown.** SQL Server is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
