-- Sample data for the bundled Evidence project.
--
-- Runs once, from docker-entrypoint-initdb.d, on an empty data
-- directory. Later restarts skip it, so anything the operator changes
-- here afterwards survives.
--
-- It exists because Evidence's bundled page needs rows to render: a
-- source query returning zero rows crashes the dev server (#725 defect
-- 7, still open). An empty database is exactly the state a fresh stack
-- starts in, so without a seed the default page fails on first visit and
-- looks like a broken stack rather than an empty one.
--
-- Do NOT drop this table on its own. `monthly_revenue.sql` selects from
-- it and `pages/index.md` renders that query, and a source query against
-- a missing table fails `npm run sources` -- which the entrypoint runs
-- before the dev server, so Evidence stops starting at all. That is the
-- same class of failure this stack's dedicated database exists to
-- prevent, reached from the other direction.
--
-- To retire the demo: replace the queries under
-- project/sources/evidence_db/ and the blocks in project/pages/index.md
-- that read them first, then drop the table.

CREATE TABLE demo_sales (
    sale_month  date           NOT NULL,
    region      text           NOT NULL,
    category    text           NOT NULL,
    revenue     numeric(10, 2) NOT NULL,
    orders      integer        NOT NULL,
    PRIMARY KEY (sale_month, region, category)
);

COMMENT ON TABLE demo_sales IS
    'Synthetic monthly sales, seeded by Nexus-Stack so the sample Evidence page renders on a fresh stack.';

-- Twelve months x three regions x two categories = 72 deterministic
-- rows. Deterministic on purpose: two operators comparing their stacks
-- should see the same numbers, so the values come from the month and
-- region rather than from random().
INSERT INTO demo_sales (sale_month, region, category, revenue, orders)
SELECT
    m.sale_month,
    r.region,
    c.category,
    ROUND((r.base + c.weight * 400 + EXTRACT(MONTH FROM m.sale_month) * 130)::numeric, 2),
    (r.base / 100 + c.weight * 5 + EXTRACT(MONTH FROM m.sale_month))::integer
FROM generate_series(DATE '2025-01-01', DATE '2025-12-01', INTERVAL '1 month')
         AS m(sale_month)
CROSS JOIN (VALUES ('EMEA', 4200), ('Americas', 5100), ('APAC', 3300))
         AS r(region, base)
CROSS JOIN (VALUES ('Hardware', 2), ('Services', 1))
         AS c(category, weight);

-- pg_stat_user_tables reports a table as soon as it exists, but
-- n_live_tup stays 0 until statistics are collected. The bundled
-- database_overview query sorts on that column, so populate it now
-- rather than waiting for autovacuum.
ANALYZE demo_sales;
