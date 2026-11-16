# 02 · Functional Requirements, Non-Functional Requirements, User Stories & Acceptance Criteria

Status column = verified by an automated test (✅) or by manual/visual check (👁). Test names are in `backend/tests/`
and `frontend/src/tests/`.

## Functional requirements

| ID | Requirement | Status / evidence |
|---|---|---|
| FR-DASH-01 | Dashboard shows branches, orders, sales (ZAR), successful/failed/pending payments, integration health, API volume, failed webhooks, uptime | ✅ `test_dashboard_summary_and_trend`, frontend `Executive dashboard` test |
| FR-DASH-02 | Revenue trend, branch performance, daily transaction summary with date range + branch filters and drill-down | ✅ API tests; 👁 screenshot |
| FR-BR-01 | Admin can create (POST), replace (PUT) and partially update (PATCH) branches | ✅ `test_create_branch_validation_and_duplicates`, `test_put_replaces_branch` |
| FR-BR-02 | Assign POS location and payment provider; enable digital channels | ✅ `test_patch_assign_pos_and_payment_and_audit` |
| FR-BR-03 | Branch performance and integration health per branch | ✅ `test_branch_performance_and_integration_health` |
| FR-POS-01 | Create Simphony check for every accepted order | ✅ `test_in_store_order_is_validated_priced_and_sent_to_pos` |
| FR-POS-02 | Push status updates to POS | ✅ `test_status_transitions` (via adapter call) |
| FR-POS-03 | Menu sync reports unmapped items | ✅ `test_menu_sync_and_transaction_sync` |
| FR-POS-04 | Transaction (closed-check) sync | ✅ same |
| FR-POS-05 | Failed POS requests are retried with back-off, logged and retryable from the UI | ✅ `test_pos_outage_marks_order_failed_alerts_and_retry_recovers` |
| FR-ORD-01 | Accept Uber Eats and Mr D orders with provider-specific mapping | ✅ `test_uber_eats_order_accepted_mapped_and_forwarded`, `test_mr_d_order_and_cancellation` |
| FR-ORD-02 | Validate branch, channel, SKUs, totals | ✅ `test_channel_not_enabled_for_branch`, `test_partner_total_mismatch_rejected`, `test_unknown_sku_rejected_with_business_error` |
| FR-ORD-03 | Prevent duplicate orders from provider retries | ✅ `test_duplicate_uber_order_is_not_created_twice` |
| FR-ORD-04 | Handle provider cancellations (API + webhook) | ✅ `test_uber_eats_cancel_webhook`, `test_mr_d_cancel_webhook_and_unknown_order` |
| FR-PAY-01 | Initiate/authorise payments idempotently | ✅ `test_idempotent_replay_returns_same_payment` |
| FR-PAY-02 | Capture via signed gateway webhook | ✅ `test_approved_payment_is_authorised_then_captured_by_signed_webhook` |
| FR-PAY-03 | Failed payments recorded with reason; alert raised | ✅ `test_declined_cards_fail_without_retry_and_alert` |
| FR-PAY-04 | Partial and full refunds (finance only) | ✅ `test_partial_then_full_refund_and_overrefund_rejected` |
| FR-LOY-01 | Earn points on capture; redeem; history | ✅ payment + loyalty tests |
| FR-LOY-02 | Failed syncs kept and retryable | ✅ `test_failed_earn_kept_and_retryable` |
| FR-INT-01 | Show status, last success, failures, latency, retries, errors per integration | ✅ `test_integration_list_configure_health_and_logs` |
| FR-INT-02 | Retry failed integrations; view logs | ✅ retry tests |
| FR-WH-01 | Register outbound webhook subscriptions | ✅ `test_webhook_event_history_and_subscriptions` |
| FR-WH-02 | Verify signatures; store and reject invalid | ✅ `test_invalid_signature_rejected_and_stored` |
| FR-WH-03 | De-duplicate events; replay failed events | ✅ `test_duplicate_webhook_processed_once`, `test_amount_mismatch_webhook_fails_then_replay_after_fix` |
| FR-AUTO-01 | Reconciliation, discrepancy detection, daily summary, branch report, failure notifications, auto-incidents | ✅ `test_automation_tools`, `test_repeated_pos_failures_auto_raise_one_incident` |
| FR-INC-01 | Create, assign, severity, status, RCA, resolution, timeline, escalation, reporting | ✅ `test_incident_lifecycle`, `test_incident_list_and_report` |
| FR-REC-01..06 | Detect missing, duplicate, mismatched, failed, settlement and POS discrepancies; export; import settlements | ✅ `test_reconciliation_matching_logic_detects_every_issue_type`, `test_settlement_csv_import` |
| FR-REP-01 | Daily/monthly sales, branch performance, payment success, order volumes, failed transactions, integration performance, loyalty activity (JSON + CSV) | ✅ `test_every_report_json_and_csv` (9 reports × 2 formats) |
| FR-SEC-01 | OAuth 2.0 password + client-credentials, JWT, RBAC, API keys | ✅ `test_auth_security.py` |
| FR-AUD-01 | Every state change audited; audit log immutable | ✅ audit assertions + `test_audit_log_is_append_only_in_postgres` |

## Non-functional requirements

| ID | Category | Requirement | How met |
|---|---|---|---|
| NFR-01 | Performance | p95 API latency < 300 ms on demo data | `/metrics` reports p50/p95/p99; Newman avg 19 ms locally |
| NFR-02 | Availability | Health/readiness endpoints for orchestrators | `/health`, `/health/ready`, Docker HEALTHCHECK |
| NFR-03 | Resilience | Vendor outage must not lose orders/points | Order stored before POS call; outbox; failed-state + retry |
| NFR-04 | Security | No secrets in code; hashed passwords; signed webhooks; least privilege | `.env`, bcrypt, HMAC, RBAC, key-pair |
| NFR-05 | Security | Card data never stored | Only `card_token` accepted; token masked in logs |
| NFR-06 | Auditability | Append-only audit log with correlation IDs | DB trigger + `X-Request-ID` |
| NFR-07 | Observability | Structured JSON logs; per-call integration logs | `monitoring/logging.py`, `integration_logs` |
| NFR-08 | Data integrity | FK, CHECK, UNIQUE constraints; transactions | `V001__initial_schema.sql` |
| NFR-09 | Maintainability | Lint + typecheck + automated tests in CI | GitHub Actions `ci.yml` |
| NFR-10 | Usability | Responsive UI, loading/error states, form validation | React components; 👁 screenshots |
| NFR-11 | Portability | Starts with `docker compose up` | `docker-compose.yml` (config validated; image build not run here — no Docker daemon) |
| NFR-12 | Localisation | ZAR, en-ZA formatting, SAST business day | `utils/format.ts`, `day_bounds()` |

## User stories with acceptance criteria (Gherkin)

**US-01 Digital order to kitchen** — *As a branch manager I want Uber Eats and Mr D orders to appear in Simphony automatically so staff don't re-key them.*
```gherkin
Given branch DBN-UML has Uber Eats enabled
When Uber Eats posts a valid order
Then TableFlow responds 202 within 1 second
And the order is stored with status "received"
And a Simphony check is created and the order becomes "accepted"
```

**US-02 Duplicate protection** — *As a branch manager I don't want the kitchen to make the same order twice.*
```gherkin
Given an Uber Eats order with id X was accepted
When Uber Eats sends order X again
Then the response says duplicate=true and returns the original order number
And only one order with external_ref X exists
```

**US-03 POS outage** — *As operations I want orders kept and alerts raised when Simphony is down.*
```gherkin
Given Simphony is unavailable
When an order arrives
Then the call is attempted 3 times with exponential back-off
And the order status is "failed" and appears in the POS hub
And a pos_failure notification is queued for n8n
And after 3 consecutive failures one SEV2 incident is auto-created
When Simphony recovers and the engineer clicks Retry
Then the order becomes "accepted"
```

**US-04 Idempotent payment** — *As finance I never want a customer charged twice because a terminal retried.*
```gherkin
Given a payment request with Idempotency-Key K succeeded
When the same request with key K is repeated
Then the original payment is returned with header Idempotent-Replayed: true
When key K is reused with a different order or amount
Then the API returns 409 IDEMPOTENCY_CONFLICT
```

**US-05 Daily reconciliation** — *As the Financial Controller I want a reconciliation by 06:30 every day.*
```gherkin
Given yesterday's orders, payments, POS checks and settlement lines are loaded
When the 06:00 n8n workflow runs
Then each order is classified matched or with one or more of 9 issue types
And the finance channel receives a summary
And discrepancies above R500 raise a SEV3 incident
```

**US-06 Refunds** — *As finance I want to refund part or all of a captured payment, with an audit trail.*
```gherkin
Given a captured payment of R164.70
When finance refunds R50.00 with a reason
Then the payment becomes partially_refunded and an audit entry records who, what and why
When anyone tries to refund more than the remaining balance
Then the API returns 422 REFUND_EXCEEDS_BALANCE
And a branch manager attempting a refund receives 403
```

**US-07 Webhook security** — *As the IT lead I want forged webhooks rejected and recorded.*
```gherkin
Given a webhook whose HMAC signature does not match
When it is posted to /webhooks/inbound/transaction-junction
Then the API returns 401, stores the event as "rejected", and changes nothing
```

**US-08 Incident handling** — *As operations I want incidents tracked to resolution with RCA.*
```gherkin
Given an open incident
When I try to resolve it without resolution notes
Then I get a validation error
When I escalate it
Then escalation level increases, a timeline entry is added and n8n is notified
```

**US-09 Loyalty never lost** — *As marketing I want points kept even if the loyalty platform is down.*

**US-10 Management report** — *As the MD I want a 07:00 digest of yesterday's sales, payments, integration health and open incidents.*
