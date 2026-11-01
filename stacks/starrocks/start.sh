#!/bin/bash
# =============================================================================
# start.sh - wraps the StarRocks all-in-one entrypoint
# =============================================================================
# Two things the image cannot be told through its environment:
#
# 1. Memory. fe.conf ships -Xmx8192m and the BE takes 90% of the host's RAM
#    by default -- on a 16 GB server shared with other stacks. Both are
#    capped here before the services start.
#
# 2. Credentials. The image's director script connects as root on every
#    start, with MYSQL_PWD as the password. While root has no password, a
#    set MYSQL_PWD makes that connection fail ("Password error, stop
#    retrying!" and a forced shutdown, measured on 4.1.7). So until the
#    password has been set, MYSQL_PWD stays unset and a background job sets
#    it once the bootstrap has finished, together with the nexus-starrocks
#    account people actually use.
#
#    Whether that has happened is recorded by a marker in /opt/nexus/state,
#    a directory of its own inside the persisted data, written only after
#    the SQL succeeded. Deciding by "FE metadata exists" instead would
#    hand MYSQL_PWD to a restart after a failed attempt, and the container
#    would shut itself down on every start from then on.
# =============================================================================
set -euo pipefail

SR_HOME=/data/deploy/starrocks
STATE=/opt/nexus/state
MARKER="$STATE/credentials-set"
: "${STARROCKS_ROOT_PASSWORD:?STARROCKS_ROOT_PASSWORD must be set}"

sed -i 's/-Xmx8192m/-Xmx2048m/' "$SR_HOME/fe/conf/fe.conf"
grep -q '^mem_limit' "$SR_HOME/be/conf/be.conf" || echo 'mem_limit = 3G' >> "$SR_HOME/be/conf/be.conf"

if [ -f "$MARKER" ]; then
    export MYSQL_PWD="$STARROCKS_ROOT_PASSWORD"
else
    echo "start.sh: credentials not set yet; setting them after bootstrap"
    unset MYSQL_PWD
    (
        until [ -f "$SR_HOME/bootstrap_done" ]; do sleep 5; done
        # The SQL goes in on stdin, so the password is not in the process
        # list. The renderer only lets an alphanumeric password through,
        # which is what makes quoting it here safe.
        if printf '%s\n' \
            "ALTER USER 'root' IDENTIFIED BY '${STARROCKS_ROOT_PASSWORD}';" \
            "CREATE USER IF NOT EXISTS 'nexus-starrocks' IDENTIFIED BY '${STARROCKS_ROOT_PASSWORD}' DEFAULT ROLE 'root';" \
            | MYSQL_PWD="" mysql -h 127.0.0.1 -P 9030 -u root --batch; then
            mkdir -p "$STATE"
            touch "$MARKER"
            echo "start.sh: credentials set"
        else
            echo "start.sh: ERROR setting credentials -- root has no password; the next start retries" >&2
        fi
    ) &
fi

exec ./entrypoint.sh
