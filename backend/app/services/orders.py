"""Order lifecycle: ingest (any channel) -> validate -> store -> forward to POS -> status updates.

Business rules enforced here (see documentation/requirements/03_BUSINESS_RULES.md):
  BR-ORD-01 An order from a provider is identified by (channel, external_ref); a repeat is a duplicate.
  BR-ORD-02 The branch must exist, be active and have the channel enabled.
  BR-ORD-03 Every SKU must exist and be active in the catalogue.
  BR-ORD-04 If the provider sends a total, it must equal the sum of lines (+-R0.01).
  BR-ORD-05 Menu prices are VAT-inclusive; VAT = total x 15/115.
  BR-ORD-06 Status changes follow the allowed transition map below.
"""
from __future__ import annotations

import re
import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.integrations.base import IntegrationRunner, get_integration
from app.integrations.micros_simphony import MicrosSimphonyAdapter
from app.integrations.ordering import ORDERING_ADAPTERS
from app.models import Branch, Customer, Order, OrderItem, Payment, Product, utcnow
from app.schemas import CanonicalOrder, OrderItemOut, OrderOut
from app.services import audit
from app.services.notifications import notify

VAT_RATE = Decimal("0.15")
CENT = Decimal("0.01")

TRANSITIONS = {
    "received": {"sent_to_pos", "accepted", "cancelled", "failed"},
    "failed": {"accepted", "cancelled"},
    "sent_to_pos": {"accepted", "cancelled", "failed"},
    "accepted": {"preparing", "ready", "cancelled"},
    "preparing": {"ready", "cancelled"},
    "ready": {"completed"},
    "completed": set(),
    "cancelled": set(),
}


class BusinessRuleError(ValueError):
    def __init__(self, message: str, code: str = "BUSINESS_RULE", status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def normalise_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0") and len(digits) == 10:
        digits = "27" + digits[1:]
    if not (digits.startswith("27") and len(digits) == 11):
        raise BusinessRuleError(f"Invalid South African phone number: {phone}", "INVALID_PHONE")
    return "+" + digits


def vat_split(total: Decimal) -> tuple[Decimal, Decimal]:
    vat = (total * VAT_RATE / (1 + VAT_RATE)).quantize(CENT, ROUND_HALF_UP)
    return (total - vat).quantize(CENT), vat


def to_out(order: Order) -> OrderOut:
    pay = sorted(order.payments, key=lambda p: p.id)[-1].status if order.payments else None
    return OrderOut(
        id=order.id, order_number=order.order_number, branch_id=order.branch_id, branch_name=order.branch.name,
        channel=order.channel, external_ref=order.external_ref, status=order.status, subtotal=order.subtotal,
        vat=order.vat, total=order.total, pos_check_ref=order.pos_check_ref, customer_id=order.customer_id,
        created_at=order.created_at, payment_status=pay,
        items=[OrderItemOut(sku=i.product.sku, name=i.product.name, quantity=i.quantity, unit_price=i.unit_price,
                            line_total=i.line_total) for i in order.items],
    )


def load_order(db: Session, order_id: int) -> Order | None:
    return db.scalar(
        select(Order).where(Order.id == order_id)
        .options(selectinload(Order.items), selectinload(Order.payments))
    )


def _upsert_customer(db: Session, name: str | None, phone: str | None) -> Customer | None:
    phone = normalise_phone(phone)
    if not phone:
        return None
    cust = db.scalar(select(Customer).where(Customer.phone == phone))
    if not cust:
        cust = Customer(full_name=name or "Guest", phone=phone)
        db.add(cust)
        db.flush()
    return cust


def ingest(db: Session, data: CanonicalOrder, actor: str) -> tuple[Order, bool]:
    """Validate and persist an order. Returns (order, is_duplicate)."""
    if data.external_ref:
        existing = db.scalar(select(Order).where(Order.channel == data.channel, Order.external_ref == data.external_ref))
        if existing:
            return existing, True  # BR-ORD-01 idempotent ingest

    branch = db.scalar(select(Branch).where(Branch.code == data.branch_code))
    if not branch or not branch.is_active:
        raise BusinessRuleError(f"Branch '{data.branch_code}' not found or inactive", "UNKNOWN_BRANCH")
    if data.channel in ("uber_eats", "mr_d") and data.channel not in (branch.digital_channels or []):
        raise BusinessRuleError(f"Channel {data.channel} is not enabled for branch {branch.code}", "CHANNEL_DISABLED")

    skus = {i.sku for i in data.items}
    products = {p.sku: p for p in db.scalars(select(Product).where(Product.sku.in_(skus)))}
    missing = sorted(s for s in skus if s not in products or not products[s].is_active)
    if missing:
        raise BusinessRuleError(f"Unknown or inactive SKUs: {', '.join(missing)}", "UNKNOWN_SKU")

    lines, total = [], Decimal("0")
    for item in data.items:
        product = products[item.sku]
        unit = (item.unit_price if item.unit_price is not None else product.price).quantize(CENT)
        line_total = (unit * item.quantity).quantize(CENT)
        total += line_total
        lines.append(OrderItem(product_id=product.id, quantity=item.quantity, unit_price=unit, line_total=line_total))

    if data.total is not None and abs(data.total - total) > CENT:
        raise BusinessRuleError(f"Order total {data.total} does not match line items {total}", "TOTAL_MISMATCH")

    customer = _upsert_customer(db, data.customer_name, data.customer_phone)
    subtotal, vat = vat_split(total)
    order = Order(
        order_number=f"TF-{utcnow():%y%m%d}-{uuid.uuid4().hex[:6].upper()}",
        branch_id=branch.id, customer_id=customer.id if customer else None, channel=data.channel,
        external_ref=data.external_ref, status="received", subtotal=subtotal, vat=vat, total=total,
        notes=data.notes, items=lines,
    )
    try:
        with db.begin_nested():  # savepoint: a concurrent duplicate loses the race cleanly
            db.add(order)
            db.flush()
    except IntegrityError:
        existing = db.scalar(select(Order).where(Order.channel == data.channel, Order.external_ref == data.external_ref))
        if existing:
            return existing, True
        raise
    audit.record(db, actor, "order.created", "order", order.id,
                 {"channel": data.channel, "external_ref": data.external_ref, "total": str(total)})
    notify(db, "new_order", "order.received",
           {"order_number": order.order_number, "branch": branch.code, "channel": data.channel, "total": str(total)})
    return order, False


def forward_to_pos(db: Session, order: Order, actor: str = "system") -> bool:
    """Send the order to Micros Simphony. On failure the order is marked failed and ops are alerted."""
    if order.pos_check_ref:
        return True
    branch = order.branch
    integ = get_integration(db, "micros_simphony")
    adapter = MicrosSimphonyAdapter(integ)
    items = [{"sku": i.product.sku, "pos_item_ref": i.product.pos_item_ref, "quantity": i.quantity} for i in order.items]
    result = IntegrationRunner(db).call(
        integ, "create_check",
        lambda: adapter.create_check(location_ref=branch.pos_location_ref, order_number=order.order_number,
                                     channel=order.channel, items=items, total=order.total),
        request_payload={"locRef": branch.pos_location_ref, "orderNumber": order.order_number, "items": items,
                         "total": str(order.total)},
        entity_type="order", entity_id=order.id, branch_id=branch.id,
    )
    if result.ok:
        order.pos_check_ref = result.data["checkRef"]
        order.status = "accepted"
        _push_provider_status(db, order)
        audit.record(db, actor, "order.forwarded_to_pos", "order", order.id, {"check_ref": order.pos_check_ref})
        return True
    order.status = "failed"
    notify(db, "pos_failure", "pos.order_forward_failed",
           {"order_number": order.order_number, "branch": branch.code, "error": result.error,
            "integration_log_id": result.log_id})
    return False


def _push_provider_status(db: Session, order: Order) -> None:
    """Tell Uber Eats / Mr D about the status change (best effort; failures are logged, not fatal)."""
    adapter_cls = ORDERING_ADAPTERS.get(order.channel)
    if not adapter_cls or not order.external_ref:
        return
    integ = get_integration(db, order.channel)
    adapter = adapter_cls(integ)
    IntegrationRunner(db).call(
        integ, "push_status", lambda: adapter.push_status(external_ref=order.external_ref, status=order.status),
        request_payload={"external_ref": order.external_ref, "status": order.status},
        entity_type="order", entity_id=order.id, branch_id=order.branch_id, max_attempts=2,
    )


def change_status(db: Session, order: Order, new_status: str, actor: str, reason: str | None = None) -> Order:
    if new_status == order.status:
        return order
    if new_status not in TRANSITIONS.get(order.status, set()):
        raise BusinessRuleError(f"Cannot change order from '{order.status}' to '{new_status}'", "INVALID_TRANSITION", 409)
    if new_status == "cancelled" and any(p.status == "captured" for p in order.payments):
        raise BusinessRuleError("Order has a captured payment; refund it before cancelling", "REFUND_REQUIRED", 409)
    old = order.status
    order.status = new_status
    if new_status == "cancelled":
        order.cancel_reason = reason
    if order.pos_check_ref:
        integ = get_integration(db, "micros_simphony")
        adapter = MicrosSimphonyAdapter(integ)
        IntegrationRunner(db).call(
            integ, "update_check_status",
            lambda: adapter.update_check_status(check_ref=order.pos_check_ref, status=new_status),
            request_payload={"checkRef": order.pos_check_ref, "status": new_status},
            entity_type="order", entity_id=order.id, branch_id=order.branch_id,
        )
    _push_provider_status(db, order)
    audit.record(db, actor, "order.status_changed", "order", order.id, {"from": old, "to": new_status, "reason": reason})
    return order


def cancel_by_provider(db: Session, channel: str, external_ref: str, reason: str) -> Order:
    order = db.scalar(select(Order).where(Order.channel == channel, Order.external_ref == external_ref))
    if not order:
        raise BusinessRuleError(f"No {channel} order with reference {external_ref}", "ORDER_NOT_FOUND", 404)
    if order.status == "cancelled":
        return order
    return change_status(db, order, "cancelled", f"provider:{channel}", reason)


def outstanding_amount(order: Order) -> Decimal:
    paid = sum((p.amount - p.refunded_amount for p in order.payments if p.status in ("authorised", "captured",
                                                                                     "partially_refunded")),
               Decimal("0"))
    return (order.total - paid).quantize(CENT)


__all__ = ["BusinessRuleError", "ingest", "forward_to_pos", "change_status", "cancel_by_provider", "to_out",
           "load_order", "outstanding_amount", "Payment"]
