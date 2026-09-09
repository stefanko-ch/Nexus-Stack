"""Create, append to and time-travel an Iceberg table on R2.

Deliberately short: marimo reads only the first 512 bytes to decide a file
is a notebook, and prose above `import marimo` pushes the markers out of
that window. The introduction lives in the first cell instead.
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
        # Iceberg on Lakekeeper

        Lakekeeper is a **catalogue**: it does not store your data, it stores
        the answer to "which files make up this table, right now". The Parquet
        files themselves go to Cloudflare R2. That split is the whole point —
        the files survive a teardown because R2 is outside the server, and the
        catalogue survives because its PostgreSQL is backed up and restored on
        every spin-up.

        This notebook uses **PyIceberg**, not Spark, and that is not a
        stylistic choice. Apache Iceberg publishes no `iceberg-spark-runtime`
        build for the Spark 4.2 this project runs, and the 4.1 build fails on
        it with a binary incompatibility. PyIceberg speaks the Iceberg REST
        protocol straight over HTTP, so it needs no JVM at all. The details
        are in `docs/stacks/spark.md`; the Spark route reopens when Iceberg
        next releases.

        What Iceberg gives you that a pile of Parquet files does not:

        - **Snapshots.** Every write creates one, and old ones stay readable.
        - **Atomic appends.** A reader sees the table before or after a write,
          never halfway through it.
        - **Schema on the table, not in your head.** Types and column names
          live in the catalogue.

        Everything below is safe to run more than once.
        """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 1 — Open the catalogue

        `get_catalog()` reads `$LAKEKEEPER_URI` and `$LAKEKEEPER_WAREHOUSE`,
        both set for you by the Marimo stack. It points at the **in-cluster**
        address `http://lakekeeper:8181/catalog`, not the public
        `https://lakekeeper.<domain>` — that one sits behind Cloudflare Access
        and hands an API client an HTML login page, which PyIceberg then fails
        to parse as JSON.
        """
    )
    return


@app.cell
def _():
    from _nexus_iceberg import get_catalog

    cat = get_catalog()
    cat.list_namespaces()
    return (cat,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2 — Create a namespace and a table

        A namespace is a folder for tables; `demo.orders` means the table
        `orders` in the namespace `demo`. PyIceberg takes the schema from an
        Arrow table, so you describe the data once and it becomes the table
        definition.
        """
    )
    return


@app.cell
def _(cat):
    import pyarrow as pa

    cat.create_namespace_if_not_exists("demo")

    orders = pa.table(
        {
            "id": pa.array([1, 2, 3, 4], pa.int64()),
            "country": pa.array(["CH", "DE", "CH", "AT"]),
            "amount": pa.array([10.5, 20.0, 5.25, 7.0], pa.float64()),
        }
    )
    tbl = cat.create_table_if_not_exists("demo.orders", schema=orders.schema)
    tbl
    return orders, pa, tbl


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3 — Write, and notice what a write costs

        `append` uploads Parquet to R2 and then commits a new snapshot in the
        catalogue. Re-running this cell appends **again** — the row count
        grows by four each time. That is the honest behaviour of an append,
        not a bug; step 5 shows how to see the history it leaves behind.

        Writes go through `s3fs`, which the Marimo image installs on purpose.
        Lakekeeper signs each S3 request on your behalf (R2 has no AWS STS
        endpoint), and PyIceberg implements that signing only in its fsspec
        backend.
        """
    )
    return


@app.cell
def _(orders, tbl):
    tbl.append(orders)
    f"{tbl.scan().to_arrow().num_rows} rows after this append"
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4 — Read it back three ways

        The conversions live on the **scan**, not on the table. `Table` itself
        only offers `to_polars()` as a shortcut — there is no
        `Table.to_arrow()`.
        """
    )
    return


@app.cell
def _(cat):
    fresh = cat.load_table("demo.orders")
    fresh.scan().to_polars()
    return (fresh,)


@app.cell
def _(fresh):
    # to_duckdb is the odd one out: the table name is REQUIRED, and it hands
    # back a connection with the data registered under that name rather than
    # a dataframe.
    con = fresh.scan().to_duckdb("orders")
    con.sql(
        "SELECT country, count(*) AS n, round(sum(amount), 2) AS total "
        "FROM orders GROUP BY country ORDER BY total DESC"
    ).pl()
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 5 — Snapshots and time travel

        Every append left a snapshot. They are not a debugging aid — they are
        how Iceberg gives you a stable read while someone else is writing, and
        they let you read the table as it was at any earlier commit.

        If you have run this notebook more than once, you will see more than
        one row below.
        """
    )
    return


@app.cell
def _(fresh):
    import datetime as _dt

    # Sorted, because `snapshots()` does NOT return them in commit order --
    # it hands back the metadata's own list, whose order is not a guarantee.
    # Taking snapshots()[0] as "the first one" looks right and quietly is not.
    snaps = [
        {
            "snapshot_id": s.snapshot_id,
            "committed": _dt.datetime.fromtimestamp(
                s.timestamp_ms / 1000, tz=_dt.timezone.utc
            ).isoformat(timespec="seconds"),
            "operation": s.summary.operation.value if s.summary else None,
        }
        for s in sorted(fresh.snapshots(), key=lambda s: s.timestamp_ms)
    ]
    snaps
    return (snaps,)


@app.cell
def _(fresh, snaps):
    # Read the table as of its oldest snapshot. After a single append that is
    # the current state; once you have run this notebook twice it is visibly
    # smaller -- which is the whole point.
    _oldest = snaps[0]["snapshot_id"]
    _then = fresh.scan(snapshot_id=_oldest).to_arrow().num_rows
    _now = fresh.scan().to_arrow().num_rows
    f"snapshot {_oldest} held {_then} rows; the table now has {_now}"
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 6 — Filter and project before the data moves

        `row_filter` and `selected_fields` are applied while reading, so
        unwanted rows and columns never leave R2. On a real table this is the
        difference between a scan and a download — and R2 charges for egress,
        so it is a habit worth forming on small tables.
        """
    )
    return


@app.cell
def _(fresh):
    fresh.scan(
        row_filter="country = 'CH'",
        selected_fields=("id", "amount"),
    ).to_polars()
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 7 — Where the bytes actually are

        The table's `location` is its subtree in the R2 bucket. Note the
        `lakekeeper/` prefix: the data bucket is shared with Unity Catalog and
        pg-ducklake, so each warehouse owns a subtree rather than the root.
        """
    )
    return


@app.cell
def _(fresh):
    _files = [f.file.file_path for f in fresh.scan().plan_files()]
    {
        "location": fresh.location(),
        "data files": len(_files),
        "first file": _files[0] if _files else None,
    }
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## What survives, and what does not

        Run a teardown and a spin-up, then re-run this notebook from step 1:
        the rows are still there, and nothing had to be re-registered. Two
        separate things make that true, and both are needed.

        | Piece | Where it lives | How it comes back |
        |---|---|---|
        | Parquet + metadata files | Cloudflare R2, under `lakekeeper/` | never left — R2 is outside the server |
        | Warehouse, namespaces, table pointers | Lakekeeper's PostgreSQL | dumped to R2 on teardown, restored on spin-up |

        Delete only one of them and you get the two failure modes worth
        recognising: files no catalogue can name, or a catalogue pointing at
        files that are gone.

        ### Things that will surprise you

        - **Appending is not idempotent.** Re-running step 3 adds the rows
          again. Use `tbl.overwrite(...)` when you want replace semantics.
        - **The public URL is not the API URL.** `https://lakekeeper.<domain>`
          is for the browser UI. Clients use `http://lakekeeper:8181/catalog`
          from inside the Docker network.
        - **Spark cannot read these tables yet** — see the intro, and #828.
        - **Deleting a table deletes the data.** The warehouse is created with
          a `hard` delete profile, so `cat.drop_table(...)` removes the objects
          from R2 too, not just the pointer.
        """
    )
    return


if __name__ == "__main__":
    app.run()
