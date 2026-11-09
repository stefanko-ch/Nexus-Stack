---
title: "Apache Fluss"
---

## Apache Fluss

![Apache Fluss](https://img.shields.io/badge/Apache_Fluss-1E40AF?logo=apache&logoColor=white)

**Streaming storage for real-time analytics**

Apache Fluss stores streams for [Flink](flink.md). Log tables are append-only like a Kafka topic, but stored and read column by column. Primary-key tables can be looked up and updated in place by a Flink job, which Kafka cannot do. Fluss sits between [Kafka](kafka.md) and the lakehouse.

| Setting | Value |
|---------|-------|
| In-cluster | `fluss:9123` (bootstrap servers) |
| Login | `nexus_fluss`, SASL/PLAIN |
| Credentials | Password generated per deployment (Infisical folder `fluss`) |
| Web UI | None — internal only, no subdomain |
| Containers | `fluss` (coordinator), `fluss-tablet` (tablet server), `fluss-zookeeper` |
| Persistence | Docker volumes `fluss-data`, `fluss-zookeeper-data`, `fluss-zookeeper-datalog` |
| Licence | Apache-2.0 |
| Website | [fluss.apache.org](https://fluss.apache.org) |

Fluss usernames allow letters, digits and underscores only, so the user is `nexus_fluss` rather than `nexus-fluss`.

### First steps

Enable the Flink stack too: its image ships the Fluss connector for Flink 1.20. In the Flink SQL client (`docker exec -it flink ./bin/sql-client.sh`):

```sql
CREATE CATALOG fluss WITH (
  'type' = 'fluss',
  'bootstrap.servers' = 'fluss:9123',
  'client.security.protocol' = 'SASL',
  'client.security.sasl.mechanism' = 'PLAIN',
  'client.security.sasl.username' = 'nexus_fluss',
  'client.security.sasl.password' = '<FLUSS_PASSWORD>'
);
USE CATALOG fluss;

CREATE TABLE orders (id INT, amount DOUBLE, PRIMARY KEY (id) NOT ENFORCED);

SET 'execution.runtime-mode' = 'batch';
INSERT INTO orders VALUES (1, 10.5), (2, 4.5);
SELECT * FROM orders WHERE id = 1;  -- 1 | 10.5
```

A table without a primary key is a log table. In streaming mode, `SELECT * FROM orders` keeps running and shows changes as they arrive.

Tested with Flink 1.20.1 and the connector: the catalog created, a primary-key table written and both rows read back, a wrong password refused (`AuthenticationException: Invalid username or password`), the rows read again after the Fluss containers were recreated.

### How it is set up

- **ZooKeeper** holds the cluster metadata.
- **The coordinator** (`fluss`) manages tables and assigns buckets. Clients bootstrap through it.
- **One tablet server** (`fluss-tablet`) stores the data.

Each server has two listeners. `CLIENT` on 9123 is the one clients use, with SASL/PLAIN. `INTERNAL` on 9124 is plaintext, for the servers among themselves; it is never advertised to clients. ZooKeeper is on a separate internal network and is not reachable from `app-network`.

### Passwords and logs

The image's entrypoint appends `FLUSS_PROPERTIES` to `conf/server.yaml` on each start and fills `${...}` references from the environment, so the password reaches no argument list. It does end up in that file inside the container.

- **No duplicate configuration.** Because a restart would append the block a second time, each start first restores the file the image shipped. Tested with `docker restart`.
- **No password in the log.** Fluss logs every setting at startup and masks keys that contain `jaas.config`, but not `credentials`. So the user is declared with `security.sasl.plain.jaas.config`, which shows as `******`, rather than the shorter `security.sasl.plain.credentials`, which would print the password.

### Resources

The coordinator has a 512 MB heap in a 1 GB container, the tablet server 768 MB in 1.5 GB, ZooKeeper 256 MB in 512 MB. Together they used about 380 MB when idle. Fluss's own guide recommends 4 cores and 16 GB for production clusters.

### Persistence

Log and KV segments are in `fluss-data`, which both servers mount as Fluss's own Docker example does. ZooKeeper's data is in its two volumes.

- **`rebuild` (default): they do not survive a teardown.** Fluss is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.

There is no remote tier to object storage configured, so all data stays on the server's disk.
