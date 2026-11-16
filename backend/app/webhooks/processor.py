"""Inbound webhook processing pipeline.

    raw body + headers
        -> 1. verify HMAC signature (reject + store as `rejected` if invalid)
        -> 2. parse and normalise (event_id, event_type) per provider
        -> 3. de-duplicate on (source, event_id)  - providers retry, so duplicates are normal
        -> 4. store as `received`
        -> 5. dispatch to a handler inside a savepoint
        -> 6. mark `processed` or `failed` (failed events can be replayed from the UI)

Signature verification happens on the *raw bytes* before JSON parsing, because
re-serialising JSON can change whitespace/key order and break the HMAC.
"""
from __future__ import annotations

import json
import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Payment, Refund, WebhookEvent, utcnow
from app.monitoring.logging import log
from app.security import signatures
from app.services import loyalty, orders
from app.services.notifications import notify

logger = logging.getLogger("tableflow.webhooks")


class WebhookProcessingError(Exception):
    pass


def _identify(source: str, payload: dict) -> tuple[str, str]:
    if source == "transaction_junction":
        return payload["id"], payload["type"]
    if source == "uber_eats":
        return payload["event_id"], payload["event_type"]
    if source == "mr_d":
        return payload["eventId"], payload["eventType"]
    raise KeyError(source)


# ------------------------------------------------------------------ handlers
def _tj_payment_captured(db: Session, payload: dict) -> str:
    data = payload["data"]
    payment = db.scalar(select(Payment).where(Payment.provider_reference == data["transactionId"]))
    if not payment:
        raise WebhookProcessingError(f"Unknown transactionId {data['transactionId']}")
    if Decimal(str(data["amount"])) != payment.amount:
        raise WebhookProcessingError(f"Captured amount {data['amount']} != authorised {payment.amount}")
    if payment.status == "captured":
        return "already captured"
    if payment.status != "authorised":
        raise WebhookProcessingError(f"Payment {payment.id} is {payment.status}, cannot capture")
    payment.status = "captured"
    order = db.get(Order, payment.order_id)
    loyalty.earn_for_order(db, order, payment.amount)
    return f"payment {payment.id} captured"


def _tj_payment_failed(db: Session, payload: dict) -> str:
    data = payload["data"]
    payment = db.scalar(select(Payment).where(Payment.provider_reference == data["transactionId"]))
    if not payment:
        raise WebhookProcessingError(f"Unknown transactionId {data['transactionId']}")
    payment.status = "failed"
    payment.failure_reason = data.get("reason", "Reported failed by gateway")
    notify(db, "failed_payment", "payment.failed",
           {"payment_id": payment.id, "amount": str(payment.amount), "reason": payment.failure_reason})
    return f"payment {payment.id} failed"


def _tj_refund_completed(db: Session, payload: dict) -> str:
    refund = db.scalar(select(Refund).where(Refund.provider_reference == payload["data"]["refundId"]))
    if not refund:
        raise WebhookProcessingError("Unknown refundId")
    refund.status = "completed"
    return f"refund {refund.id} confirmed"


def _provider_cancel(source: str):
    def handler(db: Session, payload: dict) -> str:
        ref = payload.get("meta", {}).get("resource_id") if source == "uber_eats" else payload.get("orderReference")
        reason = payload.get("reason") or payload.get("meta", {}).get("reason") or "Cancelled by provider"
        order = orders.cancel_by_provider(db, source, ref, reason)
        return f"order {order.order_number} cancelled"

    return handler


HANDLERS = {
    ("transaction_junction", "payment.captured"): _tj_payment_captured,
    ("transaction_junction", "payment.failed"): _tj_payment_failed,
    ("transaction_junction", "refund.completed"): _tj_refund_completed,
    ("uber_eats", "orders.cancel"): _provider_cancel("uber_eats"),
    ("mr_d", "ORDER_CANCELLED"): _provider_cancel("mr_d"),
}


# ------------------------------------------------------------------ pipeline
def _run_handler(db: Session, event: WebhookEvent) -> None:
    handler = HANDLERS.get((event.source, event.event_type))
    event.attempts += 1
    if not handler:
        event.status, event.error, event.processed_at = "processed", "ignored: no handler for event type", utcnow()
        return
    try:
        with db.begin_nested():
            outcome = handler(db, event.payload)
        event.status, event.error, event.processed_at = "processed", None, utcnow()
        log(logger, logging.INFO, "webhook processed", source=event.source, event_id=event.event_id, outcome=outcome)
    except (WebhookProcessingError, orders.BusinessRuleError) as exc:
        event.status, event.error = "failed", str(exc)
        log(logger, logging.WARNING, "webhook processing failed", source=event.source, event_id=event.event_id,
            error=str(exc))


def handle(db: Session, source: str, body: bytes, headers: dict[str, str]) -> tuple[WebhookEvent, int]:
    """Process one inbound webhook. Returns (event, http_status_to_return)."""
    try:
        signatures.verify(source, body, headers)
        sig_ok, sig_error = True, None
    except signatures.SignatureError as exc:
        sig_ok, sig_error = False, str(exc)

    try:
        payload = json.loads(body)
        event_id, event_type = _identify(source, payload)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        payload, event_id, event_type = {"raw": body[:2000].decode(errors="replace")}, None, "unparseable"
        sig_error = sig_error or f"invalid payload: {exc}"

    if not sig_ok or event_id is None:
        ev = WebhookEvent(source=source, event_id=f"rejected-{uuid.uuid4().hex[:12]}", event_type=event_type,
                          payload=payload, signature_valid=sig_ok, status="rejected", error=sig_error, attempts=1)
        db.add(ev)
        db.flush()
        return ev, 401 if not sig_ok else 400

    existing = db.scalar(select(WebhookEvent).where(WebhookEvent.source == source, WebhookEvent.event_id == event_id))
    if existing:
        existing.attempts += 1
        log(logger, logging.INFO, "duplicate webhook ignored", source=source, event_id=event_id)
        return existing, 200  # acknowledge so the provider stops retrying

    ev = WebhookEvent(source=source, event_id=event_id, event_type=event_type, payload=payload, signature_valid=True)
    db.add(ev)
    db.flush()
    _run_handler(db, ev)
    return ev, 200


def replay(db: Session, event: WebhookEvent) -> WebhookEvent:
    if event.status not in ("failed",):
        raise ValueError("Only failed events can be replayed")
    _run_handler(db, event)
    return event
