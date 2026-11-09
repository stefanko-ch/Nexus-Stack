---
title: "Oracle Database Free"
---

## Oracle Database Free

![Oracle](https://img.shields.io/badge/Oracle_Database_Free-F80000?logo=oracle&logoColor=white)

**Oracle Database 23ai, free edition**

The free edition of Oracle Database: the full SQL dialect, PL/SQL, JSON relational duality views and vector search. Oracle caps it at 2 CPUs, 2 GB of memory and 12 GB of user data. Next to [PostgreSQL](postgres.md), [MySQL](mysql.md) and [SQL Server](mssql.md), it covers the fourth common relational dialect.

| Setting | Value |
|---------|-------|
| In-cluster | `oracle:1521`, service `FREEPDB1` |
| Login | `nexus_oracle`, a schema user in `FREEPDB1` |
| Credentials | Password generated per deployment (Infisical folder `oracle`); SYS and SYSTEM have a separate one in the same folder |
| Web UI | None — internal only, no subdomain |
| Persistence | Docker volume `oracle-data` |
| Image | [`gvenzl/oracle-free`](https://github.com/gvenzl/oci-oracle-free), the community image |
| Licence | Oracle Free Use Terms — not an OSI licence |
| Website | [oracle.com/database/free](https://www.oracle.com/database/free/) |

Oracle identifiers cannot contain a hyphen, so the user is `nexus_oracle` rather than `nexus-oracle`.

### First steps

From a notebook, with [python-oracledb](https://python-oracledb.readthedocs.io) in thin mode (no Oracle client libraries needed):

```python
import oracledb

conn = oracledb.connect(user="nexus_oracle", password="<ORACLE_PASSWORD>", dsn="oracle:1521/FREEPDB1")
with conn.cursor() as cur:
    cur.execute("create table orders (id number primary key, amount number(10,2))")
    cur.executemany("insert into orders values (:1, :2)", [(1, 10.5), (2, 4.5)])
    conn.commit()
    cur.execute("select count(*), sum(amount) from orders")
    print(cur.fetchone())  # (2, 15)
```

SQLAlchemy uses `oracle+oracledb://nexus_oracle:<pw>@oracle:1521/?service_name=FREEPDB1`.

From the server, SQL*Plus in the container reads the connection from standard input, so the password stays off the command line:

```bash
docker exec -it oracle sqlplus /nolog
SQL> connect nexus_oracle/<ORACLE_PASSWORD>@localhost:1521/FREEPDB1
```

[CloudBeaver](cloudbeaver.md) and [DBeaver](https://dbeaver.io) connect with host `oracle`, port `1521`, service name `FREEPDB1`.

Tested: login, a table written and read, a wrong password refused (`ORA-01017`), data kept across a restart, and a password that starts with a digit.

### First start and passwords

The first start creates the database. On a laptop that took about 30 seconds; on a slower disk it can take a few minutes, and the healthcheck allows ten.

`ORACLE_PASSWORD` (SYS and SYSTEM) and `APP_USER_PASSWORD` (`nexus_oracle`) are read on that first start only. The image's entrypoint passes them to its own setup scripts inside the container during that start; they never appear on a `docker` command line. To change a password later, use `ALTER USER ... IDENTIFIED BY "..."` in SQL*Plus.

### Resources

Oracle's own limit is 2 GB of memory. The container limit is 3 GB, and it used about 2 GB when idle.

### Image updates

The community image's maintainer rebuilds existing tags in place to pick up base-image fixes, so `23.26.3-slim` can change under the same name. The database version it contains does not.

### Persistence

Data is in `oracle-data`.

- **`rebuild` (default): it does not survive a teardown.** Oracle is not in the R2 backup list.
- **`snapshot`: it survives**, because the whole disk is imaged.

### Licence

The image scripts are Apache-2.0. The database itself is under the [Oracle Free Use Terms and Conditions](https://www.oracle.com/downloads/licenses/oracle-free-license.html), which allow development, testing, teaching and production use within the edition's limits. They are not an OSI licence.
