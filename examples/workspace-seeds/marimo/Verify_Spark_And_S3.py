"""Verify the Spark cluster and its object-storage wiring.

A diagnostic notebook, not a tutorial — every cell answers one question
that has a right answer, so a failure tells you which layer broke rather
than that "Spark doesn't work".

Run it after a version bump, after a spin-up that changed the Spark stack,
or when something that used to work stopped. `Getting_Started_PySpark.py`
is the notebook to read if you want to learn PySpark; this one is the
notebook to run when you want to know whether the plumbing is intact.

It writes to `s3a://<bucket>/nexus_seeds/verify/` with `mode("overwrite")`,
so re-running it is safe and leaves nothing behind that accumulates.
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
        # Verify Spark and S3

        Each section below has an expected answer. Work top to bottom and
        stop at the first one that disagrees — later cells assume the
        earlier ones passed.

        | # | Question | Expected |
        |---|---|---|
        | 1 | Which Spark is the cluster running? | matches `services.yaml` |
        | 2 | Do executors actually start? | `45` |
        | 3 | Does Arrow round-trip through gRPC? | 4 rows |
        | 4 | Which buckets is this deployment given? | at least one |
        | 5 | Can Spark write to and read from R2? | `100` |
        | 6 | Can it still reach Hetzner? | `10` |
        """
    )
    return


@app.cell
def _():
    from _nexus_spark import get_spark

    spark = get_spark()
    return (spark,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 1 — Which Spark is the cluster running?

        This is the **server's** version, not the client's. Spark Connect
        keeps them separate on purpose, and a mismatch here against what
        `services.yaml` declares means the image did not rebuild — the
        deploy runs `docker compose up -d --build`, so a stale answer
        points at a build that failed quietly rather than at a wrong pin.
        """
    )
    return


@app.cell
def _(spark):
    print("cluster Spark:", spark.version)
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2 — Do executors actually start?

        `spark.range(...).sum()` is the smallest thing that cannot be
        answered by the driver alone: it has to schedule a task on a
        worker. This is the step that fails when the master is reachable
        but no executor can register back — the classic symptom of a
        `spark.driver.host` / bind-address problem, and it fails by
        hanging rather than erroring.

        Expected: **45**.
        """
    )
    return


@app.cell
def _(spark):
    total = spark.range(10).selectExpr("sum(id) as total").collect()[0]["total"]
    print("sum(range(10)) =", total, "— expected 45")
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3 — Does Arrow round-trip through gRPC?

        `toPandas()` pulls Arrow batches across the Connect channel and
        deserialises them client-side. It exercises the one thing plain
        SQL does not: that the Python on the executors matches the Python
        here.

        A `PYTHON_VERSION_MISMATCH` at this point means the custom image's
        Python 3.13 layer did not take effect.
        """
    )
    return


@app.cell
def _(spark):
    import sys

    pdf = spark.range(4).selectExpr("id", "id * id as squared").toPandas()
    print("client Python:", sys.version.split()[0])
    print(pdf.to_string(index=False))
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4 — Which buckets is this deployment given?

        Credentials are scoped **per bucket** in the cluster's
        `spark-defaults.conf`, so `s3a://<bucket>/...` finds its own
        endpoint. A bucket that is empty below simply was not configured
        for this deployment; the matching write cell will then fail, and
        that is expected rather than a fault.

        The names arrive through `.infisical.env`.
        """
    )
    return


@app.cell
def _():
    import os

    r2_bucket = os.environ.get("R2_BUCKET", "")
    hetzner_bucket = os.environ.get("HETZNER_S3_BUCKET", "")
    print("R2_BUCKET        :", r2_bucket or "(not configured)")
    print("HETZNER_S3_BUCKET:", hetzner_bucket or "(not configured)")
    return hetzner_bucket, r2_bucket


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 5 — Can Spark write to and read from R2?

        The point of the exercise. R2 is the data lake because it survives
        a rebuild teardown, which the server's own disk does not.

        This is also the cell that proves the cluster's S3 configuration
        applies at all. Until Spark 4.2.0 it was carried by
        `SPARK_HADOOP_fs_s3a_*` environment variables that the official
        Spark image never reads, so this write could not have worked from
        a Connect client no matter what the credentials said.

        Expected: **100**.
        """
    )
    return


@app.cell
def _(r2_bucket, spark):
    if not r2_bucket:
        print("skipped — R2_BUCKET is not set for this deployment")
    else:
        # Underscore-prefixed so the name stays private to this cell.
        # Marimo's reactive graph requires every non-private variable to
        # be defined in exactly one cell, and the Hetzner cell below wants
        # the same obvious name.
        _path = f"s3a://{r2_bucket}/nexus_seeds/verify/r2"
        spark.range(100).selectExpr("id", "id * 2 as doubled").write.mode(
            "overwrite"
        ).parquet(_path)
        _back = spark.read.parquet(_path)
        print(f"{_path} -> {_back.count()} rows, expected 100")
        _back.orderBy("id").limit(3).show()
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 6 — Can it still reach Hetzner?

        The regression check. The per-bucket rewrite was verified against
        MinIO before it shipped; Hetzner Object Storage is a different
        endpoint, and this is where a mistake in the per-bucket keys would
        surface.

        Expected: **10**.
        """
    )
    return


@app.cell
def _(hetzner_bucket, spark):
    if not hetzner_bucket:
        print("skipped — HETZNER_S3_BUCKET is not set for this deployment")
    else:
        _path = f"s3a://{hetzner_bucket}/nexus_seeds/verify/hetzner"
        spark.range(10).write.mode("overwrite").parquet(_path)
        print(f"{_path} -> {spark.read.parquet(_path).count()} rows, expected 10")
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## If something failed

        The useful error is server-side, not in this notebook. Spark
        Connect reports a truncated remote stack trace; the whole one is
        in the driver's log:

        ```bash
        ssh nexus "docker logs spark-connect --tail 100"
        ```

        And to see the configuration the cluster actually has, rather
        than the one it was meant to get:

        ```bash
        ssh nexus "docker exec spark-connect cat /opt/spark/conf/spark-defaults.conf"
        ```

        A bucket listed there without an `access.key` means the renderer
        received no credentials — that is a missing secret, not a bug in
        this notebook or in Spark.
        """
    )
    return


if __name__ == "__main__":
    app.run()
