# 01 · Master Project Handbook — TableFlow Enterprise

**Author:** Ria Rampersad

> Read this first. It explains the whole project in the order you would explain it to a technical interviewer.
> Every claim here is backed by code in this repository; where something is simulated or not verified, it says so.

---

## 1. What TableFlow Enterprise is

TableFlow Enterprise is a **restaurant integration and operations platform**. It sits between a restaurant
group's point-of-sale (Oracle MICROS Simphony), its delivery platforms (Uber Eats, Mr D), its card payment
switch (a Transaction Junction-style gateway), its loyalty platform and its back-office/finance systems. It:

- moves orders from delivery platforms into the POS automatically,
- takes payments idempotently and confirms them through signed webhooks,
- awards and redeems loyalty points without ever losing them,
- watches every integration call and raises incidents when something breaks,
- reconciles orders, payments, POS checks and acquirer settlements every day,
- alerts people and automates routine work through n8n,
- reports to management (dashboard, reports, Snowflake analytics),
- records an immutable audit trail.

The demo tenant is **Shisa Flame Chicken**, a *fictional* 12-branch South African chicken restaurant group
(Durban, Umhlanga, Pinetown, Pietermaritzburg, Ballito, Rosebank, Sandton, Soweto, Pretoria, Cape Town,
Gqeberha, Bloemfontein). All money is ZAR, VAT-inclusive at 15%, and the business day is in SAST.

**Honesty statement.** This is an independent portfolio project. Vendor integrations are **simulated**: the
adapters model each vendor's behaviour (payload shapes, response codes, failures, latency) but make no network
calls to Oracle, Transaction Junction, Uber or Mr D. Snowflake is implemented as SQL + an ELT script that runs
against a real Snowflake account *if credentials are supplied*; in this build it was run in its clearly-labelled
local DuckDB mode. Docker images and the GitHub Actions pipeline are written and the compose file is validated,
but no Docker daemon was available to build/run the images here (see the Verification Report).

## 2. Why it was created — the business problem

From the (fictional) stakeholder interviews in `requirements/01_…`:

| Pain | TableFlow answer |
|---|---|
| Delivery orders re-keyed into the POS | Partner APIs → canonical order → automatic Simphony check |
| Same order arriving twice | Idempotent ingest on (channel, external_ref) |
| Finance reconciles in Excel days later | Daily automated reconciliation with 9 discrepancy types |
| Integration failures discovered by phone | Per-call logs, health status, auto-incidents, n8n alerts |
| Loyalty points lost on timeouts | Local ledger first, failed syncs retried |
| No single view | Executive dashboard + reports + warehouse |
| No audit trail | Append-only audit log on every change |

## 3. Intended users (roles)

| Role (`roles.name`) | Demo login | Can do |
|---|---|---|
| `admin` (Ria Rampersad) | admin@tableflow.local | everything |
| `finance` | finance@tableflow.local | reconciliation, refunds, settlement import, finance journals, reports, audit |
| `operations` | ops@tableflow.local | orders, payments, incidents, automation tools, branch edits |
| `branch_manager` | manager.umhlanga@tableflow.local | own-branch orders/status/payments, loyalty redemption, incidents |
| `integration_engineer` | engineer@tableflow.local | integration config/outage simulation, retries, webhook replay & subscriptions, POS sync |
| machine client `n8n-automation` | OAuth2 client credentials | scopes `automation:run reports:read integrations:manage` |

Demo password for all users: `TableFlow!2026` (set by `SEED_DEMO_PASSWORD`; demo only).

## 4. Architecture in one paragraph

A **React + TypeScript** single-page app (served by **nginx**, which also reverse-proxies `/api`) talks to a
**FastAPI** service. FastAPI validates every request with **Pydantic**, authenticates with **JWT/OAuth 2.0**,
authorises with **RBAC**, and calls domain **services**. Services persist to **PostgreSQL** and reach vendors only
through the **IntegrationRunner**, which adds retries, logging, health tracking and automatic incidents around
simulated vendor **adapters**. Inbound vendor **webhooks** are signature-verified and de-duplicated. Business
events are written to an **outbox** table and pushed asynchronously to **n8n**, whose 8 workflows alert people,
retry work and run scheduled jobs by calling back into the API with a client-credentials token. A nightly
**ELT** script copies operational data to **Snowflake** (or DuckDB locally) where SQL builds a star schema and
reporting marts. Diagrams: `requirements/04_PROCESS_MAPS_AND_ARCHITECTURE.md`.

## 5. Repository map — every important file

```
tableflow-enterprise/
├── backend/
│   ├── app/
│   │   ├── main.py              app factory: middleware (correlation id, metrics, CORS), error envelope, routers
│   │   ├── config.py            all settings from env (Pydantic Settings)
│   │   ├── database.py          SQLAlchemy engine/session; SQLite FK pragma for tests
│   │   ├── migrate.py           Flyway-style SQL migration runner with checksums
│   │   ├── seed.py              realistic 60-day dataset with deliberate defects
│   │   ├── models/core.py       users, roles, api_clients, branches, products, customers, orders, order_items,
│   │   │                        payments, refunds, loyalty_accounts, loyalty_transactions
│   │   ├── models/ops.py        integrations, integration_logs, webhook_subscriptions, webhook_events,
│   │   │                        pos_transactions, settlement_records, inventory_items, incidents, incident_events,
│   │   │                        reconciliation_runs, reconciliation_records, notifications, audit_logs
│   │   ├── schemas/__init__.py  Pydantic request/response models + CanonicalOrder
│   │   ├── security/auth.py     bcrypt, JWT, OAuth2 dependencies, RBAC, partner API keys
│   │   ├── security/signatures.py  HMAC webhook sign/verify (+ replay window)
│   │   ├── security/keypair.py  RSA key-pair generation, DER export, fingerprint, sign/verify
│   │   ├── integrations/base.py IntegrationRunner (retry/backoff, logs, health, auto-incident), SimulatedAdapter
│   │   ├── integrations/micros_simphony.py | transaction_junction.py | ordering.py | loyalty.py | backoffice.py
│   │   ├── services/            orders, payments, loyalty, pos, reconciliation, incidents, reporting,
│   │   │                        automation, notifications (outbox), audit
│   │   ├── webhooks/processor.py verify → parse → de-dupe → handle → replay
│   │   ├── monitoring/          JSON logging, metrics, rate limiter
│   │   └── api/                 one router per module (+ simulate.py demo-only simulators)
│   └── tests/                   pytest: 102 tests (unit, API, integration, e2e, contract, regression)
├── frontend/src/
│   ├── services/api.ts          typed fetch client (token, X-Request-ID, error envelope, 401 handling)
│   ├── components/              Layout, DataTable, ui primitives (Card, Kpi, Badge, Modal, Field, ErrorBox…)
│   ├── pages/                   17 screens (incl. login) (Dashboard … AuditLog)
│   └── tests/                   Vitest + Testing Library (17 tests)
├── database/migrations/         V001 schema (generated from models), V002 triggers/views/partial indexes
├── database/sql/                13-query operational SQL library
├── database/seeds/              idempotent reference data
├── integrations/<vendor>/       contract notes + sample payloads per vendor
├── automation/n8n/              8 importable workflow JSON files
├── automation/local-runner/     Node runner that executes those workflows without n8n
├── snowflake/                   account setup, RAW tables, staging + marts SQL, analytical queries, ELT, sample data
├── postman/                     collection (87 requests) + Local/Docker environments
├── devops/docker/               backend/frontend Dockerfiles, entrypoint, nginx.conf
├── .github/workflows/ci.yml     CI/CD pipeline (copy in devops/github_actions/)
├── scripts/                     schema/workflow/Postman generators, signed-webhook sender, n8n run script
├── docker-compose.yml, .env.example, .gitignore, README.md
└── documentation/               this handbook set, requirements, runbooks, testing evidence
```

## 6. Every module

### Module 1 — Executive Dashboard (`pages/Dashboard.tsx`, `/api/v1/dashboard/*`)
KPI tiles (branches, orders, sales ZAR, successful/failed/pending payments, integration health, API volume,
failed webhooks, uptime), revenue trend stacked by channel, daily transaction outcomes, integration health list,
branch performance table. Filters: presets (Today/7d/30d/60d), date range, branch. Drill-down: KPI tiles link to
filtered screens; clicking a branch opens its detail page. Data: `services/reporting.py`.

### Module 2 — Branch Management (`Branches.tsx`, `BranchDetail.tsx`, `/api/v1/branches`)
List/filter by province; create (admin) with client- and server-side validation; PUT (replace) and PATCH (assign
Simphony location, payment provider, channels, active flag); per-branch performance, top products and
integration errors. Every change is audited.

### Module 3 — POS Integration Hub (`PosHub.tsx`, `/api/v1/pos/*`, `/orders/{id}/forward-to-pos`)
Simphony connectivity and latency, orders that failed to reach the POS with **Retry**, per-branch **menu sync**
(reports unmapped SKUs) and **transaction sync** (pulls closed checks into `pos_transactions`), live integration log.

### Module 4 — Digital Ordering (`DigitalOrders.tsx`, `/api/v1/partners/*`)
Uber Eats and Mr D inbound endpoints (API key, rate limit, 202), mapping to `CanonicalOrder`, validation,
background POS forwarding, provider status push, cancellations (API and webhook), duplicate prevention. The
**provider simulator** panel sends realistic payloads through the real pipeline, including a duplicate and a
corrupted total.

### Module 5 — Payment Hub (`Payments.tsx`, `/api/v1/payments`)
Idempotent initiation; deterministic test tokens; authorised → captured via signed webhook; failures with
ISO-8583-style reasons; partial/full refunds (finance); gateway references; failed-payment alerts.

### Module 6 — Loyalty (`Loyalty.tsx`, `/api/v1/loyalty/*`)
Members, tiers, balances, transaction history, redemption (platform-confirmed), failed-sync queue with retry.

### Module 7 — Integration Monitoring (`Integrations.tsx`, `/api/v1/integrations/*`)
Card per integration: status, mode, last success/failure, average latency, requests/failures, availability,
consecutive failures, last error; health check; **simulate outage** and **failure-rate** knobs; logs; failed-call
queue with retry of the underlying business operation.

### Module 8 — Webhook Management (`Webhooks.tsx`, `/api/v1/webhooks/*`)
Inbound endpoints for three providers; event history with signature validity, deliveries, status, error;
payload viewer; replay of failed events; outbound subscription registry; "forged webhook" security demo.

### Module 9 — Internal Automation Tools (`Automation.tsx`, `/api/v1/automation/*`)
Daily sales summary, payment reconciliation, discrepancy scan (optionally raises an incident), integration health
check (raises incidents for down integrations), low-stock report, finance GL journal posting; notification
outbox; n8n workflow catalogue.

### Module 10 — Incident Management (`Incidents.tsx`, `IncidentDetail.tsx`, `/api/v1/incidents/*`)
Create, severity, assignment, status workflow, root cause, resolution notes, timeline, escalation levels,
MTTR report. Six realistic seeded incidents (gateway timeouts, unmapped menu items, duplicate Uber orders,
webhook secret rotation, loyalty timeouts, settlement variance).

### Module 11 — Financial Reconciliation (`Reconciliation.tsx`, `/api/v1/reconciliation/*`)
Run per day/branch, nine issue types, value at risk, CSV export, resolve records, settlement CSV import.
Matching logic: section 9 below and `05_DATABASE_AND_SQL_HANDBOOK.md`.

### Module 12 — Reporting & Analytics (`Reports.tsx`, `/api/v1/reports/*`, `/snowflake`)
Nine reports (JSON/CSV) with charts; Snowflake star schema and analytical queries.

## 7. Every technology (where it lives)

| Technology | Where | Detail in |
|---|---|---|
| Python 3.12+ / FastAPI / Pydantic | `backend/app` | Doc 02 |
| SQLAlchemy 2 | models, services | Doc 03 |
| PostgreSQL 16 + SQL | migrations, views, triggers, SQL library | Doc 05 |
| React 18 / TypeScript / Vite / Recharts | `frontend/` | Doc 02, 03 |
| REST, webhooks, OAuth 2.0, JWT, API keys, HMAC, RSA key-pair | `security/`, `api/` | Docs 02, 04 |
| n8n | `automation/n8n` | Doc 04 §n8n |
| Snowflake (+ DuckDB demo) | `snowflake/` | Doc 05 |
| Docker / Compose / nginx | `devops/docker`, `docker-compose.yml` | Doc 07 |
| Git / GitHub Actions | `.github/workflows/ci.yml` | Doc 07 |
| Pytest / Vitest / Postman-Newman / Playwright (screenshots) | tests, `postman/` | Doc 06 |
| AI tooling (Copilot, Cursor) | development process | Doc 11 |

## 8. Every integration

| Integration (`integrations.name`) | Adapter | Direction | Operations |
|---|---|---|---|
| `micros_simphony` | `MicrosSimphonyAdapter` | out | create_check, update_check_status, get_menu, get_closed_checks, ping |
| `transaction_junction` | `TransactionJunctionAdapter` | out + webhooks in | authorise, refund; `payment.captured/failed`, `refund.completed` |
| `uber_eats` | `UberEatsAdapter` | in + status push | to_canonical, push_status; `orders.cancel` webhook |
| `mr_d` | `MrDAdapter` | in + status push | to_canonical, push_status; `ORDER_CANCELLED` webhook |
| `loyalty_platform` | `LoyaltyAdapter` | out | post_transaction (earn/redeem) |
| `finance_gl` | `FinanceSystemAdapter` | out | post_journal (must balance) |
| `backoffice_inventory` | `BackOfficeAdapter` | out | get_stock_levels |

## 9. Every database table (why it exists)

| Table | Why it exists |
|---|---|
| `roles`, `users` | Staff identities and RBAC roles; bcrypt hashes |
| `api_clients` | Machine clients for OAuth2 client credentials (n8n) with scopes |
| `branches` | Restaurants; POS location ref, payment provider, enabled channels |
| `products` | Menu/catalogue with Simphony item numbers (`pos_item_ref`) |
| `customers` | Phone-identified customers (E.164) |
| `orders`, `order_items` | Canonical orders from every channel; VAT split; UNIQUE (channel, external_ref) |
| `payments`, `refunds` | Gateway transactions, idempotency key, refunds |
| `loyalty_accounts`, `loyalty_transactions` | Points ledger, sync status for the external platform |
| `integrations`, `integration_logs` | Health state per integration; one row per call attempt |
| `webhook_subscriptions`, `webhook_events` | Outbound targets; inbound events with signature validity & status |
| `pos_transactions` | Closed checks pulled from Simphony (reconciliation source C) |
| `settlement_records` | Acquirer settlement lines (reconciliation source D) |
| `inventory_items` | Stock levels for low-stock automation |
| `incidents`, `incident_events` | Incidents and their timeline |
| `reconciliation_runs`, `reconciliation_records` | Each run and each discrepancy |
| `notifications` | Outbox of events for n8n and alerts delivered back |
| `audit_logs` | Append-only change history |
| `schema_migrations` | Applied migrations + checksums |

Reconciliation in brief (per non-cancelled order of the SAST business day): no payment → `missing_payment`; only
failed → `failed_payment`; >1 captured → `duplicate_payment`; captured ≠ total → `amount_mismatch`; POS check
missing → `missing_pos_record`; POS total ≠ order → `pos_amount_mismatch`; captured not on settlement →
`missing_settlement`; settled ≠ captured → `settlement_mismatch`; settlement with no payment → `unknown_settlement`.

## 10. Every API endpoint
84 operations on 72 paths. The full generated catalogue with auth per endpoint is in
`requirements/05_API_SPECIFICATION.md`; the live, try-it-out version is Swagger UI at `/docs`.

## 11. Every workflow (n8n)

| # | File | Trigger | Does |
|---|---|---|---|
| 01 | `01_failed_payment_notifications.json` | webhook `tableflow-failed-payment` | format alert → if ≥ R500 alert finance + raise SEV3 incident, else alert ops |
| 02 | `02_failed_pos_integration.json` | webhook `tableflow-pos-failure` | token → GET /pos/status → if ≥ 3 stuck orders raise SEV2 incident → alert ops |
| 03 | `03_new_order_processing.json` | webhook `tableflow-new-order` | alert branch on large (≥ R1000) delivery orders |
| 04 | `04_loyalty_point_updates.json` | webhook `tableflow-loyalty-update` | on sync failure: list failed txns → retry each → summary alert |
| 05 | `05_daily_financial_reconciliation.json` | cron 06:00 SAST | run reconciliation → if discrepancies fetch detail → finance summary |
| 06 | `06_low_stock_notifications.json` | cron every 3 h 09–20 | low-stock → group by branch → procurement alerts |
| 07 | `07_incident_escalation.json` | webhook `tableflow-incident-escalation` | page on-call for SEV1, post to incidents channel, wait 30 min, auto-escalate if still open |
| 08 | `08_daily_management_reporting.json` | cron Mon–Sat 07:00 | daily summary + open incidents → management digest |

## 12. How the components communicate

| From → To | Mechanism | Auth |
|---|---|---|
| Browser → nginx → FastAPI | HTTPS/HTTP JSON (`/api/v1`) | Bearer JWT |
| Uber Eats / Mr D → FastAPI | REST POST | `X-API-Key` |
| Gateway / providers → FastAPI | Webhook POST | HMAC signature |
| FastAPI → vendors | adapter calls via IntegrationRunner (simulated transport) | (sandbox: OAuth2 / mTLS per vendor) |
| FastAPI → n8n | async HTTP POST from outbox | network-internal; optional shared secret |
| n8n → FastAPI | REST | OAuth2 client-credentials JWT |
| n8n → alert channel | HTTP POST (Slack-compatible JSON) | `X-Alert-Token` / Slack URL |
| FastAPI → PostgreSQL | SQLAlchemy/psycopg3 | DB user from env |
| ELT → Snowflake | snowflake-connector PUT/COPY | RSA key-pair |

## 13. How to run it

**Option A — Docker (intended path)**
```bash
cp .env.example .env            # edit the CHANGE values
docker compose up --build -d    # postgres, backend (migrates + seeds), frontend, n8n
docker compose --profile setup run --rm n8n-import   # import the 8 workflows into n8n
open http://localhost:8080      # UI    | API docs http://localhost:8000/docs | n8n http://localhost:5678
```

**Option B — local processes (what was verified in this build)**
```bash
# PostgreSQL 16 running locally with database "tableflow"
cd backend && pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://tableflow:tableflow@localhost:5432/tableflow
python -m app.migrate && python -m app.seed --days 60
uvicorn app.main:app --reload --port 8000
cd ../frontend && npm install && npm run dev      # http://localhost:5173 (proxies /api to :8000)
```
Quick demo without Postgres: `DATABASE_URL=sqlite:///./demo.db python -m app.seed --create-schema` then run uvicorn with the same URL (reporting views/triggers are Postgres-only).

## 14. How to test it
```bash
cd backend && pytest                                  # 99 pass + 3 Postgres-only skipped (SQLite)
TEST_DATABASE_URL=postgresql+psycopg://…/tableflow_test pytest   # 102 pass on PostgreSQL via migrations
pytest -m regression                                  # 18 regression tests
cd frontend && npm run lint && npm run typecheck && npm test    # 17 tests
npx newman run postman/TableFlow_Enterprise.postman_collection.json -e postman/TableFlow_Local.postman_environment.json
bash scripts/run_n8n_workflows_locally.sh             # executes all 8 workflows against the API
python snowflake/etl/extract_load.py --full           # ELT (local DuckDB mode without Snowflake creds)
```
Results and evidence: `testing/TEST_REPORT.md` and `testing/evidence/`.

## 15. How to troubleshoot it
1. Get the **correlation id** (`X-Request-ID` response header, or "Reference" in the UI error box).
2. Search the JSON logs for it (`docker compose logs backend | grep <id>`), then `integration_logs.correlation_id` and `audit_logs.correlation_id`.
3. Check `/health/ready` (DB + integrations) and `/metrics` (error rate, p95).
4. Integration Monitoring screen → failed calls → open the log entry (request/response/error).
5. Follow the matching runbook in `runbooks/RUNBOOKS.md`.

| Symptom | Likely cause | Fix |
|---|---|---|
| UI shows "Not authenticated" | token expired (60 min) | sign in again |
| Orders stuck `failed` | Simphony outage / unmapped menu item | RB-01; menu sync; retry |
| Many `rejected` webhooks | secret rotated | RB-04 |
| Payments `authorised` not `captured` | capture webhook missing | discrepancy scan; simulate callback / replay |
| `/health/ready` 503 | database unreachable | RB-05 |
| n8n workflow errors on `$env` | `N8N_BLOCK_ENV_ACCESS_IN_NODE` true | set false (compose does) |

## 16. How to deploy it
CI (`.github/workflows/ci.yml`) runs lint → tests on SQLite and PostgreSQL → frontend lint/typecheck/test/build →
Newman + n8n runner against a live API → Docker build + compose smoke test (health, UI, login). The `deploy`
job is a gated placeholder because no hosting target exists. Production steps (registry, staging, migrations,
secrets, TLS, rollback) are in `07_DEVOPS_AND_DEPLOYMENT_HANDBOOK.md`. **Nothing has been deployed to production.**

## 17. The ten-minute interview story
1. Problem: fragmented restaurant systems → re-keying, late reconciliation, silent failures.
2. Requirements from Finance, Ops, branches, IT → rules like idempotency and 3-failure incidents.
3. Architecture: modular FastAPI monolith, canonical model, adapters, one integration choke-point, outbox, n8n.
4. Demo: Uber order → POS → payment → signed webhook → loyalty → reconciliation.
5. Failure demo: simulate Simphony outage → retries → failed order → incident → n8n alert → recover → retry.
6. Quality: 102 backend tests on real Postgres, 17 frontend tests, 87 Postman requests, 8 workflows executed.
7. Honest limits: simulated vendors, no production deployment, Docker not run in the build environment.
