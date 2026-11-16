# 03 · Business Rules (as implemented)

Each rule names the code that enforces it so the documentation cannot drift silently from behaviour.

## Orders — `backend/app/services/orders.py`
| ID | Rule |
|---|---|
| BR-ORD-01 | A provider order is identified by **(channel, external_ref)**. A repeat returns the original order (`duplicate=true`). Enforced in code *and* by DB constraint `uq_order_channel_external_ref`; a concurrent duplicate that loses the race is caught via savepoint + `IntegrityError`. |
| BR-ORD-02 | The branch must exist, be active, and (for Uber Eats / Mr D) have that channel enabled. |
| BR-ORD-03 | Every SKU must exist and be active. |
| BR-ORD-04 | If the provider sends a total it must equal Σ(quantity × unit price) within R0.01. Provider unit prices are accepted (platforms may mark up). |
| BR-ORD-05 | Prices are VAT-inclusive. VAT = total × 15/115, rounded half-up to cents; subtotal = total − VAT. |
| BR-ORD-06 | Allowed transitions: received→{sent_to_pos, accepted, cancelled, failed}; failed→{accepted, cancelled}; accepted→{preparing, ready, cancelled}; preparing→{ready, cancelled}; ready→{completed}. Others return 409. |
| BR-ORD-07 | Cancelling requires a reason; an order with a captured payment cannot be cancelled until refunded (409 REFUND_REQUIRED). |
| BR-ORD-08 | Phone numbers are normalised to E.164 (+27…); invalid SA numbers are rejected. |

## Payments — `backend/app/services/payments.py`
| ID | Rule |
|---|---|
| BR-PAY-01 | `Idempotency-Key` header is mandatory. Same key + same order/amount → original payment (200, `Idempotent-Replayed: true`). Same key + different body → 409. |
| BR-PAY-02 | Amount must equal the order's outstanding balance. |
| BR-PAY-03 | No payment for cancelled or failed orders (409). |
| BR-PAY-04 | Refund total ≤ captured amount; status becomes `partially_refunded` or `refunded`. |
| BR-PAY-05 | Only `finance` (and `admin`) may refund. |
| BR-PAY-06 | Declines (05, 51, 54, 14) are permanent — not retried and do not degrade integration health. Code 91 / timeouts / 5xx are retried. |
| BR-PAY-07 | Only card **tokens** are accepted; tokens are truncated in logs (`tok_visa***`). |

## Webhooks — `backend/app/webhooks/processor.py`, `security/signatures.py`
| ID | Rule |
|---|---|
| BR-WH-01 | Signature verified over raw bytes before parsing. Transaction Junction-style signatures include a timestamp; older than 300 s → rejected (replay protection). |
| BR-WH-02 | Invalid/unsigned events are stored as `rejected` (401) for forensics; they change nothing. |
| BR-WH-03 | (source, event_id) is unique; repeats are acknowledged (200) without re-processing; `attempts` incremented. |
| BR-WH-04 | Business failures (unknown transaction, amount mismatch) → `failed`, acknowledged 200 (provider retries would not help), replayable by an engineer. |
| BR-WH-05 | Capture amount must equal the authorised amount. |

## Loyalty — `backend/app/services/loyalty.py`
| ID | Rule |
|---|---|
| BR-LOY-01 | 1 point per R10 of captured amount, rounded down. |
| BR-LOY-02 | Earned once per order (unique constraint `uq_loyalty_once_per_order`). |
| BR-LOY-03 | Redemption applied only after the loyalty platform confirms; otherwise 502 and balance unchanged. |
| BR-LOY-04 | Failed earn syncs are kept as `failed` and retryable (manually or by n8n workflow 04). |
| BR-LOY-05 | Tiers by lifetime points: Bronze < 500 ≤ Silver < 1500 ≤ Gold. |

## Integrations & incidents — `integrations/base.py`, `services/incidents.py`
| ID | Rule |
|---|---|
| BR-INT-01 | Up to 3 attempts, exponential back-off 0.2 s, 0.4 s (configurable). |
| BR-INT-02 | Status: healthy → degraded (1–2 consecutive failures) → down (≥ 3). A success resets to healthy. |
| BR-INT-03 | Reaching the threshold raises **one** incident per integration; further failures add timeline notes. |
| BR-INC-01 | Severity by integration kind: payment SEV1, POS/ordering SEV2, loyalty/finance SEV3, back-office SEV4. |
| BR-INC-02 | Resolve/close requires resolution notes; closed is terminal; resolved incidents cannot be escalated. |
| BR-INC-03 | SEV1/SEV2 creation and every escalation notify n8n workflow 07. Escalation path L1 SE lead → L2 Head of Engineering → L3 CTO/vendor exec. |

## Reconciliation — `backend/app/services/reconciliation.py`
| ID | Rule |
|---|---|
| BR-REC-01 | Business day = 00:00–24:00 SAST (UTC+2). Cancelled orders are excluded. |
| BR-REC-02 | Matching keys: order↔payment by `order_id`; order↔POS by `pos_check_ref`/`order_id`; payment↔settlement by gateway `provider_reference`. |
| BR-REC-03 | Nine issue types (see Database handbook); an order is *matched* only if it produced no issue. |
| BR-REC-04 | Total absolute discrepancy > R500 raises a SEV3 reconciliation incident. |
| BR-REC-05 | Settlement import skips references already loaded (idempotent re-import). |
