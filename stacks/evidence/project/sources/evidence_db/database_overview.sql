-- Snapshot of the public schema: table list + estimated row counts.
-- Edit or replace with queries that match the data you have loaded into
-- this stack's evidence-db.
--
-- The UNION ALL branch is not decoration. A source query returning zero
-- rows makes Evidence write no parquet file while still listing it in the
-- manifest; +layout.js then builds a view over the missing file with
-- read_parquet(), DuckDB throws, and because the throw is uncaught the
-- node process exits. `restart: unless-stopped` restarts it, and the
-- container sits in a restart loop that looks nothing like "your query
-- matched nothing" (#725, defect 7).
--
-- pg_stat_user_tables is empty until a user table exists, so this query
-- can legitimately return nothing -- on a database whose tables were all
-- dropped, or one Evidence is pointed at before anything is loaded. The
-- guard makes that impossible: there is always at least one row.
--
-- Any query you add here is subject to the same trap. `WHERE NOT EXISTS`
-- over the same source is the cheapest way to make one zero-row-proof.
SELECT
    relname AS table_name,
    n_live_tup AS estimated_rows
FROM pg_stat_user_tables
UNION ALL
SELECT
    '(no user tables yet)',
    0
WHERE NOT EXISTS (SELECT 1 FROM pg_stat_user_tables)
ORDER BY estimated_rows DESC NULLS LAST,
         table_name
LIMIT 50;
