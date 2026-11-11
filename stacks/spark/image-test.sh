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
# Python is the exact build the Dockerfile pins at every path Spark can
# resolve, and that a PySpark job with a Python UDF runs.
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

echo "== Python is the exact build the Dockerfile pins"
PINNED=$(sed -n 's/^ARG PYTHON_VERSION=//p' /stack/Dockerfile)
if [ -z "$PINNED" ]; then
  echo "found no ARG PYTHON_VERSION in the Dockerfile; this test reads nothing"
  exit 1
fi
case "$PINNED" in
  3.13.*) ;;
  *) echo "the Dockerfile pins Python $PINNED; PySpark clients must match 3.13"; exit 1 ;;
esac
for interpreter in /usr/bin/python3.13 /usr/bin/python3 "$PYSPARK_PYTHON" "$PYSPARK_DRIVER_PYTHON"; do
  ACTUAL=$("$interpreter" --version)
  if [ "$ACTUAL" != "Python $PINNED" ]; then
    echo "$interpreter is '$ACTUAL', the Dockerfile pins Python $PINNED"
    exit 1
  fi
done
echo "Python $PINNED at every path Spark can resolve"

echo "== the interpreter has what a PySpark worker needs"
python3 -c "import ssl, zlib, bz2, lzma, sqlite3, ctypes, socket, select, struct"

echo "== Spark starts"
/opt/spark/bin/spark-submit --version

echo "== a Python UDF runs on a worker started with this interpreter"
JOB=$(mktemp --suffix=.py)
cat > "$JOB" <<'PYEOF'
import sys

from pyspark.sql import SparkSession
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

spark = SparkSession.builder.master("local[1]").appName("image-test").getOrCreate()
worker_version = udf(lambda _: ".".join(map(str, sys.version_info[:3])), StringType())
rows = spark.range(3).select(worker_version("id").alias("v")).distinct().collect()
spark.stop()
driver = ".".join(map(str, sys.version_info[:3]))
workers = sorted(r.v for r in rows)
print(f"driver {driver}, workers {workers}")
if workers != [driver]:
    sys.exit("the worker did not run the driver's Python")
PYEOF
if ! OUT=$(/opt/spark/bin/spark-submit --master "local[1]" "$JOB" 2>&1); then
  echo "$OUT" | tail -40
  echo "the PySpark job failed"
  exit 1
fi
RESULT=$(grep "^driver " <<<"$OUT" || true)
rm -f "$JOB"
if [ "$RESULT" != "driver $PINNED, workers ['$PINNED']" ]; then
  echo "$OUT" | tail -40
  echo "expected the driver and the worker on Python $PINNED, got: ${RESULT:-(no result line)}"
  exit 1
fi
echo "$RESULT"

echo "image test passed"
