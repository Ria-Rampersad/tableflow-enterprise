"""Internal automation tools used by operations/finance and called by n8n workflows.

* daily_summary           - sales, payments and top products for one business day
* discrepancy_scan        - orders/payments/syncs stuck in an intermediate state
* integration_health_check- ping every integration, raise incidents for those that are down
* low_stock               - inventory below re-order level (pulled via the back-office adapter)
* post_finance_journal    - push the day's sales journal to the finance/GL system
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.backoffice import BackOfficeAdapter, FinanceSystemAdapter
from app.integrations.base import AdapterError, IntegrationRunner, get_integration
from app.integrations.loyalty import LoyaltyAdapter
from app.integrations.micros_simphony import MicrosSimphonyAdapter
from app.integrations.ordering import MrDAdapter, UberEatsAdapter
from app.integrations.transaction_junction import TransactionJunctionAdapter
from app.models import (
    Branch,
    Integration,
    InventoryItem,
    LoyaltyTransaction,
    Order,
    Payment,
    WebhookEvent,
    utcnow,
)
from app.services import audit, reporting
from app.services.incidents import auto_raise_integration_incident
from app.services.reconciliation import day_bounds

ADAPTERS = {"micros_simphony": MicrosSimphonyAdapter, "transaction_junction": TransactionJunctionAdapter,
            "uber_eats": UberEatsAdapter, "mr_d": MrDAdapter, "loyalty_platform": LoyaltyAdapter,
            "finance_gl": FinanceSystemAdapter, "backoffice_inventory": BackOfficeAdapter}


def daily_summary(db: Session, business_date: date) -> dict:
    perf = reporting.branch_performance(db, business_date, business_date)
    tx = reporting.daily_transactions(db, business_date, business_date, None)
    summary = reporting.dashboard_summary(db, business_date, business_date, None)
    return {
        "business_date": business_date.isoformat(),
        "total_orders": summary["total_orders"],
        "total_sales_zar": summary["total_sales_zar"],
        "average_order_value_zar": summary["average_order_value_zar"],
        "payments": summary["payments"],
        "transactions": tx[0] if tx else {},
        "branches": [b for b in perf if b["orders"]],
        "top_products": reporting.top_products(db, business_date, business_date, limit=5),
        "integration_health": summary["integration_health"],
    }


def discrepancy_scan(db: Session, stale_minutes: int = 30) -> dict:
    cutoff = utcnow() - timedelta(minutes=stale_minutes)
    stuck_orders = db.scalars(select(Order).where(Order.status.in_(("received", "failed", "sent_to_pos")),
                                                  Order.created_at < cutoff).limit(200)).all()
    uncaptured = db.scalars(select(Payment).where(Payment.status.in_(("initiated", "authorised")),
                                                  Payment.created_at < cutoff).limit(200)).all()
    failed_loyalty = db.scalar(select(func.count(LoyaltyTransaction.id)).where(LoyaltyTransaction.sync_status == "failed"))
    failed_webhooks = db.scalar(select(func.count(WebhookEvent.id)).where(WebhookEvent.status == "failed"))
    return {
        "scanned_at": utcnow().isoformat(),
        "stuck_orders": [{"order_id": o.id, "order_number": o.order_number, "status": o.status,
                          "branch_id": o.branch_id, "total": str(o.total)} for o in stuck_orders],
        "uncaptured_payments": [{"payment_id": p.id, "status": p.status, "amount": str(p.amount),
                                 "provider_reference": p.provider_reference} for p in uncaptured],
        "failed_loyalty_syncs": failed_loyalty,
        "failed_webhook_events": failed_webhooks,
        "total_issues": len(stuck_orders) + len(uncaptured) + failed_loyalty + failed_webhooks,
    }


def integration_health_check(db: Session, actor: str) -> list[dict]:
    results = []
    runner = IntegrationRunner(db)
    for integ in db.scalars(select(Integration).order_by(Integration.id)):
        if integ.status == "disabled":
            results.append({"integration": integ.name, "status": "disabled"})
            continue
        adapter = ADAPTERS[integ.name](integ)
        res = runner.call(integ, "health_check", adapter.ping, max_attempts=1)
        if not res.ok and integ.status == "down":
            auto_raise_integration_incident(db, integ, res.error or "health check failed")
        results.append({"integration": integ.name, "status": integ.status, "ok": res.ok, "error": res.error,
                        "avg_response_ms": integ.avg_response_ms})
    audit.record(db, actor, "automation.health_check", "integration", None, {"checked": len(results)})
    return results


def low_stock(db: Session) -> list[dict]:
    integ = get_integration(db, "backoffice_inventory")
    adapter = BackOfficeAdapter(integ)
    out = []
    rows = db.execute(select(InventoryItem, Branch).join(Branch, InventoryItem.branch_id == Branch.id)
                      .where(InventoryItem.quantity_on_hand <= InventoryItem.reorder_level)
                      .order_by(Branch.code, InventoryItem.item_name)).all()
    for item, branch in rows:
        out.append({"branch": branch.code, "branch_name": branch.name, "item": item.item_name, "unit": item.unit,
                    "on_hand": float(item.quantity_on_hand), "reorder_level": float(item.reorder_level),
                    "shortfall": float(item.reorder_level - item.quantity_on_hand)})
    IntegrationRunner(db).call(integ, "get_stock_levels",
                               lambda: adapter.get_stock_levels(branch_code="ALL", items=[]), max_attempts=1)
    return out


def post_finance_journal(db: Session, business_date: date, branch: Branch, actor: str) -> dict:
    start, end = day_bounds(business_date)
    gross = db.scalar(select(func.coalesce(func.sum(Payment.amount - Payment.refunded_amount), 0)).join(Order)
                      .where(Order.branch_id == branch.id, Payment.status.in_(("captured", "partially_refunded")),
                             Payment.created_at >= start, Payment.created_at < end))
    gross = Decimal(str(gross)).quantize(Decimal("0.01"))
    vat = (gross * Decimal("15") / Decimal("115")).quantize(Decimal("0.01"))
    lines = [
        {"account": "1100-CARD-CLEARING", "debit": str(gross), "credit": "0.00"},
        {"account": "4000-SALES", "debit": "0.00", "credit": str(gross - vat)},
        {"account": "2200-VAT-OUTPUT", "debit": "0.00", "credit": str(vat)},
    ]
    integ = get_integration(db, "finance_gl")
    adapter = FinanceSystemAdapter(integ)
    res = IntegrationRunner(db).call(
        integ, "post_journal",
        lambda: adapter.post_journal(business_date=business_date, branch_code=branch.code, lines=lines),
        request_payload={"date": business_date.isoformat(), "branch": branch.code, "lines": lines},
        entity_type="branch", entity_id=branch.id, branch_id=branch.id)
    audit.record(db, actor, "finance.journal_posted" if res.ok else "finance.journal_failed", "branch", branch.id,
                 {"date": business_date.isoformat(), "gross": str(gross)})
    if not res.ok:
        raise AdapterError(res.error or "journal failed", 502, retryable=False)
    return {"journal": res.data, "lines": lines}
