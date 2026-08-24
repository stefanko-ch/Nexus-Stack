"""Getting Started with DuckDB in Marimo.

DuckDB is **pre-installed** in the Nexus-Stack Marimo image — no
``pip install`` needed. The base image ``ghcr.io/marimo-team/marimo:0.23.4-sql``
ships ``marimo[sql]`` which bundles:

    duckdb + sqlglot + ibis-framework + polars + pyarrow

So you can ``import duckdb`` directly OR use Marimo's native SQL cells
(``mo.sql(...)``) which are backed by DuckDB by default.

This notebook walks through six DuckDB patterns you'll actually use:

    1. Sanity check — version + simple SELECT
    2. Synthetic data via the ``range()`` table function — no I/O,
       runs anywhere
    3. Read remote parquet directly from HTTP via the ``httpfs`` extension
       (auto-loaded; no manual ``INSTALL httpfs`` or ``LOAD httpfs`` needed)
    4. Aggregate + window function on the public NYC Taxi dataset
    5. Convert query results to Polars / Pandas / PyArrow
    6. Marimo's native SQL cell with ``mo.sql`` (reactive DAG-aware,
       results auto-render as paginated tables)

No schedule, no API key, no Spark. Default queries hit NYC TLC's public
CloudFront — same source the Kestra ``r2-taxi-pipeline`` and Prefect
``nyc-green-taxi-pipeline`` seeds use, but DuckDB streams the parquet
columns it needs over HTTP without ever materializing a local file.

This file was seeded into your Gitea workspace repo from
``nexus-stack/examples/workspace-seeds/marimo/Getting_Started_DuckDB.py``.
Edit it in Gitea or directly in Marimo — your changes persist across
spin-ups (seeding only adds new files, never overwrites).
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
        # Getting Started with DuckDB on Marimo

        DuckDB ships with this Marimo image — no install step. The
        ``marimo[sql]`` extras bundle DuckDB + Polars + PyArrow, so the
        common analytics stack works out of the box.

        Two ways to use it from a notebook:

        - **Python API**: ``import duckdb; con = duckdb.connect()`` — full
          control over the connection (in-memory by default, persistent
          if you pass a file path), all client libraries available
          (``.df()``, ``.pl()``, ``.arrow()`` for Pandas / Polars /
          PyArrow conversion).
        - **Marimo native SQL cell**: ``mo.sql("SELECT ...")`` — Marimo
          tracks the cell as a reactive node, results render as
          paginated tables, and the SQL itself is a syntax-highlighted
          first-class cell type.

        Run cells in order or hit **Run all** — Marimo figures out the
        dependency graph from the function signatures.
        """
    )
    return


@app.cell
def _():
    # Step 1: open an in-memory DuckDB connection. ``duckdb.connect()``
    # without a path = ephemeral DB that lives as long as this notebook
    # process. For persistent storage, pass a file path:
    #     con = duckdb.connect("/app/notebooks/my_database.db")
    # The persistent file lives in the marimo named volume so it
    # survives container restarts.
    import duckdb

    con = duckdb.connect()
    return con, duckdb


@app.cell
def _(con, mo):
    # Step 1 sanity check: confirm the install + show the version. The
    # Polars-DataFrame `.pl()` accessor is one of three result-shape
    # methods DuckDB ships out of the box (`.df()` → Pandas,
    # `.arrow()` → PyArrow Table, `.pl()` → Polars). Pick whichever
    # downstream library you prefer.
    version_df = con.sql("SELECT version() AS duckdb_version").pl()
    mo.md(
        f"""
        ### 1. Sanity check

        DuckDB version: **{version_df["duckdb_version"][0]}**

        The ``con`` object is an in-memory DuckDB connection. Every
        cell below uses it.
        """,
    )
    return


@app.cell
def _(con, mo):
    # Step 2: DuckDB's `range()` table function produces a synthetic
    # table with no I/O. Useful for quick demos, smoke-tests, or
    # warming up a query plan. (`range` is DuckDB's name; Postgres
    # calls the equivalent function `generate_series`.)
    synthetic = con.sql(
        """
        SELECT
            i AS row_id,
            i * i AS squared,
            (i * 1.0 / 10) AS scaled,
            CASE WHEN i % 2 = 0 THEN 'even' ELSE 'odd' END AS parity
        FROM range(1, 11) t(i)
        """,
    ).pl()
    mo.md(
        """
        ### 2. Synthetic data — no network, no setup

        ``range(1, 11)`` is DuckDB's table function for generating
        rows. Useful for warming up query plans or building demos
        that don't depend on a remote dataset:
        """,
    )
    synthetic
    return


@app.cell
def _(con, mo):
    # Step 3: read a remote parquet directly from HTTP. The httpfs
    # extension is shipped with DuckDB AND auto-loaded on first use of
    # an http(s)/s3 URL — no `INSTALL httpfs` / `LOAD httpfs` needed
    # in modern DuckDB versions. Streams only the columns + row groups
    # the query touches.
    #
    # NYC TLC's public CloudFront is the same source the Kestra
    # `r2-taxi-pipeline` flow uses; we read directly from it without
    # uploading to R2 first because DuckDB's httpfs handles the
    # streaming. Limit to one month + 1000 rows so this runs in <2s.
    sample = con.sql(
        """
        SELECT
            tpep_pickup_datetime,
            tpep_dropoff_datetime,
            passenger_count,
            trip_distance,
            total_amount
        FROM read_parquet(
            'https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet'
        )
        LIMIT 1000
        """,
    ).pl()
    mo.md(
        f"""
        ### 3. Read remote parquet over HTTP (no download step)

        Pulled **{len(sample):,} rows** from NYC TLC's public CloudFront
        directly into DuckDB. The ``httpfs`` extension is auto-loaded
        on first use of an ``http(s)://`` URL — no manual
        ``INSTALL httpfs`` / ``LOAD httpfs`` required.

        Same trick works for ``s3://``, ``gs://``, and ``azure://``
        URLs (with the appropriate credentials in env vars).
        """,
    )
    sample.head(20)
    return (sample,)


@app.cell
def _(con, mo):
    # Step 4: aggregate + window over the same remote parquet. DuckDB's
    # query optimizer pushes the column projection down through the
    # parquet reader, so even though the source file is ~50 MiB on
    # CloudFront, only the columns we touch get streamed. The
    # `payment_type` decode is from NYC TLC's data dictionary
    # (https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).
    payment_summary = con.sql(
        """
        WITH typed AS (
            SELECT
                CASE payment_type
                    WHEN 1 THEN 'Credit card'
                    WHEN 2 THEN 'Cash'
                    WHEN 3 THEN 'No charge'
                    WHEN 4 THEN 'Dispute'
                    ELSE 'Unknown'
                END AS payment_method,
                total_amount,
                trip_distance
            FROM read_parquet(
                'https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet'
            )
            WHERE total_amount > 0 AND trip_distance > 0
        )
        SELECT
            payment_method,
            COUNT(*) AS n_trips,
            ROUND(AVG(total_amount), 2) AS avg_total,
            ROUND(SUM(total_amount), 2) AS sum_total,
            ROUND(SUM(total_amount) * 100.0 /
                  SUM(SUM(total_amount)) OVER (), 1) AS pct_of_total
        FROM typed
        GROUP BY payment_method
        ORDER BY sum_total DESC
        """,
    ).pl()
    mo.md(
        """
        ### 4. Aggregate + window function on remote parquet

        Group by payment method, compute totals + each method's
        percentage of the overall revenue using a window-aggregate
        (``SUM() OVER ()`` without a partition = grand total).
        """,
    )
    payment_summary
    return


@app.cell
def _(mo, sample):
    # Step 5: result-shape conversion. DuckDB returns a Relation;
    # the `.pl()` we've been using produces Polars. The other two
    # accessors are `.df()` (Pandas) and `.arrow()` (PyArrow Table).
    # Useful when you need to hand the result to a library that
    # expects a specific dataframe type.
    #
    # `sample` is already a Polars DataFrame (from Step 3's `.pl()`);
    # showing the round-trip patterns here.
    pandas_df = sample.to_pandas()
    arrow_table = sample.to_arrow()
    mo.md(
        f"""
        ### 5. Convert results to Polars / Pandas / PyArrow

        DuckDB returns a Relation; pick your output:

        - ``.pl()`` → Polars DataFrame ({type(sample).__name__}, {len(sample):,} rows)
        - ``.df()`` → Pandas DataFrame ({type(pandas_df).__name__}, {len(pandas_df):,} rows)
        - ``.arrow()`` → PyArrow Table ({type(arrow_table).__name__}, {arrow_table.num_rows:,} rows)

        Polars is the recommended default in Marimo — fast, lazy when
        you want it, and renders as a sortable/filterable table out of
        the box.
        """,
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ### 6. Marimo's native SQL cell

        The cell below uses ``mo.sql(...)`` — Marimo's first-class SQL
        cell type. The SQL string gets syntax-highlighted in the editor,
        the result becomes a Marimo reactive value (downstream cells
        depending on it re-run when it changes), and the output renders
        as a paginated, sortable table without any ``.head()`` /
        ``.show()`` boilerplate.

        Backed by DuckDB by default — no extra wiring needed.
        """,
    )
    return


@app.cell
def _(mo):
    # ``mo.sql`` is the reactive, DAG-aware SQL cell. It runs against
    # an internal DuckDB connection (different from our `con` above —
    # `mo.sql` keeps its own scope-internal DB). Returned value is a
    # Polars DataFrame by default. The cell auto-renders below.
    pickup_hours_distribution = mo.sql(
        """
        SELECT
            EXTRACT(HOUR FROM tpep_pickup_datetime) AS pickup_hour,
            COUNT(*) AS n_trips,
            ROUND(AVG(trip_distance), 2) AS avg_distance_miles,
            ROUND(AVG(EXTRACT(EPOCH FROM tpep_dropoff_datetime - tpep_pickup_datetime) / 60), 1)
                AS avg_duration_minutes
        FROM read_parquet(
            'https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet'
        )
        WHERE trip_distance > 0
          AND trip_distance < 50
          AND tpep_dropoff_datetime > tpep_pickup_datetime
        GROUP BY pickup_hour
        ORDER BY pickup_hour
        """,
    )
    return (pickup_hours_distribution,)


@app.cell
def _(pickup_hours_distribution, mo):
    mo.md(
        """
        Hourly pickup distribution above — the busiest hours and the
        average trip duration in each. Note how ``mo.sql`` returns a
        Polars DataFrame named ``pickup_hours_distribution`` you can
        reference in downstream Python cells:
        """,
    )
    pickup_hours_distribution
    return


@app.cell
def _(pickup_hours_distribution, mo):
    # Step 6 continued: downstream Python cell consuming the mo.sql
    # result. Marimo's reactive DAG re-runs this cell whenever the
    # SQL above re-runs.
    busiest = pickup_hours_distribution.sort("n_trips", descending=True).head(3)
    quietest = pickup_hours_distribution.sort("n_trips").head(3)
    mo.md(
        f"""
        **Busiest 3 hours:** {", ".join(f"{h:02d}:00" for h in busiest["pickup_hour"])}
        ({", ".join(f"{n:,}" for n in busiest["n_trips"])} trips)

        **Quietest 3 hours:** {", ".join(f"{h:02d}:00" for h in quietest["pickup_hour"])}
        ({", ".join(f"{n:,}" for n in quietest["n_trips"])} trips)
        """,
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Where to go from here

        - **Persist a DB to disk**: ``duckdb.connect("/app/notebooks/my.db")``
          — the file lives in Marimo's named volume across container
          restarts. Useful for keeping intermediate analytical tables
          between notebook sessions.
        - **Read from Hetzner Object Storage**: the Infisical secret-sync
          writes ``HETZNER_S3_*`` env vars into ``/app/.infisical.env``
          on every spin-up. DuckDB's ``httpfs`` doesn't auto-read
          those — pass them explicitly via DuckDB SET statements
          before issuing the query (the same DuckDB-side pattern
          ``NYC_Taxi_Pipeline.py`` uses for its OWN bootstrap step
          to upload parquets to S3 — that notebook then switches to
          ``s3a://...`` URLs for the Spark read, which uses
          hadoop-aws / Spark-stack settings, NOT DuckDB SETs):

          ```python
          import os

          # DuckDB's SET takes no parameter placeholders — you cannot
          # write SET s3_access_key_id = ? — so the values have to be
          # inlined into the SQL text, which makes quoting your job.
          # Doubling any apostrophe is the SQL-standard escape; without
          # it a value containing one closes the literal early and the
          # statement fails to parse.
          def _lit(value):
              return "'" + str(value).replace("'", "''") + "'"

          con.sql(f\"\"\"
              SET s3_endpoint = {_lit(os.environ["HETZNER_S3_ENDPOINT"].removeprefix("https://"))};
              SET s3_access_key_id = {_lit(os.environ["HETZNER_S3_ACCESS_KEY"])};
              SET s3_secret_access_key = {_lit(os.environ["HETZNER_S3_SECRET_KEY"])};
              SET s3_url_style = 'path';
          \"\"\")
          # then read with: SELECT * FROM read_parquet('s3://<bucket>/path/file.parquet')
          ```
          (DuckDB DOES auto-pick up ``AWS_ACCESS_KEY_ID`` /
          ``AWS_SECRET_ACCESS_KEY`` from the environment when those
          specific names are set, but Marimo's secret-sync uses the
          ``HETZNER_S3_*`` naming, so the explicit ``SET`` is the
          path that works without renaming env vars.)
        - **JOIN across formats**: DuckDB happily JOINs a parquet on R2
          with a CSV on disk with a Postgres table via the ``postgres``
          extension. Mix-and-match without ETL.
        - **Compare DuckDB vs Spark**: load the same parquet file through
          both engines (this notebook + ``Getting_Started_PySpark.py``)
          and benchmark on your stack — DuckDB tends to win for
          single-node queries up to a few hundred GB; Spark wins when
          you need horizontal scale.
        """,
    )
    return


if __name__ == "__main__":
    app.run()
