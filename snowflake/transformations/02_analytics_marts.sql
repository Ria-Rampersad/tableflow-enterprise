-- 02_analytics_marts.sql — STAGING -> ANALYTICS: star schema (dims + facts) and reporting marts.
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE TABLE analytics.dim_branch AS
SELECT id AS branch_id, code AS branch_code, name AS branch_name, city, province, is_active, opened_on
FROM raw.branches QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC) = 1;

CREATE OR REPLACE TABLE analytics.dim_product AS
SELECT id AS product_id, sku, name AS product_name, category, price AS list_price
FROM raw.products QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC) = 1;

CREATE OR REPLACE TABLE analytics.dim_date AS
SELECT DISTINCT business_date AS date_key,
       EXTRACT(YEAR FROM business_date) AS year, EXTRACT(MONTH FROM business_date) AS month,
       DATE_TRUNC('month', business_date) AS month_start, EXTRACT(DOW FROM business_date) AS day_of_week,
       CASE WHEN EXTRACT(DOW FROM business_date) IN (0, 5, 6) THEN TRUE ELSE FALSE END AS is_peak_day
FROM staging.orders;

CREATE OR REPLACE TABLE analytics.fct_orders AS
SELECT o.order_id, o.business_date AS date_key, o.branch_id, o.channel, o.channel_group, o.status, o.is_revenue,
       o.total, o.vat, o.subtotal,
       COALESCE(p.captured_amount, 0) AS captured_amount, COALESCE(p.attempts, 0) AS payment_attempts,
       COALESCE(p.failed_attempts, 0) AS failed_payment_attempts, i.item_count
FROM staging.orders o
LEFT JOIN (SELECT order_id, SUM(CASE WHEN is_success THEN amount - refunded_amount ELSE 0 END) AS captured_amount,
                  COUNT(*) AS attempts, SUM(CASE WHEN is_failed THEN 1 ELSE 0 END) AS failed_attempts
           FROM staging.payments GROUP BY order_id) p ON p.order_id = o.order_id
LEFT JOIN (SELECT order_id, SUM(quantity) AS item_count FROM staging.order_items GROUP BY order_id) i
       ON i.order_id = o.order_id;

CREATE OR REPLACE TABLE analytics.fct_payments AS
SELECT p.payment_id, p.business_date AS date_key, o.branch_id, o.channel, p.method, p.status, p.is_success,
       p.is_failed, p.response_code, p.amount, p.refunded_amount
FROM staging.payments p JOIN staging.orders o ON o.order_id = p.order_id;

CREATE OR REPLACE TABLE analytics.mart_daily_branch_sales AS
SELECT f.date_key, b.branch_code, b.branch_name, b.province,
       COUNT(*) AS orders,
       SUM(CASE WHEN f.is_revenue THEN f.total ELSE 0 END) AS gross_sales,
       SUM(CASE WHEN f.is_revenue THEN f.vat ELSE 0 END) AS vat,
       SUM(CASE WHEN f.channel_group = 'delivery' AND f.is_revenue THEN f.total ELSE 0 END) AS delivery_sales,
       SUM(CASE WHEN f.status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_orders,
       ROUND(SUM(CASE WHEN f.is_revenue THEN f.total ELSE 0 END) / NULLIF(SUM(CASE WHEN f.is_revenue THEN 1 ELSE 0 END), 0), 2) AS avg_ticket
FROM analytics.fct_orders f JOIN analytics.dim_branch b ON b.branch_id = f.branch_id
GROUP BY f.date_key, b.branch_code, b.branch_name, b.province;

CREATE OR REPLACE TABLE analytics.mart_payment_success AS
SELECT date_key, branch_id, COUNT(*) AS attempts, SUM(CASE WHEN is_success THEN 1 ELSE 0 END) AS successful,
       SUM(CASE WHEN is_failed THEN 1 ELSE 0 END) AS failed,
       ROUND(100.0 * SUM(CASE WHEN is_success THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN is_success OR is_failed THEN 1 ELSE 0 END), 0), 2) AS success_rate_pct
FROM analytics.fct_payments GROUP BY date_key, branch_id;

CREATE OR REPLACE TABLE analytics.mart_integration_health AS
SELECT business_date AS date_key, integration, COUNT(*) AS calls,
       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_calls,
       ROUND(AVG(response_ms)) AS avg_ms, MAX(response_ms) AS max_ms
FROM staging.integration_logs GROUP BY business_date, integration;

CREATE OR REPLACE TABLE analytics.mart_loyalty_activity AS
SELECT business_date AS date_key, SUM(CASE WHEN type = 'earn' THEN points ELSE 0 END) AS points_earned,
       SUM(CASE WHEN type = 'redeem' THEN points ELSE 0 END) AS points_redeemed,
       SUM(CASE WHEN sync_status = 'failed' THEN 1 ELSE 0 END) AS failed_syncs
FROM staging.loyalty_transactions GROUP BY business_date;
