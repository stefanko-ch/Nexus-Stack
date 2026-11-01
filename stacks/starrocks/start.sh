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
# 2. The root password. The image's director script connects as root on
#    every start, with MYSQL_PWD as the password. On the very first start
#    root has no password yet, and a set MYSQL_PWD makes that connection
#    fail ("Password error, stop retrying!" and a forced shutdown, measured
#    on 4.1.7). So on a first start -- empty FE metadata -- MYSQL_PWD is
#    left unset, and a background job sets the root password once the
#    bootstrap has finished. On every later start, including one after the
#    metadata was restored from R2, MYSQL_PWD carries the password.
# =============================================================================
set -euo pipefail

SR_HOME=/data/deploy/starrocks
: "${STARROCKS_ROOT_PASSWORD:?STARROCKS_ROOT_PASSWORD must be set}"

sed -i 's/-Xmx8192m/-Xmx2048m/' "$SR_HOME/fe/conf/fe.conf"
grep -q '^mem_limit' "$SR_HOME/be/conf/be.conf" || echo 'mem_limit = 3G' >> "$SR_HOME/be/conf/be.conf"

if [ -z "$(ls -A "$SR_HOME/fe/meta" 2>/dev/null)" ]; then
    echo "start.sh: first start (no FE metadata); root password is set after bootstrap"
    unset MYSQL_PWD
    (
        until [ -f "$SR_HOME/bootstrap_done" ]; do sleep 5; done
        if MYSQL_PWD="" mysql -h 127.0.0.1 -P 9030 -u root --batch \
            -e "ALTER USER 'root' IDENTIFIED BY '${STARROCKS_ROOT_PASSWORD}'"; then
            echo "start.sh: root password set"
        else
            echo "start.sh: ERROR setting the root password -- root has none" >&2
        fi
    ) &
else
    export MYSQL_PWD="$STARROCKS_ROOT_PASSWORD"
fi

exec ./entrypoint.sh
