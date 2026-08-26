"""Getting Started with PySpark in Marimo (via Spark Connect).

Pre-wired to talk to the Nexus-Stack Spark cluster at
sc://spark-connect:15002. The driver-JVM lives in the spark-connect
container; this notebook is a thin gRPC client.

Run cells top-to-bottom (or all at once — Marimo's reactive DAG handles
ordering automatically once dependencies are declared).
"""

import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # Getting Started with PySpark on Marimo

        Connected to **Spark Connect** (`sc://spark-connect:15002`) — the
        driver-JVM runs server-side, this notebook is a thin gRPC client.

        Run cells in order, or hit **Run all** — Marimo figures out the
        dependency graph from the function signatures.
        """
    )
    return


@app.cell
def _():
    # Import the cached SparkSession factory shipped with the workspace
    # repo (examples/workspace-seeds/marimo/_nexus_spark.py — gets seeded
    # to your Forgejo workspace on every spin-up).
    from _nexus_spark import get_spark

    spark = get_spark()
    return (spark,)


@app.cell
def _(mo, spark):
    # Local import — NOT returned from this cell. Marimo enforces
    # single-cell-defines-each-name across the DAG, and the S3 cell
    # below has its own `import os` block. Keeping `os` cell-local
    # here avoids that conflict.
    import os as _os

    _connect_url = _os.environ.get("SPARK_CONNECT_URL", "sc://spark-connect:15002")
    mo.md(
        f"""
        ## 1. Verify Cluster Connection

        - **Spark version:** `{spark.version}`
        - **Connect URL:** `{_connect_url}`
        - **Session type:** `{type(spark).__module__}.{type(spark).__name__}`
        """
    )
    return


@app.cell
def _(mo):
    mo.md("""## 2. Create a DataFrame""")
    return


@app.cell
def _(spark):
    data = [
        ("Alice", "Engineering", 85000),
        ("Bob", "Marketing", 72000),
        ("Charlie", "Engineering", 92000),
        ("Diana", "Marketing", 68000),
        ("Eve", "Engineering", 95000),
        ("Frank", "Sales", 78000),
    ]
    df = spark.createDataFrame(data, ["name", "department", "salary"])
    # Last-cell DataFrame is auto-rendered by Marimo as mo.ui.table.lazy
    # (the dedicated PySpark Connect formatter shipped in
    # marimo-team/marimo PR #4615).
    df
    return (df,)


@app.cell
def _(mo):
    mo.md("""## 3. DataFrame Operations""")
    return


@app.cell
def _(df):
    # Filter + sort. Returned DataFrame is again auto-rendered.
    df.filter(df.salary > 75000).orderBy("salary", ascending=False)
    return


@app.cell
def _(df):
    # Spark Connect requires functions from `pyspark.sql.connect.functions`,
    # NOT the top-level `pyspark.sql.functions` — the latter resolves to the
    # classic implementation (`pyspark.sql.classic.column._to_java_column`)
    # which needs a local JVM SparkContext we don't have here. There's no
    # automatic dispatch between the two in pyspark 4.1; the import path
    # has to match the session type.
    from pyspark.sql.connect import functions as F

    df.groupBy("department").agg(
        F.count("name").alias("employees"),
        F.avg("salary").alias("avg_salary"),
        F.max("salary").alias("max_salary"),
    ).orderBy("department")
    return (F,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4. Spark SQL via Ibis

        Marimo's `mo.sql(...)` cell needs an explicit engine for Spark.
        We use [Ibis](https://ibis-project.org)' `pyspark` backend as
        the bridge — it's the supported way to run Spark SQL in
        Marimo's reactive SQL cells.
        """
    )
    return


@app.cell
def _(df, spark):
    import ibis

    # Wrap the existing SparkSession so Ibis can route SQL through it.
    con = ibis.pyspark.connect(spark)

    # Register the DataFrame as a temp view for SQL access. Ibis's
    # PySpark backend expects a Spark SQL table name to query.
    df.createOrReplaceTempView("employees")
    return con, ibis


@app.cell
def _(con, mo):
    # mo.sql() with a non-DuckDB engine renders the same paginated UI.
    # Spark plans + executes server-side, results stream back via Arrow.
    high_earners = mo.sql(
        """
        SELECT department,
               COUNT(*) AS headcount,
               ROUND(AVG(salary), 0) AS avg_salary
        FROM employees
        GROUP BY department
        ORDER BY avg_salary DESC
        """,
        engine=con,
    )
    return (high_earners,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 5. Read from Hetzner Object Storage (s3a://)

        Hadoop S3A config is set on the spark-connect server side
        (Compose env-vars `SPARK_HADOOP_fs_s3a_*`). The bucket name is
        passed through to this notebook as `HETZNER_S3_BUCKET` — see
        below for an opt-in read example.
        """
    )
    return


@app.cell
def _(spark):
    import os

    bucket = os.environ.get("HETZNER_S3_BUCKET", "")
    # Initialize all return-tuple names BEFORE the conditional so
    # both branches define them. Otherwise the else-branch return
    # would raise UnboundLocalError on `sample_path` when
    # HETZNER_S3_BUCKET is unset (the common case before Infisical
    # has any S3 secrets in it).
    sample_path = None
    df_s3 = None
    if bucket:
        # Write a small CSV, then read it back. Both happen on the
        # spark-connect server side; only the resulting Arrow batches
        # come back to this notebook.
        sample_path = f"s3a://{bucket}/sample-data/marimo-employees"
        spark.range(5).selectExpr(
            "id", "concat('user-', id) AS name", "(id * 1000 + 50000) AS salary"
        ).coalesce(1).write.mode("overwrite").option("header", True).csv(sample_path)
        df_s3 = spark.read.csv(sample_path, header=True, inferSchema=True)
        result_msg = f"Read {df_s3.count()} rows back from {sample_path}"
        df_s3
    else:
        result_msg = (
            "HETZNER_S3_BUCKET is not set — skipping S3 demo. "
            "Set it via Infisical (key HETZNER_S3_BUCKET) and re-run a spin-up "
            "to populate the Marimo container env."
        )
    return bucket, df_s3, os, result_msg, sample_path


@app.cell
def _(mo, result_msg):
    mo.md(f"**Result:** {result_msg}")
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 6. Tips & Pitfalls

        - **Stopping a long Spark job:** Marimo's red Stop button does
          NOT interrupt blocking gRPC calls (upstream issue
          [marimo-team/marimo#3494](https://github.com/marimo-team/marimo/issues/3494)).
          To kill a runaway query, open the Spark Master UI at
          `https://spark.<your-domain>` and click `(kill)` next to
          the running app — the gRPC stream will fail back to Marimo
          which then shows MarimoInterrupt cleanly.
        - **Reactivity vs Spark state:** treat `spark` as immutable
          after `get_spark()`. Mutations to `spark.conf` from another
          cell are NOT tracked by Marimo's DAG and can produce
          surprising results.
        - **Driver-memory tuning:** the driver-JVM lives in the
          `spark-connect` container, not here. Bump its memory limit
          in `stacks/spark/docker-compose.yml` if your queries fail
          with OOM, NOT the Marimo container's.
        """
    )
    return


if __name__ == "__main__":
    app.run()
