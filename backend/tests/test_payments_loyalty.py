"""Modules 5 & 6: Payment Integration Hub (Transaction Junction-style) and Loyalty."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import IntegrationLog, LoyaltyAccount, LoyaltyTransaction, Notification, Order
from tests.conftest import set_integration


def pay(client, auth, order, token="tok_visa_approved", key=None, amount=None, role="operations", **params):
    return client.post("/api/v1/payments", params=params,
                       json={"order_id": order["id"], "amount": amount or order["total"], "card_token": token},
                       headers=auth(role, **{"Idempotency-Key": key or f"test-{uuid.uuid4()}"}))


def loyalty_phone(db):
    acc = db.scalars(select(LoyaltyAccount)).first()
    return acc, "0" + acc.customer.phone[3:]


@pytest.mark.regression
def test_approved_payment_is_authorised_then_captured_by_signed_webhook(client, auth, db, make_order):
    acc, phone = loyalty_phone(db)
    before = acc.points_balance
    order = make_order(phone=phone)
    r = pay(client, auth, order)
    assert r.status_code == 201 and r.json()["provider_reference"].startswith("TJ")
    # background task delivered the gateway webhook -> captured + loyalty earned
    p = client.get(f"/api/v1/payments/{r.json()['id']}", headers=auth()).json()
    assert p["status"] == "captured"
    db.refresh(acc)
    assert acc.points_balance == before + int(Decimal(order["total"]) // 10)


@pytest.mark.regression
def test_idempotent_replay_returns_same_payment(client, auth, make_order):
    order = make_order()
    key = f"idem-{uuid.uuid4()}"
    a = pay(client, auth, order, key=key)
    b = pay(client, auth, order, key=key)
    assert a.status_code == 201 and b.status_code == 200
    assert a.json()["id"] == b.json()["id"] and b.headers["Idempotent-Replayed"] == "true"


def test_idempotency_key_reuse_with_different_body_conflicts(client, auth, make_order):
    o1, o2 = make_order(), make_order()
    key = f"idem-{uuid.uuid4()}"
    pay(client, auth, o1, key=key)
    r = pay(client, auth, o2, key=key)
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_idempotency_header_required(client, auth, make_order):
    order = make_order()
    r = client.post("/api/v1/payments", json={"order_id": order["id"], "amount": order["total"],
                                              "card_token": "tok_visa_approved"}, headers=auth("operations"))
    assert r.status_code == 422


@pytest.mark.parametrize("token,reason", [("tok_declined", "05"), ("tok_insufficient_funds", "51"),
                                          ("tok_expired", "54")])
def test_declined_cards_fail_without_retry_and_alert(client, auth, db, make_order, token, reason):
    order = make_order()
    r = pay(client, auth, order, token=token)
    assert r.status_code == 201 and r.json()["status"] == "failed" and r.json()["failure_reason"].startswith(reason)
    attempts = db.scalars(select(IntegrationLog).where(IntegrationLog.entity_type == "payment",
                                                       IntegrationLog.entity_id == r.json()["id"])).all()
    assert len(attempts) == 1  # permanent decline: no retry
    n = db.scalar(select(Notification).where(Notification.workflow == "failed_payment")
                  .order_by(Notification.id.desc()))
    assert n.payload["payment_id"] == r.json()["id"]


def test_issuer_unavailable_is_retried_three_times(client, auth, db, make_order):
    order = make_order()
    r = pay(client, auth, order, token="tok_issuer_unavailable")
    assert r.json()["status"] == "failed"
    attempts = db.scalars(select(IntegrationLog).where(IntegrationLog.entity_type == "payment",
                                                       IntegrationLog.entity_id == r.json()["id"])).all()
    assert [a.attempt for a in attempts] == [1, 2, 3]


@pytest.mark.regression
def test_payment_amount_must_match_outstanding(client, auth, make_order):
    order = make_order()
    r = pay(client, auth, order, amount="1.00")
    assert r.status_code == 422 and r.json()["error"]["code"] == "AMOUNT_MISMATCH"


def test_cannot_pay_cancelled_order(client, auth, make_order):
    order = make_order()
    client.patch(f"/api/v1/orders/{order['id']}/status", json={"status": "cancelled", "reason": "test"},
                 headers=auth("operations"))
    assert pay(client, auth, order).status_code == 409


def test_cancel_with_captured_payment_requires_refund(client, auth, make_order):
    order = make_order()
    pay(client, auth, order)
    r = client.patch(f"/api/v1/orders/{order['id']}/status", json={"status": "cancelled", "reason": "x"},
                     headers=auth("operations"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "REFUND_REQUIRED"


@pytest.mark.regression
def test_partial_then_full_refund_and_overrefund_rejected(client, auth, make_order):
    order = make_order()
    pid = pay(client, auth, order).json()["id"]
    r1 = client.post(f"/api/v1/payments/{pid}/refunds", json={"amount": "50.00", "reason": "Missing side"},
                     headers=auth("finance"))
    assert r1.status_code == 201 and r1.json()["status"] == "completed"
    assert client.get(f"/api/v1/payments/{pid}", headers=auth()).json()["status"] == "partially_refunded"
    over = client.post(f"/api/v1/payments/{pid}/refunds", json={"amount": order["total"], "reason": "x too much"},
                       headers=auth("finance"))
    assert over.status_code == 422 and over.json()["error"]["code"] == "REFUND_EXCEEDS_BALANCE"
    rest = Decimal(order["total"]) - Decimal("50.00")
    r2 = client.post(f"/api/v1/payments/{pid}/refunds", json={"amount": str(rest), "reason": "Full refund"},
                     headers=auth("finance"))
    assert r2.status_code == 201
    assert client.get(f"/api/v1/payments/{pid}", headers=auth()).json()["status"] == "refunded"
    assert len(client.get(f"/api/v1/payments/{pid}/refunds", headers=auth()).json()) == 2


def test_gateway_outage_raises_sev1_incident(client, auth, db, make_order):
    from app.models import Incident

    set_integration("transaction_junction", simulate_outage=True)
    for _ in range(3):
        pay(client, auth, make_order())
    inc = db.scalar(select(Incident).where(Incident.title == "Transaction Junction integration down",
                                           Incident.status == "open"))
    assert inc is not None and inc.severity == "SEV1"


# ------------------------------------------------------------------ loyalty
def test_loyalty_redeem_and_insufficient_points(client, auth, db):
    acc = db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.points_balance >= 20))
    bal = acc.points_balance
    r = client.post(f"/api/v1/loyalty/accounts/{acc.id}/redeem", json={"points": 10}, headers=auth("operations"))
    assert r.status_code == 201 and r.json()["sync_status"] == "synced"
    db.refresh(acc)
    assert acc.points_balance == bal - 10
    too_many = client.post(f"/api/v1/loyalty/accounts/{acc.id}/redeem", json={"points": 10**5},
                           headers=auth("operations"))
    assert too_many.status_code == 422 and too_many.json()["error"]["code"] == "INSUFFICIENT_POINTS"


@pytest.mark.regression
def test_redeem_not_applied_when_platform_down(client, auth, db):
    acc = db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.points_balance >= 20))
    bal = acc.points_balance
    set_integration("loyalty_platform", simulate_outage=True)
    r = client.post(f"/api/v1/loyalty/accounts/{acc.id}/redeem", json={"points": 10}, headers=auth("operations"))
    assert r.status_code == 502
    db.expire_all()
    assert db.get(LoyaltyAccount, acc.id).points_balance == bal


def test_failed_earn_kept_and_retryable(client, auth, db, make_order):
    acc, phone = loyalty_phone(db)
    set_integration("loyalty_platform", simulate_outage=True)
    order = make_order(phone=phone)
    pay(client, auth, order)
    txn = db.scalar(select(LoyaltyTransaction).where(LoyaltyTransaction.order_id == order["id"]))
    assert txn.sync_status == "failed"
    set_integration("loyalty_platform", simulate_outage=False)
    r = client.post(f"/api/v1/loyalty/transactions/{txn.id}/retry", headers=auth("integration_engineer"))
    assert r.status_code == 200 and r.json()["sync_status"] == "synced"
    assert client.post(f"/api/v1/loyalty/transactions/{txn.id}/retry",
                       headers=auth("integration_engineer")).status_code == 409


def test_loyalty_listing_and_history(client, auth):
    accs = client.get("/api/v1/loyalty/accounts", params={"limit": 5}, headers=auth()).json()
    assert accs["total"] > 0
    detail = client.get(f"/api/v1/loyalty/accounts/{accs['items'][0]['id']}", headers=auth()).json()
    assert {"account", "transactions"} <= detail.keys()
    failed = client.get("/api/v1/loyalty/transactions", params={"sync_status": "failed"}, headers=auth()).json()
    assert all(t["sync_status"] == "failed" for t in failed["items"])


def test_order_detail_shows_payments(client, auth, make_order, db):
    order = make_order()
    pay(client, auth, order)
    d = client.get(f"/api/v1/orders/{order['id']}", headers=auth()).json()
    assert d["payments"][0]["status"] == "captured" and d["payment_status"] == "captured"
    assert db.get(Order, order["id"]).customer is not None
