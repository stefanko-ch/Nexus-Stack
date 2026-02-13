## Kafka-UI

![Kafka-UI](https://img.shields.io/badge/Kafka--UI-000000?logo=apachekafka&logoColor=white)

**Modern web UI for Apache Kafka / Redpanda management**

Kafka-UI is a free, open-source web UI for monitoring and managing Apache Kafka and Redpanda clusters. Features include:
- Multi-cluster management in one place
- Topic creation and configuration
- Real-time message browsing with filtering
- Consumer group monitoring with lag tracking
- Schema Registry support (Avro, JSON Schema, Protobuf)
- KSQL DB integration
- Live message tailing
- Topic data comparison

| Setting | Value |
|---------|-------|
| Default Port | `8181` |
| Suggested Subdomain | `kafka-ui` |
| Public Access | No (cluster management) |
| Website | [kafka-ui.provectus.io](https://docs.kafka-ui.provectus.io/) |
| Source | [GitHub](https://github.com/provectus/kafka-ui) |

### Pre-configured Connection

Kafka-UI is automatically configured to connect to the Redpanda cluster:
- **Bootstrap Servers:** `redpanda:9092`
- **Schema Registry:** `http://redpanda:8081`

> Dynamic configuration is enabled - you can add additional clusters via the UI settings.
