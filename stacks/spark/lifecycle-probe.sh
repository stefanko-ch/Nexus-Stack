#!/bin/bash
# =============================================================================
# Lifecycle probe for Spark (release gate, #712)
# =============================================================================
# Run ON THE SERVER as root, by .github/workflows/release-gate.yml through the
# spin-up's `lifecycle_probe` input:
#   lifecycle-probe.sh create <token>   before the teardown
#   lifecycle-probe.sh verify <token>   after the following spin-up
#
# Spark keeps no data of its own; what a student keeps is tables on R2, the
# data lake. Both halves run from the marimo container over Spark Connect,
# the way a notebook does: `create` writes a table to
# s3a://$R2_BUCKET/nexus_release_gate/<token>, `verify` reads it back after
# the rebuild and runs a Python UDF and a pandas_udf on the workers.
# Needs marimo enabled as well, as the client.
# =============================================================================

set -euo pipefail

ACTION=${1:?usage: lifecycle-probe.sh create|verify <token>}
TOKEN=${2:?usage: lifecycle-probe.sh create|verify <token>}
case "$ACTION" in
  create|verify) ;;
  *) echo "unknown action: $ACTION"; exit 2 ;;
esac

for c in spark spark-worker spark-connect marimo; do
  if ! docker ps --format '{{.Names}}' | grep -qx "$c"; then
    echo "spark: container $c is not running; the release gate needs spark and marimo enabled"
    exit 1
  fi
done

docker exec -u appuser marimo python3 - "$ACTION" "$TOKEN" <<'PY'
import os
import sys

import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.functions import lit, pandas_udf, udf

action, token = sys.argv[1], sys.argv[2]
bucket = os.environ.get("R2_BUCKET", "")
if not bucket:
    sys.exit("spark: R2_BUCKET is not set in the marimo container")
path = f"s3a://{bucket}/nexus_release_gate/{token}"
spark = SparkSession.builder.remote("sc://spark-connect:15002").getOrCreate()

if action == "create":
    spark.range(100).withColumn("token", lit(token)).write.mode("overwrite").parquet(path)
    print(f"spark: wrote 100 rows to {path}")
else:
    try:
        df = spark.read.parquet(path)
        rows = df.count()
    except Exception as exc:  # the remote error names the cause
        sys.exit(f"spark: table at {path} is not readable after the teardown: {type(exc).__name__}")
    tokens = {r.token for r in df.select("token").distinct().collect()}
    if rows != 100 or tokens != {token}:
        sys.exit(f"spark: table at {path} holds {rows} rows, tokens {sorted(tokens)}")
    worker = udf(lambda _: sys.version.split()[0])
    versions = {r.v for r in df.limit(3).select(worker("id").alias("v")).collect()}

    @pandas_udf("long")
    def doubled(s: pd.Series) -> pd.Series:
        return s * 2

    total = df.select(doubled("id").alias("d")).groupBy().sum("d").collect()[0][0]
    if total != 9900:
        sys.exit(f"spark: pandas_udf returned {total}, expected 9900")
    print(f"spark: table survived ({rows} rows); worker Python {sorted(versions)}; pandas_udf ok")
PY
