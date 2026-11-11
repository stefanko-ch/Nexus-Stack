#!/bin/bash
# =============================================================================
# Run `tofu apply`, again when it failed on a transient network error
# =============================================================================
# Usage (from the OpenTofu module directory):
#   bash tofu-apply-retry.sh -var-file=config.tfvars -auto-approve
#
# Every argument is passed to `tofu apply` unchanged.
#
# Why (#796): a deploy was lost because Hetzner Object Storage did not answer
# one request in the middle of an apply ("timeout awaiting response headers")
# and answered fine minutes later. The apply is the longest step and talks
# to the most third parties (Hetzner, Cloudflare, R2), and was the only one
# of them with no retry.
#
# Retried only when the output names a transport failure: a timeout, a reset
# or closed connection, a 502/503/504 from a provider API. Anything else,
# a real configuration error for instance, fails at once: retrying it would
# only print the same error three times.
#
# Safe to repeat: OpenTofu writes the state as resources are created, so a
# second apply continues from what the first one finished.
#
# The output streams to the log as it happens and is also kept in a temp
# file to classify the failure. That file is removed on exit; apply output
# can name resources and IDs, nothing here prints it a second time.
#
# Exit status: tofu's own status from the last attempt.
# =============================================================================

set -uo pipefail

ATTEMPTS="${TOFU_APPLY_ATTEMPTS:-3}"
DELAY_S="${TOFU_APPLY_RETRY_DELAY_S:-20}"

# Transport failures, as Go's net/http, the Hetzner and Cloudflare providers
# and the S3 client word them. Matched case-insensitively.
TRANSIENT='timeout awaiting response headers|i/o timeout|tls handshake timeout|connection reset by peer|connection refused|unexpected eof|broken pipe|no such host|temporary failure in name resolution|client\.timeout exceeded|context deadline exceeded|502 bad gateway|503 service unavailable|504 gateway time-?out|status code: 50[234]|statuscode: 50[234]'

LOG=$(mktemp)
trap 'rm -f "$LOG"' EXIT

attempt=1
while :; do
  tofu apply "$@" 2>&1 | tee "$LOG"
  status=${PIPESTATUS[0]}
  if [ "$status" -eq 0 ]; then
    exit 0
  fi
  if ! grep -qiE "$TRANSIENT" "$LOG"; then
    echo "❌ tofu apply failed (exit $status), not on a network error; not retrying"
    exit "$status"
  fi
  if [ "$attempt" -ge "$ATTEMPTS" ]; then
    echo "❌ tofu apply failed on a network error in all $ATTEMPTS attempts (exit $status)"
    exit "$status"
  fi
  echo "⚠️  tofu apply failed on a network error (attempt $attempt of $ATTEMPTS); retrying in ${DELAY_S}s"
  sleep "$DELAY_S"
  attempt=$((attempt + 1))
done
