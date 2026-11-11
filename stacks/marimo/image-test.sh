#!/bin/bash
# =============================================================================
# Image test for the marimo stack
# =============================================================================
# Run inside the built image by .github/workflows/stack-image-builds.yaml,
# with this folder mounted read-only at /stack. Locally:
#   docker build -t marimo-test stacks/marimo
#   docker run --rm --entrypoint "" -v "$PWD/stacks/marimo:/stack:ro" \
#     marimo-test bash /stack/image-test.sh
#
# Checks that every package the Dockerfile pins is installed at that version
# and that the libraries the seeded notebooks import do load.
# =============================================================================

set -euo pipefail

echo "== every package the Dockerfile pins is installed at that version"
python - /stack/Dockerfile <<'PYEOF'
import importlib.metadata as md
import re
import sys

text = open(sys.argv[1]).read()
pins = re.findall(r'"([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==([^"]+)"', text)
if not pins:
    sys.exit("found no pinned packages in the Dockerfile; this test reads nothing")
wrong = []
for name, version in pins:
    try:
        installed = md.version(name)
    except md.PackageNotFoundError:
        installed = "missing"
    if installed != version:
        wrong.append(f"  {name}: pinned {version}, installed {installed}")
if wrong:
    print("\n".join(wrong))
    sys.exit(1)
print(f"{len(pins)} pinned packages, all installed as pinned")
PYEOF

echo "== libraries the seeded notebooks use import"
python -c "import marimo, pyspark, ibis, pyarrow, grpc, pyiceberg, s3fs, mlflow"

echo "== command-line tools"
marimo --version
git --version
gosu --version

echo "image test passed"
