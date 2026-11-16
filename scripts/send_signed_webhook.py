"""Sign a JSON payload exactly like a provider would and POST it to TableFlow's inbound webhook endpoint.

    python scripts/send_signed_webhook.py transaction-junction integrations/transaction_junction/sample_captured_webhook.json
    python scripts/send_signed_webhook.py uber-eats integrations/uber_eats/sample_cancel_webhook.json --tamper

Secrets are read from the same environment variables as the backend (defaults = dev values).
"""
import argparse
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.security.signatures import sign  # noqa: E402

SOURCES = {"transaction-junction": "transaction_junction", "uber-eats": "uber_eats", "mr-d": "mr_d"}
ap = argparse.ArgumentParser()
ap.add_argument("provider", choices=SOURCES)
ap.add_argument("payload")
ap.add_argument("--url", default="http://localhost:8000")
ap.add_argument("--tamper", action="store_true", help="modify the body after signing (should be rejected with 401)")
a = ap.parse_args()
body = Path(a.payload).read_bytes()
headers = {**sign(SOURCES[a.provider], body), "Content-Type": "application/json"}
if a.tamper:
    body = body.replace(b"}", b' , "tampered": true}', 1) if b"}" in body else body + b" "
r = httpx.post(f"{a.url}/api/v1/webhooks/inbound/{a.provider}", content=body, headers=headers)
print(r.status_code, r.text)
