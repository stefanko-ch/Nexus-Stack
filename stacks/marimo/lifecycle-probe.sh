#!/bin/bash
# =============================================================================
# Lifecycle probe for marimo (release gate, #712)
# =============================================================================
# Run ON THE SERVER as root, by .github/workflows/release-gate.yml through the
# spin-up's `lifecycle_probe` input:
#   lifecycle-probe.sh create <token>   before the teardown
#   lifecycle-probe.sh verify <token>   after the following spin-up
#
# A student's marimo work is notebooks under /app/notebooks. `create` saves
# one there as the user marimo runs as; `verify` checks it is back, that
# marimo still recognises it as a notebook, and that marimo answers.
# =============================================================================

set -euo pipefail

ACTION=${1:?usage: lifecycle-probe.sh create|verify <token>}
TOKEN=${2:?usage: lifecycle-probe.sh create|verify <token>}
FILE=/app/notebooks/nexus_release_gate.py

case "$ACTION" in
  create)
    docker exec -u appuser marimo python3 - "$FILE" "$TOKEN" <<'PY'
import sys
path, token = sys.argv[1], sys.argv[2]
open(path, "w").write(
    "import marimo\n\napp = marimo.App()\n\n\n@app.cell\ndef _():\n"
    f"    token = {token!r}\n    return (token,)\n\n\nif __name__ == \"__main__\":\n    app.run()\n"
)
PY
    echo "marimo: wrote $FILE"
    ;;
  verify)
    docker exec marimo python3 - "$FILE" "$TOKEN" <<'PY'
import sys, urllib.request
path, token = sys.argv[1], sys.argv[2]
try:
    text = open(path).read()
except OSError as exc:
    sys.exit(f"marimo: {path} is gone after the teardown: {exc}")
if repr(token) not in text:
    sys.exit(f"marimo: {path} holds something else than this run wrote")
head = text[:512]
if "import marimo" not in head or "marimo.App" not in head:
    sys.exit("marimo: the notebook no longer reads as a notebook")
urllib.request.urlopen("http://localhost:8080/").close()
print("marimo: notebook survived, marimo answers")
PY
    ;;
  *)
    echo "unknown action: $ACTION"
    exit 2
    ;;
esac
