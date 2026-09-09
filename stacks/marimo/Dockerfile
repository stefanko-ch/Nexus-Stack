# =============================================================================
# Marimo - Reactive Python Notebook with Spark Connect client
# =============================================================================
# Base: ghcr.io/marimo-team/marimo:latest-sql (python:3.13-slim, includes
# marimo[sql] = duckdb + sqlglot + ibis + polars + pyarrow). We layer on
# git (so the entrypoint can clone the workspace repo from Forgejo) and the
# Spark Connect client packages so notebooks can talk to the spark-connect
# service via sc://spark-connect:15002 — no JDK or full pyspark needed.
#
# Why pyspark[connect] (not full pyspark): connect mode ships the gRPC
# client + Arrow serialization only. The driver-JVM runs server-side in
# the spark-connect container, so this image stays slim (no openjdk,
# ~+40 MiB instead of ~+450 MiB for full pyspark + JDK).
#
# Why ibis-framework[pyspark]: gives us mo.sql(..., engine=con) where
# con = ibis.pyspark.connect(spark). Marimo doesn't have a first-class
# Spark SQL backend, but Ibis is the supported bridge.
#
# Pin the pyspark version exactly to the cluster's Spark version (4.2.0)
# — wire-protocol skew between Connect client and server is the #1
# footgun. Bump both together.
#
# The grpcio and pyarrow pins below still satisfy 4.2.0's own floors
# (`pyarrow>=18.0.0`, `grpcio>=1.76.0`, from pyspark 4.2.0's metadata on
# PyPI), so they are left alone rather than moved for the sake of moving.
# =============================================================================

# Pinned to a specific marimo version for reproducibility AND so the
# seed notebooks' `__generated_with = "X.Y.Z"` field stays valid (a
# floating `:latest-sql` tag could pull a marimo older than the seeds'
# `__generated_with` version, which marimo refuses to open).
# When bumping: also bump `__generated_with` in
# examples/workspace-seeds/marimo/*.py to match.
FROM ghcr.io/marimo-team/marimo:0.23.4-sql

USER root

# git is needed by the entrypoint's workspace-repo clone. Marimo's base
# image is Debian (NOT Alpine) — the previous stacks/marimo/docker-compose.yml
# used `apk add` which silently failed because apk doesn't exist here;
# git was simply missing. Install via apt-get at build time so the
# entrypoint can rely on it. `gosu` is a tiny setuid helper used by the
# entrypoint to drop privileges from root → appuser AFTER chowning the
# notebook volume (a fresh docker-named-volume is mounted root:root,
# which the appuser-running marimo can't write to).
RUN apt-get update && \
    apt-get install -y --no-install-recommends git gosu && \
    rm -rf /var/lib/apt/lists/*

# Spark Connect client + Ibis adapter. `--no-cache-dir` keeps the
# layer small. ALL versions pinned exactly to make rebuilds
# reproducible — open-ended `>=` constraints would let pip pull a
# newer grpcio / pyarrow on every rebuild and silently break
# wire-protocol compat with the spark-connect 4.2.0 server. The
# pins below match the known-good combination from marimo-team's
# own pyspark smoke tests.
RUN pip install --no-cache-dir \
    "pyspark[connect]==4.2.0" \
    "ibis-framework[pyspark]==10.5.0" \
    "grpcio==1.76.0" \
    "grpcio-status==1.76.0" \
    "pyarrow==19.0.1"

# PyIceberg — the client for the Iceberg REST catalogs (Lakekeeper, Polaris).
#
# Deliberately WITHOUT the [duckdb,polars,pyarrow] extras. Those extras only
# declare dependencies that this image already carries: `marimo[sql]` brings
# duckdb and polars, and pyarrow is pinned exactly above. Asking for them
# again gives pip a reason to move pins the block above exists to hold still.
# Measured against this base image: plain `pyiceberg==0.12.0` installs its own
# dependencies and touches none of the existing ones —
#
#   before: pyarrow 19.0.1  grpcio 1.76.0  duckdb 1.5.2  polars 1.40.1
#   after:  pyarrow 19.0.1  grpcio 1.76.0  duckdb 1.5.2  polars 1.40.1
#
# The conversion methods work regardless of the extras, because they import
# their target lazily: `table.scan().to_arrow()`, `.to_duckdb()`, `.to_polars()`
# all live on DataScan, and `Table.to_polars()` is a convenience on top.
#
# NOT a Spark path. Iceberg publishes no `iceberg-spark-runtime-4.2_2.13`, and
# the 4.1 build is binary-incompatible with the Spark 4.2.0 this stack runs:
#
#   IncompatibleClassChangeError: class org.apache.iceberg.spark.source.SparkView
#   can not implement org.apache.spark.sql.connector.catalog.View,
#   because it is not an interface
#
# Spark 4.2 support landed in Iceberg's main branch on 2026-09-04 but is not in
# any release. Until it is, PyIceberg is how a notebook reaches these catalogs.
RUN pip install --no-cache-dir \
    "pyiceberg==0.12.0"

# Stay as root — the entrypoint chowns the notebooks volume then drops
# to appuser via gosu before exec'ing marimo. We can't drop here
# because the chown needs root and the entrypoint is what handles
# the volume init (the volume is mounted AFTER the image is built, so
# any chown done at build time is overlaid and lost).
