#!/bin/bash
# =============================================================================
# Lifecycle probe for Kestra (release gate, #712)
# =============================================================================
# Run ON THE SERVER as root, by .github/workflows/release-gate.yml through the
# spin-up's `lifecycle_probe` input:
#   lifecycle-probe.sh create <token>   before the teardown
#   lifecycle-probe.sh verify <token>   after the following spin-up
#
# A Kestra user's work is flows. `create` saves one through the API, as the
# UI does; `verify` reads it back after the rebuild. Kestra lost its flows
# across a rebuild teardown once (#936), which is exactly this check.
# The API is reached on the published port with the admin login from the
# stack's .env; nothing here prints the password.
# =============================================================================

set -euo pipefail

ACTION=${1:?usage: lifecycle-probe.sh create|verify <token>}
TOKEN=${2:?usage: lifecycle-probe.sh create|verify <token>}
# Overridable only so tests/unit/test_release_gate.py can run this probe
# against a stand-in; the gate never sets it.
ENV_FILE=${KESTRA_PROBE_ENV_FILE:-/opt/docker-server/stacks/kestra/.env}
API=http://localhost:8085/api/v1/flows
NAMESPACE=nexus.releasegate
FLOW=lifecycle_probe

if ! docker ps --format '{{.Names}}' | grep -qx kestra; then
  echo "kestra: not running; the release gate needs Kestra enabled on this stack"
  exit 1
fi
KUSER=$(sed -n 's/^KESTRA_ADMIN_USER=//p' "$ENV_FILE" | tail -1)
KPASS=$(sed -n 's/^KESTRA_ADMIN_PASSWORD=//p' "$ENV_FILE" | tail -1)
if [ -z "$KUSER" ] || [ -z "$KPASS" ]; then
  echo "kestra: no admin login in $ENV_FILE"
  exit 1
fi
# The login goes to curl through a config file on a file descriptor, so it
# never appears in the process list. The `<(...)` must sit in the curl
# command itself: a process substitution lives only as long as the command
# it is written in, so one stored in a variable is already closed when a
# later curl reads it ("cannot read config from '/dev/fd/63'", the first
# release gate runs on 2026-11-19).
kestra_api() {
  curl -sS --max-time 30 --config <(printf 'user = "%s:%s"\n' "$KUSER" "$KPASS") "$@"
}

case "$ACTION" in
  create)
    FLOW_YAML=$(printf 'id: %s\nnamespace: %s\ndescription: "release gate %s"\ntasks:\n  - id: hello\n    type: io.kestra.plugin.core.log.Log\n    message: "%s"\n' "$FLOW" "$NAMESPACE" "$TOKEN" "$TOKEN")
    # PUT replaces a flow left by an earlier run; POST creates it.
    # curl's exit status is reported as it is: it fails for more reasons
    # than an unreachable API, and this step cannot tell which.
    STATUS=$(kestra_api -o /dev/null -w '%{http_code}' -X PUT \
        -H 'Content-Type: application/x-yaml' --data-binary "$FLOW_YAML" "$API/$NAMESPACE/$FLOW") || {
      rc=$?
      echo "kestra: saving the flow failed (exit $rc from curl)"
      exit 1
    }
    if [ "$STATUS" = "404" ]; then
      STATUS=$(kestra_api -o /dev/null -w '%{http_code}' -X POST \
          -H 'Content-Type: application/x-yaml' --data-binary "$FLOW_YAML" "$API") || {
        rc=$?
        echo "kestra: creating the flow failed (exit $rc from curl)"
        exit 1
      }
    fi
    case "$STATUS" in
      2??) echo "kestra: saved flow $NAMESPACE.$FLOW" ;;
      *) echo "kestra: saving the flow answered HTTP $STATUS"; exit 1 ;;
    esac
    ;;
  verify)
    # -f makes an HTTP error a non-zero exit too, so a missing flow (404)
    # and a failed request land here alike; curl's own message above this
    # line says which.
    BODY=$(kestra_api -f "$API/$NAMESPACE/$FLOW?source=true") || {
      rc=$?
      echo "kestra: reading flow $NAMESPACE.$FLOW failed (exit $rc from curl; 22 is an HTTP error such as 404, a flow gone after the teardown)"
      exit 1
    }
    if ! grep -qF "release gate $TOKEN" <<< "$BODY"; then
      echo "kestra: flow $NAMESPACE.$FLOW is not the one this run saved"
      exit 1
    fi
    echo "kestra: flow survived, API answers"
    ;;
  *)
    echo "unknown action: $ACTION"
    exit 2
    ;;
esac
