# =============================================================================
# Hive Metastore - the standalone catalog service
# =============================================================================
# One line of work on top of apache/hive: the PostgreSQL JDBC driver.
#
# The image ships exactly one driver — derby-10.14.2.0.jar — and Derby is a
# single-process embedded database that would put the catalogue in the
# container's own filesystem. `ls /opt/hive/lib | grep -iE 'postgres|mysql'`
# returns nothing, and `/opt/hive/jdbc` is empty. Without this layer the
# entrypoint's schematool step fails to find a driver for DB_DRIVER=postgres.
#
# Pinned by version AND by sha256. Maven Central publishes a .sha1 next to
# the jar; the 256 below was computed from the downloaded file and the sha1
# checked against upstream's at the same time.
# =============================================================================

FROM apache/hive:4.1.0

USER root

ARG PG_JDBC_VERSION=42.7.13
ARG PG_JDBC_SHA256=6e0e4cc2d8cae902084f8a2b18728b073a6fd9d1f87c9d8bff8f298c18185b93

RUN curl -sSfL -o /opt/hive/lib/postgresql.jar \
      "https://repo1.maven.org/maven2/org/postgresql/postgresql/${PG_JDBC_VERSION}/postgresql-${PG_JDBC_VERSION}.jar" && \
    echo "${PG_JDBC_SHA256}  /opt/hive/lib/postgresql.jar" | sha256sum -c - && \
    chown hive:hive /opt/hive/lib/postgresql.jar

USER hive

EXPOSE 9083
