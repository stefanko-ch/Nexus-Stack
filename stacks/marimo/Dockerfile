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
# Pin the pyspark version exactly to the cluster's Spark version (4.1.1)
# — wire-protocol skew between Connect client and server is the #1
# footgun. Bump both together.
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
# wire-protocol compat with the spark-connect 4.1.1 server. The
# pins below match the known-good combination from marimo-team's
# own pyspark smoke tests.
RUN pip install --no-cache-dir \
    "pyspark[connect]==4.1.1" \
    "ibis-framework[pyspark]==10.5.0" \
    "grpcio==1.76.0" \
    "grpcio-status==1.76.0" \
    "pyarrow==19.0.1"

# Stay as root — the entrypoint chowns the notebooks volume then drops
# to appuser via gosu before exec'ing marimo. We can't drop here
# because the chown needs root and the entrypoint is what handles
# the volume init (the volume is mounted AFTER the image is built, so
# any chown done at build time is overlaid and lost).
