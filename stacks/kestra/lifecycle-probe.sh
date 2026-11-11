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
ENV_FILE=/opt/docker-server/stacks/kestra/.env
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
CURL_AUTH=(--config <(printf 'user = "%s:%s"\n' "$KUSER" "$KPASS"))

case "$ACTION" in
  create)
    FLOW_YAML=$(printf 'id: %s\nnamespace: %s\ndescription: "release gate %s"\ntasks:\n  - id: hello\n    type: io.kestra.plugin.core.log.Log\n    message: "%s"\n' "$FLOW" "$NAMESPACE" "$TOKEN" "$TOKEN")
    # PUT replaces a flow left by an earlier run; POST creates it.
    if ! STATUS=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' "${CURL_AUTH[@]}" -X PUT \
        -H 'Content-Type: application/x-yaml' --data-binary "$FLOW_YAML" "$API/$NAMESPACE/$FLOW"); then
      echo "kestra: API not reachable"
      exit 1
    fi
    if [ "$STATUS" = "404" ]; then
      STATUS=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' "${CURL_AUTH[@]}" -X POST \
        -H 'Content-Type: application/x-yaml' --data-binary "$FLOW_YAML" "$API")
    fi
    case "$STATUS" in
      2??) echo "kestra: saved flow $NAMESPACE.$FLOW" ;;
      *) echo "kestra: saving the flow answered HTTP $STATUS"; exit 1 ;;
    esac
    ;;
  verify)
    if ! BODY=$(curl -sS --max-time 30 -f "${CURL_AUTH[@]}" "$API/$NAMESPACE/$FLOW?source=true"); then
      echo "kestra: flow $NAMESPACE.$FLOW is gone after the teardown"
      exit 1
    fi
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
