## Apache Spark

![Spark](https://img.shields.io/badge/Apache_Spark-E25A1C?logo=apachespark&logoColor=white)

**Distributed data processing engine with standalone cluster (Master + Worker)**

Apache Spark provides a unified analytics engine for large-scale data processing. This stack runs a standalone cluster with one master and one worker node, pre-configured with Hetzner Object Storage (S3) access.

| Setting | Value |
|---------|-------|
| Default Port | `8088` (Master Web UI) |
| Cluster Port | `7077` (internal only) |
| Suggested Subdomain | `spark` |
| Public Access | No (cluster management) |
| Website | [spark.apache.org](https://spark.apache.org) |
| Source | [GitHub](https://github.com/apache/spark) |

### Architecture

| Container | Image | Purpose |
|-----------|-------|---------|
| `spark-master` | `nexus-spark:4.1.1-python3.13` | Cluster manager + Web UI (port 8088) |
| `spark-worker` | `nexus-spark:4.1.1-python3.13` | Task executor (connects to master on 7077) |

> **Custom image:** The official `apache/spark:4.1.1` ships Python 3.10 (Ubuntu 22.04), but Jupyter uses Python 3.13. PySpark requires matching Python versions between driver and executors. The custom Dockerfile installs Python 3.13 via deadsnakes PPA and adds `hadoop-aws` + AWS SDK v2 JARs for S3A filesystem support.

```
                    ┌─────────────────────┐
                    │  Jupyter PySpark     │
                    │  %%sparksql magic    │
                    └────────┬────────────┘
                             │ spark://spark-master:7077
              ┌──────────────┴──────────────┐
              │                             │
     ┌────────┴────────┐          ┌─────────┴────────┐
     │  Spark Master   │          │  Spark Worker    │
     │  UI: port 8088  │          │  (no external UI)│
     └────────┬────────┘          └─────────┬────────┘
              │                             │
              └──────────────┬──────────────┘
                             │ S3 (hadoop-aws)
                    ┌────────┴────────┐
                    │ Hetzner Object  │
                    │ Storage (S3)    │
                    └─────────────────┘
```

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
| **Total** | **3** | **5 GB** | **0.75** | **768 MB** |

On a cax31 (8 vCPU, 16 GB RAM) this leaves 5 CPU and 11 GB RAM for other services.

### Usage

1. Enable the Spark service in the Control Plane
2. Access the Master Web UI at `https://spark.YOUR_DOMAIN` to monitor the cluster
3. The Web UI shows registered workers, running applications, and completed jobs
4. Use Jupyter PySpark to submit jobs to the cluster (auto-configured)

### Connecting from Jupyter

When both Spark and Jupyter are enabled, Jupyter automatically connects to the cluster:

```python
from pyspark.sql import SparkSession
spark = SparkSession.builder \
    .master("spark://spark-master:7077") \
    .getOrCreate()

# Run a query
spark.sql("SELECT 1 as test").show()
```

> No configuration needed - `SPARK_MASTER` is automatically set to `spark://spark-master:7077` when the Spark stack is enabled.
