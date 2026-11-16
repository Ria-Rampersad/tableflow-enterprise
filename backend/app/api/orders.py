"""Orders (internal API) and the Digital Ordering partner endpoints (Uber Eats, Mr D)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Paging, paginate
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.integrations.base import AdapterError
from app.integrations.ordering import ORDERING_ADAPTERS
from app.models import Branch, Order
from app.monitoring.ratelimit import rate_limit
from app.schemas import CanonicalOrder, OrderCreate, OrderIngestResult, OrderStatusUpdate
from app.security.auth import Principal, get_current_principal, require_partner_key, require_roles
from app.services import orders as svc
from app.services.reporting import bounds

router = APIRouter(prefix="/orders", tags=["Orders"])
partners = APIRouter(prefix="/partners", tags=["Digital Ordering Partners"])
partner_limit = rate_limit("partner", lambda: get_settings().rate_limit_partner_per_minute)


@router.get("")
def list_orders(
    paging: Paging = Depends(),
    branch_id: int | None = None,
    status: str | None = None,
    channel: str | None = None,
    start: date | None = None,
    end: date | None = None,
    search: str | None = Query(None, description="order number or external reference"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    q = select(Order).options(selectinload(Order.items), selectinload(Order.payments)).order_by(Order.created_at.desc())
    if principal.roles == ["branch_manager"] and principal.branch_id:
        branch_id = principal.branch_id  # branch managers only see their own branch
    if branch_id:
        q = q.where(Order.branch_id == branch_id)
    if status:
        q = q.where(Order.status == status)
    if channel:
        q = q.where(Order.channel == channel)
    if start or end:
        s, e, *_ = bounds(start, end)
        q = q.where(Order.created_at >= s, Order.created_at < e)
    if search:
        q = q.where(or_(Order.order_number.ilike(f"%{search}%"), Order.external_ref.ilike(f"%{search}%")))
    total, rows = paginate(db, q, paging)
    return {"total": total, "items": [svc.to_out(o) for o in rows]}


@router.get("/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    order = svc.load_order(db, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    out = svc.to_out(order).model_dump(mode="json")
    out["payments"] = [{"id": p.id, "status": p.status, "amount": str(p.amount), "provider_reference":
                        p.provider_reference, "failure_reason": p.failure_reason} for p in order.payments]
    out["customer"] = ({"id": order.customer.id, "name": order.customer.full_name, "phone": order.customer.phone}
                       if order.customer else None)
    out["notes"], out["cancel_reason"] = order.notes, order.cancel_reason
    return out


@router.post("", response_model=OrderIngestResult, status_code=201, summary="Create an in-store / web order")
def create_order(body: OrderCreate, db: Session = Depends(get_db),
                 p: Principal = Depends(require_roles("operations", "branch_manager"))):
    branch = db.get(Branch, body.branch_id)
    if not branch:
        raise HTTPException(404, "Branch not found")
    canonical = CanonicalOrder(channel=body.channel, branch_code=branch.code, customer_name=body.customer_name,
                               customer_phone=body.customer_phone, items=body.items, notes=body.notes)
    order, _dup = svc.ingest(db, canonical, p.subject)
    db.commit()
    forwarded = svc.forward_to_pos(db, order, p.subject)
    db.commit()
    return OrderIngestResult(order=svc.to_out(svc.load_order(db, order.id)), pos_forwarded=forwarded,
                             message="Order sent to POS" if forwarded else "Order saved; POS forwarding failed")


@router.patch("/{order_id}/status")
def update_status(order_id: int, body: OrderStatusUpdate, db: Session = Depends(get_db),
                  p: Principal = Depends(require_roles("operations", "branch_manager"))):
    order = svc.load_order(db, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    svc.change_status(db, order, body.status, p.subject, body.reason)
    db.commit()
    return svc.to_out(svc.load_order(db, order_id))


@router.post("/{order_id}/forward-to-pos", summary="Retry sending a failed order to Micros Simphony")
def retry_forward(order_id: int, db: Session = Depends(get_db),
                  p: Principal = Depends(require_roles("operations", "integration_engineer", "branch_manager"))):
    order = svc.load_order(db, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status not in ("received", "failed"):
        raise HTTPException(409, f"Order is {order.status}; only received/failed orders can be (re)forwarded")
    ok = svc.forward_to_pos(db, order, p.subject)
    db.commit()
    return {"forwarded": ok, "order": svc.to_out(svc.load_order(db, order_id))}


# ---------------------------------------------------------------- partners
def _forward_in_background(order_id: int) -> None:
    """Runs after the 202 response: partners need a fast acknowledgement, POS forwarding can take seconds."""
    with SessionLocal() as db:
        order = svc.load_order(db, order_id)
        if order and order.status == "received":
            svc.forward_to_pos(db, order, "system:partner-ingest")
            db.commit()


def _ingest_partner(provider: str, payload: dict, background: BackgroundTasks, db: Session) -> dict:
    adapter_cls = ORDERING_ADAPTERS[provider]
    try:
        canonical = adapter_cls.to_canonical(payload)
    except AdapterError as exc:
        raise HTTPException(422, str(exc)) from exc
    order, duplicate = svc.ingest(db, canonical, f"partner:{provider}")
    db.commit()
    if not duplicate:
        background.add_task(_forward_in_background, order.id)
    return {"accepted": True, "duplicate": duplicate, "order_number": order.order_number, "order_id": order.id,
            "status": order.status,
            "message": "Duplicate order ignored (already received)" if duplicate else "Order accepted for processing"}


@partners.post("/uber-eats/orders", status_code=202, dependencies=[Depends(partner_limit)],
               summary="Inbound Uber Eats order (simulated contract)")
def uber_eats_order(background: BackgroundTasks, payload: dict = Body(...), db: Session = Depends(get_db),
                    _: str = Depends(require_partner_key("uber_eats"))):
    return _ingest_partner("uber_eats", payload, background, db)


@partners.post("/mr-d/orders", status_code=202, dependencies=[Depends(partner_limit)],
               summary="Inbound Mr D order (simulated contract)")
def mr_d_order(background: BackgroundTasks, payload: dict = Body(...), db: Session = Depends(get_db),
               _: str = Depends(require_partner_key("mr_d"))):
    return _ingest_partner("mr_d", payload, background, db)


def _cancel(channel: str, external_ref: str, reason: str, db: Session):
    order = svc.cancel_by_provider(db, channel, external_ref, reason)
    db.commit()
    return {"order_number": order.order_number, "status": order.status}


@partners.post("/uber-eats/orders/{external_ref}/cancel", dependencies=[Depends(partner_limit)])
def uber_cancel(external_ref: str, reason: str = Body("Cancelled by customer", embed=True),
                db: Session = Depends(get_db), _: str = Depends(require_partner_key("uber_eats"))):
    return _cancel("uber_eats", external_ref, reason, db)


@partners.post("/mr-d/orders/{external_ref}/cancel", dependencies=[Depends(partner_limit)])
def mrd_cancel(external_ref: str, reason: str = Body("Cancelled by customer", embed=True),
               db: Session = Depends(get_db), _: str = Depends(require_partner_key("mr_d"))):
    return _cancel("mr_d", external_ref, reason, db)
