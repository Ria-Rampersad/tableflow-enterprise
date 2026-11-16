"""POS Integration Hub operations: menu sync and transaction (closed-check) sync with Micros Simphony."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.base import IntegrationRunner, get_integration
from app.integrations.micros_simphony import MicrosSimphonyAdapter
from app.models import Branch, Order, PosTransaction, Product
from app.services import audit
from app.services.notifications import notify
from app.services.reconciliation import day_bounds


def menu_sync(db: Session, branch: Branch, actor: str) -> dict:
    integ = get_integration(db, "micros_simphony")
    adapter = MicrosSimphonyAdapter(integ)
    products = [{"pos_item_ref": p.pos_item_ref, "name": p.name, "category": p.category, "price": p.price,
                 "is_active": p.is_active} for p in db.scalars(select(Product).order_by(Product.sku))]
    result = IntegrationRunner(db).call(
        integ, "menu_sync", lambda: adapter.get_menu(location_ref=branch.pos_location_ref, products=products),
        request_payload={"locRef": branch.pos_location_ref}, entity_type="branch", entity_id=branch.id,
        branch_id=branch.id,
    )
    if not result.ok:
        notify(db, "pos_failure", "pos.menu_sync_failed", {"branch": branch.code, "error": result.error})
        return {"ok": False, "error": result.error, "items": 0}
    # Compare POS menu with our catalogue: unmapped items and price drift are what break order forwarding.
    pos_items = {m["menuItemId"]: m for m in result.data["menuItems"]}
    unmapped = [p.sku for p in db.scalars(select(Product)) if not p.pos_item_ref or p.pos_item_ref not in pos_items]
    audit.record(db, actor, "pos.menu_sync", "branch", branch.id, {"items": len(pos_items), "unmapped": unmapped})
    return {"ok": True, "items": len(pos_items), "unmapped_skus": unmapped, "menu": result.data["menuItems"]}


def transaction_sync(db: Session, branch: Branch, business_date: date, actor: str) -> dict:
    """Pull closed checks for the day from Simphony and upsert them into pos_transactions."""
    integ = get_integration(db, "micros_simphony")
    adapter = MicrosSimphonyAdapter(integ)
    start, end = day_bounds(business_date)
    sent = db.scalars(select(Order).where(Order.branch_id == branch.id, Order.pos_check_ref.is_not(None),
                                          Order.created_at >= start, Order.created_at < end,
                                          Order.status != "cancelled")).all()
    open_checks = [{"check_ref": o.pos_check_ref, "total": o.total, "order_id": o.id} for o in sent]
    result = IntegrationRunner(db).call(
        integ, "transaction_sync",
        lambda: adapter.get_closed_checks(location_ref=branch.pos_location_ref, business_date=business_date,
                                          open_checks=open_checks),
        request_payload={"locRef": branch.pos_location_ref, "busDt": business_date.isoformat()},
        entity_type="branch", entity_id=branch.id, branch_id=branch.id,
    )
    if not result.ok:
        notify(db, "pos_failure", "pos.transaction_sync_failed", {"branch": branch.code, "error": result.error})
        return {"ok": False, "error": result.error, "inserted": 0}
    by_ref = {o.pos_check_ref: o for o in sent}
    existing = {t.check_number for t in db.scalars(select(PosTransaction).where(PosTransaction.branch_id == branch.id))}
    inserted = 0
    for chk in result.data["checks"]:
        number = chk["checkRef"]
        if number in existing:
            continue
        order = by_ref.get(chk["checkRef"])
        db.add(PosTransaction(branch_id=branch.id, check_number=number, order_id=order.id if order else None,
                              total=chk["totalDue"], tender_type=chk["tenderType"], business_date=business_date))
        inserted += 1
    audit.record(db, actor, "pos.transaction_sync", "branch", branch.id,
                 {"date": business_date.isoformat(), "inserted": inserted})
    return {"ok": True, "checks": len(result.data["checks"]), "inserted": inserted}
