---
title: "Eclipse Mosquitto"
---

## Eclipse Mosquitto

![Mosquitto](https://img.shields.io/badge/Mosquitto-3C5280?logo=eclipsemosquitto&logoColor=white)

**MQTT broker for IoT data**

MQTT is how devices publish telemetry: small messages on hierarchical topics such as `factory/line1/temperature`, with QoS levels and retained messages. Mosquitto is the reference broker.

| Setting | Value |
|---------|-------|
| In-cluster | `mqtt://mosquitto:1883` |
| Credentials | `nexus-mosquitto`, password generated per deployment (Infisical folder `mosquitto`) |
| Web UI | None — internal only, no subdomain |
| Persistence | Docker volume `mosquitto-data` |
| Website | [mosquitto.org](https://mosquitto.org) |

### Where it fits

Mosquitto is the entry point of an IoT pipeline: [Node-RED](node-red.md), [Redpanda Connect](redpanda-connect.md), [Conduit](conduit.md) or a Python client subscribe and forward the data into [Kafka](kafka.md) or a database.

### Authentication

Anonymous access is off. A client without a login is refused (`not authorised`). The configuration and the password file are written on every start, so the password always matches the one in Infisical.

### First steps

From a notebook on `app-network`:

```python
import paho.mqtt.publish as publish

publish.single(
    "factory/line1/temperature", "21.5",
    hostname="mosquitto",
    auth={"username": "nexus-mosquitto", "password": "<MOSQUITTO_PASSWORD>"},
)
```

A subscriber sees it on the same topic. Wildcards are `+` for one level and `#` for the rest.

### Persistence

Retained messages and persistent sessions are in `mosquitto-data`.

- **`rebuild` (default): they do not survive a teardown.** Mosquitto is not in the R2 backup list.
- **`snapshot`: they survive**, because the whole disk is imaged.
