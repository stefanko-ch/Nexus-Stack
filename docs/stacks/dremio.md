---
title: "Dremio"
---

## Dremio

![Dremio](https://img.shields.io/badge/Dremio-31B48D?logoColor=white)

**Lakehouse query engine with a SQL UI**

Dremio queries data where it lies: object storage, Iceberg catalogs, relational databases and files, through one SQL layer. It brings a web SQL editor, a semantic layer of virtual datasets, and reflections, which are materialised copies that accelerate repeated queries.

| Setting | Value |
|---------|-------|
| Default Port | `9047` (bound to `127.0.0.1` on the host) |
| In-cluster | `dremio:31010` (JDBC/ODBC), `dremio:32010` (Arrow Flight), `http://dremio:9047` (REST) |
| Suggested Subdomain | `dremio` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | Admin `nexus-admin`, password generated per deployment (Infisical folder `dremio`) |
| Resources | 4 GB for Dremio (its minimum), 5 GB container limit |
| Persistence | Docker volume `dremio-data` |
| Website | [dremio.com](https://www.dremio.com) |
| Source | [GitHub](https://github.com/dremio/dremio-oss) |

### Dremio next to Trino

[Trino](trino.md) is a federated SQL engine without a UI of its own. Dremio adds the web editor, virtual datasets and reflections, and has a source type for [Nessie](nessie.md).

### Authentication

The first user created becomes the admin, and after that Dremio refuses to create another first user. `dremio-init` claims it on the first start as `nexus-admin` with a generated password, and checks that it logs in as admin. If someone created the first user in the seconds before, it fails with a message saying so; reset `dremio-data` to reclaim it.

### First steps

1. Log in as `nexus-admin` with `DREMIO_PASSWORD` from Infisical.
2. Add a source under **Sources**, for example object storage such as [MinIO](minio.md) through the S3 source type, a PostgreSQL database, or a [Nessie](nessie.md) catalog. Connecting Nessie has not been tested here.
3. Query in the SQL editor. A query that needs no source:

```sql
SELECT 1 + 1 AS two
```

From Python, the REST API runs SQL as a job:

```python
import requests, time

base = "http://dremio:9047"
token = requests.post(f"{base}/apiv2/login",
    json={"userName": "nexus-admin", "password": "<DREMIO_PASSWORD>"}).json()["token"]
h = {"Authorization": f"_dremio{token}"}
job = requests.post(f"{base}/api/v3/sql", headers=h, json={"sql": "SELECT 1 + 1 AS two"}).json()["id"]
while requests.get(f"{base}/api/v3/job/{job}", headers=h).json()["jobState"] != "COMPLETED":
    time.sleep(1)
print(requests.get(f"{base}/api/v3/job/{job}/results", headers=h).json()["rows"])  # [{'two': 2}]
```

### Resources

Dremio refuses to start with less than 4 GB (`Dremio requires at least 4 GB memory to run`), so `DREMIO_MAX_MEMORY_SIZE_MB` is 4096 and the container limit 5 GB. That makes it one of the heaviest stacks: enable it when it is needed.

### Persistence

Sources, virtual datasets, reflections and users are in `dremio-data`.

- **`rebuild` (default): they do not survive a teardown.** Dremio is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
