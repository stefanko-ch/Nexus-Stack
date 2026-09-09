#!/bin/bash
# =============================================================================
# Materialise Unity Catalog's per-deployment configuration, then hand over.
# =============================================================================
# Both files below carry values that differ per deployment, and one of them
# carries a password. Writing them here rather than bind-mounting them from the
# host is deliberate, and the reason is a bug this repository already paid for
# once:
#
#   A single-file bind mount pins the inode. The deploy's rsync REPLACES files
#   rather than rewriting them, so the container keeps reading the copy it saw
#   when it was created -- for as long as it lives. Measured on Spark before
#   #810: the host file carried the fix, `docker exec ... stat` inside the
#   container reported a different inode from hours earlier, and the deploy
#   reported success while the cluster ran the old configuration.
#
# Mounting the whole directory is the fix Spark used, but it is not available
# here: /home/unitycatalog/etc/conf also holds certs.json, key_id.txt,
# private_key.der, public_key.der and token.txt, which the server needs and
# this repository does not have. Mounting over the directory would hide them.
#
# So: no config bind mount at all. Static settings are baked into the image
# (see the Dockerfile), per-deployment values arrive as environment variables,
# and this script writes them into the files the server reads. The deploy runs
# `docker compose up -d --build` every time, so a changed image is picked up
# without anything extra.
#
# `set -u` matters as much as `set -e` here: an unset variable would otherwise
# expand to nothing and write a syntactically valid config file pointing at the
# wrong database, which fails later and further away.
set -euo pipefail

CONF_DIR="/home/unitycatalog/etc/conf"

# --- Metastore ---------------------------------------------------------------
# hibernate.properties is read ONLY from this file. Unlike server.properties,
# it has no environment-variable override -- HibernateConfigurator loads the
# path directly (server/.../HibernateConfigurator.java:95) with no consultation
# of System.getenv. That asymmetry is why this script exists in the first place.
: "${UC_DB_HOST:?unity-catalog: UC_DB_HOST is unset}"
: "${UC_DB_NAME:?unity-catalog: UC_DB_NAME is unset}"
: "${UC_DB_USER:?unity-catalog: UC_DB_USER is unset}"
: "${UC_DB_PASSWORD:?unity-catalog: UC_DB_PASSWORD is unset}"

# Removed first, then written under a restrictive umask. Both halves matter:
#
#   - `umask` alone does nothing here. The image ships a hibernate.properties
#     at 0644, and a redirect onto an EXISTING file truncates it while leaving
#     its mode untouched -- so the password landed in a world-readable file.
#     Measured in the container, not reasoned about.
#   - chmod-after-write would close it, but leaves a window in which the file
#     already holds the password at 0644.
#
# Deleting first means the redirect creates the file, which is when umask
# applies, and there is no moment where it exists with the wrong mode.
rm -f "$CONF_DIR/hibernate.properties"
(
  umask 077
  cat > "$CONF_DIR/hibernate.properties" <<EOF
# Written at container start by entrypoint.sh. Not the image's copy, and not a
# bind mount -- edits here are lost on the next start.
hibernate.connection.driver_class=org.postgresql.Driver
hibernate.connection.url=jdbc:postgresql://${UC_DB_HOST}/${UC_DB_NAME}
hibernate.connection.user=${UC_DB_USER}
hibernate.connection.password=${UC_DB_PASSWORD}
hibernate.hbm2ddl.auto=update
hibernate.show_sql=false
hibernate.archive.autodetection=class
hibernate.use_sql_comments=true
EOF
)

# --- Object storage ----------------------------------------------------------
# These keys COULD be passed as environment variables instead --
# ServerProperties.getProperty checks System.getenv before the file -- but they
# would have to be named literally `s3.bucketPath.0`, and a dotted environment
# variable name is awkward enough through compose and .env that writing the file
# is the plainer option.
#
# Rebuilt from the pristine copy the Dockerfile keeps beside it, NOT appended to
# whatever is already there. The container restarts (`restart: unless-stopped`),
# and each restart re-runs this script against the same writable layer -- so a
# plain `>>` would stack another s3.* block on every restart and grow the file
# without bound. Properties.load would still resolve the last one, which is
# precisely what would keep the growth invisible until someone read the file.
# `cat >` rather than `cp`, and the difference is not stylistic. This image is
# Alpine, so `cp` is BusyBox's: it recreates the destination with the SOURCE's
# mode. The base file is 0444, so a `cp` leaves server.properties read-only and
# the append below fails with "Permission denied" -- and on the next start even
# the copy fails, because the destination is no longer writable either.
# Redirection truncates the existing file and leaves its mode alone.
cat "$CONF_DIR/server.properties.base" > "$CONF_DIR/server.properties"

# Subtree this catalog owns inside the shared data bucket. Not configurable on
# purpose: the value is part of the bucket's layout contract, and a deployment
# that changed it would silently orphan every table already recorded, because
# Unity Catalog stores table locations ABSOLUTELY -- `s3://bucket/demo/cities`,
# not a path relative to bucketPath. A location outside the configured
# bucketPath gets no credentials vended for it.
#
# The bucket is shared: Lakekeeper owns `lakekeeper/`, pg-ducklake writes its
# own tables, and Spark can be pointed anywhere. Before this prefix existed,
# Unity Catalog was the only one writing to the ROOT, so its tables showed up
# as a bare schema name -- a folder called `demo` that says nothing about who
# made it, and that would collide outright with any other stack choosing the
# same word.
UC_R2_PREFIX="unity-catalog"

if [ -n "${UC_R2_BUCKET:-}" ]; then
  : "${R2_ACCOUNT_ID:?unity-catalog: UC_R2_BUCKET is set but R2_ACCOUNT_ID is not}"
  : "${R2_ENDPOINT_HOST:?unity-catalog: UC_R2_BUCKET is set but R2_ENDPOINT_HOST is not}"
  : "${R2_ACCESS_KEY_ID:?unity-catalog: UC_R2_BUCKET is set but R2_ACCESS_KEY_ID is not}"
  : "${R2_SECRET_ACCESS_KEY:?unity-catalog: UC_R2_BUCKET is set but R2_SECRET_ACCESS_KEY is not}"

  cat >> "$CONF_DIR/server.properties" <<EOF

# --- Appended at container start by entrypoint.sh ---
s3.bucketPath.0=s3://${UC_R2_BUCKET}/${UC_R2_PREFIX}
s3.region.0=auto
# Never dereferenced. ServerProperties.getS3Configurations drops a bucket entry
# unless bucketPath+region+awsRoleArn OR accessKey+secretKey+sessionToken are
# all present -- and credentialGenerator does NOT count towards either triple.
# This placeholder exists only to satisfy that gate;
# AwsCredentialVendor.createPerBucketCredentialGenerator returns the class below
# before any role is assumed.
s3.awsRoleArn.0=arn:aws:iam::000000000000:role/unused-with-credential-generator
s3.credentialGenerator.0=ch.nexusstack.unitycatalog.R2TemporaryCredentialGenerator
EOF
else
  echo "unity-catalog: no R2 bucket configured — external tables on object storage will not work" >&2
fi

exec "$@"
