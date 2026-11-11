#!/bin/bash
# =============================================================================
# Run every proven stack's lifecycle probe on the server (release gate, #712)
# =============================================================================
# Env: PROBE_ACTION (create|verify), PROBE_TOKEN (letters, digits, - and _).
# Reads the proven set from services.yaml, runs
#   stacks/<name>/lifecycle-probe.sh <action> <token>
# on `nexus` over ssh for each, and fails if any probe fails or is missing.
# A probe is safe to repeat (create overwrites, verify only reads), so a
# dropped connection (ssh exit 255) is retried once (#972).
# =============================================================================

set -uo pipefail

case "${PROBE_ACTION:-}" in
  create|verify) ;;
  *) echo "❌ PROBE_ACTION must be create or verify"; exit 2 ;;
esac
if ! [[ "${PROBE_TOKEN:-}" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "❌ PROBE_TOKEN must be letters, digits, - and _"
  exit 2
fi

if ! PROVEN=$(python3 -c '
import yaml
services = yaml.safe_load(open("services.yaml"))["services"]
print("\n".join(sorted(n for n, e in services.items() if e.get("tier") == "proven")))
'); then
  echo "❌ Could not read the proven set from services.yaml"
  exit 1
fi
if [ -z "$PROVEN" ]; then
  echo "❌ services.yaml names no proven stack; the gate would check nothing"
  exit 1
fi

FAILED=0
PASSED=0
while IFS= read -r stack; do
  probe="stacks/$stack/lifecycle-probe.sh"
  if [ ! -f "$probe" ]; then
    echo "❌ $stack: no $probe"
    FAILED=$((FAILED + 1))
    continue
  fi
  echo "── $stack: $PROBE_ACTION"
  attempt=1
  while :; do
    ssh -o BatchMode=yes nexus bash -s -- "$PROBE_ACTION" "$PROBE_TOKEN" < "$probe"
    status=$?
    if [ "$status" -ne 255 ] || [ "$attempt" -ge 2 ]; then
      break
    fi
    echo "   ssh dropped (exit 255); retrying once"
    attempt=$((attempt + 1))
    sleep 15
  done
  if [ "$status" -eq 0 ]; then
    PASSED=$((PASSED + 1))
  else
    echo "❌ $stack: $PROBE_ACTION failed (exit $status)"
    FAILED=$((FAILED + 1))
  fi
done <<< "$PROVEN"

echo ""
if [ "$FAILED" -ne 0 ]; then
  echo "❌ Lifecycle probe ($PROBE_ACTION): $PASSED passed, $FAILED failed"
  exit 1
fi
echo "✅ Lifecycle probe ($PROBE_ACTION): all $PASSED proven stacks passed"
