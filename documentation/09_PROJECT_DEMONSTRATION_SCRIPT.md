# 09 · Project Demonstration Script (≈25 minutes)

**Before the interview**: stack running and seeded; browser tabs open — UI (`:8080` or `:5173`), Swagger (`:8000/docs`),
n8n (`:5678`) or a terminal for the local runner, VS Code on the repo; zoom 110%; integrations all healthy
(Integration Monitoring → End outage if needed). Have `documentation/requirements/04_…` diagrams open.

| Time | Show on screen | Say |
|---|---|---|
| 0:00 | README / architecture diagram | "TableFlow Enterprise is a portfolio project I designed and built end to end to practise the Solutions Engineer role: connecting POS, delivery, payments, loyalty and back-office systems for a fictional 12-branch restaurant group. Vendor integrations are simulated — I'll show exactly where." |

## 1. Business problem (2 min)
Show `requirements/01_…` pain table. Say: "Finance reconciled in Excel days later, delivery orders were re-keyed,
and failures were discovered by phone. I interviewed (fictional) Finance, Ops, a branch manager and IT and turned
their statements into rules — for example 'the same order arriving twice' became a unique key on channel plus
external reference."

## 2. Architecture & stack (3 min)
Show the system and sequence diagrams. Say: "React/TypeScript front end behind nginx; FastAPI with Pydantic;
PostgreSQL; every vendor call goes through one IntegrationRunner that retries, logs and tracks health; events go to
an outbox that n8n consumes; a nightly ELT feeds Snowflake. One modular service because one engineer must run it."

## 3. Live walkthrough — dashboard (2 min)
Sign in as **admin** using the demo button. Point at KPI tiles, change preset 7d → 30d, choose a branch, click
**Failed payments** (drills into Payments filtered). Back; click **Umhlanga Gateway** in branch performance → branch
detail (sales chart, top products, integration errors, configuration).

## 4. Order integration (3 min)
Digital Ordering → Uber Eats → **Send new Uber Eats order**. Say: "This sends an Uber-shaped payload — amounts in
cents — through the real pipeline: API key, rate limit, mapping to our canonical order, validation, store, 202,
then background POS forwarding." Open the provider payload. Click the new order → status **Accepted**, Simphony
check reference, VAT split. Click **Re-send same order** → yellow "Duplicate order ignored". Click **wrong total** →
TOTAL_MISMATCH error with reference id. Optional: Swagger `POST /partners/mr-d/orders` with `integrations/mr_d/sample_order.json`.

## 5. Payment (2 min)
In the order detail choose `tok_visa_approved` → **Take payment**. Status goes authorised → captured (webhook).
Say: "Every payment needs an Idempotency-Key; replaying returns the same payment, reusing the key with a different
amount is a 409." Take payment on another order with `tok_declined` → failed with "05 Do not honour", no retry.
Payments screen → open a captured payment → refund R20 (sign in as finance if needed).

## 6. Webhook (2 min)
Webhooks screen: show processed events, signature column, deliveries count. Click **Send forged webhook** → 401 and a
`rejected` event. Terminal: `python scripts/send_signed_webhook.py transaction-junction integrations/transaction_junction/sample_captured_webhook.json`
→ accepted but `failed` (unknown transaction) → open it → explain replay. Say: "Signature is checked over raw bytes,
with a timestamp to stop replays; duplicates are acknowledged but not re-processed."

## 7. Failed integration & retry (3 min) — the strongest part
Integration Monitoring → Simphony → **Simulate outage**. Digital Ordering → send 3 orders. POS Hub: orders in
"Failed POS requests"; Simphony **down**. Integration Monitoring logs: attempts `retrying, retrying, failed` with
HTTP 503. Incidents: auto-created **SEV2 "Oracle MICROS Simphony integration down"** — open the timeline.
Automation → Notification outbox: `pos_failure` events. Back to Integration Monitoring → **End outage** → POS Hub
→ **Retry** → order Accepted. Say: "Orders were never lost: stored first, retried with back-off, marked failed,
alerted, one incident — not one per failure — and recoverable with one click."

## 8. Financial reconciliation (2 min)
Reconciliation → yesterday → **Reconcile**. Walk the chips: failed payment, missing settlement, unknown
settlement… Hover for definitions. **Export CSV**. Say: "Nine rules, matching keys are order id, POS check ref and
gateway reference; an order is matched only if every check passes; above R500 raises an incident."

## 9. Automated workflows (2 min)
n8n UI (or VS Code) → open workflow 07: webhook → SEV1? → page on-call → wait 30 minutes → get token → still open?
→ auto-escalate. Run `bash scripts/run_n8n_workflows_locally.sh` and show 8 × `"ok":true`. Automation screen →
outbox shows `n8n_alert` **delivered** messages including the management digest. Be clear that the run used the
local runner if n8n isn't up.

## 10. Testing (1.5 min)
Terminal: `pytest -q` (99 pass + 3 Postgres-only skipped) and the Postgres run (102 pass). Show
`test_reconciliation_matching_logic_detects_every_issue_type` briefly. Newman summary: 87 requests / 91 assertions /
0 failures. Frontend `npm test` 17 pass.

## 11. Deployment (1 min)
Show `docker-compose.yml` and `ci.yml` stages. Say honestly: "Compose is validated and the pipeline is written;
I haven't deployed to production, and in the environment I built this in I couldn't run Docker images, so that's
the next verification step."

## 12. Lessons learned (1 min)
- Database constraints caught bugs my code didn't (negative seed payment).
- Real Postgres testing matters (the migration `%` bug never appears on SQLite).
- Idempotency must be designed at every entry point, not added later.
- Honesty about simulation is part of good solution engineering.

## Likely follow-ups and where to point
"Show me the retry code" → `integrations/base.py:IntegrationRunner.call`. "Where's RBAC?" → `security/auth.py`
`require_roles`. "How do you stop duplicates under concurrency?" → `services/orders.py:ingest` savepoint + UNIQUE.
"How do the n8n workflows authenticate?" → workflow node "Get API token" + `/auth/token`.
