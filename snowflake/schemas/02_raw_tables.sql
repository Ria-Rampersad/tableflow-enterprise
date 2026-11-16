-- 02_raw_tables.sql — landing tables. Column order == CSV column order produced by etl/extract_load.py.
-- Portable SQL: also executed by DuckDB in local demo mode.
CREATE SCHEMA IF NOT EXISTS raw;
CREATE TABLE IF NOT EXISTS raw.branches (id INTEGER, code VARCHAR, name VARCHAR, city VARCHAR, province VARCHAR,
  is_active BOOLEAN, opened_on DATE, _extracted_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS raw.products (id INTEGER, sku VARCHAR, name VARCHAR, category VARCHAR, price DECIMAL(12,2),
  _extracted_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS raw.orders (id INTEGER, order_number VARCHAR, branch_id INTEGER, customer_id INTEGER,
  channel VARCHAR, status VARCHAR, subtotal DECIMAL(12,2), vat DECIMAL(12,2), total DECIMAL(12,2),
  created_at TIMESTAMP, business_date DATE, updated_at TIMESTAMP, _extracted_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS raw.order_items (id INTEGER, order_id INTEGER, product_id INTEGER, quantity INTEGER,
  unit_price DECIMAL(12,2), line_total DECIMAL(12,2), _extracted_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS raw.payments (id INTEGER, order_id INTEGER, provider_reference VARCHAR, amount DECIMAL(12,2),
  method VARCHAR, status VARCHAR, failure_reason VARCHAR, refunded_amount DECIMAL(12,2), created_at TIMESTAMP,
  business_date DATE, updated_at TIMESTAMP, _extracted_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS raw.loyalty_transactions (id INTEGER, account_id INTEGER, order_id INTEGER, type VARCHAR,
  points INTEGER, sync_status VARCHAR, created_at TIMESTAMP, business_date DATE, _extracted_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS raw.integration_logs (id INTEGER, integration VARCHAR, operation VARCHAR, status VARCHAR,
  response_ms INTEGER, attempt INTEGER, created_at TIMESTAMP, business_date DATE, _extracted_at TIMESTAMP);
