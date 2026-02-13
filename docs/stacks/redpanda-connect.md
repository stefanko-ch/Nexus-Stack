## Redpanda Connect

![Redpanda Connect](https://img.shields.io/badge/Redpanda_Connect-E4405F?logo=redpanda&logoColor=white)

**Declarative data streaming framework for real-time pipelines**

Redpanda Connect (formerly Benthos) is a high-performance stream processor that makes building data pipelines simple. Features include:
- Declarative YAML configuration
- Hundreds of connectors (Kafka, PostgreSQL, S3, HTTP, etc.)
- Built-in data transformation with Bloblang
- Stateless and easy to scale
- Real-time and batch processing
- Prometheus metrics endpoint

| Setting | Value |
|---------|-------|
| Default Port | `4195` |
| Suggested Subdomain | `redpanda-connect` |
| Public Access | No (data pipelines) |
| Website | [redpanda.com](https://redpanda.com) |
| Docs | [docs.redpanda.com/redpanda-connect](https://docs.redpanda.com/redpanda-connect/) |
| Source | [GitHub](https://github.com/redpanda-data/connect) |

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `/ready` | Health check endpoint |
| `/metrics` | Prometheus metrics |
| `/version` | Version information |

### Configuration

The pipeline configuration is in `stacks/redpanda-connect/config.yaml`. By default, a simple HTTP echo pipeline is configured. Replace with your own pipeline configuration.

Example pipeline to stream from Redpanda to stdout:
```yaml
input:
  kafka:
    addresses: ["redpanda:9092"]
    topics: ["my-topic"]
    consumer_group: "my-consumer"

output:
  stdout: {}
```
