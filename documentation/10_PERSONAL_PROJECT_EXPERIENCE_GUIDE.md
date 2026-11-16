# 10 · Personal Project Experience & Technical Decision Guide

Use this to describe your contribution **accurately**. TableFlow is an independent portfolio project. Do not
describe it as employment, team work, production traffic or a live vendor integration.

## Honest framing (use these sentences)
- "I designed and developed this as an independent end-to-end portfolio project."
- "The POS, payment, delivery and loyalty integrations are simulated adapters that model the vendors' behaviour; I don't have vendor sandbox access, so I designed them so the transport can be swapped without changing the business logic."
- "The data is generated — a fictional 12-branch chicken restaurant group — but it's realistic: ZAR, VAT, SAST trading days and deliberate defects for reconciliation to find."
- "I tested the backend against a real PostgreSQL database; the Snowflake model ran on DuckDB locally because I don't have a Snowflake account; the Docker setup is written and validated but I'd want to run it end to end before calling it done."
- "I used AI coding assistants and reviewed, tested and corrected their output."

Avoid: "deployed to production", "integrated with Transaction Junction", "processed real payments", "led a team", "reduced reconciliation time by X%" (no real users measured it).

## Project objectives
Eliminate re-keying; idempotent order and payment handling; visible integration health; automated daily
reconciliation; alerting/automation via n8n; management reporting; complete audit trail; documented, testable, deployable.

## Architecture decisions (and how to defend them)
| Decision | Why | What I'd change at scale |
|---|---|---|
| Modular monolith | one engineer, low volume, simpler ops | split payments/ordering into services if teams or load grow |
| Canonical order + adapters | rules written once; new provider = one class | contract tests per provider sandbox |
| IntegrationRunner choke-point | uniform retries/logs/health/incidents | add jitter, circuit-breaker half-open state, per-vendor timeouts |
| Outbox → n8n | requests never blocked by alerting | message broker if many consumers |
| UNIQUE constraints for idempotency | only reliable guard under concurrency | — |
| SQL migrations + drift test | DBA-readable, triggers/views first-class | Alembic autogenerate could also work |
| JWT + RBAC, client credentials for n8n | stateless, least privilege | IdP with PKCE, refresh tokens, MFA |
| Postgres OLTP + Snowflake ELT | analytics never slows trading | dbt for transformations and tests |

## Features implemented
12 modules (Master Handbook §6), 84 API operations, 16 UI screens, 7 simulated integrations, webhook pipeline for 3
providers, 9 reconciliation rules, 9 reports, 8 n8n workflows + local runner, Snowflake setup/model/queries/ELT,
Postman collection, Docker/Compose/nginx, CI pipeline, 10 handbooks, requirements set, runbooks, UAT pack.

## Technical challenges encountered
1. **Idempotency under concurrency** — a lookup-then-insert races; solved with a UNIQUE constraint and a savepoint that catches the violation and returns the winner.
2. **Webhook signature verification** — must use raw bytes; added timestamp tolerance for replay protection and stored rejected events for forensics.
3. **Business day vs UTC** — trading days are SAST; built `day_bounds()` and dialect-aware date bucketing so reports and reconciliation agree on what "yesterday" means.
4. **Testing the same code on SQLite and Postgres** — JSON vs JSONB variant, FK pragma for SQLite, Postgres-only tests for triggers/views.
5. **Making simulated integrations useful** — failure knobs on each integration row so outages and retries can be demonstrated live.
6. **Testing n8n without n8n** — contract tests plus a small interpreter for the node subset used.

## Bugs identified and fixed during the build (real, from the build log)
| # | Bug | How found | Fix | Guard |
|---|---|---|---|---|
| 1 | Migration runner failed on V002: psycopg treated `%` in a PL/pgSQL `RAISE` as a placeholder | first Postgres migration run | execute migration files via raw DBAPI cursor with no parameters | every Postgres test run applies migrations |
| 2 | Seed produced a negative "short payment" (−R15.00) on cheap orders | Postgres CHECK `ck_payment_amount_positive` rejected the insert | only inject mismatches on orders > R60 | constraint stays |
| 3 | Admin couldn't create users with `@tableflow.local` emails | API test `test_admin_creates_user_with_password_policy` (422) | `EmailStr` rejects reserved domains → pattern validation | test |
| 4 | Contract test found no routes | newer FastAPI nests included routers, so `app.routes` isn't flat | read routes from the OpenAPI spec | test itself |
| 5 | Postman requests after login returned 401 | Newman run | empty `token` in the environment overrode the collection variable; removed it | Newman in CI |
| 6 | ELT analytical query runner crashed | first ELT run | header comment contained the `-- name:` marker; anchored the split to line starts | ELT evidence log |
| 7 | Incremental ELT overwrote sample CSVs with empty files | second ELT run | incremental extracts go to a timestamped folder | — |
| 8 | UI simulator returned 404 | Playwright UI pass | API process predated the new router; restarted — added note to always restart after adding routers | Playwright pass, zero console errors |
| 9 | Long codes/JSON wrapped badly in tables | screenshot review | nowrap for codes/amounts, wrapping for JSON | visual |

## Testing performed
102 backend tests on PostgreSQL (99 + 3 skipped on SQLite), 92% coverage, 18 regression tests, 17 frontend tests,
87 Postman requests / 91 assertions via Newman, 8 n8n workflows executed against the live API, ELT full +
incremental runs, 13 SQL library queries executed, 19 UI screens loaded in headless Chrome with no console errors.

## Design trade-offs
- In-process rate limiting/metrics (simple) vs Redis/Prometheus (multi-replica).
- Background tasks (simple) vs a job queue (durable) — mitigated by persisting before forwarding and retry tooling.
- `limit/offset` pagination (simple) vs keyset (consistent at scale).
- Password grant for the first-party SPA (demo simplicity) vs Authorization Code + PKCE (production).

## Security considerations
bcrypt, JWT expiry + active-user check, RBAC per endpoint, API keys compared in constant time, HMAC webhooks with
replay window, tokens-only payments, secrets from env, append-only audit trigger, nginx CSP, ruff security rules
(each finding reviewed: three false positives annotated with reasons).

## Areas for future improvement
Real vendor sandboxes; Authorization Code + PKCE/MFA; refresh tokens; Redis-backed rate limits; Prometheus/OTel;
durable job queue; dual webhook secrets during rotation; dbt for the warehouse; Playwright E2E in CI; POPIA data
retention policy; running the Docker stack and GitHub Actions end to end.

## Sample interview answers
**"Tell me about your project."** "I designed and developed TableFlow Enterprise as an independent end-to-end
portfolio project, aimed at the kind of work in this role. It connects simulated Simphony, a Transaction
Junction-style gateway, Uber Eats, Mr D and a loyalty platform through a FastAPI backend with PostgreSQL, a React
TypeScript dashboard and n8n workflows. The parts I'm proudest of are the integration layer — every vendor call goes
through one runner that retries, logs and raises incidents — and the daily reconciliation that matches orders,
payments, POS checks and settlements."

**"What was hard?"** "Idempotency. A check-then-insert isn't safe when Uber retries quickly, so I put a unique
constraint on channel plus external reference and caught the violation inside a savepoint to return the original order."

**"What would you do differently?"** "Get a vendor sandbox early — my adapters are faithful to public descriptions,
but a real contract always surprises you. And I'd run the full Docker stack in CI from day one."

**"Is it production ready?"** "No. It's production-*style*: tested, documented and containerised, but simulated
vendors, demo auth flows and in-process rate limiting mean it needs the improvements I listed before real traffic."
