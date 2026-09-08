"""Create and query a Delta table that outlives the server.

The point of this notebook is not Delta and not SQL — it is that the table
you create here is still there after a teardown and spin-up, which is not
true of anything written to the server's own disk.

Two independent pieces make that work, and both have to be in place:

* **Unity Catalog** remembers that the table exists, in a PostgreSQL
  metastore that the snapshot layer carries across as a `pg_dump`.
* **Cloudflare R2** holds the files themselves, outside the server
  entirely.

Run `Verify_Spark_And_S3.py` first if anything here fails — it isolates
which layer broke.
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
        # Unity Catalog on R2

        A table here has a **three-part name**: `unity.<schema>.<table>`.
        The leading `unity` is the catalog, and it is what tells Spark to
        ask Unity Catalog rather than its own built-in catalog.

        Spark's own catalog is still the default on purpose, so every
        notebook that does not care about any of this keeps working.
        """
    )
    return


@app.cell
def _():
    import os

    from _nexus_spark import get_spark

    spark = get_spark()

    # Seeded notebooks land in every workspace, whether or not the stack they
    # describe is enabled. Two things have to be true for the cells below, and
    # they fail differently, so they are reported separately rather than as one
    # "not available".
    bucket = os.environ.get("R2_BUCKET", "")
    # Empty unless the deploy wrote the catalog block, which it does only when
    # the unity-catalog stack is enabled. Checked against the cluster rather
    # than guessed from the environment: this is the server's configuration,
    # and Spark Connect keeps client and server config separate.
    catalog = spark.conf.get("spark.sql.catalog.unity", "")
    ready = bool(bucket) and bool(catalog)

    print("R2 bucket    :", bucket or "(not configured)")
    print("unity catalog:", catalog or "(not enabled on this deployment)")
    if not ready:
        print()
        print("The cells below will skip. Enable Unity Catalog in the Control")
        print("Plane and re-run a spin-up to work through this notebook.")
    return bucket, ready, spark


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 1 — A schema to put tables in

        Catalogs contain schemas, schemas contain tables. `unity` already
        exists; the schema is yours to name.
        """
    )
    return


@app.cell
def _(bucket, ready, spark):
    if not ready:
        print("skipped — see the setup cell above for which half is missing")
    else:
        spark.sql("CREATE SCHEMA IF NOT EXISTS unity.workshop")
        spark.sql("SHOW SCHEMAS IN unity").show()
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2 — A table whose files live in R2

        `LOCATION` is what puts the data outside the server. Note the
        scheme: **`s3://`, not `s3a://`** — Unity Catalog refuses the
        latter with `Unsupported URI scheme: s3a`, even though Spark reads
        both. The cluster maps `fs.s3.impl` onto the S3A filesystem so the
        shorter scheme still works.

        `IF NOT EXISTS` matters here: this notebook is seeded to every
        workspace and you may well run it twice.
        """
    )
    return


@app.cell
def _(bucket, ready, spark):
    if not ready:
        print("skipped — see the setup cell above for which half is missing")
    else:
        _location = f"s3://{bucket}/workshop/cities"
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS unity.workshop.cities (
                id INT,
                name STRING,
                country STRING
            ) USING delta LOCATION '{_location}'
        """)
        print("table location:", _location)
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3 — Write, then read it back

        `INSERT` appends, so re-running this cell adds the rows again. That
        is ordinary SQL behaviour rather than something to work around —
        use `SELECT DISTINCT` below, or drop the table and start over, if
        the duplicates bother you.
        """
    )
    return


@app.cell
def _(bucket, ready, spark):
    if not ready:
        print("skipped — see the setup cell above for which half is missing")
    else:
        spark.sql("""
            INSERT INTO unity.workshop.cities VALUES
                (1, 'Zürich', 'CH'),
                (2, 'Lisbon', 'PT'),
                (3, 'Tallinn', 'EE')
        """)
        spark.sql("""
            SELECT DISTINCT id, name, country
            FROM unity.workshop.cities
            ORDER BY id
        """).show()
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4 — What the catalog knows about it

        This is the part a plain Parquet file in a bucket does not give
        you: the table has a name, a schema, and a description that any
        other tool pointed at the same catalog can discover.
        """
    )
    return


@app.cell
def _(bucket, ready, spark):
    if not ready:
        print("skipped — see the setup cell above for which half is missing")
    else:
        spark.sql("SHOW TABLES IN unity.workshop").show()
        spark.sql("DESCRIBE TABLE unity.workshop.cities").show()
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## What just happened, and why it survives

        The Delta files went to R2 and the registration went to Unity
        Catalog's PostgreSQL. Neither is on the server's disk, so a
        teardown that destroys the machine destroys neither.

        Worth understanding: Spark never received the bucket's own
        credentials. It asked Unity Catalog for access to that one
        location, and got back a short-lived token minted for the request —
        read-only when the query only reads. The long-lived key stays
        inside the catalog server.

        You can see the same table from the Unity Catalog UI at
        `https://unity-catalog.<your-domain>`.
        """
    )
    return


if __name__ == "__main__":
    app.run()
