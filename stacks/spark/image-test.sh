#!/bin/bash
# =============================================================================
# Image test for the spark stack
# =============================================================================
# Run inside the built image by .github/workflows/stack-image-builds.yaml,
# with this folder mounted read-only at /stack. Locally:
#   docker build -t spark-test stacks/spark
#   docker run --rm --entrypoint "" -v "$PWD/stacks/spark:/stack:ro" \
#     spark-test bash /stack/image-test.sh
#
# Checks that every jar the Dockerfile downloads is in /opt/spark/jars, that
# Python is the version PySpark clients must match, and that Spark starts.
# =============================================================================

set -euo pipefail

echo "== every jar the Dockerfile downloads is present"
JARS=$(grep -oE '"[A-Za-z0-9_./-]+\.jar"' /stack/Dockerfile | tr -d '"' | sed 's|.*/||' | sort -u)
if [ -z "$JARS" ]; then
  echo "found no jars in the Dockerfile; this test reads nothing"
  exit 1
fi
MISSING=0
COUNT=0
while IFS= read -r jar; do
  COUNT=$((COUNT + 1))
  if [ ! -s "/opt/spark/jars/$jar" ]; then
    echo "  missing or empty: /opt/spark/jars/$jar"
    MISSING=1
  fi
done <<<"$JARS"
if [ "$MISSING" -ne 0 ]; then
  exit 1
fi
echo "$COUNT jars, all present"

echo "== Python is 3.13, the version PySpark clients must match"
PY_VERSION=$(python3 --version)
echo "$PY_VERSION"
case "$PY_VERSION" in
  "Python 3.13."*) ;;
  *) echo "expected Python 3.13"; exit 1 ;;
esac

echo "== Spark starts"
/opt/spark/bin/spark-submit --version

echo "image test passed"
