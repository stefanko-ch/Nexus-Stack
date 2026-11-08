---
title: "Apache Kafka"
---

## Apache Kafka

![Apache Kafka](https://img.shields.io/badge/Apache_Kafka-231F20?logo=apachekafka&logoColor=white)

**The reference event-streaming broker, in KRaft mode**

Apache Kafka is the distributed log behind most event-streaming architectures:
- producers append to partitioned topics;
- consumer groups read them independently;
- the data stays for replay.

This stack runs one node that is both broker and controller (KRaft mode, no ZooKeeper), sized for teaching.

| Setting | Value |
|---------|-------|
| Bootstrap server | `kafka:9092`, inside `app-network` only |
| Public Access | None — internal only |
| Credentials | None (`PLAINTEXT` listener) |
| Heap | 512 MB, container limit 1 GB |
| Persistence | Docker volume `kafka-data` (see [Persistence](#persistence)) |
| Website | [kafka.apache.org](https://kafka.apache.org) |
| Source | [GitHub](https://github.com/apache/kafka) |

### Kafka next to Redpanda

[Redpanda](redpanda.md) speaks the same protocol and is the lighter choice. This stack is the Apache implementation, for courses that want the original and its own tooling. Both can run at once: Redpanda is at `redpanda:9092`, Kafka at `kafka:9092`.

### Connecting

From a notebook on `app-network`:

```python
from confluent_kafka import Producer

producer = Producer({"bootstrap.servers": "kafka:9092"})
producer.produce("events", b"hello")
producer.flush()
```

The command-line tools are in the container:

```bash
ssh nexus "docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic events"
ssh nexus "docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list"
```

[Kafka UI](kafka-ui.md) and [AKHQ](akhq.md) are configured for Redpanda. To browse this broker with them, add a cluster with bootstrap server `kafka:9092`.

### Authentication

The listener is `PLAINTEXT` without authentication: anything on `app-network` can produce and consume. That is why the stack is internal only. It has no hostname and no firewall rule, and it is on the `NO_OWN_AUTH` list in `tests/unit/test_stack_conventions.py`, which keeps it that way. The Kafka protocol cannot cross the HTTPS tunnel anyway.

### Persistence

Topic data is in the `kafka-data` volume.

- **`rebuild` (default): topics do not survive a teardown.** Kafka is not in the R2 backup list.
- **`snapshot`: topics survive**, because the whole disk is imaged.
