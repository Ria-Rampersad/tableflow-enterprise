# 06 · Technical Solution Design

## 1. Design goals
1. **Never lose a business event** (order, payment, point) because a vendor is down.
2. **Never double-process** an event because a vendor retried.
3. **See every integration call** (who, what, how long, result) and be able to retry it.
4. **Keep vendor specifics at the edge** so a new provider is one adapter, not a rewrite.
5. **Small and operable** by one Solutions Engineer: one API service, one database, n8n for glue.

## 2. Key decisions (ADR summary)

| # | Decision | Alternatives considered | Why |
|---|---|---|---|
| ADR-01 | Modular monolith (one FastAPI service, modules by domain) | Microservices | One engineer, low volume; modules can be split later along the same boundaries |
| ADR-02 | Canonical order model + adapter per provider | Provider-specific tables | Business rules written once; adding a provider = one mapping class |
| ADR-03 | `IntegrationRunner` as the only path to vendors | Retries inside each adapter | Uniform retries, logging, health, incident creation; adapters stay simple |
| ADR-04 | Idempotency enforced in the database (UNIQUE) and in code | Code-only checks | Code checks lose races under concurrency; the constraint is the final guard |
| ADR-05 | Transactional outbox for n8n notifications | Call n8n inline | Inline calls block requests and fail when n8n is down |
| ADR-06 | Partner orders acknowledged 202, POS forwarding in background | Synchronous forwarding | Providers time out if we hold the request while Simphony is slow |
| ADR-07 | HMAC-SHA256 webhook signatures + timestamp tolerance | IP allow-listing only | IPs change; signatures prove origin and integrity; timestamps stop replays |
| ADR-08 | JWT access tokens (HS256, 60 min) + RBAC roles | Server sessions | Stateless API, works for SPA and machine clients alike |
| ADR-09 | OAuth 2.0 client-credentials for n8n | Shared admin user | Least privilege via scopes; revocable per client |
| ADR-10 | Raw SQL migrations (Flyway-style runner) generated from ORM then hand-extended | Alembic | Reviewable SQL for DBAs; triggers/views are first-class; drift caught by a test |
| ADR-11 | PostgreSQL for operations, Snowflake for analytics (ELT) | Reports on Postgres only | Heavy analytics must not compete with order processing |
| ADR-12 | Simulated vendors with failure knobs (`simulate_outage`, `failure_rate`, `latency_ms`) | Mock only in tests | The *running* system can demonstrate outages, retries and incidents |
| ADR-13 | Money as `NUMERIC(12,2)` / Python `Decimal`, JSON strings | float | Floats cannot represent cents exactly |
| ADR-14 | Business day computed in SAST | UTC days | Restaurants trade until 22:00 SAST; UTC days would split trading days |

## 3. Module design
| Module | API router | Service | Key tables |
|---|---|---|---|
| Executive dashboard | `api/reports.py` | `services/reporting.py` | orders, payments, integrations, webhook_events |
| Branches | `api/branches.py` | (router + reporting) | branches |
| POS hub | `api/integrations.py` (`pos_router`) | `services/pos.py`, `services/orders.py` | pos_transactions, integration_logs |
| Digital ordering | `api/orders.py` (`partners`) | `services/orders.py` + `integrations/ordering.py` | orders, order_items, customers |
| Payments | `api/payments.py` | `services/payments.py` | payments, refunds |
| Loyalty | `api/loyalty.py` | `services/loyalty.py` | loyalty_accounts, loyalty_transactions |
| Integration monitoring | `api/integrations.py` | `integrations/base.py` | integrations, integration_logs |
| Webhooks | `api/webhooks.py` | `webhooks/processor.py` | webhook_events, webhook_subscriptions |
| Automation | `api/automation.py` | `services/automation.py` | notifications, inventory_items |
| Incidents | `api/incidents.py` | `services/incidents.py` | incidents, incident_events |
| Reconciliation | `api/reconciliation.py` | `services/reconciliation.py` | reconciliation_runs/records, settlement_records |
| Reports | `api/reports.py` | `services/reporting.py` | (views) |

## 4. Security design
- **Authentication**: bcrypt (cost 12) password hashes; JWT with `sub`, `roles`, `typ`, `iat`, `exp`, `iss`.
- **Authorisation**: `require_roles(...)` dependency per endpoint; `admin` passes everything; client scopes map to roles (`automation:run`→operations, `reports:read`→finance, `integrations:manage`→integration_engineer); branch managers are scoped to their branch in order listings.
- **Partner auth**: per-provider API keys from env, constant-time comparison.
- **Webhooks**: HMAC over raw body; timestamp tolerance 300 s; invalid events stored as `rejected`.
- **Secrets**: only in environment variables / `.env` (git-ignored); webhook subscription stores the *name* of the secret env var, never the secret.
- **Input validation**: Pydantic schemas (types, ranges, regex for codes/phones/emails), plus business-rule validation.
- **Data minimisation**: card tokens only, masked in logs.
- **Audit**: every mutation writes `audit_logs` (actor, action, entity, details, IP, correlation id); DB trigger makes it append-only.
- **Transport/edge**: nginx security headers (CSP, X-Frame-Options, nosniff). TLS terminates at the hosting edge (not configured here).
- **Rate limiting**: sliding window per API key / IP.
- **Key-pair**: RSA 2048 key generation, DER export for the Snowflake connector, fingerprint, sign/verify.

Known limitations (honest): rate limiter and metrics are in-process (need Redis/Prometheus for multiple replicas);
no refresh tokens; JWT in `sessionStorage` (an httpOnly cookie is safer against XSS); no MFA.

## 5. Failure handling matrix
| Failure | Detection | Behaviour | Recovery |
|---|---|---|---|
| POS timeout/5xx | AdapterError retryable | 3 attempts, order `failed`, alert, health degraded→down, incident at 3 | Retry button / `forward-to-pos` / log retry |
| Card declined | Response 05/51/54 | Payment `failed`, no retry, alert | Customer uses another card |
| Gateway down | 91 / 503 | Retried, then failed; SEV1 incident | Ops follows runbook RB-02 |
| Duplicate provider order | UNIQUE + lookup | Return original (`duplicate=true`) | none needed |
| Forged/stale webhook | HMAC/timestamp | 401, stored `rejected` | Investigate source; rotate secret |
| Webhook for unknown payment | Handler error | `failed`, 200 ack | Fix data, replay |
| Loyalty platform down | AdapterError | Earn kept `failed`; redeem refused (502) | Retry (UI or n8n workflow 04) |
| n8n down | HTTP error in dispatcher | Outbox row `failed` | Re-dispatch; alerts not lost |
| DB down | `/health/ready` 503 | API errors 500 with correlation id | Runbook RB-05 |
