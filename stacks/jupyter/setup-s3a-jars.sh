#!/bin/bash
# =============================================================================
# Download and install hadoop-aws + AWS SDK v2 JARs for S3A filesystem support.
# Runs as root via Jupyter's before-notebook.d hook (before user switch).
#
# JARs are cached in the persistent volume (.spark-jars/) so the ~641MB
# download only happens on first start.
# =============================================================================
JARS_CACHE=/home/jovyan/work/.spark-jars
if [ ! -f "$JARS_CACHE/hadoop-aws-3.4.2.jar" ]; then
    echo "[jupyter] Downloading S3A support JARs (first start only)..."
    mkdir -p "$JARS_CACHE"
    curl -fSL https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.4.2/hadoop-aws-3.4.2.jar \
        -o "$JARS_CACHE/hadoop-aws-3.4.2.jar"
    curl -fSL https://repo1.maven.org/maven2/software/amazon/awssdk/bundle/2.29.52/bundle-2.29.52.jar \
        -o "$JARS_CACHE/bundle-2.29.52.jar"
    chown -R 1000:100 "$JARS_CACHE"
    echo "[jupyter] S3A JARs downloaded."
fi
cp -n "$JARS_CACHE/hadoop-aws-3.4.2.jar" /usr/local/spark/jars/
cp -n "$JARS_CACHE/bundle-2.29.52.jar" /usr/local/spark/jars/
