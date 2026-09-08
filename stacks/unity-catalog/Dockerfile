# =============================================================================
# Unity Catalog + the R2 credential generator
# =============================================================================
# Upstream's image, plus one compiled class. Everything else this stack needs is
# already inside it:
#
#   - The PostgreSQL JDBC driver (42.7.12) is on the server classpath as shipped.
#     Verified in the image rather than assumed:
#       $ docker run --rm --entrypoint sh unitycatalog/unitycatalog:v0.6.0 \
#           -c 'case "$(cat /home/unitycatalog/server/target/classpath)" in
#                 *postgresql-42*) echo on-classpath ;; esac'
#       on-classpath
#     So switching the metastore to Postgres needs a hibernate.properties and
#     nothing else.
#
#   - Jackson, used below to build the JWT segments, is a compile dependency of
#     the server itself.
#
# WHY A CUSTOM CLASS AT ALL. See the class javadoc for the measurements; in
# short, neither built-in generator can talk to R2, and returning credentials
# without a session token fails client-side in unitycatalog-hadoop.
#
# HOW IT GETS ONTO THE CLASSPATH. The launcher runs
# `java -cp $(cat server/target/classpath) io.unitycatalog.server.UnityCatalogServer`
# — the classpath is a FILE read at startup, so appending one entry is enough
# and the server itself is not rebuilt.
# =============================================================================

# The compile stage copies upstream's tree to the SAME path it lives at in the
# published image, because server/target/classpath holds absolute paths. Copying
# it anywhere else silently produces an unresolvable classpath and a compile
# error about missing Unity Catalog classes.
FROM unitycatalog/unitycatalog:v0.6.0 AS upstream

FROM eclipse-temurin:17-jdk AS build
COPY --from=upstream /home/unitycatalog /home/unitycatalog
COPY credentials/R2TemporaryCredentialGenerator.java \
     /src/ch/nexusstack/unitycatalog/
# --release 17 pins the bytecode to what the runtime image actually runs
# (Corretto 17, class file version 61). Without it, a newer JDK base image would
# emit classes the server cannot load, and the failure would appear at vend time
# rather than at build time.
RUN javac --release 17 \
      -cp "$(cat /home/unitycatalog/server/target/classpath)" \
      -d /out \
      /src/ch/nexusstack/unitycatalog/R2TemporaryCredentialGenerator.java \
 && cd /out \
 && jar cf /nexus-uc-credentials.jar . \
 && jar tf /nexus-uc-credentials.jar

FROM unitycatalog/unitycatalog:v0.6.0
USER root
COPY --from=build /nexus-uc-credentials.jar \
     /home/unitycatalog/jars-extra/nexus-uc-credentials.jar
RUN CP=/home/unitycatalog/server/target/classpath \
 && chmod u+w "$CP" \
 && printf ':%s' /home/unitycatalog/jars-extra/nexus-uc-credentials.jar >> "$CP" \
 && chmod a-w "$CP" \
 && chmod a+r /home/unitycatalog/jars-extra/nexus-uc-credentials.jar

# The static half of the configuration, baked in rather than bind-mounted. The
# per-deployment half (metastore DSN, bucket) is written by entrypoint.sh at
# container start; see the comment block there for why nothing under etc/conf is
# mounted from the host.
#
# `.base` is the pristine copy the entrypoint rebuilds from on every start, so
# restarts cannot stack duplicate s3.* blocks.
COPY conf/server.properties /home/unitycatalog/etc/conf/server.properties.base
COPY entrypoint.sh /usr/local/bin/nexus-entrypoint.sh
RUN chmod 0755 /usr/local/bin/nexus-entrypoint.sh \
 && chown unitycatalog:unitycatalog /home/unitycatalog/etc/conf/server.properties.base \
 && chmod 0444 /home/unitycatalog/etc/conf/server.properties.base

# Back to the unprivileged user upstream runs as. Leaving this as root would
# undo the one thing the base image already gets right.
USER unitycatalog
ENTRYPOINT ["/usr/local/bin/nexus-entrypoint.sh"]
# Unchanged from upstream, and named explicitly because setting ENTRYPOINT
# above would otherwise leave the inherited CMD as the argument to a script
# that ends in `exec "$@"` -- correct today, but only by inheritance.
CMD ["./bin/start-uc-server"]
