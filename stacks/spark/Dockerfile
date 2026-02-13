# =============================================================================
# Apache Spark - Custom image with Python 3.13 and S3A support
# =============================================================================
# The official apache/spark:4.1.1 image is based on Ubuntu 22.04 (Jammy) which
# ships Python 3.10. Jupyter pyspark-notebook uses Python 3.13 (via conda).
# PySpark requires matching Python minor versions between driver and executors.
#
# This Dockerfile:
# 1. Installs Python 3.13 from the deadsnakes PPA to match Jupyter.
# 2. Downloads hadoop-aws + AWS SDK v2 JARs for S3A filesystem support
#    (required for s3a:// paths, e.g. Hetzner Object Storage).
# =============================================================================

FROM apache/spark:4.1.1

USER root

# Install Python 3.13 from deadsnakes PPA to match Jupyter's Python version.
# The base image (Ubuntu 22.04 Jammy) only ships Python 3.10.
RUN apt-get update && \
    apt-get install -y software-properties-common curl && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.13 && \
    rm -rf /var/lib/apt/lists/*

# Configure Spark to use Python 3.13 without overwriting the system python3 (3.10).
ENV PYSPARK_PYTHON=/usr/bin/python3.13 \
    PYSPARK_DRIVER_PYTHON=/usr/bin/python3.13

# Download hadoop-aws and AWS SDK v2 bundle for S3A filesystem support.
# Spark 4.1.x ships Hadoop 3.4.2 but does not include the hadoop-aws module.
# These JARs enable s3a:// paths (e.g., Hetzner Object Storage).
RUN curl -fSL https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.4.2/hadoop-aws-3.4.2.jar \
        -o /opt/spark/jars/hadoop-aws-3.4.2.jar && \
    curl -fSL https://repo1.maven.org/maven2/software/amazon/awssdk/bundle/2.29.52/bundle-2.29.52.jar \
        -o /opt/spark/jars/bundle-2.29.52.jar

USER spark
