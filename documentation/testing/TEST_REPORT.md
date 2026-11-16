# Test Report — TableFlow Enterprise v1.0.0

**Date**: 16 November 2026 · **Environment**: Linux build container, Python 3.13, Node 22, PostgreSQL 16.15
(local server), headless Chrome. **No Docker daemon** was available in this environment.

## 1. Summary
| Suite | Executed | Passed | Failed | Skipped | Evidence |
|---|---|---|---|---|---|
| Backend pytest — SQLite | 102 | 99 | 0 | 3 (Postgres-only) | `evidence/junit-sqlite.xml`, `pytest-sqlite-coverage.txt` |
| Backend pytest — PostgreSQL via migrations | 102 | 102 | 0 | 0 | `evidence/junit-postgres.xml`, `pytest-postgres.txt` |
| Regression subset (`-m regression`) | 18 | 17 | 0 | 1 (Postgres-only on SQLite) | CI step |
| Backend coverage | — | 92% lines (`app/`, excl. seed) | | | `pytest-sqlite-coverage.txt` |
| Frontend Vitest | 17 | 17 | 0 | 0 | `evidence/frontend-vitest.txt` |
| Frontend ESLint / tsc / vite build | 3 | 3 | 0 | 0 | build logs |
| Postman via Newman | 87 requests / 91 assertions | 91 | 0 | 0 | `evidence/newman-cli.txt`, `newman-junit.xml` |
| n8n workflows (local runner, live API) | 8 | 8 | 0 | 0 | `evidence/n8n-local-runner.txt` |
| Snowflake ELT (local DuckDB mode) | full + incremental | ✓ | 0 | — | `evidence/snowflake-elt-local.txt` |
| SQL library on PostgreSQL | 13 queries | 13 | 0 | 0 | executed with `ON_ERROR_STOP=1` |
| UI smoke (Playwright, live API) | 19 screens/actions | 19 | 0 | 0 | `evidence/screenshots/` (0 console errors) |
| Ruff (backend app + tests) | — | clean | | | CI step |

## 2. Coverage of test types
Unit · API (positive + negative) · integration (backend↔Postgres, adapters↔services, webhooks↔payments↔loyalty,
frontend↔backend contract) · contract (n8n, Postman, schema drift) · end-to-end (API journeys, Newman, workflow runs,
browser) · regression.

## 3. Not executed / outstanding (honest list)
| Item | Status | Reason / next step |
|---|---|---|
| Docker image build & `docker compose up` | **Not run** | no Docker daemon in build environment; `docker compose config` validated. Run `docker compose up --build` |
| GitHub Actions workflow | **Not run on GitHub** | repository not pushed from this environment; each step was executed locally |
| Workflows inside a real n8n instance | **Not run** | n8n not available; executed with local runner. Import and run in n8n |
| Snowflake account load | **Not run** | no credentials; identical SQL run on DuckDB |
| Vendor sandboxes | **N/A** | integrations simulated by design |
| UAT by business users | **Pending** | pack prepared (`UAT_SCENARIOS.md`) |
| Load/performance testing | **Not done** | functional latency only (Newman avg 19 ms); suggest k6/Locust |
| Accessibility audit | **Not done** | semantic roles/labels used; full WCAG audit outstanding |

## 4. Defects found and fixed during testing
| ID | Severity | Defect | Found by | Status |
|---|---|---|---|---|
| DEF-001 | S1 | Migration V002 failed (psycopg `%` placeholder) | Postgres migration run | Fixed |
| DEF-002 | S3 | Seed created negative payment amount | Postgres CHECK constraint | Fixed |
| DEF-003 | S2 | Admin could not create `.local` users | API test | Fixed |
| DEF-004 | S3 | Contract test found no routes (nested routers) | contract test | Fixed |
| DEF-005 | S3 | Postman token not applied after login | Newman | Fixed |
| DEF-006 | S2 | ELT analytical query runner crashed | ELT run | Fixed |
| DEF-007 | S2 | Incremental ELT overwrote sample data | ELT run | Fixed |
| DEF-008 | S3 | UI simulator 404 (stale API process) | Playwright | Fixed (restart) |
| DEF-009 | S4 | Table/JSON wrapping | screenshot review | Fixed |
| DEF-010 | S4 | Webhook API hid error for acknowledged failures | manual script | Fixed |
No open defects at the time of this report.
