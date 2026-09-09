"""Iceberg REST catalogue factory for Marimo notebooks (PyIceberg).

Usage in a Marimo cell:

    from _nexus_iceberg import get_catalog
    cat = get_catalog()
    cat.list_namespaces()

This is the Iceberg counterpart to ``_nexus_spark.py``, and it is a different
shape of client on purpose. PyIceberg speaks the Iceberg REST protocol
directly over HTTP: no JVM, no runtime jar, no Spark-version matrix. That is
not merely convenient here — it is currently the only way. Iceberg publishes
no ``iceberg-spark-runtime`` build for the Spark 4.2 this project runs, and
the 4.1 build fails on it with an ``IncompatibleClassChangeError``. See
``docs/stacks/spark.md`` and issue #828.

Connection defaults
-------------------
The catalogue URL is read from ``$LAKEKEEPER_URI`` and the warehouse name from
``$LAKEKEEPER_WAREHOUSE``, both set by ``stacks/marimo/docker-compose.yml``.
The fallbacks below match what ``render_lakekeeper_hook`` creates, so a
notebook works unchanged on a default deployment.

Always the **in-cluster** URL, never ``https://lakekeeper.<domain>``. The
public hostname is behind Cloudflare Access, which answers an unauthenticated
client with an HTML login page — PyIceberg then fails while parsing that as
JSON, which reads like a catalogue bug and is not one.

Why the session is cached
-------------------------
Same reasoning as ``_nexus_spark``: Marimo's reactive graph re-runs cells when
their inputs change, but module-level state survives. One catalogue object per
process keeps the HTTP session and its token warm instead of re-fetching
``/v1/config`` on every cell.

Reading a table
---------------
The conversions live on the *scan*, not on the table::

    tbl = cat.load_table("demo.orders")
    tbl.scan().to_arrow()          # pyarrow.Table
    tbl.scan().to_polars()         # polars.DataFrame
    tbl.scan().to_pandas()         # pandas.DataFrame
    con = tbl.scan().to_duckdb("orders")   # NOTE: name is required,
    con.sql("SELECT * FROM orders")        # and this returns a CONNECTION

``Table`` itself carries only ``to_polars()`` as a shortcut; there is no
``Table.to_arrow()`` and no ``Table.to_duckdb()``.

Writing a table
---------------
Writes go through ``s3fs``, which the Marimo image installs for this reason.
Lakekeeper's warehouses use remote signing — the catalogue signs each S3
request on the client's behalf, because Cloudflare R2 has no AWS STS endpoint
— and PyIceberg implements remote signing only in its fsspec FileIO. Without
``s3fs`` a write fails with ``ModuleNotFoundError`` *after* the table has
already been created in the catalogue, which leaves a real but empty table
behind.
"""
from __future__ import annotations

import os
from typing import Optional

from pyiceberg.catalog import Catalog, load_catalog

# Kept in step with services.LAKEKEEPER_WAREHOUSE. If that constant is
# renamed, this fallback has to move with it or a default deployment stops
# resolving.
DEFAULT_URI = "http://lakekeeper:8181/catalog"
DEFAULT_WAREHOUSE = "nexus"

_catalog: Optional[Catalog] = None


def get_catalog(warehouse: Optional[str] = None) -> Catalog:
    """Return a process-wide Iceberg REST catalogue, creating it on first call.

    Pass ``warehouse`` to open a different one; that bypasses the cache and
    returns a fresh catalogue object rather than replacing the cached default,
    so a notebook can hold both at once.
    """
    global _catalog
    uri = os.environ.get("LAKEKEEPER_URI", DEFAULT_URI)
    if warehouse is not None:
        return load_catalog("nexus", **{"type": "rest", "uri": uri, "warehouse": warehouse})
    if _catalog is None:
        name = os.environ.get("LAKEKEEPER_WAREHOUSE", DEFAULT_WAREHOUSE)
        _catalog = load_catalog("nexus", **{"type": "rest", "uri": uri, "warehouse": name})
    return _catalog


def reset_catalog() -> None:
    """Drop the cached catalogue so the next get_catalog() rebuilds it.

    Needed after changing ``$LAKEKEEPER_URI`` or ``$LAKEKEEPER_WAREHOUSE`` from
    inside a notebook — the cache is keyed on nothing, so it would otherwise
    keep handing back the catalogue built from the old values.
    """
    global _catalog
    _catalog = None
