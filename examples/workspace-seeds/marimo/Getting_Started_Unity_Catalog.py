"""Create and query a Delta table that outlives the server.

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
        # Unity Catalog on R2

        The point of this notebook is not Delta and not SQL — it is that the
        table you create here is still there after a teardown and spin-up,
        which is not true of anything written to the server's own disk.

        Two independent pieces make that work, and both have to be in place:

        * **Unity Catalog** remembers that the table exists, in a PostgreSQL
          metastore that the snapshot layer carries across as a `pg_dump`.
        * **Cloudflare R2** holds the files themselves, outside the server
          entirely.

        Run `Verify_Spark_And_S3.py` first if anything here fails — it
        isolates which layer broke.

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
        spark.sql("CREATE SCHEMA IF NOT EXISTS unity.demo")
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
        _location = f"s3://{bucket}/demo/cities"
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS unity.demo.cities (
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
            INSERT INTO unity.demo.cities VALUES
                (1, 'Zürich', 'CH'),
                (2, 'Lisbon', 'PT'),
                (3, 'Tallinn', 'EE')
        """)
        spark.sql("""
            SELECT DISTINCT id, name, country
            FROM unity.demo.cities
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
        spark.sql("SHOW TABLES IN unity.demo").show()
        spark.sql("DESCRIBE TABLE unity.demo.cities").show()
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 5 — A volume, for the files that are not tables

        A table is Delta: columns, rows, a schema. A **volume** is the
        catalog's answer for everything else — a CSV someone handed you, a
        folder of images, a trained model. The catalog tracks the name and
        the location; the bytes live in R2 exactly as a table's do.

        Volumes are not part of Spark SQL. `SHOW VOLUMES` is a Databricks
        dialect and Spark rejects it, so this section talks to Unity
        Catalog's REST API directly — with `urllib` from the standard
        library, no install needed.
        """
    )
    return


@app.cell
def _():
    import json
    import os
    import urllib.error
    import urllib.request

    UC_API = "http://unitycatalog:8080/api/2.1/unity-catalog"

    def uc(path, body=None, method=None):
        """Call the catalog. Returns (status, parsed-body-or-text)."""
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{UC_API}{path}",
            data=data,
            method=method or ("POST" if data else "GET"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            # The catalog answered and said no. The body carries the reason.
            return exc.code, (exc.read() or b"").decode()[:300]
        except urllib.error.URLError as exc:
            # No answer at all: the container is down, or the name does not
            # resolve. Caught separately so a stopped catalog reads as a
            # sentence rather than a traceback — HTTPError is a subclass of
            # URLError, so the order of these two matters.
            return "unreachable", (
                f"{UC_API} did not answer ({exc.reason}). Is the "
                "unity-catalog stack enabled and running?"
            )

    r2_endpoint = os.environ.get("R2_ENDPOINT", "")
    return r2_endpoint, uc


@app.cell
def _(bucket, ready, uc):
    if not ready:
        print("skipped — see the setup cell above for which half is missing")
    else:
        _location = f"s3://{bucket}/demo/volumes/reports"
        # Create-if-absent by hand: the API has no IF NOT EXISTS, and a
        # second run would otherwise fail on a volume that is already there.
        _status, _existing = uc("/volumes/unity.demo.reports")
        if _status == 200:
            print("volume already exists:", _existing["storage_location"])
        else:
            print(
                uc(
                    "/volumes",
                    {
                        "catalog_name": "unity",
                        "schema_name": "demo",
                        "name": "reports",
                        "volume_type": "EXTERNAL",
                        "storage_location": _location,
                    },
                )[0],
                _location,
            )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 6 — Ask the catalog for permission, then write

        This is the part worth slowing down for. **You never hold the
        bucket's key.** You name a volume, the catalog hands back
        credentials minted for that request, and they expire.

        Ask for `WRITE_VOLUME` and you get write access; ask for
        `READ_VOLUME` and the token cannot write at all. Either way it is
        confined to this volume's prefix — a token for `demo/volumes/reports`
        cannot touch `demo/volumes/anything-else`.

        PyArrow does the S3 work here because it ships with this image and
        speaks session tokens. `boto3` is not installed; DuckDB would work
        too.
        """
    )
    return


@app.cell
def _(r2_endpoint, ready, uc):
    if not ready:
        print("skipped — see the setup cell above for which half is missing")
    elif not r2_endpoint:
        print("skipped — R2_ENDPOINT is not set for this deployment")
    else:
        import pyarrow as pa
        import pyarrow.csv as pacsv
        from pyarrow import fs

        _volume = uc("/volumes/unity.demo.reports")[1]
        _status, _vend = uc(
            "/temporary-volume-credentials",
            {"volume_id": _volume["volume_id"], "operation": "WRITE_VOLUME"},
        )
        _cred = _vend["aws_temp_credentials"]

        _s3 = fs.S3FileSystem(
            access_key=_cred["access_key_id"],
            secret_key=_cred["secret_access_key"],
            session_token=_cred["session_token"],
            endpoint_override=r2_endpoint,
            region="auto",
        )
        # PyArrow paths are bucket-relative-with-bucket, not URLs: strip the
        # scheme from what the catalog returned rather than rebuilding it.
        _key = _volume["storage_location"].removeprefix("s3://") + "/cities.csv"

        _table = pa.table({"id": [1, 2, 3], "name": ["Zürich", "Lisbon", "Tallinn"]})
        with _s3.open_output_stream(_key) as _out:
            pacsv.write_csv(_table, _out)
        print("wrote  ", _key)

        with _s3.open_input_stream(_key) as _in:
            print("read   ", _in.read().decode().strip().replace("\n", " | "))
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 7 — Both kinds of object, side by side

        The catalog now holds a table and a volume in the same schema, and
        the Control Plane UI lists both under `unity` → `demo`.
        """
    )
    return


@app.cell
def _(ready, uc):
    if not ready:
        print("skipped — see the setup cell above for which half is missing")
    else:
        print(
            "tables :",
            [
                t["name"]
                for t in uc("/tables?catalog_name=unity&schema_name=demo")[1].get("tables", [])
            ],
        )
        print(
            "volumes:",
            [
                v["name"]
                for v in uc("/volumes?catalog_name=unity&schema_name=demo")[1].get("volumes", [])
            ],
        )
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

        The same applies to the volume, with one difference worth noticing:
        the table's credentials were vended to Spark without you seeing
        them, while for the volume you asked and received them yourself.
        Same mechanism, one step more visible.

        ## Two things the UI will not show you

        **The table has no columns.** Open `unity.demo.cities` in the UI and
        the Columns section is empty, even though the query above returned
        rows. The Spark connector registers the table's type, format and
        location and leaves the schema in the Delta log at that location —
        so Spark reads it from there, and the catalog never sees it. Not a
        fault in this deployment: a table created through the REST API *with*
        a `columns` array does show them.

        **The volume shows no files.** Unity Catalog has no files API — only
        the volume's own metadata. Your `cities.csv` is in R2 and this
        notebook just read it back; there is simply no endpoint the browser
        could list it from.

        ## Why Functions and Models stay empty

        Open the catalog UI at `https://unity-catalog.<your-domain>` and the
        schema shows four sections. Two of them will have nothing in them,
        and that is not a fault in this deployment:

        - **Functions** — the catalog can store one, but the Spark connector
          does not implement Spark's function interface. Any attempt from a
          notebook answers `MISSING_CATALOG_ABILITY.FUNCTIONS: Catalog unity
          does not support functions`. Registering one you cannot call would
          fill the section and teach nothing.
        - **Models** — Unity Catalog keeps model artefacts in a *managed*
          location, and this stack configures none: tables and volumes both
          carry an explicit location instead. Creating one fails with
          `FAILED_PRECONDITION ... has managed location configured`.

        Both are tracked as issues in Nexus-Stack rather than worked around
        here.
        """
    )
    return


if __name__ == "__main__":
    app.run()
