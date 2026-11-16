"""Modules 3 & 4: POS Integration Hub (Micros Simphony) and Digital Ordering (Uber Eats, Mr D)."""
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Incident, IntegrationLog, Notification, Order
from tests.conftest import MRD_KEY, UBER_KEY, mrd_payload, set_integration, uber_payload


@pytest.mark.regression
def test_in_store_order_is_validated_priced_and_sent_to_pos(make_order):
    order = make_order(items=[{"sku": "CHK-HLF", "quantity": 1}, {"sku": "SIDE-CHP", "quantity": 2}])
    assert order["status"] == "accepted" and order["pos_check_ref"].startswith("SIM-LOC")
    assert Decimal(order["total"]) == Decimal("164.70")  # 104.90 + 2 x 29.90
    assert Decimal(order["vat"]) == Decimal("21.48")  # 164.70 x 15/115
    assert Decimal(order["subtotal"]) + Decimal(order["vat"]) == Decimal(order["total"])


def test_unknown_sku_rejected_with_business_error(client, auth, db):
    from app.models import Branch

    b = db.scalar(select(Branch).where(Branch.code == "DBN-UML"))
    r = client.post("/api/v1/orders", json={"branch_id": b.id, "items": [{"sku": "NOPE-1", "quantity": 1}]},
                    headers=auth("operations"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNKNOWN_SKU"


def test_order_payload_validation(client, auth):
    r = client.post("/api/v1/orders", json={"branch_id": 1, "items": [{"sku": "CHK-QTR", "quantity": 0}],
                                            "customer_phone": "12345"}, headers=auth("operations"))
    assert r.status_code == 422
    fields = {tuple(d["loc"][-2:]) if d["loc"][-1] == "quantity" else d["loc"][-1]
              for d in r.json()["error"]["details"]}
    assert "customer_phone" in fields


def test_uber_eats_order_accepted_mapped_and_forwarded(client, db):
    payload = uber_payload()
    r = client.post("/api/v1/partners/uber-eats/orders", json=payload, headers=UBER_KEY)
    assert r.status_code == 202 and r.json()["duplicate"] is False
    order = db.get(Order, r.json()["order_id"])
    db.refresh(order)
    assert order.channel == "uber_eats" and order.external_ref == payload["id"]
    assert order.total == Decimal("161.70") and order.status == "accepted" and order.pos_check_ref
    assert order.customer.phone == "+27821234567"


@pytest.mark.regression
def test_duplicate_uber_order_is_not_created_twice(client, db):
    payload = uber_payload()
    first = client.post("/api/v1/partners/uber-eats/orders", json=payload, headers=UBER_KEY).json()
    second = client.post("/api/v1/partners/uber-eats/orders", json=payload, headers=UBER_KEY).json()
    assert second["duplicate"] is True and second["order_id"] == first["order_id"]
    count = db.scalar(select(func.count(Order.id)).where(Order.external_ref == payload["id"]))
    assert count == 1


def test_partner_api_key_required(client):
    assert client.post("/api/v1/partners/uber-eats/orders", json=uber_payload()).status_code == 401
    assert client.post("/api/v1/partners/uber-eats/orders", json=uber_payload(),
                       headers=MRD_KEY).status_code == 401  # Mr D key is not valid for Uber endpoint


def test_malformed_partner_payload_422(client):
    r = client.post("/api/v1/partners/uber-eats/orders", json={"id": "x", "cart": {}}, headers=UBER_KEY)
    assert r.status_code == 422 and "Invalid Uber Eats payload" in r.json()["error"]["message"]


@pytest.mark.regression
def test_partner_total_mismatch_rejected(client):
    r = client.post("/api/v1/partners/uber-eats/orders", json=uber_payload(total=100), headers=UBER_KEY)
    assert r.status_code == 422 and r.json()["error"]["code"] == "TOTAL_MISMATCH"


def test_channel_not_enabled_for_branch(client):
    # DBN-PNT only trades on Mr D
    r = client.post("/api/v1/partners/uber-eats/orders", json=uber_payload(branch_code="DBN-PNT"), headers=UBER_KEY)
    assert r.status_code == 422 and r.json()["error"]["code"] == "CHANNEL_DISABLED"


def test_mr_d_order_and_cancellation(client, db):
    payload = mrd_payload()
    r = client.post("/api/v1/partners/mr-d/orders", json=payload, headers=MRD_KEY)
    assert r.status_code == 202
    order = db.get(Order, r.json()["order_id"])
    assert order.total == Decimal("104.80") and order.customer.phone == "+27731234567"
    c = client.post(f"/api/v1/partners/mr-d/orders/{payload['orderReference']}/cancel",
                    json={"reason": "Driver unavailable"}, headers=MRD_KEY)
    assert c.status_code == 200 and c.json()["status"] == "cancelled"


@pytest.mark.regression
def test_status_transitions(client, auth, make_order):
    order = make_order()
    url = f"/api/v1/orders/{order['id']}/status"
    assert client.patch(url, json={"status": "preparing"}, headers=auth("branch_manager")).status_code == 200
    bad = client.patch(url, json={"status": "accepted"}, headers=auth("operations"))
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "INVALID_TRANSITION"
    assert client.patch(url, json={"status": "cancelled"}, headers=auth("operations")).status_code == 422
    assert client.patch(url, json={"status": "ready"}, headers=auth("operations")).json()["status"] == "ready"
    assert client.patch(url, json={"status": "completed"}, headers=auth("operations")).json()["status"] == "completed"


@pytest.mark.regression
def test_pos_outage_marks_order_failed_alerts_and_retry_recovers(client, auth, db, make_order):
    set_integration("micros_simphony", simulate_outage=True)
    order = make_order()
    assert order["status"] == "failed" and order["pos_check_ref"] is None
    logs = db.scalars(select(IntegrationLog).where(IntegrationLog.entity_type == "order",
                                                   IntegrationLog.entity_id == order["id"])
                      .order_by(IntegrationLog.attempt)).all()
    assert [entry.status for entry in logs] == ["retrying", "retrying", "failed"]  # 3 attempts with backoff
    note = db.scalar(select(Notification).where(Notification.workflow == "pos_failure")
                     .order_by(Notification.id.desc()))
    assert note.payload["order_number"] == order["order_number"]

    set_integration("micros_simphony", simulate_outage=False)
    r = client.post(f"/api/v1/integrations/logs/{logs[-1].id}/retry", headers=auth("integration_engineer"))
    assert r.status_code == 200 and r.json()["ok"] is True
    assert client.get(f"/api/v1/orders/{order['id']}", headers=auth()).json()["status"] == "accepted"


def test_repeated_pos_failures_auto_raise_one_incident(client, db, make_order):
    set_integration("micros_simphony", simulate_outage=True)
    before = db.scalar(select(func.count(Incident.id)).where(Incident.source == "automated",
                                                             Incident.status == "open"))
    for _ in range(4):
        make_order()
    db.expire_all()
    incidents = db.scalars(select(Incident).where(Incident.title.like("%Simphony integration down%"),
                                                  Incident.status == "open")).all()
    assert len(incidents) == 1 and incidents[0].severity == "SEV2"
    assert db.scalar(select(func.count(Incident.id)).where(Incident.source == "automated",
                                                           Incident.status == "open")) == before + 1


def test_menu_sync_and_transaction_sync(client, auth, db, make_order):
    from datetime import datetime, timedelta, timezone

    from app.models import Branch, PosTransaction

    b = db.scalar(select(Branch).where(Branch.code == "DBN-UML"))
    r = client.post(f"/api/v1/pos/branches/{b.id}/menu-sync", headers=auth("integration_engineer")).json()
    assert r["ok"] and r["items"] == 24 and r["unmapped_skus"] == []
    order = make_order()
    today = (datetime.now(timezone.utc) + timedelta(hours=2)).date()
    s = client.post(f"/api/v1/pos/branches/{b.id}/transaction-sync", params={"business_date": today.isoformat()},
                    headers=auth("finance")).json()
    assert s["ok"] and s["inserted"] >= 1
    assert db.scalar(select(PosTransaction).where(PosTransaction.order_id == order["id"])) is not None
    status = client.get("/api/v1/pos/status", headers=auth()).json()
    assert status["integration"]["name"] == "micros_simphony"


def test_list_orders_filters_and_branch_manager_scope(client, auth):
    r = client.get("/api/v1/orders", params={"channel": "uber_eats", "limit": 5}, headers=auth())
    assert r.status_code == 200 and all(o["channel"] == "uber_eats" for o in r.json()["items"])
    mine = client.get("/api/v1/orders", params={"limit": 50}, headers=auth("branch_manager")).json()["items"]
    assert len({o["branch_id"] for o in mine}) == 1
