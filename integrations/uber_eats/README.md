# Uber Eats ordering adapter — SIMULATED

**Code:** `backend/app/integrations/ordering.py (UberEatsAdapter)`  
**Operations:** inbound order mapping (amounts in cents), status push, cancel webhook (X-Uber-Signature HMAC)

## Sample payloads
- `sample_cancel_webhook.json`
- `sample_order.json`

## Limitations of the simulation
Payload shape is modelled on Uber's public Order API descriptions; production use requires Uber Eats Marketplace partner onboarding.

Full explanation: `documentation/04_INTEGRATION_ENGINEERING_HANDBOOK.md`.
