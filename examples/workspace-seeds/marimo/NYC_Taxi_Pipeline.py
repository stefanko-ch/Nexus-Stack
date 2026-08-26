"""NYC Yellow-Taxi 2025 pipeline — Spark Connect + Marimo.

Mirror of the Kestra `r2-taxi-pipeline.yaml` flow, adapted for Marimo:

    1. Bootstrap: download monthly Yellow-Taxi parquets from NYC TLC's
       public CloudFront and upload each to Hetzner Object Storage.
       DuckDB does the transfer via `s3://...` (its httpfs extension's
       URL scheme — same physical bucket as the s3a:// reads below,
       just a different client-library URI prefix). No compute-cluster
       round-trip needed.
    2. Read all months back as a Spark DataFrame via the Connect server
       using `s3a://...` (Spark's Hadoop-FileSystem URI scheme; uses
       hadoop-aws under the hood, which is configured server-side in
       spark-connect).
    3. Aggregate stats with Spark SQL and render as a paginated table.

Both `s3://` (DuckDB) and `s3a://` (Spark) point at the same physical
object: `<HETZNER_S3_BUCKET>/nexus-tutorials/NYC/yellow_tripdata_2025-MM.parquet`.
The two URI schemes are just two clients' conventions for talking to
S3-compatible storage; the bytes on disk are identical.

Default: 2 months (Jan + Feb 2025). Edit the `months` list to add more.
The Kestra flow has the same default for the same reason — every student
stack runs this on every "Execute", so a small default keeps CloudFront
egress and run time low when a cohort hits the button at once.

Pre-reqs:
    - Marimo + Spark stacks both enabled
    - Infisical has these secrets (synced into Marimo's env on spin-up):
        HETZNER_S3_BUCKET, HETZNER_S3_ENDPOINT,
        HETZNER_S3_ACCESS_KEY, HETZNER_S3_SECRET_KEY
      Without them, the bootstrap cell raises early with a clear hint.

Why DuckDB for the transfer (not Spark): pyspark[connect] doesn't read
HTTP URLs natively, and a "download to /tmp then write via Spark" path
would shuttle 60 MiB per month through the Marimo container. DuckDB's
httpfs streams directly from CloudFront to S3 in-process — same pattern
the Kestra equivalent uses (DuckDB+httpfs for the stats query).
"""

import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # NYC Yellow-Taxi 2025 Pipeline

        End-to-end demo: bootstrap public NYC TLC parquet files into
        Hetzner Object Storage, then analyse with Spark Connect.

        Mirrors the Kestra flow `nexus-tutorials.r2-taxi-pipeline` —
        same data source, similar shape, different runtime (Marimo
        + DuckDB + Spark Connect instead of Kestra + DuckDB).
        """
    )
    return


@app.cell
def _():
    from _nexus_spark import get_spark

    spark = get_spark()
    return (spark,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 1. Verify Hetzner S3 credentials

        Pulled from Infisical via the `.infisical.env` env_file (see
        Marimo secret-sync block). If any are
        missing, fix them in Infisical and re-run a spin-up to
        repopulate the container env.
        """
    )
    return


@app.cell
def _(mo):
    import os

    _required = [
        "HETZNER_S3_BUCKET",
        "HETZNER_S3_ENDPOINT",
        "HETZNER_S3_ACCESS_KEY",
        "HETZNER_S3_SECRET_KEY",
    ]
    _missing = [k for k in _required if not os.environ.get(k)]

    if _missing:
        s3_env_ok = False
        s3_status_md = mo.md(
            f"""
            > ⚠️ **Missing env vars:** `{", ".join(_missing)}`
            >
            > Add them to Infisical (any folder), re-run a spin-up, and
            > the Marimo container will pick them up via the
            > `.infisical.env` file. The downstream cells will skip
            > themselves until this is satisfied.
            """
        )
    else:
        s3_env_ok = True
        s3_status_md = mo.md(
            f"""
            ✓ All four `HETZNER_S3_*` env vars are set.

            - **Bucket:** `{os.environ["HETZNER_S3_BUCKET"]}`
            - **Endpoint:** `{os.environ["HETZNER_S3_ENDPOINT"]}`
            """
        )
    s3_status_md
    return os, s3_env_ok


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2. Months to bootstrap

        Default: Jan + Feb 2025 (~120 MiB total). Extend the list below
        to bootstrap more months — `["01", ..., "12"]` for the full
        year (~720 MiB).

        Why a small default: this notebook ships as a seed in every
        student workspace, so a "Run all" hits CloudFront simultaneously
        across the cohort. A 2-month default keeps egress + run time
        modest. Same rationale as the Kestra equivalent.
        """
    )
    return


@app.cell
def _():
    months = ["01", "02"]
    return (months,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3. Bootstrap — DuckDB streams CloudFront → Hetzner S3

        DuckDB's `httpfs` extension reads HTTPS and writes S3 in the
        same query, so each month moves CloudFront → S3 in-process
        (no /tmp staging, no compute-cluster round-trip).

        Re-running this cell is **idempotent in spirit**: DuckDB's `COPY
        ... TO` overwrites the destination if it already exists. If
        you've already bootstrapped these months, re-running just
        overwrites with byte-identical content (~10s per month due to
        re-download).
        """
    )
    return


@app.cell
def _(months, os, s3_env_ok):
    upload_results = []
    if s3_env_ok:
        import duckdb

        # Lightweight DuckDB connection — in-memory, no persistence
        # needed; just a vehicle for the httpfs extension.
        _con = duckdb.connect(":memory:")
        _con.execute("INSTALL httpfs; LOAD httpfs;")

        # DuckDB's httpfs config style is global per-connection.
        # Endpoint must NOT include the scheme prefix (DuckDB adds
        # http(s):// itself based on s3_use_ssl). Strip it defensively
        # so users can paste a full URL into Infisical without
        # breaking things.
        # DuckDB's SET statements take no parameter placeholders — you
        # cannot write SET s3_access_key_id = ? — so these values have
        # to be inlined into the SQL text. That makes quoting our job:
        # an apostrophe inside a value would close the string literal
        # early, and the statement then fails with a syntax error whose
        # message can carry a fragment of the value into the notebook
        # output. Doubling the apostrophe is the SQL-standard escape.
        def _lit(value: object) -> str:
            """Render a value as a safely quoted SQL string literal."""
            return "'" + str(value).replace("'", "''") + "'"

        _endpoint = os.environ["HETZNER_S3_ENDPOINT"]
        _endpoint_host = _endpoint.replace("https://", "").replace("http://", "")
        _con.execute(f"SET s3_endpoint = {_lit(_endpoint_host)};")
        _con.execute(f"SET s3_access_key_id = {_lit(os.environ['HETZNER_S3_ACCESS_KEY'])};")
        _con.execute(f"SET s3_secret_access_key = {_lit(os.environ['HETZNER_S3_SECRET_KEY'])};")
        _con.execute("SET s3_url_style = 'path';")
        _con.execute("SET s3_use_ssl = true;")

        _bucket = os.environ["HETZNER_S3_BUCKET"]
        for _month in months:
            _src = (
                f"https://d37ci6vzurychx.cloudfront.net/trip-data/"
                f"yellow_tripdata_2025-{_month}.parquet"
            )
            # Match the Kestra flow's path: nexus-tutorials/NYC/...
            # so both seeds end up at the same logical location even
            # though they target different S3 backends (R2 vs Hetzner).
            _dst = (
                f"s3://{_bucket}/nexus-tutorials/NYC/"
                f"yellow_tripdata_2025-{_month}.parquet"
            )
            _con.execute(
                f"COPY (SELECT * FROM read_parquet({_lit(_src)})) "
                f"TO {_lit(_dst)} (FORMAT PARQUET);"
            )
            upload_results.append({"month": _month, "src": _src, "dst": _dst})
        _con.close()
    upload_results
    return (upload_results,)


@app.cell
def _(mo, s3_env_ok, upload_results):
    if s3_env_ok and upload_results:
        bootstrap_summary_md = mo.md(
            f"✓ Uploaded **{len(upload_results)}** months to "
            f"`{upload_results[0]['dst'].rsplit('/', 1)[0]}/`"
        )
    else:
        bootstrap_summary_md = mo.md(
            "⏭️  Bootstrap skipped — see Section 1 for missing env vars."
        )
    bootstrap_summary_md
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4. Read back via Spark + register as SQL view

        Spark's S3A connector (configured server-side in `spark-connect`)
        reads the Parquet files directly. The wildcard `2025-*.parquet`
        catches every month present in S3 — extending `months` above
        widens the analysis automatically without touching this cell.
        """
    )
    return


@app.cell
def _(os, s3_env_ok, spark):
    if s3_env_ok:
        _bucket = os.environ["HETZNER_S3_BUCKET"]
        trips = spark.read.parquet(
            f"s3a://{_bucket}/nexus-tutorials/NYC/yellow_tripdata_2025-*.parquet"
        )
        trips.createOrReplaceTempView("trips")
    else:
        trips = None
    trips
    return (trips,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 5. Quick stats — Spark SQL

        Same shape as the Kestra flow's DuckDB query, but runs
        distributed on the spark-worker. Result streams back via
        Arrow and renders as a Marimo paginated table.
        """
    )
    return


@app.cell
def _(s3_env_ok, spark, trips):
    if s3_env_ok and trips is not None:
        stats = spark.sql(
            """
            SELECT
              COUNT(*)                       AS total_trips,
              ROUND(AVG(trip_distance), 2)   AS avg_distance_mi,
              ROUND(AVG(total_amount), 2)    AS avg_fare_usd,
              ROUND(AVG(passenger_count), 2) AS avg_passengers,
              MIN(tpep_pickup_datetime)      AS earliest_pickup,
              MAX(tpep_pickup_datetime)      AS latest_pickup
            FROM trips
            """
        )
    else:
        stats = None
    stats
    return (stats,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 6. Per-payment-type breakdown

        Bonus aggregation that wasn't in the Kestra flow — shows the
        difference Spark makes once the data's in S3: the same query
        runs distributed on the worker, results stream back as a
        small Arrow batch.
        """
    )
    return


@app.cell
def _(s3_env_ok, spark, trips):
    if s3_env_ok and trips is not None:
        from pyspark.sql.connect import functions as F

        by_payment = (
            trips.groupBy("payment_type")
            .agg(
                F.count("*").alias("trips"),
                F.round(F.avg("total_amount"), 2).alias("avg_fare_usd"),
                F.round(F.avg("tip_amount"), 2).alias("avg_tip_usd"),
            )
            .orderBy("trips", ascending=False)
        )
    else:
        by_payment = None
    by_payment
    return (by_payment,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 7. Where to go next

        - **Extend `months` to all 12** to see Spark's distributed-read
          shine on ~30 M rows. The cluster's single worker handles it
          comfortably; bumping `spark-worker` cores would speed it up
          further.
        - **Compare with the Kestra equivalent** at
          `nexus-tutorials.r2-taxi-pipeline` — same data, same path
          shape (`nexus-tutorials/NYC/...`), different runtime. Useful
          for understanding when to reach for which tool.
        - **Try Spark SQL via Ibis cells** (see
          `Getting_Started_PySpark.py`'s Section 4) for SQL with
          Marimo's reactive DataFrame UI.
        """
    )
    return


if __name__ == "__main__":
    app.run()
