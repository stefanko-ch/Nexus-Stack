---
title: "NATS"
---

## NATS

![NATS](https://img.shields.io/badge/NATS-27AAE1?logo=natsdotio&logoColor=white)

**Lightweight messaging with JetStream persistence**

NATS is one small server for publish/subscribe, request/reply and, with JetStream, persistent streams, a key-value store and an object store.

| Setting | Value |
|---------|-------|
| In-cluster | `nats://nats:4222` |
| Credentials | `nexus-nats`, password generated per deployment (Infisical folder `nats`) |
| Monitoring | `http://nats:8222` (`/healthz`, `/varz`, `/jsz`), no auth, internal only |
| Web UI | None — internal only, no subdomain |
| Persistence | Docker volume `nats-data` (JetStream) |
| Website | [nats.io](https://nats.io) |

### Where it fits

[Kafka](kafka.md) and [Redpanda](redpanda.md) are partitioned logs built for throughput. [RabbitMQ](rabbitmq.md) is a queue broker. NATS is the lightweight option for messaging between services: subjects such as `orders.created` instead of topics, wildcards (`orders.*`, `orders.>`), and no partitions to plan.

### First steps

From a notebook on `app-network` (`pip install nats-py`):

```python
import asyncio
import nats

async def main():
    nc = await nats.connect("nats://nats:4222", user="nexus-nats", password="<NATS_PASSWORD>")
    js = nc.jetstream()
    await js.add_stream(name="ORDERS", subjects=["orders.>"])
    await js.publish("orders.created", b'{"id": 1}')

    sub = await js.pull_subscribe("orders.>", durable="reader")
    for msg in await sub.fetch(1):
        print(msg.subject, msg.data)
        await msg.ack()

    kv = await js.create_key_value(bucket="config")
    await kv.put("feature", b"on")
    print((await kv.get("feature")).value)
    await nc.close()

asyncio.run(main())
```

The Python snippet was not run here. The same operations were tested with the `nats` CLI: a stream, a published message, and a key-value bucket.

### Authentication

A client without the login gets `Authorization Violation`. The password is not in `nats-server.conf`. NATS reads it from the `NATS_PASSWORD` environment variable.

### Persistence

JetStream streams, key-value and object stores are in `nats-data`, limited to 10 GB on disk and 256 MB in memory.

- **`rebuild` (default): they do not survive a teardown.** NATS is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
