# 12 · Requirements Traceability Matrix — Pedros Solutions Engineer job advert → TableFlow

**Source note.** The full advert text could not be retrieved (job-board pages blocked automated access). Rows marked
**[Advert]** come from the publicly indexed excerpt of the Pedros "Solutions Engineer" listing (Durban/Newlands);
rows marked **[Brief]** come from the requirement list in the project brief, which itself was derived from the
advert. Re-check against the full advert before an interview and add any missing line.

Verification status: ✅ Verified by executed test/run · 👁 Verified manually/visually · ◐ Implemented, partially
verified (reason given) · ○ Documented only.

| # | Job advert requirement | Technology / responsibility | TableFlow implementation | Relevant source files | Demonstration | Docs | Status |
|---|---|---|---|---|---|---|---|
| 1 | [Advert] Deliver small projects end to end: requirements → build → testing → release | Solution lifecycle | Full lifecycle artefacts + working system | `documentation/requirements/*`, `backend`, `frontend`, `tests`, `ci.yml` | Demo script §1–11 | 01, 06, 07 | ✅ |
| 2 | [Advert] Work directly with Product Owners and business stakeholders | Requirements gathering | Stakeholder analysis, 5 interview notes, need→spec example | `requirements/01_…` | Demo §1 | req/01 | ○ (fictional stakeholders) |
| 3 | [Advert] Connect POS systems (Micros Simphony) | POS integration | Simphony adapter: checks, status, menu sync, transaction sync, retries | `integrations/micros_simphony.py`, `services/pos.py`, `pages/PosHub.tsx` | Demo §4, §7 | 04 §3 | ✅ (simulated vendor) |
| 4 | [Advert] Connect digital ordering platforms | Uber Eats, Mr D | Partner APIs, mapping, validation, de-dupe, cancellations | `integrations/ordering.py`, `api/orders.py`, `pages/DigitalOrders.tsx` | Demo §4 | 04 §5–6 | ✅ (simulated) |
| 5 | [Advert] Connect payment systems | Transaction Junction-style | Authorise, idempotency, webhooks, refunds, settlement import | `integrations/transaction_junction.py`, `services/payments.py` | Demo §5 | 04 §4 | ✅ (simulated) |
| 6 | [Advert] Connect back-office systems | Finance GL, inventory | Journal posting, stock levels | `integrations/backoffice.py`, `services/automation.py` | Automation screen | 04 §8 | ✅ (simulated) |
| 7 | [Advert] Build tools for Stores, Operations and Finance | Internal tools | 17-screen app: branch views, POS hub, incidents, reconciliation, automation tools | `frontend/src/pages/*` | Demo §3–8 | 01 §6 | ✅ 👁 |
| 8 | [Advert] Python (FastAPI) | Backend | 84 API operations, Pydantic, DI, background tasks | `backend/app` | Swagger `/docs` | 02, 03 | ✅ |
| 9 | [Advert] React | Frontend | SPA with charts, tables, forms | `frontend/src` | Demo §3 | 02, 03 | ✅ |
| 10 | [Advert] TypeScript | Frontend | strict TS, typed API client | `frontend/src/services` | `npm run typecheck` | 02 | ✅ |
| 11 | [Advert] PostgreSQL | Operational DB | 26 tables, constraints, indexes, triggers, views, migrations | `database/`, `models/` | `psql` queries | 05 | ✅ |
| 12 | [Advert] n8n | Automation | 8 importable workflows + compose service + local runner | `automation/` | Demo §9 | 04 §15 | ◐ (executed with local runner, not inside n8n) |
| 13 | [Advert] Query Snowflake and operational databases | Data / SQL | Snowflake setup, ELT, star schema, 9 analytical queries; 13-query Postgres library | `snowflake/`, `database/sql/` | `extract_load.py` | 05 §11 | ◐ (Snowflake SQL run on DuckDB; Postgres ✅) |
| 14 | [Advert] Scope larger initiatives and hand to Engineering | Complexity assessment | Scoring model + 4 worked decisions | `requirements/01_…` §7 | Discussion | req/01 | ○ |
| 15 | [Brief] REST APIs (GET/POST/PUT/PATCH) | API design | PUT branches/subscriptions, PATCH branches/orders/incidents/integrations | `api/*` | Postman | req/05 | ✅ |
| 16 | [Brief] Webhooks | Inbound events | HMAC verification, replay window, de-dupe, replay, subscriptions | `webhooks/processor.py`, `security/signatures.py` | Demo §6 | 04 §10 | ✅ |
| 17 | [Brief] OAuth 2.0 | Auth | Password grant (staff), client credentials (n8n) | `api/auth.py` | Postman folder 00 | 02 | ✅ |
| 18 | [Brief] JWT, RBAC, password hashing | Security | HS256 JWT, 5 roles, bcrypt | `security/auth.py` | 403 demo | 02, req/06 | ✅ |
| 19 | [Brief] API keys, rate limiting, idempotency, retries | Integration hygiene | Partner keys, sliding window, Idempotency-Key, back-off | `security/`, `monitoring/ratelimit.py`, `integrations/base.py` | Demo §4–5, §7 | 04 §12–14 | ✅ |
| 20 | [Brief] Key-pair authentication | Snowflake auth | RSA generation, DER, fingerprint, sign/verify | `security/keypair.py` | `python -m app.security.keypair ./keys` | 02 | ✅ (keys) ◐ (not against Snowflake) |
| 21 | [Brief] Loyalty systems | Loyalty | Earn/redeem, tiers, failed-sync retry | `services/loyalty.py` | Loyalty screen | 04 §7 | ✅ (simulated) |
| 22 | [Brief] Postman | API testing | 87 requests, 2 environments, Newman | `postman/` | `newman run …` | 06 §8 | ✅ |
| 23 | [Brief] Automated testing (pytest, regression, integration, E2E, frontend) | QA | 102 + 17 tests, regression marker, contract tests | `backend/tests`, `frontend/src/tests` | Demo §10 | 06 | ✅ |
| 24 | [Brief] UAT | Acceptance | 18 persona scenarios + sign-off | `testing/UAT_SCENARIOS.md` | — | 06 §12 | ○ (not executed by business users) |
| 25 | [Brief] Docker / Docker Compose | Containers | Backend/frontend images, compose with Postgres + n8n | `devops/docker`, `docker-compose.yml` | `docker compose up` | 07 | ◐ (config validated; images not built here) |
| 26 | [Brief] Git | Version control | repo with history, `.gitignore`, branching guide | repo root | `git log` | 07 §1 | ✅ |
| 27 | [Brief] CI/CD, GitHub Actions | Pipeline | 5-job workflow | `.github/workflows/ci.yml` | — | 07 §5 | ◐ (steps run locally; workflow not run on GitHub) |
| 28 | [Brief] Production releases | Release management | release checklist, staging→prod design, rollback | Doc 07 §6, §8 | — | 07 | ○ (no production environment) |
| 29 | [Brief] Monitoring & logging | Observability | JSON logs, correlation ids, `/metrics`, `/health/ready`, integration logs | `monitoring/`, `api/health.py` | `/metrics` | 07 §7 | ✅ |
| 30 | [Brief] Incident management | Support | Auto + manual incidents, escalation, MTTR | `services/incidents.py`, pages | Demo §7 | runbooks | ✅ |
| 31 | [Brief] Root-cause analysis & runbooks | Support | 6 runbooks, RCA example, report template | `runbooks/RUNBOOKS.md` | — | runbooks | ○ |
| 32 | [Brief] Financial reconciliation | Finance tooling | 9-rule engine, CSV export/import | `services/reconciliation.py` | Demo §8 | 05 §9 | ✅ |
| 33 | [Brief] Reporting & analytics | Reporting | 9 reports JSON/CSV + dashboard | `services/reporting.py`, `pages/Reports.tsx` | Reports screen | 01 §6 | ✅ |
| 34 | [Brief] AI-assisted development (Claude, Copilot, Cursor) | Ways of working | Usage, prompts, human review, wrong-output examples | Doc 11 | — | 11 | ○ |
| 35 | [Brief] Audit trail | Compliance | append-only audit table + trigger | `services/audit.py`, V002 | Audit screen | 05 §7 | ✅ |
