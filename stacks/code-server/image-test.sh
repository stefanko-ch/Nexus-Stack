#!/bin/bash
# =============================================================================
# Image test for the code-server stack
# =============================================================================
# Run inside the built image by .github/workflows/stack-image-builds.yaml,
# with this folder mounted read-only at /stack. Locally:
#   docker build -t code-server-test stacks/code-server
#   docker run --rm --entrypoint "" -v "$PWD/stacks/code-server:/stack:ro" \
#     code-server-test bash /stack/image-test.sh
#
# Checks what a rebuild can silently change: that the venv holds exactly the
# versions requirements.txt pins, that every dbt adapter loads, and that the
# tools the tutorials call are on PATH.
# =============================================================================

set -euo pipefail

VENV=/opt/nexus-venv
PY="$VENV/bin/python"

echo "== every installed package is the version requirements.txt pins"
"$PY" - /stack/requirements.txt <<'PYEOF'
import importlib.metadata as md
import re
import sys

def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()

pins = {}
for line in open(sys.argv[1]):
    line = line.split(";")[0].strip()
    if line and not line.startswith("#") and "==" in line:
        name, version = line.split("==")
        pins[norm(name)] = version

installed = {norm(d.metadata["Name"]): d.version for d in md.distributions()}
wrong = {n: (v, pins.get(n)) for n, v in installed.items() if pins.get(n) != v}
if wrong:
    print("installed but not what the lock file pins (installed, pinned):")
    for name, pair in sorted(wrong.items()):
        print(f"  {name}: {pair}")
    sys.exit(1)
print(f"{len(installed)} packages, all as pinned")
PYEOF

echo "== dbt lists every adapter the image promises"
DBT_OUT=$("$VENV/bin/dbt" --version 2>&1) || { echo "$DBT_OUT"; echo "dbt --version failed"; exit 1; }
for adapter in postgres duckdb clickhouse spark trino databricks; do
  if ! grep -q -- "- $adapter:" <<<"$DBT_OUT"; then
    echo "$DBT_OUT"
    echo "dbt does not list the $adapter adapter"
    exit 1
  fi
done
echo "all six adapters listed"

echo "== notebook and database libraries import"
"$PY" -c "import jupyterlab, sql, polars, plotly, duckdb, psycopg, databricks.sql"

echo "== command-line tools"
duckdb --version
psql --version
uv --version
git --version

echo "image test passed"
