# Integration contracts & sample payloads

Adapter **code** lives in `backend/app/integrations/`. This folder holds the provider-facing contracts and sample payloads used in tests, Postman and demos.

All vendor integrations are **simulated** (mode = `simulated` on every row of the `integrations` table). See each sub-folder README for what a live integration would additionally require.

Send a sample yourself:
```bash
curl -X POST localhost:8000/api/v1/partners/uber-eats/orders -H 'X-API-Key: dev-uber-key-change-me' \
  -H 'Content-Type: application/json' -d @integrations/uber_eats/sample_order.json
python scripts/send_signed_webhook.py transaction-junction integrations/transaction_junction/sample_captured_webhook.json
```
