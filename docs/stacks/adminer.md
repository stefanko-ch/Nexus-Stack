## Adminer

![Adminer](https://img.shields.io/badge/Adminer-34567C?logo=adminer&logoColor=white)

**Lightweight database management tool**

Adminer is a full-featured database management tool written in a single PHP file. Despite its small size, it supports a wide range of databases and provides essential features for database administration. Features include:
- Support for PostgreSQL, MySQL, SQLite, MS SQL, Oracle, MongoDB, and more
- SQL query editor with syntax highlighting
- Table structure viewer and editor
- Data import/export (SQL, CSV)
- User and permission management
- Lightweight alternative to phpMyAdmin or pgAdmin

| Setting | Value |
|---------|-------|
| Default Port | `8888` |
| Suggested Subdomain | `adminer` |
| Public Access | No (database access) |
| Website | [adminer.org](https://www.adminer.org) |
| Source | [GitHub](https://github.com/vrana/adminer) |

### Usage

1. Access Adminer at `https://adminer.<domain>`
2. Login page shows pre-filled connection details:
   - **System**: PostgreSQL (select if not pre-selected)
   - **Server**: `postgres` (pre-filled)
   - **Username**: From Infisical (`POSTGRES_USERNAME`)
   - **Password**: From Infisical (`POSTGRES_PASSWORD`)
   - **Database**: `postgres` (or leave empty to see all databases)
3. Click "Login"

> ℹ️ **Note:** Server hostname is pre-configured as `postgres`. Get username and password from Infisical - you need to enter them on each login (Adminer doesn't save credentials).
