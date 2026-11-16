# 04 · Integration Engineering Handbook

## 1. Simulated vs live integrations — read this first

| Aspect | In this project (simulated) | A live integration additionally needs |
|---|---|---|
| Transport | Adapter method returns data in-process; latency and failures are *simulated* from `integrations.config` | HTTPS client (httpx) with timeouts, TLS, sometimes mTLS/IP allow-listing |
| Contract | Modelled on public descriptions/industry patterns; **not** vendor specifications | Vendor API docs, sandbox, certification/test scripts |
| Credentials | None | OAuth2 client id/secret, API keys, certificates — stored in a secret manager |
| Data | Generated | Real menus, locations, merchant IDs |
| Mode flag | `integrations.mode = 'simulated'` (shown in UI) | `sandbox` then `live` after sign-off |

Everything *around* the transport is real and tested: canonical mapping, validation, idempotency, retries,
logging, health, incidents, signature verification, replay, reconciliation. Replacing a simulated adapter means
re-implementing its methods with HTTP calls — callers do not change.

## 2. Integration patterns used
1. **Adapter + canonical model** — provider payload → `CanonicalOrder` → one set of business rules.
2. **Single outbound choke-point** — `IntegrationRunner.call()`.
3. **Idempotent receiver** — orders `(channel, external_ref)`, payments `Idempotency-Key`, webhooks `(source, event_id)`.
4. **Retry with exponential back-off**; classify errors as retryable vs permanent.
5. **Circuit-breaker-lite** — consecutive-failure counter drives `degraded`/`down` and raises an incident; a success closes it.
6. **Transactional outbox** — notifications written in the same DB transaction, dispatched asynchronously.
7. **Async acknowledgement** — partners get 202 immediately; POS forwarding runs in the background.
8. **Store-and-replay** — every inbound webhook is persisted; failed ones can be replayed.

## 3. POS — Oracle MICROS Simphony adapter (`integrations/micros_simphony.py`)
| Operation | Called by | Request (key fields) | Response | Errors |
|---|---|---|---|---|
| `create_check` | `orders.forward_to_pos` | `locRef`, `orderNumber`, items with `pos_item_ref`, total | `checkRef`, `checkNum`, `revenueCenter` (2 for delivery), `orderType`, `status=OPEN` | 400 no locRef; 422 unmapped menu items (permanent); 503/504 (retryable) |
| `update_check_status` | `orders.change_status` | `checkRef`, status | echoed status | 400 |
| `get_menu` | `pos.menu_sync` | `locRef` | `menuItems[]` (`menuItemId`, `name{en-US}`, `familyGroup`, `prices[]`) | transport |
| `get_closed_checks` | `pos.transaction_sync` | `locRef`, `busDt` | `checks[]` (`checkRef`, `totalDue`, `tenderType`) | transport |
**Data mapping**: `products.pos_item_ref` ↔ `menuItemId`; `branches.pos_location_ref` ↔ `locRef`; `orders.pos_check_ref` ↔ `checkRef`.
**Live version**: Simphony cloud APIs are accessed with OAuth 2.0 against an organisation/location hierarchy; check posting requires revenue-centre, order-type and tender configuration agreed with the POS administrator.

## 4. Payments — Transaction Junction-style adapter (`integrations/transaction_junction.py`)
- `authorise(amount, currency, card_token, merchant_ref, idempotency_key)` → `transactionId` (deterministic from the idempotency key), `responseCode`, `authCode`.
- Response codes: `00` approved · `05` do not honour · `51` insufficient funds · `54` expired · `14` invalid card (all **permanent**) · `91` issuer/switch inoperative (**retryable**).
- `refund(transaction_id, amount, reason)` → `refundId`.
- Webhooks in: `payment.captured`, `payment.failed`, `refund.completed`, header `X-TJ-Signature: t=<unix>,v1=<hex HMAC of "t.body">`.
- Settlement: CSV import (`provider_reference,branch_code,amount,fee,business_date`).
- **Why tokens only**: TableFlow never sees card numbers, keeping it out of PCI DSS cardholder-data scope.
- **Live version**: merchant onboarding, terminal/merchant IDs, TJ's message specification, certification. No such account exists here — the adapter is *sandbox-ready architecture*, not a claim of a working TJ integration.

## 5. Uber Eats adapter (`integrations/ordering.py: UberEatsAdapter`)
Mapping: `id`→`external_ref`; `store.external_reference_id`→`branch_code`; `eater.first_name/last_name/phone`→customer;
`cart.items[].external_data`→SKU, `quantity`, `price.unit_price.amount` (**cents**)→Rand; `payment.charges.total.amount`→total;
`cart.special_instructions`→notes. Status push vocabulary: accepted→`ACCEPTED`, ready→`READY_FOR_PICKUP`,
completed→`COMPLETED`, cancelled→`DENIED`. Cancel webhook `orders.cancel` with `meta.resource_id`, header
`X-Uber-Signature` (HMAC of body). Sample: `integrations/uber_eats/`.

## 6. Mr D adapter (`MrDAdapter`)
Mapping: `orderReference`, `restaurant.branchCode`, `customer.name/mobile` (local 0… format → normalised to +27),
`lines[].productCode/qty/unitPrice` (**Rand**), `orderTotal`. Status vocabulary CONFIRMED / IN_KITCHEN / READY /
COLLECTED / REJECTED. Webhook `ORDER_CANCELLED`, header `X-MrD-Signature: sha256=<hex>`. **Entirely fictional
contract** — it exists to show a second provider with different units, naming and signing mapped into the same
canonical model.

## 7. Loyalty adapter (`integrations/loyalty.py`)
`post_transaction(member_number, txn_type, points, reference)` → `transactionRef`. 404 member not found
(permanent); transport errors retryable. Ledger-first design: the local `loyalty_transactions` row exists before
the push, so a failure never loses points.

## 8. Back-office & finance adapters (`integrations/backoffice.py`)
`FinanceSystemAdapter.post_journal` rejects unbalanced journals (422, permanent). `BackOfficeAdapter.get_stock_levels`
is the source for low-stock automation.

## 9. REST communication details
- Timeouts: n8n dispatcher 5 s (`N8N_TIMEOUT_SECONDS`); live adapters should use connect 3 s / read 10 s.
- Headers in: `X-API-Key`, `Idempotency-Key`, `X-Request-ID`, signature headers. Out: `X-Request-ID`, `Idempotent-Replayed`, `Retry-After`.
- Content: JSON; money as decimal strings; Uber cents converted at the edge.

## 10. Webhook processing (`webhooks/processor.py`)
Pipeline: raw bytes → verify → parse/identify → reject | duplicate | store → handle in savepoint → processed/failed.
Status meanings: `processed` (done or no handler), `failed` (business error, replayable), `rejected`
(bad signature/payload, never processed), `duplicate` (reserved; duplicates are counted via `attempts`).
Return codes: 200 (incl. duplicates and business failures — retrying would not help), 401 bad signature, 400 unparseable.
Try it: `python scripts/send_signed_webhook.py transaction-junction integrations/transaction_junction/sample_captured_webhook.json [--tamper]`.

## 11. Authentication matrix
| Edge | Mechanism | Secret storage |
|---|---|---|
| Providers → TableFlow (orders) | API key per provider | `PARTNER_API_KEYS` env |
| Providers → TableFlow (webhooks) | HMAC-SHA256 (+timestamp) | `WEBHOOK_SECRET_*` env |
| n8n → TableFlow | OAuth2 client credentials → JWT | `api_clients.client_secret_hash` (bcrypt); n8n env |
| TableFlow → Snowflake | RSA key-pair | private key file path in env |
| Staff → TableFlow | OAuth2 password grant → JWT | `users.password_hash` (bcrypt) |

## 12. Retry strategy
`RETRY_MAX_ATTEMPTS=3`, `RETRY_BASE_DELAY_SECONDS=0.2` → waits 0.2 s, 0.4 s. Production guidance: add jitter
(±20%) to avoid thundering herds; respect `Retry-After` on 429; never retry non-idempotent vendor calls without an
idempotency key; push long retries to a queue (n8n workflow 04 retries loyalty asynchronously).

## 13. Error handling
| Error class | Example | Handling |
|---|---|---|
| Validation | bad payload | 422 at the edge; nothing stored |
| Business | unknown SKU, total mismatch | 422 with code; nothing stored |
| Permanent vendor | declined card, unmapped item | no retry; entity marked failed; alert |
| Transient vendor | timeout, 503, 91 | retry; then failed + health degraded; incident at threshold |
| Duplicate | provider retry | return original |
| Unexpected | bug | 500 with correlation id; logged with stack trace |

## 14. Idempotency — summary
| Inbound | Key | Enforcement | Duplicate response |
|---|---|---|---|
| Partner order | (channel, external_ref) | lookup + UNIQUE + savepoint | 202 `duplicate: true` |
| Payment | `Idempotency-Key` header | lookup + UNIQUE; body comparison | 200 + `Idempotent-Replayed`; 409 if body differs |
| Webhook | (source, event_id) | lookup + UNIQUE | 200, attempts+1 |
| Loyalty earn | (account, order, type) | lookup + UNIQUE | skipped |
| Settlement import | provider_reference | pre-load set + UNIQUE | counted as skipped |

## 15. n8n integration
TableFlow → n8n: outbox paths in `WORKFLOW_PATHS` must equal webhook node paths (contract test enforces).
n8n → TableFlow: "Get API token" node (client credentials) then bearer header on every HTTP node. Alerts:
Slack-compatible JSON to `ALERT_WEBHOOK_URL` (default: TableFlow's `/api/v1/alerts/sink` with `X-Alert-Token`).
Setup: `docker compose up -d n8n && docker compose --profile setup run --rm n8n-import`, then activate workflows
in the n8n UI. Without n8n: `bash scripts/run_n8n_workflows_locally.sh`.

## 16. Adding a new provider (e.g. "Bolt Food") — checklist
1. Add channel to `ORDER_CHANNELS` + a migration altering `ck_order_channel`.
2. `BoltFoodAdapter.to_canonical` + `push_status` in `ordering.py`; register in `ORDERING_ADAPTERS`.
3. Partner endpoint with `require_partner_key("bolt_food")`; key in env.
4. Webhook source in `signatures.py` + `HANDLERS` + `SOURCES`.
5. Seed/insert an `integrations` row; tests mirroring `test_uber_eats_*`; Postman requests; docs.
