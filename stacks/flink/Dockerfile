# =============================================================================
# Apache Flink - Custom image with the Kafka SQL and Fluss connectors
# =============================================================================
# The official flink:1.20.1 image does not include the Kafka SQL connector.
# Without it, Flink SQL cannot create Kafka/Redpanda source or sink tables.
#
# This Dockerfile downloads the flink-sql-connector-kafka fat JAR into
# /opt/flink/lib/ so it is available to all SQL jobs out of the box.
# =============================================================================

FROM flink:1.20.1

# Download the Kafka SQL connector (fat JAR with all Kafka client dependencies).
# Version 3.4.0-1.20 is compatible with Flink 1.20.x.
RUN curl -fSL https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.4.0-1.20/flink-sql-connector-kafka-3.4.0-1.20.jar \
        -o /opt/flink/lib/flink-sql-connector-kafka-3.4.0-1.20.jar

# The Apache Fluss connector, so Flink SQL can use the fluss stack as a
# catalog (CREATE CATALOG ... WITH ('type' = 'fluss', ...)). The 1.20 build
# of Fluss 1.0.0, matching the fluss stack's server version.
RUN curl -fSL https://repo1.maven.org/maven2/org/apache/fluss/fluss-flink-1.20/1.0.0/fluss-flink-1.20-1.0.0.jar \
        -o /opt/flink/lib/fluss-flink-1.20-1.0.0.jar
