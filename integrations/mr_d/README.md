# Mr D ordering adapter — SIMULATED

**Code:** `backend/app/integrations/ordering.py (MrDAdapter)`  
**Operations:** inbound order mapping (amounts in Rand), status push, ORDER_CANCELLED webhook (X-MrD-Signature)

## Sample payloads
- `sample_cancel_webhook.json`
- `sample_order.json`

## Limitations of the simulation
Mr D has no public API documentation; this contract is entirely fictional and exists to show how a second provider with a different shape maps into the same canonical order.

Full explanation: `documentation/04_INTEGRATION_ENGINEERING_HANDBOOK.md`.
