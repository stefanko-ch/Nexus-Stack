---
title: "Apache Flink"
---

## Apache Flink

![Flink](https://img.shields.io/badge/Apache_Flink-E6526F?logo=apacheflink&logoColor=white)

**Distributed stream and batch processing engine with standalone cluster (JobManager + TaskManager)**

Apache Flink provides a framework for stateful computations over data streams and bounded datasets. This stack runs a standalone cluster with one JobManager and one TaskManager, accessible via the JobManager Web UI.

| Setting | Value |
|---------|-------|
| Default Port | `8081` (JobManager Web UI + REST API) |
| RPC Port | `6123` (internal only) |
| Suggested Subdomain | `flink` |
| Public Access | No (cluster management) |
| Website | [flink.apache.org](https://flink.apache.org) |
| Source | [GitHub](https://github.com/apache/flink) |

### Architecture

| Container | Image | Purpose |
|-----------|-------|---------|
| `flink-jobmanager` | `nexus-flink:1.20.1` | Cluster manager + Web UI (port 8081) |
| `flink-taskmanager` | `nexus-flink:1.20.1` | Task executor (connects to JobManager on 6123) |

> **Custom image:** Based on the Docker Library `flink` image (multi-arch: amd64 + arm64) with the Kafka SQL and Apache Fluss connectors baked in. Note: `apache/flink` is amd64-only and does not work on ARM servers.

```
                    ┌─────────────────────┐
                    │   Flink REST API     │
                    │   / Web UI :8081     │
                    └────────┬────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
     ┌────────┴────────┐          ┌─────────┴────────┐
     │  JobManager     │          │  TaskManager     │
     │  UI: port 8081  │          │  (no external UI)│
     │  RPC: 6123      │◄─────────│  slots: 2        │
     └─────────────────┘          └──────────────────┘
```

### Configuration

- **Task slots:** Configurable via `FLINK_TASKMANAGER_SLOTS` in `.env` (default: 2)
- **Configuration:** Passed via `FLINK_PROPERTIES` environment variable as multi-line key-value pairs

Key `FLINK_PROPERTIES` values:

| Property | Default | Description |
|----------|---------|-------------|
| `taskmanager.numberOfTaskSlots` | `2` | Parallel task slots per TaskManager |
| `taskmanager.memory.process.size` | `3072m` | Total TaskManager process memory |
| `jobmanager.memory.process.size` | `1024m` | Total JobManager process memory |

### Resource Limits

Docker resource limits prevent Flink from consuming all server resources:

| Container | CPU Limit | Memory Limit | CPU Reserved | Memory Reserved |
|-----------|-----------|-------------|-------------|-----------------|
| `flink-jobmanager` | 1 | 1 GB | 0.25 | 256 MB |
| `flink-taskmanager` | 2 | 4 GB | 0.5 | 512 MB |
| **Total** | **3** | **5 GB** | **0.75** | **768 MB** |

On a cax31 (8 vCPU, 16 GB RAM) this leaves 5 CPU and 11 GB RAM for other services.

### Usage

1. Enable the Flink service in the Control Plane
2. Access the JobManager Web UI at `https://flink.YOUR_DOMAIN` to monitor the cluster
3. The Web UI shows registered TaskManagers, running jobs, and completed jobs
4. Submit jobs via the REST API at `https://flink.YOUR_DOMAIN/jars/upload`

### Submitting Jobs via REST API

```bash
# Upload a JAR
curl -X POST https://flink.YOUR_DOMAIN/jars/upload \
  -H "Content-Type: multipart/form-data" \
  -F "jarfile=@my-job.jar"

# Run the uploaded JAR (use jar ID from upload response)
curl -X POST https://flink.YOUR_DOMAIN/jars/<jar-id>/run \
  -H "Content-Type: application/json" \
  -d '{"entryClass": "com.example.MyJob"}'
```

### Kafka SQL Connector

The custom Flink image includes the `flink-sql-connector-kafka` JAR (`3.4.0-1.20`) pre-installed in `/opt/flink/lib/`. This enables Flink SQL to read from and write to Redpanda (Kafka-compatible) without manual JAR management.

**Example: Read from Redpanda via Flink SQL (Dinky)**

```sql
CREATE TABLE test_events (
    id STRING,
    `timestamp` STRING,
    user_id INT,
    event_type STRING,
    amount INT
) WITH (
    'connector' = 'kafka',
    'topic' = 'test-events',
    'properties.bootstrap.servers' = 'redpanda:9092',
    'properties.group.id' = 'flink-test',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json'
);

SELECT * FROM test_events LIMIT 10;
```

> The `test-events` topic is automatically created by the Redpanda Datagen service with sample e-commerce events.

### Fluss Connector

The image also includes the Apache Fluss connector (`fluss-flink-1.20`, `1.0.0`), so Flink SQL can use the [Fluss](fluss.md) stack as a catalog of log and primary-key tables:

```sql
CREATE CATALOG fluss WITH (
  'type' = 'fluss',
  'bootstrap.servers' = 'fluss:9123',
  'client.security.protocol' = 'SASL',
  'client.security.sasl.mechanism' = 'PLAIN',
  'client.security.sasl.username' = 'nexus_fluss',
  'client.security.sasl.password' = '<FLUSS_PASSWORD>'
);
```

The password is in Infisical (folder `fluss`). The connector version matches the Fluss server version; change both together.

### Connecting from Other Services

Other services on `app-network` can submit jobs to the JobManager REST API:

```
http://flink:8081
```
