-- Monthly revenue by region, from the seeded demo_sales table.
-- Replace this file once you have your own data; the page that renders
-- it is pages/index.md.
--
-- Guarded like database_overview.sql, and for a case that one does not
-- cover: there the guard fires when no table exists, here when the table
-- exists but holds no rows. `DELETE FROM demo_sales` reaches exactly that
-- state, and it is what someone does while replacing the demo data with
-- their own -- so this is the likelier of the two paths into the zero-row
-- crash (#725, defect 7).
--
-- The guard tests the CTE, not demo_sales. Testing the table would be
-- equivalent only because this query has no WHERE clause; add one and the
-- two stop agreeing. Guarding the CTE is right in both cases, so it is
-- what this example shows.
--
-- The placeholder is a visible one on purpose. A flat zero line labelled
-- "(no data)" reads as an empty table at a glance; a silently absent
-- series would look like a rendering problem.
WITH monthly AS (
    SELECT
        sale_month,
        region,
        SUM(revenue) AS revenue,
        SUM(orders)  AS orders
    FROM demo_sales
    GROUP BY sale_month, region
)
SELECT * FROM monthly
UNION ALL
SELECT DATE '2025-01-01', '(no data)', 0, 0
WHERE NOT EXISTS (SELECT 1 FROM monthly)
ORDER BY sale_month, region;
