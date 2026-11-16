"""Payments: initiate/authorise, idempotency, gateway webhooks, refunds.

Flow (mirrors a real acquirer):
  1. POST /payments with an `Idempotency-Key` header.
  2. Gateway authorises synchronously -> payment.status = authorised (or failed).
  3. Gateway later sends a signed `payment.captured` webhook -> status = captured,
     loyalty points are earned.

  BR-PAY-01 Same Idempotency-Key + same body returns the original payment; different body -> 409.
  BR-PAY-02 Amount must equal the order's outstanding balance.
  BR-PAY-03 Payments cannot be taken for cancelled orders.
  BR-PAY-04 Refund total may not exceed captured amount.
  BR-PAY-05 Only finance/admin may refund (enforced in the API layer).
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.base import IntegrationRunner, get_integration
from app.integrations.transaction_junction import TransactionJunctionAdapter
from app.models import Payment, Refund, utcnow
from app.schemas import PaymentCreate
from app.security import signatures
from app.services import audit
from app.services.notifications import notify
from app.services.orders import BusinessRuleError, load_order, outstanding_amount


def create_payment(db: Session, data: PaymentCreate, idempotency_key: str, actor: str) -> tuple[Payment, bool]:
    """Returns (payment, replayed). `replayed` is True when the idempotency key was seen before."""
    existing = db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
    if existing:
        if existing.order_id != data.order_id or existing.amount != data.amount:
            raise BusinessRuleError("Idempotency-Key reused with a different request body", "IDEMPOTENCY_CONFLICT", 409)
        return existing, True

    order = load_order(db, data.order_id)
    if not order:
        raise BusinessRuleError("Order not found", "ORDER_NOT_FOUND", 404)
    if order.status in ("cancelled", "failed"):
        raise BusinessRuleError(f"Cannot take payment for a {order.status} order", "ORDER_NOT_PAYABLE", 409)
    due = outstanding_amount(order)
    if data.amount != due:
        raise BusinessRuleError(f"Amount {data.amount} does not match outstanding balance {due}", "AMOUNT_MISMATCH")

    payment = Payment(order_id=order.id, amount=data.amount, currency=data.currency, method=data.method,
                      idempotency_key=idempotency_key, status="initiated", provider="transaction_junction")
    db.add(payment)
    db.flush()

    integ = get_integration(db, "transaction_junction")
    adapter = TransactionJunctionAdapter(integ)
    result = IntegrationRunner(db).call(
        integ, "authorise",
        lambda: adapter.authorise(amount=data.amount, currency=data.currency, card_token=data.card_token,
                                  merchant_ref=order.order_number, idempotency_key=idempotency_key),
        request_payload={"amount": str(data.amount), "currency": data.currency, "merchantRef": order.order_number,
                         "cardToken": data.card_token[:8] + "***"},  # never log full card data
        entity_type="payment", entity_id=payment.id, branch_id=order.branch_id,
    )
    if result.ok:
        payment.status = "authorised"
        payment.provider_reference = result.data["transactionId"]
    else:
        payment.status = "failed"
        payment.failure_reason = result.error
        notify(db, "failed_payment", "payment.failed",
               {"payment_id": payment.id, "order_number": order.order_number, "branch": order.branch.code,
                "amount": str(payment.amount), "reason": result.error})
    audit.record(db, actor, "payment.created", "payment", payment.id,
                 {"status": payment.status, "amount": str(payment.amount), "order_id": order.id})
    return payment, False


def build_gateway_webhook(payment: Payment, event_type: str = "payment.captured") -> tuple[bytes, dict]:
    """What the (simulated) gateway POSTs back to us. Signed exactly like a real provider callback."""
    body = json.dumps({
        "id": f"evt_{uuid.uuid4().hex[:20]}",
        "type": event_type,
        "created": utcnow().isoformat(),
        "data": {"transactionId": payment.provider_reference, "amount": str(payment.amount), "currency": "ZAR",
                 "merchantRef": payment.order.order_number if payment.order else None},
    }).encode()
    return body, signatures.sign("transaction_junction", body)


def refund_payment(db: Session, payment: Payment, amount: Decimal, reason: str, actor: str) -> Refund:
    if payment.status not in ("captured", "partially_refunded"):
        raise BusinessRuleError(f"Cannot refund a payment in status {payment.status}", "NOT_REFUNDABLE", 409)
    remaining = payment.amount - payment.refunded_amount
    if amount > remaining:
        raise BusinessRuleError(f"Refund {amount} exceeds refundable balance {remaining}", "REFUND_EXCEEDS_BALANCE")
    refund = Refund(payment_id=payment.id, amount=amount, reason=reason, requested_by=actor)
    db.add(refund)
    db.flush()
    integ = get_integration(db, "transaction_junction")
    adapter = TransactionJunctionAdapter(integ)
    result = IntegrationRunner(db).call(
        integ, "refund",
        lambda: adapter.refund(transaction_id=payment.provider_reference, amount=amount, reason=reason),
        request_payload={"transactionId": payment.provider_reference, "amount": str(amount)},
        entity_type="refund", entity_id=refund.id,
    )
    if not result.ok:
        refund.status = "failed"
        audit.record(db, actor, "refund.failed", "refund", refund.id, {"error": result.error})
        raise BusinessRuleError(f"Refund failed at gateway: {result.error}", "REFUND_FAILED", 502)
    refund.status = "completed"
    refund.provider_reference = result.data["refundId"]
    payment.refunded_amount += amount
    payment.status = "refunded" if payment.refunded_amount == payment.amount else "partially_refunded"
    audit.record(db, actor, "refund.completed", "refund", refund.id,
                 {"payment_id": payment.id, "amount": str(amount), "reason": reason})
    return refund
