---
title: "ksqlDB"
---

## ksqlDB

![ksqlDB](https://img.shields.io/badge/ksqlDB-231F20?logo=apachekafka&logoColor=white)

**Streaming SQL on Kafka**

ksqlDB runs SQL over Kafka topics. `CREATE STREAM` and `CREATE TABLE` describe topics, and persistent queries filter, join and aggregate them continuously. Their results are materialized views that answer pull queries, while push queries stream every change.

| Setting | Value |
|---------|-------|
| In-cluster | `http://ksqldb:8088` (REST API) |
| Requires | The [Kafka](kafka.md) stack (`kafka:9092`) |
| Credentials | None — internal only |
| Web UI | None — no subdomain |
| Persistence | In Kafka topics |
| License | Confluent Community License |
| Website | [ksqldb.io](https://ksqldb.io) |

### Authentication

None. Like the Kafka broker it runs on, ksqlDB is reachable only from containers on `app-network`. It is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`, which keeps it from ever getting a public port.

### First steps

Open the ksql CLI inside the container:

```bash
docker exec -it ksqldb ksql http://localhost:8088
```

```sql
SET 'auto.offset.reset' = 'earliest';

CREATE STREAM orders (id INT, amount DOUBLE)
  WITH (KAFKA_TOPIC = 'orders', VALUE_FORMAT = 'JSON', PARTITIONS = 1);

INSERT INTO orders (id, amount) VALUES (1, 10.5);
INSERT INTO orders (id, amount) VALUES (2, 4.5);

CREATE TABLE totals AS
  SELECT 'all' AS k, SUM(amount) AS total, COUNT(*) AS n
  FROM orders GROUP BY 'all' EMIT CHANGES;

SELECT * FROM totals;   -- all | 15.0 | 2
```

The REST API takes the same statements, for example from a notebook:

```python
import requests

requests.post("http://ksqldb:8088/ksql",
    headers={"Content-Type": "application/vnd.ksql.v1+json"},
    json={"ksql": "SHOW STREAMS;"}).json()
```

### Resources

The image would start the JVM with a 3 GB heap; it is capped at 640 MB, inside a 1 GB container limit.

### Persistence

ksqlDB keeps its queries in a command topic and its state in changelog topics, so everything lives in Kafka. It survives exactly as long as the Kafka stack's data does.

### License

The image is under the [Confluent Community License](https://www.confluent.io/confluent-community-license/), which is not an OSI open-source licence. Read its terms before using ksqlDB beyond learning and internal use.
