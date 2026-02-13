## Jupyter PySpark

![Jupyter](https://img.shields.io/badge/Jupyter-F37726?logo=jupyter&logoColor=white)

**Interactive PySpark notebook platform with Spark SQL support and cluster connectivity**

JupyterLab with PySpark pre-configured to connect to the Apache Spark cluster. Supports Python notebooks, PySpark DataFrames, and Spark SQL via `%%sparksql` magic cells. Features include:
- PySpark pre-installed with Spark cluster connectivity
- Spark SQL magic cells (`%%sparksql`) auto-loaded on startup
- JupyterLab interface with file browser and terminal
- Hetzner Object Storage (S3) integration for data access
- Gitea integration with `jupyterlab-git` (auto-clones workspace repo)
- Markdown and LaTeX rendering

| Setting | Value |
|---------|-------|
| Default Port | `8087` |
| Suggested Subdomain | `jupyter` |
| Public Access | No (development environment) |
| Website | [jupyter.org](https://jupyter.org) |
| Source | [GitHub](https://github.com/jupyter/jupyter) |

### Kernel Selection

Jupyter provides two kernels:

| Kernel | Description |
|--------|-------------|
| **PySpark (Spark Cluster)** | Auto-creates a SparkSession connected to the cluster. `spark` and `sc` variables are immediately available. |
| **Python 3 (ipykernel)** | Plain Python kernel without auto-Spark. Use this for non-Spark notebooks. |

When creating a new notebook, select **PySpark (Spark Cluster)** to get automatic Spark connectivity. The kernel prints `SparkSession ready (master: spark://spark-master:7077)` on startup.

### Spark Integration

When the Spark stack is enabled, the PySpark kernel automatically connects to `spark://spark-master:7077`. When Spark is not enabled, it falls back to `local[*]` mode (runs Spark locally within the container).

**With PySpark kernel (auto-configured):**
```python
# spark and sc are already available - no setup needed
spark.sql("SELECT 1 as test").show()
```

**Spark SQL magic cell:**
```
%%sparksql
SELECT 'hello spark' as greeting
```

**S3 access (Hetzner Object Storage):**
```python
df = spark.read.csv("s3a://your-bucket/path/file.csv")
```

### Usage

1. Enable the Jupyter service in the Control Plane
2. Access `https://jupyter.YOUR_DOMAIN`
3. Select the **PySpark (Spark Cluster)** kernel when creating a notebook
4. Authentication is handled by Cloudflare Access (token auth disabled)
5. Notebooks are persisted in a Docker volume (`jupyter-data`)
6. PySpark and `sparksql-magic` are pre-installed; Spark SQL is auto-loaded
