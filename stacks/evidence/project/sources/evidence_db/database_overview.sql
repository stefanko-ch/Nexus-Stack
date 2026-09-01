-- Snapshot of the public schema: table list + estimated row counts.
-- Edit or replace with queries that match the data you have loaded into
-- this stack's evidence-db.
--
-- The CTE-plus-UNION-ALL shape is not decoration. A source query returning
-- zero rows makes Evidence write no parquet file while still listing it in
-- the manifest; +layout.js then builds a view over the missing file with
-- read_parquet(), DuckDB throws, and because the throw is uncaught the node
-- process exits. `restart: unless-stopped` restarts it, and the container
-- sits in a restart loop that looks nothing like "your query matched
-- nothing" (#725, defect 7).
--
-- Copy this shape for any query you add. Guard against the CTE, never
-- against the underlying table: `WHERE NOT EXISTS (SELECT 1 FROM overview)`
-- asks "did the query produce anything", while `... FROM pg_stat_user_tables`
-- would ask "does the source hold anything" -- and those differ the moment
-- the query has a WHERE or a JOIN. A query filtering `status = 'active'`
-- over a table of inactive rows returns nothing while the table is not
-- empty, so a source-level guard stays silent and the crash happens anyway.
WITH overview AS (
    SELECT
        relname AS table_name,
        n_live_tup AS estimated_rows
    FROM pg_stat_user_tables
)
SELECT * FROM overview
UNION ALL
SELECT '(no user tables yet)', 0
WHERE NOT EXISTS (SELECT 1 FROM overview)
ORDER BY estimated_rows DESC NULLS LAST,
         table_name
LIMIT 50;
