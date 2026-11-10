---
title: "DataOps TestGen"
---

## DataOps TestGen

![DataOps TestGen](https://img.shields.io/badge/DataOps_TestGen-06B6D4?logoColor=white)

**Data quality tests generated from data profiles**

TestGen connects to a database and profiles every column. From the profile it generates validation tests: value ranges, patterns, freshness, row counts and referential checks. It runs them on a schedule and scores each table. Next to [Soda](soda.md), whose checks you write yourself, TestGen writes them for you and shows the results in a UI.

| Setting | Value |
|---------|-------|
| URL | `https://testgen.<domain>` |
| In-cluster | `http://testgen:8530` (REST API and MCP server) |
| Login | `nexus-admin` |
| Credentials | Password generated per deployment (Infisical folder `testgen`) |
| Persistence | Docker volumes `testgen-db-data` and `testgen-data` |
| Licence | Apache-2.0 |
| Website | [datakitchen.io](https://datakitchen.io/dataops-testgen/) |

### First steps

1. Open `https://testgen.<domain>` and log in as `nexus-admin` with `TESTGEN_PASSWORD` from Infisical.
2. Under **Connections**, add a database. Supported targets include PostgreSQL, Snowflake, Databricks, SQL Server, Redshift and BigQuery. The [Postgres](postgres.md) stack is at host `postgres`, port `5432`.
3. Create a **table group** (a schema or a set of tables), run **profiling**, then **generate tests** and **run tests**. The results show per table, with a score.

To try it without your own data, TestGen can build a demo database and run the whole cycle on it:

```bash
docker exec testgen testgen quick-start
```

`quick-start` recreates the demo database and, while doing so, closes every open connection to TestGen's own database, the web UI's included. The UI does not reconnect: on the server it showed only its title until the container was restarted. Restart it after a quick-start:

```bash
docker restart testgen
```

Tested:
- the system database was set up on the first start and upgraded on the second;
- `nexus-admin` was stored with the generated password, checked against its bcrypt hash; a wrong password did not match;
- `quick-start` profiled 64 columns, generated 227 tests and recorded 1,623 test results;
- the tests were kept across a restart.

**Not tried here:** logging in through the browser.

### Setup and upgrades

`testgen-init` runs before the app on every start:
- **If the system database does not exist,** it runs `testgen setup-system-db`, which creates it and `nexus-admin`.
- **If it exists,** it runs `testgen upgrade-system-version`, as upstream's installer does after an image update.

The decision is made on whether the database exists, not on whether the upgrade failed. An upgrade that fails for any other reason fails the init, rather than falling through to a fresh setup.

### Keys

TestGen encrypts the target-database credentials it stores with `TG_DECRYPT_SALT` and `TG_DECRYPT_PASSWORD`. It signs its tokens with `TG_JWT_HASHING_KEY`, a base64 string of 32 bytes. All three are generated once per stack. New values would make the stored credentials unreadable.

### Resources

The app (UI, scheduler and API in one container) used about 800 MB after the demo run, and its PostgreSQL about 50 MB. Upstream's installer allows 10 GB for large profiling runs. Here the limit is 2 GB, which suits teaching-size databases.

### Persistence

Connections, profiles, tests and results are in TestGen's PostgreSQL (`testgen-db-data`).

- **`rebuild` (default): they do not survive a teardown.** TestGen is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
