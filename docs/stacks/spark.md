---
title: "Apache Spark"
---

## Apache Spark

![Spark](https://img.shields.io/badge/Apache_Spark-E25A1C?logo=apachespark&logoColor=white)

**Distributed data processing engine with standalone cluster (Master + Worker + Spark Connect)**

Apache Spark provides a unified analytics engine for large-scale data processing. This stack runs a standalone cluster with one master, one worker, and a Spark Connect server, pre-configured with Hetzner Object Storage (S3) access.

| Setting | Value |
|---------|-------|
| Default Port | `8088` (Master Web UI) |
| Classic cluster port | `7077` (internal — Jupyter connects here) |
| Spark Connect port | `15002` (internal Docker network only — Marimo / future code-server connect here via `sc://spark-connect:15002`. NOT published to the host or routed via Cloudflare Tunnel.) |
| Suggested Subdomain | `spark` |
| Public Access | No (cluster management) |
| Website | [spark.apache.org](https://spark.apache.org) |
| Source | [GitHub](https://github.com/apache/spark) |

### Architecture

| Container | Image | Purpose |
|-----------|-------|---------|
| `spark-master` | `nexus-spark:4.2.0-python3.13` | Cluster manager + Web UI (port 8088); accepts classic-protocol clients on 7077 |
| `spark-worker` | `nexus-spark:4.2.0-python3.13` | Task executor (connects to master on 7077) |
| `spark-connect` | `nexus-spark:4.2.0-python3.13` | gRPC server on 15002 — driver-JVM for thin clients (Marimo, code-server). Connects to master like any other Spark application. |

> **Custom image:** The official `apache/spark:4.2.0` ships Python 3.10 (Ubuntu 22.04), but our Jupyter / spark-worker setup uses Python 3.13. PySpark requires matching Python versions between driver and executors. The custom Dockerfile installs Python 3.13 via deadsnakes PPA, adds `hadoop-aws` + AWS SDK v2 JARs for S3A filesystem support, and pre-downloads the Spark Connect server JARs (`spark-connect_2.13-4.2.0.jar`, `spark-connect-common_2.13-4.2.0.jar`) into `/opt/spark/jars/` so the Connect server starts without ivy resolution at runtime.

### The S3A jars track Spark's bundled Hadoop

This is the part of a version bump that is easy to miss, because nothing fails at build time:

| Spark | bundles Hadoop | so `hadoop-aws` must be | and the AWS SDK v2 |
|---|---|---|---|
| 4.1.1 | 3.4.2 | 3.4.2 | 2.29.52 |
| 4.2.0 | **3.5.0** | **3.5.0** | **2.35.4** |

The Hadoop version comes from `spark-parent_2.13-<version>.pom`, and can be read straight out of the image (`ls /opt/spark/jars/ | grep hadoop-client-api`). The SDK version comes from `hadoop-project-<version>.pom`'s `aws-java-sdk-v2.version`. Leaving `hadoop-aws` behind produces a `NoSuchMethodError` deep inside a task rather than a build failure.

`hadoop-aws` 3.5.0 also introduced a compile-scope dependency that 3.4.2 did not have, `software.amazon.s3.analyticsaccelerator:analyticsaccelerator-s3` (1.3.1, from the same POM). Whether `S3AFileSystem` loads it eagerly or only under `fs.s3a.input.stream.type=analytics` was not determined, so it is baked in rather than gambled on.

Every jar the Dockerfile downloads is verified against Maven Central's published SHA-1.

### S3 is configured in a file, not in the environment

`stacks/spark/spark-defaults.conf` is rendered per deployment by `service_env._render_spark` and mounted into all three containers. `spark-defaults.conf.template` next to it is the reviewable copy; the rendered one is gitignored because it holds object-storage credentials.

Before Spark 4.2.0 this stack set `SPARK_HADOOP_fs_s3a_*` environment variables instead. **They never did anything:**

```bash
docker run --rm --entrypoint sh apache/spark:4.2.0 -c 'grep -c SPARK_HADOOP /opt/entrypoint.sh'
# 0
```

That translation is a Bitnami-image feature. The official image does not do it, and Spark reads only `AWS_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` from the environment. S3 access worked from [Jupyter](jupyter.md) only because `stacks/jupyter/spark-init.py` reads the same variables with `os.environ.get()` and applies them by hand — which is why Jupyter still sets them and a test allows it there.

A config file is also the only place that reaches every process that matters. Spark Connect does **not** propagate driver-side `SparkConf`, so a client that sets a property gets ignored; `--conf` flags in the compose `command:` would configure `spark-connect` alone, leaving the master, the workers and any interactive `spark-shell` untouched.

Credentials are scoped per bucket (`fs.s3a.bucket.<name>.endpoint`), because this deployment can reach two stores with different endpoints. A global `fs.s3a.endpoint` would have to be wrong for one of them.

The file also widens `spark.redaction.regex`. Spark's default is `(?i)secret|password|token`, which hides `fs.s3a.secret.key` and leaves `fs.s3a.access.key` visible — and the master UI on port 8088 renders the environment page for every running application.

```
   ┌──────────────────────┐          ┌──────────────────────┐
   │  Jupyter PySpark     │          │  Marimo PySpark      │
   │  (driver-JVM local)  │          │  (gRPC client only)  │
   └──────────┬───────────┘          └──────────┬───────────┘
              │ spark://spark-master:7077       │ sc://spark-connect:15002
              │ (classic standalone)            │ (gRPC + Arrow)
              ▼                                 ▼
     ┌────────────────┐                 ┌──────────────────┐
     │  Spark Master  │                 │  Spark Connect   │
     │   UI: 8088     │ ◄───── 7077 ────│   driver-JVM     │
     │   port 7077    │                 │   port 15002     │
     └───────┬────────┘                 └─────────┬────────┘
             │                                    │
             ▼                                    │
     ┌────────────────┐                           │
     │  Spark Worker  │ ◄─── tasks (both ─────────┘
     │  (executors)   │       protocols converge here)
     └───────┬────────┘
             │ S3 (hadoop-aws)
             ▼
     ┌────────────────┐
     │ Hetzner Object │
     │ Storage (S3)   │
     └────────────────┘
```

Both protocols hit the same worker pool — applications submitted via classic 7077 and via Connect 15002 share the worker's cores and memory according to standard Spark FIFO scheduling.

### Configuration

- **Worker cores:** Configurable via `SPARK_WORKER_CORES` (default: 2)
- **Worker memory:** Configurable via `SPARK_WORKER_MEMORY` (default: 3g)
- **S3 access:** Pre-configured via `SPARK_HADOOP_fs_s3a_*` environment variables when Hetzner Object Storage credentials are available

### Resource Limits

Docker resource limits prevent Spark from consuming all server resources:

| Container | CPU Limit | Memory Limit | CPU Reserved | Memory Reserved |
|-----------|-----------|-------------|-------------|-----------------|
| `spark-master` | 1 | 1 GB | 0.25 | 256 MB |
| `spark-worker` | 2 | 4 GB | 0.5 | 512 MB |
| `spark-connect` | 1 | 1.5 GB | 0.25 | 256 MB |
| **Total** | **4** | **6.5 GB** | **1.0** | **1024 MB** |

On a cax31 (8 vCPU, 16 GB RAM) this leaves 4 CPU and ~9.5 GB RAM for other services. The `spark-connect` container holds the driver-JVM for ALL Connect clients (Marimo, future code-server) — bump its memory if multiple notebooks run heavy queries concurrently.

### Usage

1. Enable the Spark service in the Control Plane
2. Access the Master Web UI at `https://spark.YOUR_DOMAIN` to monitor the cluster
3. The Web UI shows registered workers, running applications, and completed jobs
4. Use Jupyter PySpark to submit jobs to the cluster (auto-configured)

### Connecting from Jupyter (classic protocol)

When both Spark and Jupyter are enabled, Jupyter automatically connects to the cluster on port 7077:

```python
from pyspark.sql import SparkSession
spark = SparkSession.builder \
    .master("spark://spark-master:7077") \
    .getOrCreate()

# Run a query
spark.sql("SELECT 1 as test").show()
```

> No configuration needed — `SPARK_MASTER` is automatically set to `spark://spark-master:7077` when the Spark stack is enabled. Jupyter's driver-JVM lives in the Jupyter container; the worker runs the executors.

### Connecting from Marimo (Spark Connect)

When both Spark and Marimo are enabled, Marimo talks to the `spark-connect` server at port 15002 via gRPC. The driver-JVM lives in the `spark-connect` container, NOT in Marimo — Marimo is a thin client (no JDK, no full pyspark).

```python
from pyspark.sql.connect.session import SparkSession
spark = SparkSession.builder.remote("sc://spark-connect:15002").getOrCreate()
spark.sql("SELECT 1 as test").show()
```

A pre-built helper module ships in the workspace seed at `marimo/_nexus_spark.py` — see [docs/stacks/marimo.md](./marimo.md) for the recommended pattern.

### Connect vs. Classic — when to use which

- **Classic (`spark://...:7077`)**: Jupyter today. Driver runs in the client. Full PySpark API surface, including the bits that haven't been ported to Connect yet (some RDD operations, certain UDF modes). Heavier client (needs JDK + full pyspark).
- **Connect (`sc://...:15002`)**: Marimo today, code-server in the future. Driver runs server-side in the `spark-connect` container. Thin client (gRPC + Arrow). Better fit for reactive notebooks; first-class formatter support in Marimo. Some advanced features have caveats — check the [Spark Connect compatibility matrix](https://spark.apache.org/docs/latest/spark-connect-overview.html#what-is-supported-in-spark-40) before relying on niche APIs.

Both protocols submit applications to the same `spark-master`, so they share the worker's resources.
