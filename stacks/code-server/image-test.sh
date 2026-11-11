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

echo "== the venv holds exactly the packages requirements.txt pins"
"$PY" - /stack/requirements.txt <<'PYEOF'
import importlib.metadata as md
import re
import sys

from packaging.markers import Marker


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


pins = {}
for line in open(sys.argv[1]):
    line = line.strip()
    if not line or line.startswith("#") or "==" not in line:
        continue
    requirement, _, marker = line.partition(";")
    # The lock file is universal: a line for another platform or Python
    # version is rightly absent from this image.
    if marker.strip() and not Marker(marker.strip()).evaluate():
        continue
    name, version = requirement.strip().split("==")
    pins[norm(name)] = version

installed = {norm(d.metadata["Name"]): d.version for d in md.distributions()}
wrong = {n: (installed.get(n, "missing"), pins.get(n, "not pinned")) for n in pins | installed}
wrong = {n: pair for n, pair in wrong.items() if pair[0] != pair[1]}
if wrong:
    print("the venv and the lock file disagree (installed, pinned):")
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
