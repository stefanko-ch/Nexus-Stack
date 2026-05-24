-- Snapshot of the public schema: table list + estimated row counts.
-- Edit or replace with queries that match the data the operator has
-- loaded into the nexus-postgres instance.
SELECT
    relname AS table_name,
    n_live_tup AS estimated_rows
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC NULLS LAST,
         relname
LIMIT 50;
