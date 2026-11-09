---
title: "RabbitMQ"
---

## RabbitMQ

![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?logo=rabbitmq&logoColor=white)

**Message broker with queues, exchanges and a management UI**

RabbitMQ routes messages through exchanges into queues, where consumers take them off and acknowledge them. Work queues, publish/subscribe, topic routing and dead-letter queues are all built from those pieces.

| Setting | Value |
|---------|-------|
| Default Port | `15672` (management UI, bound to `127.0.0.1` on the host) |
| In-cluster | `amqp://rabbitmq:5672` |
| Suggested Subdomain | `rabbitmq` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | `nexus-rabbitmq`, password generated per deployment (Infisical folder `rabbitmq`) |
| Persistence | Docker volume `rabbitmq-data` |
| Website | [rabbitmq.com](https://www.rabbitmq.com) |

### RabbitMQ next to Kafka

[Kafka](kafka.md) and [Redpanda](redpanda.md) are logs: messages stay, and every consumer reads at its own offset. RabbitMQ is a queue: a message goes to one consumer and is gone once acknowledged. Teaching when to use which needs both.

### Authentication

The built-in `guest` user only works from localhost, so the stack creates `nexus-rabbitmq` on the first start. The same login works for the management UI, its HTTP API and AMQP clients.

### First steps

```python
import pika

params = pika.ConnectionParameters(
    host="rabbitmq",
    credentials=pika.PlainCredentials("nexus-rabbitmq", "<RABBITMQ_PASSWORD>"),
)
with pika.BlockingConnection(params) as conn:
    ch = conn.channel()
    ch.queue_declare(queue="tasks", durable=True)
    ch.basic_publish(exchange="", routing_key="tasks", body=b"hello")
```

The queue and its message show up in the management UI under **Queues and Streams**.

### Persistence

Queues, exchanges, users and durable messages are in `rabbitmq-data`. The password takes effect when that volume is first created. After that, RabbitMQ keeps the user it made, as a database keeps its initial password.

- **`rebuild` (default): the data does not survive a teardown.** RabbitMQ is not in the R2 backup list.
- **`snapshot`: the data survives**, because the whole disk is imaged.
