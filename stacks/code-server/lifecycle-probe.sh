#!/bin/bash
# =============================================================================
# Lifecycle probe for code-server (release gate, #712)
# =============================================================================
# Run ON THE SERVER as root, by .github/workflows/release-gate.yml through the
# spin-up's `lifecycle_probe` input:
#   lifecycle-probe.sh create <token>   before the teardown
#   lifecycle-probe.sh verify <token>   after the following spin-up
#
# What a student keeps in code-server is their home directory. `create`
# writes a file there as the `coder` user, through the container, the way
# the editor would; `verify` reads it back after the rebuild and checks the
# editor answers.
# =============================================================================

set -euo pipefail

ACTION=${1:?usage: lifecycle-probe.sh create|verify <token>}
TOKEN=${2:?usage: lifecycle-probe.sh create|verify <token>}
FILE=/home/coder/.nexus-release-gate/marker

case "$ACTION" in
  create)
    docker exec -u coder code-server sh -c 'mkdir -p "$(dirname "$1")" && printf "%s" "$2" > "$1"' _ "$FILE" "$TOKEN"
    echo "code-server: wrote $FILE"
    ;;
  verify)
    if ! GOT=$(docker exec code-server cat "$FILE" 2>&1); then
      echo "code-server: $FILE is gone after the teardown: $GOT"
      exit 1
    fi
    if [ "$GOT" != "$TOKEN" ]; then
      echo "code-server: $FILE holds something else than this run wrote"
      exit 1
    fi
    docker exec code-server curl -fsS -o /dev/null http://localhost:8080/healthz
    echo "code-server: file survived, editor answers"
    ;;
  *)
    echo "unknown action: $ACTION"
    exit 2
    ;;
esac
