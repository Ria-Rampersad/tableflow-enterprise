-- analytical_queries.sql — example questions Finance / Ops / Management ask of the warehouse.
-- Each query starts with a "name:" marker comment so etl/extract_load.py can run them in local demo mode.

-- name: monthly_sales_by_province
SELECT DATE_TRUNC('month', date_key) AS month, province, SUM(gross_sales) AS gross_sales, SUM(orders) AS orders
FROM analytics.mart_daily_branch_sales GROUP BY 1, 2 ORDER BY 1, 3 DESC;

-- name: branch_rank_last_7_days
SELECT branch_code, branch_name, SUM(gross_sales) AS sales_7d,
       RANK() OVER (ORDER BY SUM(gross_sales) DESC) AS sales_rank
FROM analytics.mart_daily_branch_sales
WHERE date_key >= (SELECT MAX(date_key) FROM analytics.mart_daily_branch_sales) - INTERVAL '6 days'
GROUP BY branch_code, branch_name ORDER BY sales_rank;

-- name: week_on_week_growth
WITH weekly AS (
  SELECT branch_code, DATE_TRUNC('week', date_key) AS week, SUM(gross_sales) AS sales
  FROM analytics.mart_daily_branch_sales GROUP BY 1, 2)
SELECT branch_code, week, sales, LAG(sales) OVER (PARTITION BY branch_code ORDER BY week) AS prev_week,
       ROUND(100.0 * (sales - LAG(sales) OVER (PARTITION BY branch_code ORDER BY week))
             / NULLIF(LAG(sales) OVER (PARTITION BY branch_code ORDER BY week), 0), 1) AS wow_growth_pct
FROM weekly ORDER BY branch_code, week;

-- name: delivery_share_by_branch
SELECT branch_code, ROUND(100.0 * SUM(delivery_sales) / NULLIF(SUM(gross_sales), 0), 1) AS delivery_share_pct
FROM analytics.mart_daily_branch_sales GROUP BY branch_code ORDER BY delivery_share_pct DESC;

-- name: decline_reasons
SELECT response_code, COUNT(*) AS declines, ROUND(SUM(amount), 2) AS value_declined
FROM analytics.fct_payments WHERE is_failed GROUP BY response_code ORDER BY declines DESC;

-- name: worst_payment_days
SELECT p.date_key, b.branch_code, p.success_rate_pct, p.failed
FROM analytics.mart_payment_success p JOIN analytics.dim_branch b ON b.branch_id = p.branch_id
WHERE p.attempts >= 10 ORDER BY p.success_rate_pct ASC LIMIT 10;

-- name: peak_vs_offpeak_ticket
SELECT d.is_peak_day, ROUND(AVG(f.total), 2) AS avg_ticket, COUNT(*) AS orders
FROM analytics.fct_orders f JOIN analytics.dim_date d ON d.date_key = f.date_key
WHERE f.is_revenue GROUP BY d.is_peak_day;

-- name: top_products_by_category
SELECT category, product_name, revenue, cat_rank FROM (
  SELECT p.category, p.product_name, SUM(i.line_total) AS revenue,
         ROW_NUMBER() OVER (PARTITION BY p.category ORDER BY SUM(i.line_total) DESC) AS cat_rank
  FROM staging.order_items i JOIN analytics.dim_product p ON p.product_id = i.product_id
  GROUP BY p.category, p.product_name) t
WHERE cat_rank <= 2 ORDER BY category, cat_rank;

-- name: integration_reliability
SELECT integration, SUM(calls) AS calls, SUM(failed_calls) AS failed,
       ROUND(100.0 * (SUM(calls) - SUM(failed_calls)) / NULLIF(SUM(calls), 0), 3) AS availability_pct
FROM analytics.mart_integration_health GROUP BY integration ORDER BY availability_pct;
