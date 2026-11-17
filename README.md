# TableFlow Enterprise

**Author:** Ria Rampersad · independent portfolio project (2026)

**Restaurant operations, payments, integrations & automation platform** — an independent, end-to-end portfolio
project built to demonstrate the Solutions Engineer role (requirements → design → build → integrate → test →
deploy → support) for a South African restaurant business.

> Demo tenant: **Shisa Flame Chicken** (fictional, 12 branches, ZAR, SAST). All vendor integrations — Oracle MICROS
> Simphony, a Transaction Junction-style gateway, Uber Eats, Mr D, loyalty, finance GL, inventory — are
> **simulated adapters** behind a sandbox-ready interface. No real company data or credentials are used.

## What's inside
| Area | Highlights |
|---|---|
| Backend | Python · FastAPI · Pydantic · SQLAlchemy · 84 REST operations · OAuth 2.0 + JWT · RBAC · API keys · HMAC webhooks · idempotency · retries · rate limiting · structured logs · health/metrics |
| Frontend | React 18 · TypeScript · Vite · Recharts · 17 screens (incl. login) (dashboard, branches, orders, digital ordering, payments, loyalty, POS hub, integrations, webhooks, automation, incidents, reconciliation, reports, audit) |
| Database | PostgreSQL 16 · SQL migrations · constraints, indexes, triggers, views · 13-query SQL library |
| Analytics | Snowflake setup, RAW→STAGING→ANALYTICS star schema, analytical queries, ELT with key-pair auth (local DuckDB mode) |
| Automation | 8 importable n8n workflows + local runner |
| Quality | 102 backend tests (real Postgres), 17 frontend tests, 87-request Postman collection, regression pack, UAT pack |
| DevOps | Dockerfiles, Docker Compose (Postgres, API, UI, n8n), nginx, GitHub Actions CI/CD |
| Docs | 13 handbooks incl. 122-question interview guide, demo script, runbooks, traceability matrix, verification report |

## Quickest start on Windows (no Docker, no Node, no PostgreSQL)
Double-click **`RUN ME.bat`**. It uses your Python (3.10+, Anaconda works), installs packages into `%LOCALAPPDATA%\TableFlow\venv`,
seeds a SQLite demo database and serves the UI + API at http://localhost:8000. Close the window to stop.

## Quick start (Docker)
```bash
cp .env.example .env              # change the CHANGE-… values
docker compose up --build -d
docker compose --profile setup run --rm n8n-import      # import n8n workflows (optional)
```
- UI: http://localhost:8080 — demo logins (password `TableFlow!2026`): `admin@`, `finance@`, `ops@`, `manager.umhlanga@`, `engineer@` + `tableflow.local`
- API docs (Swagger): http://localhost:8000/docs · n8n: http://localhost:5678

## Quick start (without Docker)
```bash
# 1. PostgreSQL 16 with a database "tableflow" owned by user tableflow/tableflow
cd backend && pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://tableflow:tableflow@localhost:5432/tableflow
python -m app.migrate && python -m app.seed --days 60
uvicorn app.main:app --reload --port 8000
# 2. In another terminal
cd frontend && npm install && npm run dev        # http://localhost:5173
```

## Tests
```bash
cd backend && pytest                                         # SQLite
TEST_DATABASE_URL=postgresql+psycopg://tableflow:tableflow@localhost:5432/tableflow_test pytest   # PostgreSQL
cd ../frontend && npm run lint && npm run typecheck && npm test
npx newman run postman/TableFlow_Enterprise.postman_collection.json -e postman/TableFlow_Local.postman_environment.json
bash scripts/run_n8n_workflows_locally.sh                    # needs the API running
python snowflake/etl/extract_load.py --full                  # ELT (DuckDB demo unless Snowflake creds set)
```

## Verification status (honest)
Verified here: backend tests on PostgreSQL (102/102), frontend lint/typecheck/tests/build, Newman (91/91 assertions),
all 8 workflows via the local runner, ELT in local mode, SQL library, browser pass over every screen.
**Not verified here**: building/running the Docker images (no Docker daemon available), the GitHub Actions run,
workflows inside a real n8n server, loading a real Snowflake account, live vendor APIs. Nothing is deployed to
production. Details: `documentation/13_FINAL_VERIFICATION_REPORT.md`.

## Documentation
Start at `documentation/00_INDEX.md` → `01_MASTER_PROJECT_HANDBOOK.md`.

## Repository layout
`backend/` API · `frontend/` UI · `database/` migrations, seeds, SQL · `integrations/` contracts & sample payloads ·
`automation/` n8n workflows + local runner · `snowflake/` warehouse SQL + ELT · `postman/` · `devops/` Docker &
CI copy · `.github/workflows/` CI · `scripts/` generators & tools · `documentation/`.
