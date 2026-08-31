-- Monthly revenue by region, from the seeded demo_sales table.
-- Replace this file once you have your own data; the page that renders
-- it is pages/index.md.
SELECT
    sale_month,
    region,
    SUM(revenue) AS revenue,
    SUM(orders)  AS orders
FROM demo_sales
GROUP BY sale_month, region
ORDER BY sale_month, region;
