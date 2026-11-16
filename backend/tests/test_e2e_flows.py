"""End-to-end business scenarios through the public API only (no direct DB writes)."""
import io
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.security import signatures
from tests.conftest import UBER_KEY, set_integration, uber_payload


def today_sast():
    return (datetime.now(timezone.utc) + timedelta(hours=2)).date()


@pytest.mark.regression
def test_e2e_digital_order_to_reconciled(client, auth, tokens):
    """Uber Eats order -> POS -> payment -> signed webhook -> loyalty -> POS sync -> settlement -> recon matched."""
    accounts = client.get("/api/v1/loyalty/accounts", params={"limit": 1}, headers=auth()).json()["items"]
    member = accounts[0]
    payload = uber_payload(branch_code="JHB-RSB", phone=member["phone"],
                           items=(("MEAL-FAM", 1, 35990), ("DRK-CAN", 2, 2190)))
    # 1-5. provider sends order; validated, stored, forwarded to POS
    r = client.post("/api/v1/partners/uber-eats/orders", json=payload, headers=UBER_KEY)
    assert r.status_code == 202
    order = client.get(f"/api/v1/orders/{r.json()['order_id']}", headers=auth()).json()
    assert order["status"] == "accepted" and order["pos_check_ref"]
    # 6-7. payment authorised, webhook captures
    pay = client.post("/api/v1/payments", json={"order_id": order["id"], "amount": order["total"],
                                                "card_token": "tok_visa_approved"},
                      headers=auth("operations", **{"Idempotency-Key": f"e2e-{uuid.uuid4()}"})).json()
    assert client.get(f"/api/v1/payments/{pay['id']}", headers=auth()).json()["status"] == "captured"
    # 8. loyalty points updated
    acc = client.get(f"/api/v1/loyalty/accounts/{member['id']}", headers=auth()).json()
    assert acc["account"]["points_balance"] == member["points_balance"] + 40  # R403.70 -> 40 points
    # 9. n8n notifications recorded in the outbox
    wfs = {n["workflow"] for n in client.get("/api/v1/notifications", params={"limit": 20},
                                             headers=auth()).json()["items"]}
    assert {"new_order", "loyalty_update"} <= wfs
    # kitchen flow
    for s in ("preparing", "ready", "completed"):
        assert client.patch(f"/api/v1/orders/{order['id']}/status", json={"status": s},
                            headers=auth("operations")).status_code == 200
    # POS closed checks + acquirer settlement for today
    d = today_sast().isoformat()
    sync = client.post(f"/api/v1/pos/branches/{order['branch_id']}/transaction-sync", params={"business_date": d},
                       headers=auth("finance")).json()
    assert sync["ok"]
    csv_text = f"provider_reference,branch_code,amount,fee,business_date\n{pay['provider_reference']},JHB-RSB," \
               f"{pay['amount']},7.06,{d}\n"
    client.post("/api/v1/reconciliation/settlements/import", headers=auth("finance"),
                files={"file": ("s.csv", io.BytesIO(csv_text.encode()), "text/csv")})
    # 10. reconciliation: this order must not appear as a discrepancy
    run = client.post("/api/v1/reconciliation/runs", json={"business_date": d, "branch_id": order["branch_id"]},
                      headers=auth("finance")).json()
    assert all(rec["order_id"] != order["id"] for rec in run["records"])
    # audit trail captured each step
    audit = client.get("/api/v1/audit-logs", params={"limit": 200}, headers=auth()).json()["items"]
    actions = {a["action"] for a in audit}
    assert {"order.created", "order.forwarded_to_pos", "payment.created", "reconciliation.run"} <= actions


def test_e2e_failure_path_pos_down_then_recovered_and_cancel_via_webhook(client, auth):
    set_integration("micros_simphony", simulate_outage=True)
    payload = uber_payload()
    oid = client.post("/api/v1/partners/uber-eats/orders", json=payload, headers=UBER_KEY).json()["order_id"]
    assert client.get(f"/api/v1/orders/{oid}", headers=auth()).json()["status"] == "failed"
    pos = client.get("/api/v1/pos/status", headers=auth()).json()
    assert any(o["id"] == oid for o in pos["failed_orders"])
    set_integration("micros_simphony", simulate_outage=False)
    assert client.post(f"/api/v1/orders/{oid}/forward-to-pos", headers=auth("operations")).json()["forwarded"]
    body = json.dumps({"event_id": str(uuid.uuid4()), "event_type": "orders.cancel",
                       "meta": {"resource_id": payload["id"]}}).encode()
    client.post("/api/v1/webhooks/inbound/uber-eats", content=body, headers=signatures.sign("uber_eats", body))
    assert client.get(f"/api/v1/orders/{oid}", headers=auth()).json()["status"] == "cancelled"


def test_demo_simulators(client, auth):
    r = client.post("/api/v1/simulate/partner-order", json={"provider": "mr_d", "branch_code": "DBN-PNT"},
                    headers=auth("integration_engineer")).json()
    assert r["result"]["accepted"] and not r["result"]["duplicate"]
    ref = r["provider_payload"]["orderReference"]
    dup = client.post("/api/v1/simulate/partner-order", json={"provider": "mr_d", "branch_code": "DBN-PNT",
                                                              "repeat_external_ref": ref},
                      headers=auth("integration_engineer")).json()
    assert dup["result"]["duplicate"] is True
    bad = client.post("/api/v1/simulate/partner-order", json={"provider": "uber_eats", "corrupt_total": True},
                      headers=auth("integration_engineer"))
    assert bad.status_code == 422
    c = client.post("/api/v1/simulate/provider-cancel", json={"order_id": r["result"]["order_id"]},
                    headers=auth("operations")).json()
    assert c["event_status"] == "processed"
    forged = client.post("/api/v1/simulate/bad-signature-webhook", headers=auth("operations")).json()
    assert forged["http_status"] == 401 and forged["event_status"] == "rejected"
    assert client.post("/api/v1/simulate/partner-order", json={"provider": "mr_d"},
                       headers=auth("finance")).status_code == 403
