# =============================================================================
# Apache Spark - Custom image with Python 3.13
# =============================================================================
# The official apache/spark:4.1.1 image is based on Ubuntu 22.04 (Jammy) which
# ships Python 3.10. Jupyter pyspark-notebook uses Python 3.13 (via conda).
# PySpark requires matching Python minor versions between driver and executors.
#
# This Dockerfile installs Python 3.13 from the deadsnakes PPA to match Jupyter.
# =============================================================================

FROM apache/spark:4.1.1

USER root

# Install Python 3.13 from deadsnakes PPA to match Jupyter's Python version.
# The base image (Ubuntu 22.04 Jammy) only ships Python 3.10.
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.13 && \
    ln -sf /usr/bin/python3.13 /usr/bin/python3 && \
    rm -rf /var/lib/apt/lists/*

USER spark
