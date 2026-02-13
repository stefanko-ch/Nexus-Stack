#!/bin/bash
set -euo pipefail
# =============================================================================
# Download and install hadoop-aws + AWS SDK v2 JARs for S3A filesystem support.
# Runs as root via Jupyter's before-notebook.d hook (before user switch).
#
# JARs are cached in the persistent volume (.spark-jars/) so the ~642MB
# download (hadoop-aws ~1MB + AWS SDK v2 bundle ~641MB) only happens on
# first start.
# =============================================================================
JARS_CACHE=/home/jovyan/work/.spark-jars
HADOOP_AWS="$JARS_CACHE/hadoop-aws-3.4.2.jar"
AWS_BUNDLE="$JARS_CACHE/bundle-2.29.52.jar"

if [ ! -f "$HADOOP_AWS" ] || [ ! -f "$AWS_BUNDLE" ]; then
    echo "[jupyter] Downloading S3A support JARs (first start only)..."
    mkdir -p "$JARS_CACHE"
    curl -fSL https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.4.2/hadoop-aws-3.4.2.jar \
        -o "$HADOOP_AWS"
    curl -fSL https://repo1.maven.org/maven2/software/amazon/awssdk/bundle/2.29.52/bundle-2.29.52.jar \
        -o "$AWS_BUNDLE"
    chown -R 1000:100 "$JARS_CACHE"
    echo "[jupyter] S3A JARs downloaded."
fi
cp -n "$HADOOP_AWS" /usr/local/spark/jars/
cp -n "$AWS_BUNDLE" /usr/local/spark/jars/
