# =============================================================================
# Apache Spark - Custom image with Python 3.13, S3A, and Spark Connect support
# =============================================================================
# The official apache/spark:4.2.0 image is based on Ubuntu 22.04 (Jammy) which
# ships Python 3.10. Jupyter pyspark-notebook uses Python 3.13 (via conda).
# PySpark requires matching Python minor versions between driver and executors.
#
# This Dockerfile:
# 1. Installs Python 3.13 from the deadsnakes PPA to match Jupyter.
# 2. Downloads hadoop-aws + AWS SDK v2 JARs for S3A filesystem support
#    (required for s3a:// paths, e.g. Hetzner Object Storage).
# 3. Downloads Spark Connect server JARs so the master can start a gRPC
#    Connect endpoint (port 15002) for thin clients (Marimo, code-server,
#    eventually Jupyter). Classic standalone-cluster on 7077 keeps
#    serving Jupyter unchanged.
# =============================================================================

FROM apache/spark:4.2.0

USER root

# Install Python 3.13 from deadsnakes PPA to match Jupyter's Python version.
# The base image (Ubuntu 22.04 Jammy) only ships Python 3.10.
RUN apt-get update && \
    apt-get install -y software-properties-common curl && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.13 && \
    rm -rf /var/lib/apt/lists/*

# Repoint /usr/bin/python3 -> python3.13, so that a process which ends up
# resolving the bare name still gets the version the driver runs.
#
# ⚠️ The claim this comment used to make has NOT been re-confirmed on
# 4.2.0, so it is not repeated as fact. It said Spark's
# PythonWorkerFactory hardcodes the literal "python3" and ignores
# `spark.pyspark.python`, `spark.executorEnv.PYSPARK_PYTHON` and
# `PYSPARK_PYTHON` alike. In the 4.2.0 source that is not what the code
# does: `PythonWorkerFactory` takes `pythonExec` as a parameter
# (PythonWorkerFactory.scala:75), and the only bare "python3" is a
# FALLBACK, reached solely when neither env var is set:
#
#   PythonUtils.scala:159
#   sys.env.getOrElse("PYSPARK_DRIVER_PYTHON",
#                     sys.env.getOrElse("PYSPARK_PYTHON", "python3"))
#
# Either the behaviour changed between 4.1.1 and 4.2.0, or the original
# diagnosis attributed a real symptom to the wrong line. The symlink is
# kept either way: it costs nothing, and it makes the fallback land on
# 3.13 instead of 3.10 — which is the outcome that was wanted, whatever
# the mechanism. If a PYTHON_VERSION_MISMATCH ever reappears, start by
# re-deriving the cause rather than trusting this paragraph.
#
# Safety: the spark-worker container is minimal at runtime — no
# package installs (apt-get only runs at image build time, never
# inside the running container), no systemd, no OS scripts that
# would care which python3.x is the default. The previous concern
# about "not overwriting system python3" was theoretical; in
# practice nothing else in this image touches python3 at runtime
# except Spark itself, and Spark wants 3.13.
RUN ln -sf /usr/bin/python3.13 /usr/bin/python3

# PYSPARK_PYTHON env-var kept as belt-and-suspenders. With the symlink
# fix above, even Spark's hardcoded "python3" path resolves to 3.13,
# but explicit configuration still helps if anything in Spark looks
# up via this env var first.
ENV PYSPARK_PYTHON=/usr/bin/python3.13 \
    PYSPARK_DRIVER_PYTHON=/usr/bin/python3.13

# Download hadoop-aws and its runtime dependencies for S3A filesystem
# support. Spark ships the Hadoop client but not the hadoop-aws module,
# so these JARs are what makes s3a:// paths work at all.
#
# ⚠️ The hadoop-aws version MUST track the Hadoop that Spark bundles, and
# that changed with this base image:
#
#   Spark 4.1.1 -> Hadoop 3.4.2   (spark-parent_2.13-4.1.1.pom)
#   Spark 4.2.0 -> Hadoop 3.5.0   (spark-parent_2.13-4.2.0.pom)
#
# Confirmed in the image itself: /opt/spark/jars/hadoop-client-api-3.5.0.jar.
# Leaving 3.4.2 here would put a version-skewed hadoop-aws against
# hadoop-common 3.5.0 — the shape of failure that costs an afternoon
# because it surfaces as a NoSuchMethodError deep in a task, not as a
# build error.
#
# The AWS SDK version is not chosen freely either: hadoop-project-3.5.0.pom
# sets aws-java-sdk-v2.version=2.35.4.
#
# analyticsaccelerator-s3 is new in hadoop-aws 3.5.0 and is a COMPILE-scope
# dependency there (it was absent in 3.4.2). Whether S3AFileSystem loads it
# eagerly or only under `fs.s3a.input.stream.type=analytics` was not
# determined, so it is baked rather than gambled on: a missing compile-scope
# class costs a NoClassDefFoundError at first S3 access, and 4 MB of image
# is the cheaper side of that bet. Version from the same POM
# (amazon-s3-analyticsaccelerator-s3.version=1.3.1).
#
# Every artifact is SHA-1 verified — see the reasoning in the Connect
# block below. This closes the TODO that block used to carry: hadoop-aws
# and the SDK bundle were the two downloads without a guard.
RUN set -eux; \
    for a in \
        "org/apache/hadoop/hadoop-aws/3.5.0/hadoop-aws-3.5.0.jar" \
        "software/amazon/awssdk/bundle/2.35.4/bundle-2.35.4.jar" \
        "software/amazon/s3/analyticsaccelerator/analyticsaccelerator-s3/1.3.1/analyticsaccelerator-s3-1.3.1.jar" \
    ; do \
        jar="/opt/spark/jars/${a##*/}"; \
        curl -fSL "https://repo1.maven.org/maven2/$a" -o "$jar"; \
        curl -fSL "https://repo1.maven.org/maven2/$a.sha1" \
            | awk -v j="$jar" '{print $1 "  " j}' \
            | sha1sum -c -; \
    done

# Download Spark Connect server JARs. Pre-baking them avoids a ~30s
# ivy-resolution cold-start every container boot (which is what
# `--packages org.apache.spark:spark-connect_2.13:4.2.0` would do at
# runtime). Same pattern as the hadoop-aws JARs above. Pinned to
# match the apache/spark:4.2.0 base so there's no Scala-major or
# protobuf-shading mismatch with the rest of the assembly.
#
# Each JAR is verified against Maven Central's published SHA-1
# checksum so the build fails loudly if the artifact bytes get
# tampered with at the registry, in transit, or via a
# cache/CDN-poisoning attack. SHA-1 (not 256/512) because Maven
# Central only publishes .sha1 and .md5 sidecars for these
# artifacts — verified live (.sha512 returns 404). SHA-1 is
# cryptographically weak BUT still effective against random
# corruption + non-targeted tampering, which is the realistic
# threat model for a Maven Central CDN-fetch in CI.
#
# The loop form matters beyond tidiness: the earlier per-JAR blocks
# repeated the artifact path four times each, and `sha1sum -c` reports a
# name mismatch and a hash mismatch with the same exit status. A typo in
# one of the four copies therefore failed the build with a message that
# pointed at tampering. Deriving the filename from the path removes that.
RUN set -eux; \
    for a in \
        "org/apache/spark/spark-connect_2.13/4.2.0/spark-connect_2.13-4.2.0.jar" \
        "org/apache/spark/spark-connect-common_2.13/4.2.0/spark-connect-common_2.13-4.2.0.jar" \
    ; do \
        jar="/opt/spark/jars/${a##*/}"; \
        curl -fSL "https://repo1.maven.org/maven2/$a" -o "$jar"; \
        curl -fSL "https://repo1.maven.org/maven2/$a.sha1" \
            | awk -v j="$jar" '{print $1 "  " j}' \
            | sha1sum -c -; \
    done

USER spark
