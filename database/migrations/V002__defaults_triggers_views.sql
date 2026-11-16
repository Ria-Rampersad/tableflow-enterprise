-- V002: database-side defaults, integrity triggers and reporting views.
-- Hand-written. PostgreSQL-specific features that the ORM does not generate.

-- 1. Server-side defaults so ad-hoc SQL / ETL inserts behave like the application.
ALTER TABLE orders              ALTER COLUMN created_at SET DEFAULT now(), ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE payments            ALTER COLUMN created_at SET DEFAULT now(), ALTER COLUMN updated_at SET DEFAULT now(),
                                ALTER COLUMN currency   SET DEFAULT 'ZAR';
ALTER TABLE audit_logs          ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE integration_logs    ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE webhook_events      ALTER COLUMN received_at SET DEFAULT now();
ALTER TABLE incidents           ALTER COLUMN opened_at SET DEFAULT now(), ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE settlement_records  ALTER COLUMN imported_at SET DEFAULT now();

-- 2. Keep updated_at honest even when rows are changed outside the API.
CREATE OR REPLACE FUNCTION tf_touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orders_updated     BEFORE UPDATE ON orders     FOR EACH ROW EXECUTE FUNCTION tf_touch_updated_at();
CREATE TRIGGER trg_payments_updated   BEFORE UPDATE ON payments   FOR EACH ROW EXECUTE FUNCTION tf_touch_updated_at();
CREATE TRIGGER trg_incidents_updated  BEFORE UPDATE ON incidents  FOR EACH ROW EXECUTE FUNCTION tf_touch_updated_at();
CREATE TRIGGER trg_branches_updated   BEFORE UPDATE ON branches   FOR EACH ROW EXECUTE FUNCTION tf_touch_updated_at();

-- 3. The audit trail is append-only: block UPDATE and DELETE at database level.
CREATE OR REPLACE FUNCTION tf_audit_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only (attempted %)', TG_OP;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_no_update BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION tf_audit_immutable();

-- 4. Partial indexes for the "things that need attention" queries the dashboards run constantly.
CREATE INDEX ix_payments_failed      ON payments (created_at)        WHERE status = 'failed';
CREATE INDEX ix_orders_needs_action  ON orders (branch_id, created_at) WHERE status IN ('received','failed');
CREATE INDEX ix_loyalty_failed_sync  ON loyalty_transactions (created_at) WHERE sync_status = 'failed';
CREATE INDEX ix_incidents_open       ON incidents (severity, opened_at) WHERE status IN ('open','investigating','mitigated');

-- 5. Reporting views (business day in South African time).
CREATE OR REPLACE VIEW vw_daily_branch_sales AS
SELECT  (o.created_at AT TIME ZONE 'Africa/Johannesburg')::date AS business_date,
        b.code                                                  AS branch_code,
        b.name                                                  AS branch_name,
        b.province,
        count(*)                                                AS orders,
        sum(o.total)                                            AS gross_sales_incl_vat,
        sum(o.vat)                                              AS vat,
        round(avg(o.total), 2)                                  AS avg_ticket
FROM    orders o
JOIN    branches b ON b.id = o.branch_id
WHERE   o.status NOT IN ('cancelled','failed')
GROUP BY 1, 2, 3, 4;

CREATE OR REPLACE VIEW vw_payment_success_daily AS
SELECT  (p.created_at AT TIME ZONE 'Africa/Johannesburg')::date AS business_date,
        b.code AS branch_code,
        count(*) FILTER (WHERE p.status IN ('captured','refunded','partially_refunded')) AS successful,
        count(*) FILTER (WHERE p.status = 'failed')                                     AS failed,
        round(100.0 * count(*) FILTER (WHERE p.status IN ('captured','refunded','partially_refunded'))
              / NULLIF(count(*) FILTER (WHERE p.status IN ('captured','refunded','partially_refunded','failed')), 0), 2)
                                                                                         AS success_rate_pct
FROM    payments p
JOIN    orders o   ON o.id = p.order_id
JOIN    branches b ON b.id = o.branch_id
GROUP BY 1, 2;

CREATE OR REPLACE VIEW vw_integration_health_daily AS
SELECT  (l.created_at AT TIME ZONE 'Africa/Johannesburg')::date AS business_date,
        i.name AS integration,
        count(*)                                        AS calls,
        count(*) FILTER (WHERE l.status = 'failed')     AS failed,
        count(*) FILTER (WHERE l.status = 'retrying')   AS retries,
        round(avg(l.response_ms))                       AS avg_ms,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY l.response_ms) AS p95_ms
FROM    integration_logs l
JOIN    integrations i ON i.id = l.integration_id
GROUP BY 1, 2;
