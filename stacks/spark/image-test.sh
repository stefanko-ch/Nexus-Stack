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

echo "== every package requirements.txt pins is installed at that version"
python3 - /stack/requirements.txt <<'PYEOF'
import importlib.metadata as md
import sys

pins = []
for line in open(sys.argv[1]):
    line = line.split(";")[0].strip()
    if line and not line.startswith("#") and "==" in line:
        pins.append(line.split("=="))
if not pins:
    sys.exit("found no pinned packages in requirements.txt; this test reads nothing")
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

# The two kinds of UDF that need pandas and pyarrow on the worker: an
# Arrow-optimised one (what Spark Connect uses by default) and a pandas_udf.
import pandas as pd
from pyspark.sql.functions import pandas_udf

arrow_version = udf(lambda _: ".".join(map(str, sys.version_info[:3])), StringType(), useArrow=True)
arrow_rows = spark.range(3).select(arrow_version("id").alias("v")).distinct().collect()


@pandas_udf("long")
def doubled(s: pd.Series) -> pd.Series:
    return s * 2


total = spark.range(10).select(doubled("id").alias("d")).groupBy().sum("d").collect()[0][0]
spark.stop()
if sorted(r.v for r in arrow_rows) != sorted(r.v for r in rows):
    sys.exit("the Arrow UDF ran on a different Python than the plain one")
if total != 90:
    sys.exit(f"the pandas_udf returned {total}, expected 90")
print("arrow udf and pandas_udf ok")
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
if ! grep -q "^arrow udf and pandas_udf ok$" <<<"$OUT"; then
  echo "$OUT" | tail -40
  echo "the Arrow UDF or the pandas_udf did not run"
  exit 1
fi
echo "arrow udf and pandas_udf ok"
RESULT=$(grep "^driver " <<<"$OUT" || true)
rm -f "$JOB"
if [ "$RESULT" != "driver $PINNED, workers ['$PINNED']" ]; then
  echo "$OUT" | tail -40
  echo "expected the driver and the worker on Python $PINNED, got: ${RESULT:-(no result line)}"
  exit 1
fi
echo "$RESULT"

echo "image test passed"
