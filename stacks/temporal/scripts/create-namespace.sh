#!/bin/sh
# =============================================================================
# Temporal - create the `default` namespace (runs in temporalio/admin-tools)
# =============================================================================
# The server creates only its internal `temporal-system` namespace. Every SDK
# sample, and the Web UI's landing page, assume `default` exists; without it
# the first `client.start_workflow(...)` fails with "Namespace default is not
# found".
#
# Idempotent: an existing namespace is detected with `describe` and left
# alone, so its retention and any settings changed by hand survive a restart.
#
# Runs after `temporal` reports healthy, but a freshly started frontend can
# still refuse namespace operations for a few seconds while membership
# settles, so creation is retried a bounded number of times. The last error is
# printed rather than swallowed, and exhausting the retries exits 1 -- which
# `temporal-ui` sees through service_completed_successfully, so
# `docker compose up` fails loudly instead of leaving a UI with no namespace.
# =============================================================================
set -eu

NAMESPACE="${DEFAULT_NAMESPACE:-default}"
ADDRESS="${TEMPORAL_ADDRESS:?must be set}"
RETENTION="${DEFAULT_NAMESPACE_RETENTION:-72h}"
MAX_ATTEMPTS=30
SLEEP_SECONDS=2

attempt=1
while :; do
  if temporal operator namespace describe --namespace "$NAMESPACE" --address "$ADDRESS" >/dev/null 2>&1; then
    echo "Namespace '$NAMESPACE' already exists; leaving it unchanged"
    exit 0
  fi

  if output=$(temporal operator namespace create --namespace "$NAMESPACE" --retention "$RETENTION" --address "$ADDRESS" 2>&1); then
    echo "Namespace '$NAMESPACE' created (retention $RETENTION)"
    exit 0
  fi

  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "ERROR: could not create namespace '$NAMESPACE' after $MAX_ATTEMPTS attempts" >&2
    echo "Last error: ${output:-(no output)}" >&2
    exit 1
  fi

  echo "Namespace '$NAMESPACE' not created yet (attempt $attempt/$MAX_ATTEMPTS): ${output:-(no output)}"
  attempt=$((attempt + 1))
  sleep "$SLEEP_SECONDS"
done
