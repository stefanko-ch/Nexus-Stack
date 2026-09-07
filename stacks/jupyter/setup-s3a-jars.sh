#!/bin/bash
# =============================================================================
# Download and install hadoop-aws + AWS SDK v2 JARs for S3A filesystem support.
# Runs as root via Jupyter's before-notebook.d hook (before user switch).
#
# This script is sourced (not subshelled) by Jupyter's start.sh, so we must
# save and restore shell options to avoid leaking them to the parent process.
#
# JARs are cached in the persistent volume (.spark-jars/) so the ~642MB
# download (hadoop-aws ~1MB + AWS SDK v2 bundle ~641MB) only happens on
# first start.
#
# ⚠️ THESE VERSIONS TRACK JUPYTER'S OWN SPARK, NOT THE CLUSTER'S.
# The two are different things and nothing in this repository keeps them
# aligned. `quay.io/jupyter/pyspark-notebook` builds with `spark_version=`
# empty, so upstream's setup_spark.py picks the newest Spark off the mirror
# at image build time, and the `python-3.13` tag is rolling. Measured on
# 2026-09-07, that image ships spark-core_2.13-4.2.0 and
# hadoop-client-api-3.5.0 — hence 3.5.0 / 2.35.4 below (from
# hadoop-project-3.5.0.pom's aws-java-sdk-v2.version).
#
# It happens to match the cluster today. It is not guaranteed to tomorrow,
# and classic Spark mode requires driver/executor version parity. That is
# the open question in issue #809; until it is settled, re-check what the
# image actually bundles before changing these:
#
#   docker run --rm --entrypoint sh quay.io/jupyter/pyspark-notebook:python-3.13 \
#     -c 'ls /usr/local/spark/jars/ | grep -E "spark-core|hadoop-client-api"'
# =============================================================================
_SAVED_OPTS=$(set +o)
set -eo pipefail
JARS_CACHE=/home/jovyan/work/.spark-jars
HADOOP_AWS="$JARS_CACHE/hadoop-aws-3.5.0.jar"
AWS_BUNDLE="$JARS_CACHE/bundle-2.35.4.jar"

if [ ! -f "$HADOOP_AWS" ] || [ ! -f "$AWS_BUNDLE" ]; then
    echo "[jupyter] Downloading S3A support JARs (first start only)..."
    mkdir -p "$JARS_CACHE"
    # Sweep older versions out of the cache first. Without this a version
    # bump leaves the previous pair behind — the guard above only asks
    # whether the NEW filenames exist — and `cp -n` below refuses to
    # overwrite, so both versions end up on the classpath with the stale
    # one winning by name order. On a persistent volume that would survive
    # every redeploy, and 641MB of it.
    find "$JARS_CACHE" -maxdepth 1 -type f \
        \( -name 'hadoop-aws-*.jar' -o -name 'bundle-*.jar' \) -delete
    rm -f /usr/local/spark/jars/hadoop-aws-*.jar /usr/local/spark/jars/bundle-*.jar
    curl -fSL https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.5.0/hadoop-aws-3.5.0.jar \
        -o "$HADOOP_AWS"
    curl -fSL https://repo1.maven.org/maven2/software/amazon/awssdk/bundle/2.35.4/bundle-2.35.4.jar \
        -o "$AWS_BUNDLE"
    chown -R 1000:100 "$JARS_CACHE"
    echo "[jupyter] S3A JARs downloaded."
fi
cp -n "$HADOOP_AWS" /usr/local/spark/jars/
cp -n "$AWS_BUNDLE" /usr/local/spark/jars/

# Restore caller's shell options so we don't leak -eo pipefail to start.sh
eval "$_SAVED_OPTS"
