"""SparkSession factory for Marimo notebooks (Spark Connect).

Usage in a Marimo cell:

    from _nexus_spark import get_spark
    spark = get_spark()
    df = spark.createDataFrame([("a", 1), ("b", 2)], ["k", "v"])
    df  # rendered as paginated mo.ui.table.lazy by Marimo's PySpark formatter

The session is cached at module level — multiple cells / multiple notebooks
calling get_spark() in the same Python process share one Connect channel
to sc://spark-connect:15002. Marimo's reactive DAG re-runs cells when their
upstream changes, but module-level state survives — by design here, since
re-establishing the gRPC channel on every cell run would be wasteful.

The Spark Connect URL is read from $SPARK_CONNECT_URL (set by
stacks/marimo/docker-compose.yml). Override per-notebook by setting
os.environ["SPARK_CONNECT_URL"] = "sc://other-cluster:15002" *before* the
first get_spark() call.

Note on Hadoop / S3 config: Spark Connect does NOT propagate driver-side
SparkConf to the remote driver — Hadoop properties (s3a endpoint, keys)
must be set on the spark-connect *server* side. Setting them here is a
no-op.

They live in ``stacks/spark/spark-defaults.conf``, rendered per deployment
by ``service_env._render_spark`` and mounted into all three Spark
containers. This paragraph used to name ``SPARK_HADOOP_*`` environment
variables instead, which was wrong twice over: they were never read by the
official Spark image (that translation is a Bitnami feature), and they no
longer exist in the compose file.

Credentials are scoped per bucket, so ``s3a://<bucket>/...`` finds its own
endpoint. The bucket names reach this container through ``.infisical.env``
as ``R2_BUCKET`` and ``HETZNER_S3_BUCKET``.
"""
from __future__ import annotations

import os
from typing import Optional

# pyspark.sql.connect.session.SparkSession is the Connect client; using it
# directly (rather than pyspark.sql.SparkSession) avoids ambiguity about
# which mode is in play.
from pyspark.sql.connect.session import SparkSession

_session: Optional[SparkSession] = None


def get_spark() -> SparkSession:
    """Return a process-wide Spark Connect session, creating it on first call."""
    global _session
    if _session is None:
        url = os.environ.get("SPARK_CONNECT_URL", "sc://spark-connect:15002")
        _session = SparkSession.builder.remote(url).getOrCreate()
    return _session


def stop_spark() -> None:
    """Stop the cached session and clear the module-level reference.

    Use this if you need to fully reset the gRPC channel (rare — most
    config changes don't require it). After this, the next get_spark()
    call will create a fresh session.
    """
    global _session
    if _session is not None:
        _session.stop()
        _session = None
