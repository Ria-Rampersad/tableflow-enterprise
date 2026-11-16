# Transaction Junction-style payment adapter — SIMULATED

**Code:** `backend/app/integrations/transaction_junction.py`  
**Operations:** authorise (idempotent by Idempotency-Key), refund, signed webhooks (payment.captured / payment.failed / refund.completed), settlement CSV import

## Sample payloads
- `sample_authorise_request.json`
- `sample_authorise_response.json`
- `sample_captured_webhook.json`
- `sample_settlement.csv`

## Limitations of the simulation
Uses ISO 8583-style response codes and test card tokens. No merchant account or TJ sandbox credentials exist in this project; the real message specification is available only to TJ clients.

Full explanation: `documentation/04_INTEGRATION_ENGINEERING_HANDBOOK.md`.
