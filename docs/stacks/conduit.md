---
title: "Conduit"
---

## Conduit

![Conduit](https://img.shields.io/badge/Conduit-00A3E0?logoColor=white)

**Data streaming and CDC pipelines**

Conduit moves data between systems in real time. A pipeline reads from a source connector, runs processors, and writes to a destination. Built-in connectors cover PostgreSQL (including CDC), Kafka, S3, files, a generator and a log. It is one small Go binary.

| Setting | Value |
|---------|-------|
| Default Port | `8120` (bound to `127.0.0.1` on the host; container port `8080`) |
| In-cluster | `http://conduit:8080` (HTTP API), `conduit:8084` (gRPC) |
| Suggested Subdomain | `conduit` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | API token, generated per deployment (Infisical folder `conduit`) |
| Persistence | Docker volume `conduit-data` (connector positions) |
| Website | [conduit.io](https://conduit.io) |
| Source | [GitHub](https://github.com/ConduitIO/conduit) |

### Conduit next to Kafka Connect, Debezium and NiFi

[Debezium](debezium.md) and Kafka Connect are the JVM route to CDC, and [NiFi](nifi.md) is the visual flow tool. Conduit covers the straightforward pipelines with a fraction of the resources: it used 25 to 40 MB of memory in testing.

### Web UI and authentication

Open `https://conduit.<domain>` and enter `CONDUIT_API_TOKEN` from Infisical. The UI shows the pipelines and their status and can start and stop them. Every API call needs the token as `Authorization: Bearer <token>`.

The UI shows a banner saying *No auth configured — anyone who can reach this API can start or stop pipelines*. That banner is wrong here: with the token set, every unauthenticated call, stopping a pipeline included, is refused with `401` (tested).

### Pipelines

Pipelines are YAML files in `stacks/conduit/pipelines/` on the server, read when Conduit starts. The stack ships `demo.yaml`, which generates two records a second and writes them to Conduit's log, so a running pipeline is visible without any other stack.

A pipeline into the [Kafka](kafka.md) stack, tested with the Kafka stack enabled:

```yaml
version: "2.2"
pipelines:
  - id: to-kafka
    status: running
    name: to-kafka
    connectors:
      - id: generator
        type: source
        plugin: "builtin:generator"
        settings:
          format.type: structured
          format.options.id: int
          format.options.name: string
          operations: create
          rate: "2"
      - id: kafka
        type: destination
        plugin: "builtin:kafka"
        settings:
          servers: kafka:9092
          topic: conduit-demo
```

Save it next to `demo.yaml` and restart the container (`docker restart conduit`). The records arrive in `conduit-demo` as OpenCDC JSON.

### Persistence

Connector positions, the record of how far each source has read, are in `conduit-data`. The pipeline files live in the stack directory and come back with every deploy.

- **`rebuild` (default): positions do not survive a teardown,** so sources start reading from the beginning again.
- **`snapshot`: they survive**, because the whole disk is imaged.
