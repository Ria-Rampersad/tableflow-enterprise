# Operational Runbooks

Common first steps for every runbook:
1. Note the time, affected branches/channels and any correlation id from the UI error ("Reference: …").
2. Check `GET /health/ready`, the **Integration Monitoring** screen and **Incidents** (an automated incident may already exist — use it rather than opening a duplicate).
3. Set the incident to `investigating`, assign yourself, add timeline notes as you go.
4. After resolution: root cause, resolution notes, prevention actions; close within 48 h after a post-incident review for SEV1/SEV2.

Severity guide: **SEV1** money at risk or all branches can't trade card payments · **SEV2** a core integration down for one or more branches · **SEV3** degraded/partial, workaround exists · **SEV4** cosmetic/low impact.

---

## RB-01 POS integration failure (Micros Simphony)
**Signals**: orders in `failed`; POS Hub "Orders awaiting POS" > 0; Simphony status `degraded`/`down`; auto-incident "Oracle MICROS Simphony integration down" (SEV2); n8n workflow 02 alert.
**Diagnose**
1. Integration Monitoring → Simphony → Logs (filter `failed`). Read `http_status` + `error_message`:
   - 503/504/timeouts across branches → vendor/network outage.
   - 422 "Menu items not mapped" at one branch → configuration (new product without `pos_item_ref`).
   - 400 "locRef missing" → branch `pos_location_ref` empty.
2. `SELECT branch_id, count(*) FROM orders WHERE status='failed' GROUP BY 1;` — one branch or all?
**Resolve**
- Outage: tell branches to take delivery orders on the provider tablet temporarily; contact vendor; when health check passes, retry failed orders (POS Hub → Retry, or `POST /orders/{id}/forward-to-pos`).
- Unmapped item: map `pos_item_ref`, run **Menu sync** for the branch (should show `unmapped_skus: []`), retry orders.
**Verify**: failed count returns to 0, status `healthy`, provider status pushes succeed.
**Prevent**: menu sync as part of every menu change; alert on first `422` from Simphony.

## RB-02 Payment gateway failure
**Signals**: payment success rate drops; many `91`/503 failures; TJ status `down`; auto SEV1 incident; n8n workflow 01 alerts.
**Diagnose**
1. Distinguish **declines** (05/51/54 – customer/issuer, *not* an outage) from **gateway errors** (91, 5xx, timeouts) — `SELECT left(failure_reason,2), count(*) FROM payments WHERE created_at > now()-interval '30 min' GROUP BY 1;`
2. Gateway errors at all branches → provider incident; at one branch → that branch's terminals/network.
**Resolve**: escalate to provider (SEV1 → escalation level 1 immediately); branches fall back to standalone terminals/cash per business continuity plan; when restored, run a discrepancy scan for `authorised` payments without capture and use "simulate/replay" capture where the provider confirms.
**Verify**: success rate back to baseline (> 95%), no stuck `authorised` payments.
**Prevent**: provider maintenance calendar; synthetic health check every 5 min (automation endpoint) feeding n8n.

## RB-03 Duplicate order processing
**Signals**: kitchen reports a double order; reconciliation `duplicate_payment`; provider retry storm.
**Diagnose**
1. `SELECT channel, external_ref, count(*) FROM orders GROUP BY 1,2 HAVING count(*)>1;` — should be **empty** (UNIQUE constraint). If empty, the duplicate is not in TableFlow: the provider sent two *different* order ids (customer double-submitted) — check provider portal.
2. Webhook events: `attempts > 1` for one `event_id` shows provider retries that were correctly absorbed.
3. Payments: two captured payments for one order → check `idempotency_key`s — different keys mean the client didn't reuse its key.
**Resolve**: cancel the extra order (with reason); refund the duplicate payment (Finance); inform customer.
**Verify**: reconciliation run for that day shows the issue resolved (mark record resolved).
**Prevent**: ensure terminals/clients send a stable `Idempotency-Key` per checkout attempt.

## RB-04 Webhook delivery failure
**Signals**: Webhooks screen shows `rejected` or `failed` spikes; payments stuck `authorised`; dashboard "Failed webhooks".
**Diagnose**
- `rejected` + "signature mismatch" for every event → secret rotated/mismatched. "timestamp outside tolerance" → clock skew or replayed old events.
- `failed` + "Unknown transactionId" → event for a payment we don't have (wrong merchant/env) or arrived before our record committed.
- No events at all → provider can't reach us (DNS/TLS/firewall) — check provider delivery dashboard.
**Resolve**
1. Secret: obtain new secret from provider, update `WEBHOOK_SECRET_*` in the secret manager, restart backend, ask provider to redeliver (or replay from their console).
2. Failed events: fix the cause, then **Replay** each (`POST /webhooks/events/{id}/replay`).
**Verify**: new events `processed`; stuck payments captured.
**Prevent**: dual-secret support during rotation (future), alert when rejected events > 5 in 10 min.

## RB-05 Database connectivity failure
**Signals**: `/health/ready` 503 with `database.ok=false`; API 500s; backend container unhealthy.
**Diagnose**: `docker compose ps postgres`; `docker compose logs postgres` (disk full? OOM? auth?); `pg_isready`;
connection count `SELECT count(*) FROM pg_stat_activity;` vs `max_connections`; disk `df -h`.
**Resolve**: restart postgres if crashed; free disk; fix credentials; reduce pool / raise `max_connections`; if data corruption → restore from latest backup (PITR) to a new instance, repoint `DATABASE_URL`.
**Verify**: readiness 200, error rate back to 0, orders flowing (partner orders arriving during the outage were rejected with 5xx and will be retried by providers).
**Prevent**: monitoring on connections/disk, automated backups + restore drills, connection pooler (PgBouncer).

## RB-06 Failed daily reconciliation
**Signals**: n8n workflow 05 error, no run for yesterday in Reconciliation, or a run with an unusually high discrepancy count.
**Diagnose**
1. Did it run? `SELECT * FROM reconciliation_runs WHERE business_date = current_date - 1;`
2. Workflow error → token/credentials (`TABLEFLOW_CLIENT_SECRET`), API down, timeout.
3. Many `missing_settlement` → settlement file not imported yet. Many `missing_pos_record` → POS transaction sync didn't run.
**Resolve**: import the settlement CSV (`/reconciliation/settlements/import`), run POS transaction sync per branch, re-run reconciliation for the date (runs are repeatable; each creates a new run record).
**Verify**: discrepancies return to the normal handful (declines, genuine short-pays); notify Finance.
**Prevent**: make workflow 05 depend on "settlement imported" (or schedule after the file's SLA), alert on missing run by 06:30.

---

## Incident report template
```
Reference / title:          Severity:            Status:
Detected (time, how):       Resolved (time):     Duration / MTTR:
Impact (branches, orders, ZAR, customers):
Timeline (from incident_events):
Root cause (5 whys):
Resolution:
Prevention actions (owner, due date):
Lessons learned:
```

## Root-cause analysis example (seeded INC-00002)
**Problem**: Simphony check creation failed at Liberty Midlands (PMB-LBT) for 3 hours.
Why 1: Simphony returned 422 for 14 orders. → Why 2: orders contained "Spicy Rice Bowl" with no Simphony item number. →
Why 3: the product was added to TableFlow's catalogue without a `pos_item_ref`. → Why 4: menu changes had no
checklist step to map POS items. → Why 5: menu sync was manual and not run after the change.
**Root cause**: process gap — menu changes aren't validated against Simphony. **Fix**: map item, menu sync, retry
orders. **Prevention**: menu sync reports unmapped SKUs (implemented); add menu sync to the change checklist; alert on first 422.

## How a Solutions Engineer handles incidents
Investigate with evidence (logs, correlation ids, SQL) → contain (workaround, communicate) → resolve (fix, retry,
replay) → document (timeline, RCA, notes) → prevent (test that reproduces it, monitoring, process change) →
share (post-incident review, update this runbook).
