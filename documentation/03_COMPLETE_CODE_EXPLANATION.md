# 03 · Complete Code Explanation

Organised by folder and file. For key functions: **does · why · receives · returns · interacts with · on failure**.

---

## backend/app/main.py — application factory
- `create_app()` builds the FastAPI app, adds CORS, the `request_context` middleware, four exception handlers and
  mounts 15 routers under `/api/v1` (health at root).
- `request_context` middleware: reads or creates `X-Request-ID`, stores it in a `ContextVar` so every log line,
  integration log and audit row carries it; times the request; records metrics with the *route template*
  (`/api/v1/orders/{order_id}`, not the concrete id — keeps metric cardinality low); logs one JSON line per request.
- Exception handlers: `BusinessRuleError` → its status + code; `RequestValidationError` → 422 `VALIDATION_ERROR` with
  `details[].loc/msg`; `HTTPException` → `HTTP_<status>` (preserves headers such as `Retry-After`); any other
  exception → 500 `INTERNAL_ERROR` with correlation id and the stack trace logged, never returned.
- `lifespan`: configures logging; optionally `create_all` (tests/demo); starts `dispatcher_loop` if `N8N_WEBHOOK_BASE_URL` is set.

## backend/app/config.py
`Settings(BaseSettings)` — every tunable comes from env/.env with a type. Properties `partner_keys` (parses
`provider:key,…`) and `cors_origin_list`. `get_settings()` is cached. **Failure**: a wrong type (e.g.
`RETRY_MAX_ATTEMPTS=abc`) fails at start-up, not mid-request.

## backend/app/database.py
`Base` (declarative), `_make_engine(url)` (pool_pre_ping; SQLite: `check_same_thread=False`, `StaticPool` for
`sqlite://`, and `PRAGMA foreign_keys=ON` so SQLite enforces FKs like Postgres), `SessionLocal`,
`configure_engine()`, `get_db()` (yields a session, always closes it).

## backend/app/models/
- `core.py` / `ops.py` — SQLAlchemy 2 typed models. `JSONType = JSON().with_variant(JSONB(), "postgresql")` gives
  JSONB in Postgres and JSON in SQLite. `Money = Numeric(12, 2)`. Table-level `CheckConstraint`s encode allowed
  statuses/channels; `UniqueConstraint`s encode idempotency (`uq_order_channel_external_ref`,
  `uq_webhook_source_event`, `uq_loyalty_once_per_order`, `uq_settlement_provider_ref`, `uq_pos_branch_check`).
  `Index`es support dashboard filters (`ix_orders_branch_created`, `ix_payments_status_created`, …).
- Relationships: `Order.items` (cascade delete-orphan), `Order.payments`, `Payment.refunds`, `Incident.events`
  (ordered), `ReconciliationRun.records`.

## backend/app/schemas/__init__.py
Pydantic contracts. Notable: `CanonicalOrder` (the internal order every channel maps into), `OrderStatusUpdate`
(reason required for cancel), `PaymentCreate` (Decimal amount, ZAR only, card token), `IncidentUpdate` (notes
required to resolve/close), `IntegrationConfigUpdate` (failure_rate 0–1), `UserCreate` (password must contain
letters and digits; email pattern rather than `EmailStr` — see Doc 10 bug #3).

## backend/app/security/
### auth.py
| Function | Does | Receives → Returns | On failure |
|---|---|---|---|
| `hash_password` / `verify_password` | bcrypt hash/check (cost 12) | plain → hash / bool | malformed hash → False |
| `create_access_token` | sign JWT | subject, roles, type, extra → str | — |
| `decode_token` | verify signature, expiry, issuer | token → claims | 401 "Token expired"/"Invalid token" |
| `get_current_principal` | dependency: token → `Principal` (user from DB, or client scopes → roles) | request, token, db → Principal | 401 if missing/inactive |
| `require_roles(*roles)` | dependency factory for RBAC | → checker | 403 listing required roles |
| `require_partner_key(provider)` | constant-time API key check | `X-API-Key` → provider | 401 |
### signatures.py
`sign(source, body)` produces the provider header (used by simulators, scripts, tests); `verify(source, body,
headers)` recomputes HMAC-SHA256 and compares with `hmac.compare_digest`; TJ variant parses `t=…,v1=…` and
enforces the 300 s window. Raises `SignatureError` with a precise reason.
### keypair.py
`generate_keypair`, `load_private_key`, `private_key_der` (for Snowflake), `public_key_fingerprint`,
`sign_challenge`/`verify_challenge`; runnable as a CLI that prints the `ALTER USER … RSA_PUBLIC_KEY` statement.

## backend/app/integrations/
### base.py — the most important integration file
- `AdapterError(message, http_status, retryable, payload)` — the only exception adapters raise.
- `SimulatedAdapter._simulate_transport()` — reads `integration.config`: `simulate_outage` → 503 retryable;
  `failure_rate` → random 504; returns simulated latency. `ping()` for health checks.
- `IntegrationRunner.call(integration, operation, fn, request_payload, entity_type, entity_id, branch_id, max_attempts)`
  - **does**: run `fn` up to N times; exponential back-off (`base × 2^(attempt-1)`); write one `integration_logs`
    row per attempt (`success`, `retried_ok`, `retrying`, `failed`); update health; return `CallResult`.
  - **why**: one place for retries/logging/health so every adapter behaves identically.
  - **on failure**: permanent errors (`retryable=False`, e.g. card declined) stop immediately and do *not*
    degrade health; retryable errors increment `consecutive_failures`; at the threshold (3) status becomes
    `down` and `auto_raise_integration_incident` is called exactly once.
### micros_simphony.py / transaction_junction.py / ordering.py / loyalty.py / backoffice.py
Vendor adapters (Doc 04). `ordering.py` also holds the status vocabularies (`UBER_STATUS`, `MRD_STATUS`) and
`ORDERING_ADAPTERS` registry used by the partner endpoints.

## backend/app/services/
### orders.py
| Function | Does | Notes |
|---|---|---|
| `ingest(db, CanonicalOrder, actor)` → `(Order, duplicate)` | de-dupe, validate branch/channel/SKUs/total, upsert customer, VAT split, insert in a **savepoint**, audit, outbox `new_order` | race-safe: `IntegrityError` → return the winner |
| `forward_to_pos(db, order)` → bool | create Simphony check via runner; success → `accepted` + provider status push; failure → `failed` + `pos_failure` alert | idempotent: returns True if already has a check |
| `change_status(db, order, new, actor, reason)` | transition map, refund-before-cancel rule, push to POS + provider, audit | 409 on invalid transition |
| `cancel_by_provider` | find by (channel, external_ref) and cancel | 404 if unknown |
| `outstanding_amount(order)` | total − (authorised/captured − refunded) | used by payments |
| `normalise_phone`, `vat_split`, `to_out`, `load_order` | helpers | |
### payments.py
`create_payment` (idempotency check/conflict → validations → `initiated` row → authorise via runner →
`authorised`/`failed` + alert → audit); `build_gateway_webhook` (what the simulated gateway posts back, signed);
`refund_payment` (eligibility, balance, gateway call, status update, audit; failure → 502 and the failed refund row is kept).
### loyalty.py
`earn_for_order` (once per order, local ledger first, then `_push` to platform), `redeem` (balance check, platform
must confirm, else 502 and no deduction), `retry_sync`, `tier_for`.
### reconciliation.py
`day_bounds(date)` (SAST day → UTC range); `run(db, date, branch_id, actor)` implements the 9-rule matching
(see Doc 05), stores run + records, audits, raises an incident above R500.
### pos.py
`menu_sync` (fetch Simphony menu, report unmapped SKUs), `transaction_sync` (pull closed checks for the day,
upsert `pos_transactions`, skip existing).
### incidents.py
`create_incident` (reference `INC-00001` from the id, created event, audit, notify for SEV1/2),
`auto_raise_integration_incident` (one open incident per integration), `update_incident` (transition map,
assignment, severity, RCA fields, audit), `escalate` (levels, notify n8n).
### reporting.py
Dialect-aware date bucketing (`to_char(timezone('Africa/Johannesburg', col))` in Postgres, `strftime(…,'+2 hours')`
in SQLite) and all dashboard/report queries using SQLAlchemy Core expressions with `CASE` aggregations.
### automation.py
`daily_summary`, `discrepancy_scan`, `integration_health_check`, `low_stock`, `post_finance_journal` (balanced
Dr card clearing / Cr sales / Cr VAT output).
### notifications.py
`notify()` inserts an outbox row (`pending` if n8n configured, else `recorded`); `dispatch_pending()` posts with
`httpx.AsyncClient` and marks `sent`/`failed`; `dispatcher_loop()` runs every 10 s and never dies on errors.
### audit.py
`record(db, actor, action, entity_type, entity_id, details, ip)` adds the correlation id automatically.

## backend/app/webhooks/processor.py
`handle(db, source, body, headers)` → `(WebhookEvent, http_status)`: verify → parse (`_identify` per provider) →
rejected (401/400) | duplicate (200, attempts+1) | new event → `_run_handler`. `HANDLERS` maps
`(source, event_type)` → function. `_run_handler` executes inside `db.begin_nested()` so a failed handler rolls
back only its own changes; sets `processed`/`failed` with error. `replay()` re-runs failed events only.

## backend/app/monitoring/
`logging.py` (JsonFormatter, `log()` helper with structured fields, correlation id), `metrics.py` (thread-safe
counters, latency deque, p50/p95/p99, uptime), `ratelimit.py` (sliding window + FastAPI dependency factory).

## backend/app/api/ — routers
`auth.py`, `branches.py`, `orders.py` (internal + `partners` router + `_forward_in_background`), `payments.py`
(+ `_simulate_gateway_callback` background task), `loyalty.py`, `integrations.py` (+ `pos_router`, log retry
dispatcher), `webhooks.py`, `incidents.py`, `reconciliation.py` (CSV export/import), `reports.py` (dashboard +
`REPORTS` registry with CSV output), `automation.py` (+ `admin` router: notifications, audit logs, alert sink),
`health.py`, `simulate.py` (demo-only; 404 when `ENVIRONMENT=production`), `deps.py` (paging, client IP, get_or_404).
Pattern in every mutating endpoint: dependency auth → service call → `db.commit()` → response model.

## backend/app/migrate.py & seed.py
`migrate()` creates `schema_migrations`, applies `V###__*.sql` in order inside a transaction each, records
SHA-256 checksums and refuses to run if an applied file changed. `seed()` builds reference data via ORM and
~10k orders/payments/logs via Core bulk `insert()` with explicit ids, then realigns Postgres sequences.

## backend/tests/
`conftest.py` (env setup before import, SQLite or Postgres+migrations, seed 5 days, per-test integration reset,
token per role, payload factories), and 9 test modules — see Doc 06.

---

## frontend/src
- `main.tsx` mounts `<App/>` inside `BrowserRouter`. `App.tsx` lazy-loads pages and guards routes with `RequireAuth`.
- `services/api.ts` — `request()` adds token and request id, encodes JSON/form/multipart, throws `ApiError(status,
  message, code, details, correlationId)`, clears session + emits `tableflow:logout` on 401; `login()` performs the
  OAuth2 password flow then `GET /auth/me`; `api.download()` saves CSV exports.
- `hooks/useApi.ts` — `useApi(loader, deps)` (loading/error/reload, ignores stale responses), `useAction()` (busy/error for mutations).
- `components/DataTable.tsx` — generic typed table: column renderers, click-to-sort, row click drill-down, server pagination, empty state.
- `components/ui.tsx` — Card, Kpi (clickable for drill-down), Badge (status→tone map), Button (busy spinner), ErrorBox (shows validation details and correlation reference), Modal (Esc to close), Field, JsonView, Toast, PageHeader, SimulatedTag.
- `components/Layout.tsx` — sidebar navigation (role-filtered), top bar with user and sign-out, responsive drawer on mobile.
- `pages/*` — one per module; each uses `useApi` for data, `useAction` for mutations, shows `Spinner`/`ErrorBox`/`Empty`, and validates forms before calling the API (e.g. `validateBranch`, refund amount bounds, incident title length).
- `utils/format.ts` — en-ZA currency/number/date formatting in `Africa/Johannesburg`.

## automation/local-runner/n8n-local-runner.mjs
Loads a workflow JSON, starts at the trigger, executes nodes breadth-first following `connections`, evaluates
`={{ }}` expressions with `$json/$env/$('Node')`, runs Code nodes as async functions, implements IF v2 operators,
skips Wait (noted), honours `onError: continueRegularOutput`, prints a trace, exits non-zero on failure.

## snowflake/etl/extract_load.py
`extract(full)` (watermarks in `.watermarks.json`; full → `sample_data/`, incremental → timestamped folder),
`snowflake_configured()`, `load_snowflake()` (key-pair connect, PUT/COPY, run transformations),
`load_local()` (DuckDB, same SQL, prints analytical query results).

## scripts/
`generate_schema_sql.py` (V001 from models), `build_n8n_workflows.py` (8 workflows), `build_postman.py`
(collection + environments), `send_signed_webhook.py` (sign & post, `--tamper`), `run_n8n_workflows_locally.sh`.

## Code walkthrough to rehearse: "what happens when Uber Eats retries an order?"
1. `orders.uber_eats_order` → `require_partner_key("uber_eats")` + `partner_limit`.
2. `_ingest_partner` → `UberEatsAdapter.to_canonical(payload)`.
3. `svc.ingest` → `select(Order).where(channel, external_ref)` finds the existing row → returns `(order, True)`.
4. No background task is scheduled; response `{"duplicate": true, "order_number": …}` with 202.
5. If two identical requests race, both pass step 3, one INSERT wins, the other hits `uq_order_channel_external_ref`
   inside the savepoint → `IntegrityError` → re-select → `duplicate=True`.
