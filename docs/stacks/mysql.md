---
title: "MySQL"
---

## MySQL

![MySQL](https://img.shields.io/badge/MySQL-4479A1?logo=mysql&logoColor=white)

**MySQL 8.4 LTS**

The most widely used open-source relational database, and the usual source in change-data-capture exercises.

| Setting | Value |
|---------|-------|
| In-cluster | `mysql:3306`, database `nexus` |
| User | `nexus-mysql` |
| Credentials | Password generated per deployment (Infisical folder `mysql`) |
| Web UI | None — internal only, no subdomain |
| Persistence | Docker volume `mysql-data` |
| Website | [mysql.com](https://www.mysql.com) |

### Connecting

Any MySQL client on `app-network` connects to `mysql:3306` as `nexus-mysql`. [CloudBeaver](cloudbeaver.md) and [Adminer](adminer.md) both support MySQL.

```python
import pymysql

conn = pymysql.connect(host="mysql", user="nexus-mysql",
                       password="<MYSQL_PASSWORD>", database="nexus")
```

The root password is generated too and is not handed out.

### Change data capture

Binary logging is on by default in MySQL 8.4, in `ROW` format, which is what [Debezium](debezium.md)'s MySQL connector reads. `nexus-mysql` gets the privileges that connector needs on the first start: `RELOAD`, `FLUSH_TABLES`, `REPLICATION SLAVE` and `REPLICATION CLIENT` (`01-cdc-grants.sql`). Connecting Debezium to it has not been tested here.

### Persistence

Databases are in `mysql-data`. The passwords and grants take effect when that volume is first initialised.

- **`rebuild` (default): the data does not survive a teardown.** MySQL is not in the R2 backup list.
- **`snapshot`: the data survives**, because the whole disk is imaged.
