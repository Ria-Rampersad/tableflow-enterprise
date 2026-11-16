"""Modules 7, 8, 10: Integration Monitoring, Webhook Management, Incident Management."""
import json
import uuid

import pytest
from sqlalchemy import select

from app.models import Payment, WebhookEvent
from app.security import signatures
from tests.conftest import MRD_KEY, UBER_KEY, mrd_payload, set_integration, uber_payload


def tj_event(payment_ref, amount, event_type="payment.captured", event_id=None):
    return json.dumps({"id": event_id or f"evt_{uuid.uuid4().hex[:16]}", "type": event_type,
                       "data": {"transactionId": payment_ref, "amount": str(amount)}}).encode()


def authorised_payment(client, auth, make_order):
    order = make_order()
    r = client.post("/api/v1/payments", params={"auto_capture": False},
                    json={"order_id": order["id"], "amount": order["total"], "card_token": "tok_mc_approved"},
                    headers=auth("operations", **{"Idempotency-Key": f"wh-{uuid.uuid4()}"}))
    assert r.json()["status"] == "authorised"
    return r.json()


def test_valid_webhook_processed(client, auth, make_order):
    p = authorised_payment(client, auth, make_order)
    body = tj_event(p["provider_reference"], p["amount"])
    r = client.post("/api/v1/webhooks/inbound/transaction-junction", content=body,
                    headers={**signatures.sign("transaction_junction", body), "Content-Type": "application/json"})
    assert r.status_code == 200 and r.json()["status"] == "processed"
    assert client.get(f"/api/v1/payments/{p['id']}", headers=auth()).json()["status"] == "captured"


@pytest.mark.regression
def test_invalid_signature_rejected_and_stored(client, auth, db, make_order):
    p = authorised_payment(client, auth, make_order)
    body = tj_event(p["provider_reference"], p["amount"])
    r = client.post("/api/v1/webhooks/inbound/transaction-junction", content=body,
                    headers={"X-TJ-Signature": "t=1,v1=deadbeef"})
    assert r.status_code == 401
    ev = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == r.json()["event_id"]))
    assert ev.status == "rejected" and ev.signature_valid is False
    assert db.get(Payment, p["id"]).status == "authorised"  # nothing changed


@pytest.mark.regression
def test_duplicate_webhook_processed_once(client, auth, db, make_order):
    acc_points_before = None
    p = authorised_payment(client, auth, make_order)
    body = tj_event(p["provider_reference"], p["amount"], event_id=f"evt_dup_{uuid.uuid4().hex[:8]}")
    h = signatures.sign("transaction_junction", body)
    first = client.post("/api/v1/webhooks/inbound/transaction-junction", content=body, headers=h).json()
    second = client.post("/api/v1/webhooks/inbound/transaction-junction", content=body, headers=h).json()
    assert first["status"] == "processed" and second["status"] == "processed"
    ev = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == first["event_id"]))
    db.refresh(ev)
    assert ev.attempts == 2  # second delivery counted, not re-processed
    assert acc_points_before is None


@pytest.mark.regression
def test_amount_mismatch_webhook_fails_then_replay_after_fix(client, auth, db, make_order):
    p = authorised_payment(client, auth, make_order)
    body = tj_event(p["provider_reference"], "1.00")
    r = client.post("/api/v1/webhooks/inbound/transaction-junction", content=body,
                    headers=signatures.sign("transaction_junction", body))
    assert r.json()["status"] == "failed"
    ev = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == r.json()["event_id"]))
    # engineer corrects the stored payload (e.g. after confirming with the gateway) and replays
    ev.payload = {**ev.payload, "data": {**ev.payload["data"], "amount": p["amount"]}}
    db.commit()
    rr = client.post(f"/api/v1/webhooks/events/{ev.id}/replay", headers=auth("integration_engineer"))
    assert rr.status_code == 200 and rr.json()["status"] == "processed" and rr.json()["attempts"] == 2
    assert client.post(f"/api/v1/webhooks/events/{ev.id}/replay",
                       headers=auth("integration_engineer")).status_code == 409


def test_uber_eats_cancel_webhook(client, auth):
    payload = uber_payload()
    oid = client.post("/api/v1/partners/uber-eats/orders", json=payload, headers=UBER_KEY).json()["order_id"]
    body = json.dumps({"event_id": str(uuid.uuid4()), "event_type": "orders.cancel",
                       "meta": {"resource_id": payload["id"], "reason": "Eater cancelled"}}).encode()
    r = client.post("/api/v1/webhooks/inbound/uber-eats", content=body, headers=signatures.sign("uber_eats", body))
    assert r.json()["status"] == "processed"
    assert client.get(f"/api/v1/orders/{oid}", headers=auth()).json()["status"] == "cancelled"


def test_mr_d_cancel_webhook_and_unknown_order(client, auth):
    payload = mrd_payload()
    oid = client.post("/api/v1/partners/mr-d/orders", json=payload, headers=MRD_KEY).json()["order_id"]
    body = json.dumps({"eventId": str(uuid.uuid4()), "eventType": "ORDER_CANCELLED",
                       "orderReference": payload["orderReference"], "reason": "Store closed"}).encode()
    r = client.post("/api/v1/webhooks/inbound/mr-d", content=body, headers=signatures.sign("mr_d", body))
    assert r.json()["status"] == "processed"
    assert client.get(f"/api/v1/orders/{oid}", headers=auth()).json()["status"] == "cancelled"
    body2 = json.dumps({"eventId": str(uuid.uuid4()), "eventType": "ORDER_CANCELLED",
                        "orderReference": "MRD-DOESNOTEXIST"}).encode()
    r2 = client.post("/api/v1/webhooks/inbound/mr-d", content=body2, headers=signatures.sign("mr_d", body2))
    assert r2.json()["status"] == "failed"


def test_webhook_event_history_and_subscriptions(client, auth):
    ev = client.get("/api/v1/webhooks/events", params={"status": "rejected"}, headers=auth()).json()
    assert ev["total"] >= 1 and all(e["status"] == "rejected" for e in ev["items"])
    sub = {"name": "Finance ERP", "target_url": "https://erp.example.invalid/hooks", "event_types": ["payment.failed"]}
    r = client.post("/api/v1/webhooks/subscriptions", json=sub, headers=auth("integration_engineer"))
    assert r.status_code == 201
    upd = client.put(f"/api/v1/webhooks/subscriptions/{r.json()['id']}", json={**sub, "is_active": False},
                     headers=auth("integration_engineer"))
    assert upd.json()["is_active"] is False
    bad = client.post("/api/v1/webhooks/subscriptions", json={**sub, "target_url": "ftp://x"},
                      headers=auth("integration_engineer"))
    assert bad.status_code == 422


# ------------------------------------------------------------------ integration monitoring
def test_integration_list_configure_health_and_logs(client, auth):
    items = client.get("/api/v1/integrations", headers=auth()).json()
    assert {i["name"] for i in items} >= {"micros_simphony", "transaction_junction", "uber_eats", "mr_d",
                                          "loyalty_platform", "finance_gl", "backoffice_inventory"}
    assert all(i["mode"] == "simulated" for i in items)
    tj = next(i for i in items if i["name"] == "transaction_junction")
    r = client.patch(f"/api/v1/integrations/{tj['id']}", json={"simulate_outage": True},
                     headers=auth("integration_engineer"))
    assert r.json()["config"]["simulate_outage"] is True
    hc = client.post(f"/api/v1/integrations/{tj['id']}/health-check", headers=auth("integration_engineer")).json()
    assert hc["ok"] is False and hc["status"] in ("degraded", "down")
    logs = client.get(f"/api/v1/integrations/{tj['id']}/logs", params={"status": "failed"}, headers=auth()).json()
    assert logs["total"] >= 1
    assert client.patch(f"/api/v1/integrations/{tj['id']}", json={"failure_rate": 2},
                        headers=auth("integration_engineer")).status_code == 422
    assert client.patch(f"/api/v1/integrations/{tj['id']}", json={"simulate_outage": False},
                        headers=auth("finance")).status_code == 403


def test_health_check_automation_reports_down(client, auth):
    set_integration("uber_eats", simulate_outage=True)
    r = client.post("/api/v1/automation/integration-health-check", headers=auth("operations")).json()
    ue = next(x for x in r["results"] if x["integration"] == "uber_eats")
    assert ue["ok"] is False


# ------------------------------------------------------------------ incidents
def test_incident_lifecycle(client, auth, tokens):
    body = {"title": "Payment gateway latency spike", "severity": "SEV2", "category": "payment",
            "description": "p95 > 3s"}
    inc = client.post("/api/v1/incidents", json=body, headers=auth("operations")).json()
    assert inc["reference"].startswith("INC-") and inc["events"][0]["event_type"] == "created"
    iid = inc["id"]
    users = client.get("/api/v1/auth/users", headers=auth()).json()
    eng = next(u for u in users if u["role"] == "integration_engineer")
    r = client.patch(f"/api/v1/incidents/{iid}", json={"status": "investigating", "assigned_to_id": eng["id"]},
                     headers=auth("operations"))
    assert r.json()["status"] == "investigating" and r.json()["assigned_to_id"] == eng["id"]
    esc = client.post(f"/api/v1/incidents/{iid}/escalate", json={"reason": "Customer impact growing"},
                      headers=auth("operations")).json()
    assert esc["escalation_level"] == 1
    no_notes = client.patch(f"/api/v1/incidents/{iid}", json={"status": "resolved"}, headers=auth("operations"))
    assert no_notes.status_code == 422
    done = client.patch(f"/api/v1/incidents/{iid}", json={"status": "resolved", "root_cause": "Provider DNS",
                                                          "resolution_notes": "Provider fixed DNS; monitored 30m"},
                        headers=auth("operations")).json()
    assert done["status"] == "resolved" and done["resolved_at"]
    bad = client.patch(f"/api/v1/incidents/{iid}", json={"status": "open"}, headers=auth("operations"))
    assert bad.status_code == 409
    types = [e["event_type"] for e in done["events"]]
    assert {"created", "status_change", "assignment", "escalation"} <= set(types)
    assert client.post(f"/api/v1/incidents/{iid}/escalate", json={}, headers=auth("operations")).status_code == 409


def test_incident_list_and_report(client, auth):
    r = client.get("/api/v1/incidents", params={"open_only": True}, headers=auth()).json()
    assert all(i["status"] in ("open", "investigating", "mitigated") for i in r["items"])
    rep = client.get("/api/v1/incidents/report", headers=auth()).json()
    assert rep["total"] >= 1 and "by_severity" in rep
