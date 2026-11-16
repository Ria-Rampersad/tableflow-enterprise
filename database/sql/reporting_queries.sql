-- TableFlow operational SQL library (PostgreSQL). Each query is runnable as-is against the seeded DB:
--   psql "$DATABASE_URL" -f database/sql/reporting_queries.sql

-- Q1  Today's sales per branch (business day in SAST)
SELECT b.code, b.name, COUNT(*) AS orders, SUM(o.total) AS sales_incl_vat, ROUND(AVG(o.total), 2) AS avg_ticket
FROM orders o JOIN branches b ON b.id = o.branch_id
WHERE (o.created_at AT TIME ZONE 'Africa/Johannesburg')::date = (now() AT TIME ZONE 'Africa/Johannesburg')::date
  AND o.status NOT IN ('cancelled', 'failed')
GROUP BY b.code, b.name ORDER BY sales_incl_vat DESC;

-- Q2  Payment success rate per branch, last 7 days (FILTER clause)
SELECT b.code,
       COUNT(*) FILTER (WHERE p.status IN ('captured','refunded','partially_refunded')) AS ok,
       COUNT(*) FILTER (WHERE p.status = 'failed') AS failed,
       ROUND(100.0 * COUNT(*) FILTER (WHERE p.status IN ('captured','refunded','partially_refunded'))
             / NULLIF(COUNT(*) FILTER (WHERE p.status <> 'initiated'), 0), 2) AS success_pct
FROM payments p JOIN orders o ON o.id = p.order_id JOIN branches b ON b.id = o.branch_id
WHERE p.created_at >= now() - interval '7 days'
GROUP BY b.code ORDER BY success_pct;

-- Q3  Decline reasons (first two chars = ISO 8583-style response code)
SELECT LEFT(failure_reason, 2) AS code, failure_reason, COUNT(*) AS n, SUM(amount) AS value
FROM payments WHERE status = 'failed' GROUP BY 1, 2 ORDER BY n DESC;

-- Q4  Orders with more than one captured payment (duplicate charges) - reconciliation input
SELECT o.order_number, o.total, COUNT(p.id) AS captured_payments, SUM(p.amount) AS charged
FROM orders o JOIN payments p ON p.order_id = o.id AND p.status = 'captured'
GROUP BY o.id, o.order_number, o.total HAVING COUNT(p.id) > 1;

-- Q5  Captured payments missing from the acquirer settlement report (anti-join)
SELECT p.id, p.provider_reference, p.amount, (p.created_at AT TIME ZONE 'Africa/Johannesburg')::date AS business_date
FROM payments p
LEFT JOIN settlement_records s ON s.provider_reference = p.provider_reference
WHERE p.status = 'captured' AND s.id IS NULL
  AND p.created_at < date_trunc('day', now() AT TIME ZONE 'Africa/Johannesburg') AT TIME ZONE 'Africa/Johannesburg'
ORDER BY p.created_at DESC LIMIT 50;

-- Q6  Orders that never reached the POS (operations work queue)
SELECT o.id, o.order_number, b.code, o.channel, o.total, o.created_at
FROM orders o JOIN branches b ON b.id = o.branch_id
WHERE o.status = 'failed' ORDER BY o.created_at DESC;

-- Q7  Integration latency percentiles, last 24h
SELECT i.name, COUNT(*) AS calls,
       percentile_cont(0.5)  WITHIN GROUP (ORDER BY l.response_ms) AS p50_ms,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY l.response_ms) AS p95_ms,
       COUNT(*) FILTER (WHERE l.status = 'failed') AS failed
FROM integration_logs l JOIN integrations i ON i.id = l.integration_id
WHERE l.created_at >= now() - interval '24 hours'
GROUP BY i.name ORDER BY p95_ms DESC;

-- Q8  Running daily revenue + 7-day moving average (window functions)
WITH daily AS (
  SELECT (created_at AT TIME ZONE 'Africa/Johannesburg')::date AS d, SUM(total) AS revenue
  FROM orders WHERE status NOT IN ('cancelled','failed') GROUP BY 1)
SELECT d, revenue,
       SUM(revenue) OVER (ORDER BY d) AS running_total,
       ROUND(AVG(revenue) OVER (ORDER BY d ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS ma_7d
FROM daily ORDER BY d;

-- Q9  Top 3 products per branch (ROW_NUMBER partition)
SELECT * FROM (
  SELECT b.code, p.name, SUM(i.quantity) AS qty, SUM(i.line_total) AS revenue,
         ROW_NUMBER() OVER (PARTITION BY b.code ORDER BY SUM(i.line_total) DESC) AS rn
  FROM order_items i JOIN orders o ON o.id = i.order_id JOIN branches b ON b.id = o.branch_id
  JOIN products p ON p.id = i.product_id
  WHERE o.status NOT IN ('cancelled','failed') GROUP BY b.code, p.name) t
WHERE rn <= 3 ORDER BY code, rn;

-- Q10 Loyalty: members close to the next tier
SELECT a.member_number, c.full_name, a.tier, a.lifetime_points,
       CASE a.tier WHEN 'Bronze' THEN 500 - a.lifetime_points WHEN 'Silver' THEN 1500 - a.lifetime_points END AS points_to_next
FROM loyalty_accounts a JOIN customers c ON c.id = a.customer_id
WHERE a.tier <> 'Gold' ORDER BY points_to_next LIMIT 20;

-- Q11 Mean time to resolve incidents by severity
SELECT severity, COUNT(*) AS incidents,
       ROUND(AVG(EXTRACT(EPOCH FROM resolved_at - opened_at) / 60)) AS mttr_minutes
FROM incidents WHERE resolved_at IS NOT NULL GROUP BY severity ORDER BY severity;

-- Q12 Who changed what (audit trail) for one order
SELECT created_at, actor, action, details FROM audit_logs
WHERE entity_type = 'order' ORDER BY created_at DESC LIMIT 20;

-- Q13 Query plan check: is the composite index used for branch + date filters?
EXPLAIN SELECT COUNT(*) FROM orders WHERE branch_id = 1 AND created_at >= now() - interval '7 days';
