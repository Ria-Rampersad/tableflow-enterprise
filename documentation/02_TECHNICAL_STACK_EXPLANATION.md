# 02 · Technical Stack Explanation

For each technology: **What** · **Why chosen** · **Where used** · **How it works here** · **Talks to** ·
**Concepts to know** · **Common errors & troubleshooting** · **Interview Q&A**.

---

## Python 3.12+
- **What**: general-purpose language; the backend, ELT, generators and seed are Python.
- **Why**: fast to build integrations, excellent libraries (FastAPI, SQLAlchemy, cryptography), readable for reviewers.
- **Where**: `backend/app`, `snowflake/etl`, `scripts/`. Verified on Python 3.13 here; Dockerfile pins 3.12.
- **How**: type hints everywhere (`Mapped[int]`, `dict | None`), `Decimal` for money, dataclasses (`Principal`, `CallResult`), context vars for correlation ids.
- **Concepts**: virtual environments, `Decimal` vs float, `contextvars`, generators (`get_db`), exceptions as control flow (`AdapterError`, `BusinessRuleError`).
- **Errors**: `ModuleNotFoundError: app` → run from `backend/` or `python -m`; float rounding in money → use `Decimal(str(x))`.
- **Q: Why Decimal for money?** Binary floats can't represent 0.10 exactly; `0.1+0.2 != 0.3`. Cents must reconcile to the cent, so money is `NUMERIC(12,2)` in SQL and `Decimal` in Python, and JSON carries it as strings.

## FastAPI
- **What**: async-capable Python web framework built on Starlette + Pydantic; generates OpenAPI automatically.
- **Why**: validation, dependency injection and Swagger docs out of the box; very little boilerplate.
- **Where**: `app/main.py` (factory, middleware, exception handlers), `app/api/*.py` (routers).
- **How**: routers declare dependencies — `Depends(get_db)` gives a session; `Depends(require_roles("finance"))` enforces RBAC; `BackgroundTasks` runs POS forwarding after a 202. Middleware sets the correlation id and records metrics. Exception handlers turn `BusinessRuleError`, validation errors and HTTP errors into one JSON envelope.
- **Talks to**: browser/n8n/providers (HTTP), PostgreSQL (via SQLAlchemy), n8n (httpx).
- **Concepts**: path vs query vs body params, dependency injection, `response_model`, status codes, background tasks, lifespan events, sync endpoints run in a threadpool.
- **Errors**: 422 with `loc` path → read `details`; dependency order (auth runs before body validation); forgetting `db.commit()` → change lost.
- **Q: Sync or async endpoints?** Most endpoints are sync because SQLAlchemy sessions here are sync; FastAPI runs them in a threadpool so they don't block the event loop. Truly async work (n8n dispatch) uses `httpx.AsyncClient` in an asyncio task.
- **Q: How does Swagger get auth?** `OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")` tells OpenAPI about the password flow, so "Authorize" in `/docs` logs in and attaches the bearer token.

## Pydantic v2
- **What**: data validation using type hints. **Where**: `app/schemas`, `app/config.py`.
- **How**: `OrderStatusUpdate` uses a `model_validator` to require a reason when cancelling; `BranchCreate.code` has a regex; `PaymentCreate.amount` is `Decimal` with `gt=0, decimal_places=2`; `Settings` reads env vars with type conversion.
- **Q: Validation vs business rules?** Pydantic checks *shape* (types, ranges, formats) → 422 `VALIDATION_ERROR`. Services check *meaning* (SKU exists, total matches, transition allowed) → 422/409 with a specific code.

## REST API architecture
- Resources as nouns (`/orders/{id}`), verbs via methods: **GET** read, **POST** create/action, **PUT** full replace (`/branches/{id}`, `/webhooks/subscriptions/{id}`), **PATCH** partial update (`/branches/{id}`, `/orders/{id}/status`, `/incidents/{id}`, `/integrations/{id}`).
- Status codes mean something (202 for async accept, 409 for state conflicts). Versioned under `/api/v1`. Pagination `limit/offset`.
- **Q: PUT vs PATCH?** PUT replaces the whole resource (all required fields sent); PATCH changes only the supplied fields (`model_dump(exclude_unset=True)`).
- **Q: Is POST idempotent?** Not by default. We make payment POSTs idempotent with `Idempotency-Key` and provider order POSTs idempotent with `(channel, external_ref)`.

## Webhooks
- **What**: HTTP callbacks a provider sends when something happens. **Where**: `api/webhooks.py`, `webhooks/processor.py`, `security/signatures.py`.
- **How**: raw body → HMAC verify (+timestamp for TJ) → parse → de-dupe on `(source, event_id)` → handler in savepoint → `processed`/`failed`; rejected events stored.
- **Errors**: signature mismatch after JSON re-serialisation (always verify raw bytes); clock skew; duplicate processing (solved by unique key).
- **Q: Why return 200 for a duplicate?** Providers retry until they get 2xx. A duplicate is already handled, so acknowledging stops the retries without reprocessing.

## OAuth 2.0
- **What**: authorisation framework defining *grants* for obtaining access tokens.
- **Where**: `/api/v1/auth/login` (resource-owner password grant, for staff in this internal app and Swagger), `/api/v1/auth/token` (client-credentials grant for n8n).
- **How**: client credentials: `grant_type=client_credentials`, `client_id`, `client_secret` (bcrypt-hashed in `api_clients`), optional `scope` that must be a subset of the client's scopes → JWT with `typ=client` and `scopes`.
- **Q: Why not password grant for everything?** OAuth 2.1 discourages the password grant for third-party apps. It is acceptable here only because the SPA is first-party; a production build would use Authorization Code + PKCE via an identity provider (Entra ID/Okta). Machine-to-machine uses client credentials, which is the correct grant.

## JWT
- **What**: signed JSON token: header.payload.signature. **Where**: `security/auth.py`.
- **How**: HS256 with `JWT_SECRET_KEY`; claims `sub`, `roles`, `typ`, `iat`, `exp` (60 min), `iss`. Verification checks signature, expiry and issuer; user tokens are re-checked against the DB (inactive users rejected).
- **Errors**: `Token expired` (401) → log in again; tampered token → "Invalid token".
- **Q: Can you revoke a JWT?** Not directly — it's stateless. Mitigations: short expiry, re-checking `is_active` per request (done), a deny-list or refresh-token rotation (future work).

## Key-pair authentication
- **What**: authenticate by proving possession of a private key; the server only stores the public key.
- **Where**: `security/keypair.py`, `snowflake/schemas/01_account_setup.sql`, `snowflake/etl/extract_load.py`.
- **How**: generate RSA-2048 PKCS#8 (optionally passphrase-encrypted, file mode 600) → register the public key on the Snowflake user (`RSA_PUBLIC_KEY`) → connector receives DER bytes → verify with `RSA_PUBLIC_KEY_FP` fingerprint. Tests prove sign/verify and fingerprinting.
- **Q: Why better than a password?** No shared secret travels or sits in Snowflake; keys can be rotated with two slots (`RSA_PUBLIC_KEY_2`); service users can be password-less.

## Role-based access control & password hashing
- 5 roles, `require_roles()` per endpoint, admin bypass, branch scoping. bcrypt with random salt and cost 12 — two hashes of the same password differ (`test_password_hashing_is_salted_bcrypt`).

## React
- **What**: UI library of components and hooks. **Where**: `frontend/src`.
- **How**: routes in `App.tsx` with lazy-loaded pages; `useApi` hook for load/error/reload; `useAction` for mutations; shared `DataTable` with sorting/pagination/drill-down; Recharts for charts; forms with inline validation; toasts, modals, loading & error states.
- **Errors**: hooks after early return (rule of hooks) — ESLint `react-hooks` plugin enforces; stale responses — `useApi` ignores out-of-date requests via a sequence counter.
- **Q: How does the frontend talk to the backend?** `services/api.ts` → `fetch('/api/v1/...')` with bearer token and `X-Request-ID`. In dev Vite proxies `/api` to :8000; in Docker nginx does — one origin, no CORS needed.

## TypeScript
- Static types for API responses (`services/types.ts`), props and state; `strict` mode; `tsc -b --noEmit` runs in CI. Caught real issues during the build (e.g. an `unknown` error type in a test).
- **Q: Do TS types validate API responses at runtime?** No — they are compile-time only. Runtime validation happens on the server (Pydantic); a stricter client could add zod.

## PostgreSQL & SQL
- System of record with FKs, CHECK constraints, UNIQUE constraints for idempotency, composite and partial indexes, JSONB columns, triggers (append-only audit, `updated_at`), and reporting views. Details in Doc 05.
- **Errors**: `CheckViolation` (caught a seed bug), `UniqueViolation` (idempotency race — handled), psycopg `%` placeholder confusion (caught a migration-runner bug).

## Snowflake
- Cloud data warehouse separating storage and compute; virtual warehouses auto-suspend. Here: RAW → STAGING → ANALYTICS with a star schema, loaded by `PUT` + `COPY INTO`, authenticated by key-pair. **Not connected in this build**; the identical SQL ran on DuckDB locally.
- **Q: ETL vs ELT?** ETL transforms before loading; ELT loads raw data first and transforms inside the warehouse with SQL — cheaper to change, keeps raw history. TableFlow uses ELT.

## n8n
- Workflow automation tool: nodes (triggers, HTTP, IF, Code, Wait) connected in a graph; self-hostable.
- **Where**: `automation/n8n/*.json` (8 workflows), compose service `n8n`, import job `n8n-import`.
- **How**: webhook-triggered workflows receive events from TableFlow's outbox; schedule-triggered ones call the API with a client-credentials token; alerts go to `ALERT_WEBHOOK_URL`.
- **Errors**: `$env` access blocked → `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`; workflows imported inactive → activate; webhook URL differs between test and production mode (`/webhook-test/` vs `/webhook/`).
- **Verification honesty**: workflows were executed by `automation/local-runner` (a Node interpreter for the node subset used), not inside n8n.

## Docker & Docker Compose
- Images: multi-stage backend (non-root user, healthcheck, entrypoint runs migrations + optional seed) and frontend (Node build → nginx). Compose wires postgres, backend, frontend, n8n with health-based `depends_on`.
- **Errors**: backend starts before DB is ready → `condition: service_healthy`; port already in use → change host port; stale volume schema → `docker compose down -v` (destroys data).

## Git
- Feature branches → PR → CI → merge to `main`; conventional commit messages; `.gitignore` excludes `.env`, keys, DuckDB files and build output.

## GitHub Actions / CI/CD
- `ci.yml`: backend (ruff, pytest SQLite + Postgres service container, regression subset, coverage/JUnit artifacts) · frontend (lint, typecheck, tests, build) · api-contract (Newman + n8n runner against a live API) · docker (build, compose up, deployment checks) · deploy (gated placeholder).
- **Note**: the workflow file is written but has not been executed on GitHub (no repository push from this environment).

## Postman
- Collection with 87 requests in 11 folders, positive *and* negative cases, test scripts that chain variables (token, order id, payment id); two environments (Local :8000, Docker :8080). Run in CI with Newman — 87/87 requests, 91/91 assertions passed here.

## Interview quick-fire (stack)
- *Why FastAPI over Django?* API-first, automatic OpenAPI, Pydantic validation, lighter; no need for Django's templating/admin.
- *Why PostgreSQL?* ACID transactions for money, rich constraints, JSONB, window functions, mature tooling.
- *Why not Kafka for events?* Volume is modest; an outbox table + n8n meets needs with far less operational cost. Kafka becomes worthwhile with many consumers or high throughput.
- *Why n8n rather than code?* Ops/finance alerts change often; n8n lets non-developers see and adjust the flow while TableFlow keeps business logic in tested code.
