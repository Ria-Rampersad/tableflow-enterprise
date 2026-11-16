-- 01_staging.sql — RAW -> STAGING: keep the latest version of each row (incremental loads append
-- re-extracted rows), enforce types, derive flags. Portable Snowflake/DuckDB SQL (QUALIFY supported by both).
CREATE SCHEMA IF NOT EXISTS staging;

CREATE OR REPLACE TABLE staging.orders AS
SELECT id AS order_id, order_number, branch_id, customer_id, channel, status, subtotal, vat, total,
       created_at, business_date,
       CASE WHEN status IN ('accepted','preparing','ready','completed','sent_to_pos') THEN TRUE ELSE FALSE END AS is_revenue,
       CASE WHEN channel IN ('uber_eats','mr_d') THEN 'delivery' ELSE 'direct' END AS channel_group
FROM raw.orders
QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC, _extracted_at DESC) = 1;

CREATE OR REPLACE TABLE staging.payments AS
SELECT id AS payment_id, order_id, provider_reference, amount, method, status, failure_reason, refunded_amount,
       created_at, business_date,
       CASE WHEN status IN ('captured','refunded','partially_refunded') THEN TRUE ELSE FALSE END AS is_success,
       CASE WHEN status = 'failed' THEN TRUE ELSE FALSE END AS is_failed,
       LEFT(failure_reason, 2) AS response_code
FROM raw.payments
QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC, _extracted_at DESC) = 1;

CREATE OR REPLACE TABLE staging.order_items AS
SELECT DISTINCT id AS order_item_id, order_id, product_id, quantity, unit_price, line_total FROM raw.order_items;

CREATE OR REPLACE TABLE staging.loyalty_transactions AS
SELECT DISTINCT id AS loyalty_txn_id, account_id, order_id, type, points, sync_status, business_date FROM raw.loyalty_transactions;

CREATE OR REPLACE TABLE staging.integration_logs AS
SELECT DISTINCT id AS log_id, integration, operation, status, response_ms, attempt, business_date FROM raw.integration_logs;
