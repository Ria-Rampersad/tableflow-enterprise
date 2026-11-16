# 06 · Testing & QA Handbook

## 1. Test strategy (pyramid)
| Level | Tool | Count | What it proves |
|---|---|---|---|
| Unit | pytest, Vitest | ~25 | pure functions: signatures, key-pair, rate limiter, password hashing, VAT, formatters, form validation, API client |
| API / component | pytest + FastAPI TestClient; Testing Library | ~60 | each endpoint: positive & negative, RBAC, validation, error envelope; UI components |
| Integration | pytest on **real PostgreSQL** via migrations | whole suite | backend ↔ DB, triggers, views, schema drift; adapters ↔ services; webhooks ↔ payments ↔ loyalty |
| Contract | pytest | 11 | n8n workflow files & Postman collection reference real routes; outbox paths match n8n webhook paths |
| End-to-end | pytest (API-only), Newman, n8n runner, Playwright screenshots | 3 + 87 + 8 + 19 screens | full business journeys |
| Regression | `pytest -m regression` | 18 | previously found defects & highest-risk behaviour |
| UAT | manual scripts | 18 scenarios | business acceptance (`testing/UAT_SCENARIOS.md`) |

## 2. How to run
```bash
cd backend
pytest                                   # SQLite, fast (≈8 s)
TEST_DATABASE_URL=postgresql+psycopg://tableflow:tableflow@localhost:5432/tableflow_test pytest   # real Postgres
pytest -m regression                     # regression pack
pytest --cov=app --cov-report=term       # coverage (92% measured)
cd ../frontend && npm test               # Vitest
npx newman run postman/TableFlow_Enterprise.postman_collection.json -e postman/TableFlow_Local.postman_environment.json
bash scripts/run_n8n_workflows_locally.sh
```
The Postgres run **drops and recreates the `public` schema** of the test database — never point it at real data.

## 3. Unit testing — example
```python
def test_webhook_signature_roundtrip_and_tamper():
    body = b'{"id":"evt_1","type":"payment.captured"}'
    for source in ("transaction_junction", "uber_eats", "mr_d"):
        headers = signatures.sign(source, body)
        signatures.verify(source, body, headers)              # passes
        with pytest.raises(signatures.SignatureError):
            signatures.verify(source, body + b" ", headers)   # one extra byte fails
```

## 4. API testing — positive and negative
`test_create_branch_validation_and_duplicates`: 201 → 409 duplicate → 422 with exactly `code` and `province` in
`details`. Every module has both: e.g. payments (approve, decline×3, retryable, idempotent replay, conflict,
missing header, amount mismatch, cancelled order, over-refund, RBAC 403).

## 5. Integration testing
- Backend ↔ PostgreSQL: whole suite under `TEST_DATABASE_URL` (102 passed), plus Postgres-only tests: schema drift, append-only audit trigger, reporting views.
- POS adapter ↔ backend: `test_pos_outage_marks_order_failed_alerts_and_retry_recovers` asserts attempt log `retrying, retrying, failed`, alert payload, then recovery.
- Payment adapter ↔ backend ↔ webhook ↔ loyalty: `test_approved_payment_is_authorised_then_captured_by_signed_webhook`.
- Frontend ↔ backend: Vitest dashboard test asserts the UI renders the exact API contract; Playwright pass loaded all 16 routes against the live API with **zero console errors**.
- n8n workflows: contract tests (structure + routes) and live execution with the local runner (8/8 ok). Not executed inside n8n.

## 6. End-to-end scenarios
`test_e2e_digital_order_to_reconciled`: Uber order → POS → payment → signed capture webhook → +40 loyalty points →
n8n outbox → kitchen statuses → POS sync → settlement import → reconciliation shows no discrepancy for the order →
audit trail contains every step. `test_e2e_failure_path_…`: POS outage → failed → recovery → retry → provider cancel webhook.

## 7. Regression testing
Marked with `@pytest.mark.regression`, covering: duplicate orders, idempotent payments, duplicate webhooks,
redeem-while-platform-down, RBAC on refunds, POS outage recovery, refund limits, signature rejection,
webhook replay, reconciliation rules, schema drift, Postman↔routes, full e2e. Run on every CI build.
Purpose: prove that changes to orders, payments and integrations don't break existing behaviour.

## 8. Postman
87 requests across health/auth, branches, partners, orders/POS, payments, webhooks, loyalty, integrations,
incidents, reconciliation/automation, reports. Tests store variables (`token`, `order_id`, `payment_id`…) so the
collection runs top-to-bottom. Negative requests assert 401/409/422.

## 9. Test data
- `app.seed`: 60 days, 12 branches, 24 products, 450 customers, 320 loyalty members, ~10.6k orders with injected defects (4.5% declines, duplicates, short payments, settlement gaps, POS gaps, failed loyalty syncs, rejected webhooks, historic incidents). Deterministic (`random.Random(20261116)`).
- Tests seed 5 days and create their own data with unique references so they're order-independent.
- `snowflake/sample_data/*.csv`, `integrations/*/sample_*.json`.

## 10. Defect reporting template
```
ID: DEF-###          Severity: S1 blocker | S2 major | S3 minor | S4 cosmetic
Title:               Environment/build:
Steps to reproduce:  1. … 2. …
Expected:            Actual:
Evidence:            correlation id, screenshot, log excerpt
Root cause:          Fix:               Regression test:
```
Defects found and fixed during this build are listed in `testing/TEST_REPORT.md` §4 and Doc 10.

## 11. Test evidence
`documentation/testing/evidence/`: JUnit XML (SQLite + Postgres), coverage summary, Postgres run log, Newman CLI +
JUnit, Vitest verbose output, n8n runner trace, ELT run log. Screenshots were captured during verification
(`documentation/testing/evidence/screenshots/`).

## 12. UAT and release sign-off
UAT scripts per persona in `testing/UAT_SCENARIOS.md` with expected/actual/pass and sign-off blocks.
Release checklist: all CI jobs green · regression pack green · no open S1/S2 defects · UAT signed by Finance and
Operations · migration rehearsed on a copy of production · rollback plan written · release notes published.
