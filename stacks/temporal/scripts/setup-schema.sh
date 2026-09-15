#!/bin/sh
# =============================================================================
# Temporal - one-shot schema setup (runs in temporalio/admin-tools)
# =============================================================================
# Replaces what the deprecated `temporalio/auto-setup` image did on every
# start. Upstream deprecated that image in the v1.30.1 release notes and
# publishes no tag for it past 1.29.x; its replacement in
# temporalio/samples-server/compose is this same sequence, run from
# admin-tools before the server starts.
#
# Safe to run on every `docker compose up`, which is exactly how it runs.
# Measured against temporalio/admin-tools:1.32.0 and postgres:17-alpine by
# running the full sequence twice against the same database:
#   - `create` on a database that already exists exits 0
#   - `setup-schema -v 0.0` on an initialised database logs "Current database
#     schema version 1.19 is greater than initial schema version 0.0. Skip
#     version upgrade" and exits 0
#   - `update-schema` applies only the versioned directories newer than the
#     recorded version, and "found zero updates" when there are none
# Result both times: temporal at 1.19, temporal_visibility at 1.14.
#
# `update-schema` is also what makes a server version bump work: bump the
# admin-tools image with the server image and this applies the new
# migrations before the new server starts.
#
# `set -eu`: any failing step exits non-zero, so `temporal` (which waits on
# service_completed_successfully) never starts against a half-built schema
# and `docker compose up` reports the failure.
# =============================================================================
set -eu

: "${POSTGRES_PWD:?must be set (TEMPORAL_DB_PASSWORD, rendered by service_env._render_temporal)}"

# temporal-sql-tool reads the password from SQL_PASSWORD rather than a flag,
# which keeps it out of the process argument list.
SQL_PASSWORD="$POSTGRES_PWD"
export SQL_PASSWORD

SCHEMA_ROOT=/etc/temporal/schema/postgresql/v12

sql_tool() {
  temporal-sql-tool \
    --plugin postgres12 \
    --ep "${POSTGRES_SEEDS}" \
    -p "${DB_PORT:-5432}" \
    -u "${POSTGRES_USER}" \
    "$@"
}

echo "Temporal schema setup: waiting for ${POSTGRES_SEEDS}:${DB_PORT:-5432}"
nc -z -w 10 "${POSTGRES_SEEDS}" "${DB_PORT:-5432}"

# Two databases: `temporal` holds executions and history, `temporal_visibility`
# backs the list/filter queries the Web UI runs.
for db in temporal temporal_visibility; do
  case "$db" in
    temporal) dir="$SCHEMA_ROOT/temporal/versioned" ;;
    temporal_visibility) dir="$SCHEMA_ROOT/visibility/versioned" ;;
  esac
  echo "Temporal schema setup: database $db"
  sql_tool --db "$db" create
  sql_tool --db "$db" setup-schema -v 0.0
  sql_tool --db "$db" update-schema -d "$dir"
done

echo "Temporal schema setup complete"
