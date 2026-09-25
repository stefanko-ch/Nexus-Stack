"""Browse the shared PostgreSQL and chart a query.

Ships with the stack so that a fresh Streamlit is not an empty page, and
so the connection to the shared `postgres` stack is demonstrated once
rather than rediscovered in every app.
"""

from __future__ import annotations

import os

import pandas as pd
import psycopg2
import streamlit as st

st.title("Warehouse explorer")

PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")

TABLES_SQL = """
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name
"""


@st.cache_resource
def connect() -> psycopg2.extensions.connection:
    """One connection per server process, reused across reruns.

    Read-only at the session level: every statement this app sends runs
    in a read-only transaction, so a mistyped UPDATE in the query box
    below is refused by PostgreSQL rather than by a check here.
    """
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "postgres"),
        user=os.environ.get("POSTGRES_USER", "nexus-postgres"),
        password=PASSWORD,
        connect_timeout=5,
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


def run(sql: str) -> pd.DataFrame:
    with connect().cursor() as cur:
        cur.execute(sql)
        columns = [c.name for c in cur.description or []]
        return pd.DataFrame(cur.fetchall(), columns=columns)


if not PASSWORD:
    st.warning(
        "No `POSTGRES_PASSWORD` in this container's environment, so there is "
        "nothing to connect to. Enable the **postgres** stack in the Control "
        "Plane and spin up again."
    )
    st.stop()

try:
    tables = run(TABLES_SQL)
except psycopg2.Error as exc:
    st.error(f"Could not reach the shared PostgreSQL: {exc}")
    st.stop()

st.subheader("Tables")
if tables.empty:
    st.info("The database has no user tables yet.")
else:
    st.dataframe(tables, width="stretch", hide_index=True)

st.subheader("Query")
default = (
    f"SELECT * FROM {tables.iloc[0]['table_schema']}.{tables.iloc[0]['table_name']} LIMIT 100"
    if not tables.empty
    else "SELECT version()"
)
sql = st.text_area("SQL", value=default, height=120)

if st.button("Run", type="primary"):
    try:
        result = run(sql)
    except psycopg2.Error as exc:
        st.error(str(exc))
    else:
        st.dataframe(result, width="stretch")
        numeric = result.select_dtypes("number")
        if not numeric.empty and len(result) > 1:
            st.bar_chart(numeric)
