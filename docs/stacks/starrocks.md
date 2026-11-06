---
title: "StarRocks"
---

## StarRocks

![StarRocks](https://img.shields.io/badge/StarRocks-1F4FFF?logo=apache&logoColor=white)

**Fast MPP analytics database (MySQL protocol) that queries Iceberg, Delta Lake and Parquet in place**

StarRocks is a columnar, massively parallel OLAP database built for sub-second aggregations over large tables. Beyond its own tables it queries the lakehouse in place: external catalogs read Iceberg, Delta Lake, Hive and Paimon, and `FILES()` reads Parquet straight from S3-compatible storage.

| Setting | Value |
|---------|-------|
| Endpoint | `starrocks:9030` (MySQL protocol), inside `app-network` |
| Host port | `9030`, bound to `127.0.0.1` — for an SSH tunnel |
| Web UI | None (internal-only service) |
| Credentials | `nexus-starrocks` (admin role), password generated per deployment |
| Persistence | `/mnt/nexus-data/starrocks`, backed up to R2 |
| Website | [starrocks.io](https://www.starrocks.io) |
| Source | [GitHub](https://github.com/StarRocks/starrocks) |

### Connecting

Any MySQL client works. The account is `nexus-starrocks`, with StarRocks' `root` role; the username and password are in Infisical, folder `starrocks`, as `STARROCKS_USERNAME` and `STARROCKS_PASSWORD`.

- **CloudBeaver / Adminer** in the stack: a MySQL connection to host `starrocks`, port `9030`, user `nexus-starrocks`.
- **From a notebook:**
  ```python
  import pymysql
  conn = pymysql.connect(host="starrocks", port=9030, user="nexus-starrocks", password="<STARROCKS_PASSWORD>")
  ```
- **From a laptop:** `ssh -N -L 9030:localhost:9030 nexus`, then `mysql -h 127.0.0.1 -P 9030 -u nexus-starrocks -p`.

A single backend means every table needs `"replication_num" = "1"` unless the default already says so.

### The credentials, and why there is a start script

The image's own start script connects as `root` on every start, using `MYSQL_PWD` as the password. On the very first start `root` has no password yet, and a set `MYSQL_PWD` makes that connection fail — "Password error, stop retrying!" and a forced shutdown (measured on 4.1.7).

`stacks/starrocks/start.sh` therefore wraps the entrypoint:

- **Until the credentials are set:** `MYSQL_PWD` stays unset, and a background job runs once the bootstrap has finished. It gives `root` the generated password and creates `nexus-starrocks` with the same password and the `root` role, the SQL going in on stdin so the password is not in the process list.
- **After that:** `MYSQL_PWD` carries the password on every start, including one after a restore from R2.

Which of the two applies is decided by a marker, `/opt/nexus/state/credentials-set`, written only after the SQL succeeded. It lives in `/mnt/nexus-data/starrocks/nexus`, inside the backed-up directory, so a restore brings it back with the data it describes. Deciding by "FE metadata exists" instead would hand `MYSQL_PWD` to a restart after a failed attempt, and the container would then shut itself down on every start.

`root` keeps a password because the image's scripts need it; the account to use is `nexus-starrocks`, following this repository's rule against default account names. The renderer only lets an alphanumeric password through, because `start.sh` quotes it inside SQL.

The password is kept across a rebuild teardown, because the restored metadata holds it. Checked locally: after the first start the marker was written and an empty root password refused; after removing and recreating the container on the same data, StarRocks started cleanly and data written before was still there; and from another container on `app-network`, `nexus-starrocks` could create a database and table and showed `GRANT 'root'`, while a connection without a password was refused.

### Memory

Heavy for a shared server. `fe.conf` ships `-Xmx8192m` and the backend takes 90% of the host's memory by default; `start.sh` caps the frontend heap at 2 GB and the backend at `mem_limit = 3G`. Container limit: 6 GB. Measured idle: about 0.9 GB.

### The all-in-one image

One frontend and one backend in one container, as StarRocks publishes it for local testing. Right-sized for teaching; no high availability. `hostname` is fixed in the compose file because a persisted frontend refuses to start under a different host name.

### Health

The image's own `health_check.sh`: the bootstrap has finished, and the frontend's and backend's `/api/health` answer.
