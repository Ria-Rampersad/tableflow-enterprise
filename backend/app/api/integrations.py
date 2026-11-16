"""Integration Monitoring + POS Integration Hub endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Paging, get_or_404, paginate
from app.database import get_db
from app.models import Branch, Integration, IntegrationLog, LoyaltyTransaction, Order
from app.schemas import IntegrationConfigUpdate, IntegrationLogOut, IntegrationOut
from app.security.auth import Principal, get_current_principal, require_roles
from app.services import audit, automation, loyalty, orders, pos

router = APIRouter(prefix="/integrations", tags=["Integration Monitoring"])
pos_router = APIRouter(prefix="/pos", tags=["POS Integration Hub"])


@router.get("", response_model=list[IntegrationOut])
def list_integrations(db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    return db.scalars(select(Integration).order_by(Integration.kind, Integration.name)).all()


@router.get("/{integration_id}", response_model=IntegrationOut)
def get_integration(integration_id: int, db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    return get_or_404(db, Integration, integration_id)


@router.patch("/{integration_id}", response_model=IntegrationOut,
              summary="Change simulation knobs (outage, failure rate, latency) or disable an integration")
def configure(integration_id: int, body: IntegrationConfigUpdate, db: Session = Depends(get_db),
              p: Principal = Depends(require_roles("integration_engineer"))):
    integ = get_or_404(db, Integration, integration_id)
    changes = body.model_dump(exclude_unset=True)
    cfg = dict(integ.config or {})
    for k in ("simulate_outage", "failure_rate", "latency_ms"):
        if k in changes:
            cfg[k] = changes[k]
    integ.config = cfg
    if "status" in changes:
        integ.status = changes["status"]
        if changes["status"] == "healthy":
            integ.consecutive_failures = 0
    audit.record(db, p.subject, "integration.configured", "integration", integ.id, changes)
    db.commit()
    return integ


@router.post("/{integration_id}/health-check")
def health_check(integration_id: int, db: Session = Depends(get_db),
                 p: Principal = Depends(require_roles("integration_engineer", "operations"))):
    integ = get_or_404(db, Integration, integration_id)
    adapter = automation.ADAPTERS[integ.name](integ)
    from app.integrations.base import IntegrationRunner

    res = IntegrationRunner(db).call(integ, "health_check", adapter.ping, max_attempts=1)
    db.commit()
    return {"integration": integ.name, "ok": res.ok, "status": integ.status, "error": res.error,
            "response": res.data}


@router.get("/{integration_id}/logs")
def integration_logs(integration_id: int, paging: Paging = Depends(), status: str | None = None,
                     db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    get_or_404(db, Integration, integration_id)
    q = select(IntegrationLog).where(IntegrationLog.integration_id == integration_id)
    if status:
        q = q.where(IntegrationLog.status == status)
    total, rows = paginate(db, q.order_by(IntegrationLog.created_at.desc()), paging)
    return {"total": total, "items": [IntegrationLogOut.model_validate(r) for r in rows]}


@router.get("/logs/failed")
def failed_logs(paging: Paging = Depends(), db: Session = Depends(get_db),
                _: Principal = Depends(get_current_principal)):
    q = select(IntegrationLog).where(IntegrationLog.status == "failed").order_by(IntegrationLog.created_at.desc())
    total, rows = paginate(db, q, paging)
    return {"total": total, "items": [IntegrationLogOut.model_validate(r) for r in rows]}


@router.post("/logs/{log_id}/retry", summary="Retry the business operation behind a failed integration call")
def retry_failed(log_id: int, db: Session = Depends(get_db),
                 p: Principal = Depends(require_roles("integration_engineer", "operations"))):
    entry = get_or_404(db, IntegrationLog, log_id, "Integration log")
    if entry.status != "failed":
        raise HTTPException(409, "Only failed calls can be retried")
    if entry.entity_type == "order" and entry.operation == "create_check":
        order = db.scalar(select(Order).where(Order.id == entry.entity_id).options(selectinload(Order.items)))
        if order.status not in ("received", "failed"):
            raise HTTPException(409, f"Order already {order.status}")
        ok = orders.forward_to_pos(db, order, p.subject)
        result = {"retried": "create_check", "ok": ok, "order_status": order.status}
    elif entry.entity_type == "loyalty_transaction":
        txn = db.get(LoyaltyTransaction, entry.entity_id)
        if txn.sync_status != "failed":
            raise HTTPException(409, "Loyalty transaction already synced")
        loyalty.retry_sync(db, txn, p.subject)
        result = {"retried": "loyalty_sync", "ok": txn.sync_status == "synced"}
    elif entry.entity_type == "branch" and entry.operation in ("menu_sync", "transaction_sync"):
        branch = db.get(Branch, entry.entity_id)
        r = pos.menu_sync(db, branch, p.subject) if entry.operation == "menu_sync" else \
            pos.transaction_sync(db, branch, entry.created_at.date(), p.subject)
        result = {"retried": entry.operation, "ok": r["ok"]}
    else:
        raise HTTPException(422, f"Operation '{entry.operation}' is not retryable from the console")
    audit.record(db, p.subject, "integration.retry", "integration_log", entry.id, result)
    db.commit()
    return result


# ---------------------------------------------------------------- POS hub
@pos_router.get("/status")
def pos_status(db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    integ = db.scalar(select(Integration).where(Integration.name == "micros_simphony"))
    branches = db.scalars(select(Branch).where(Branch.pos_system == "micros_simphony").order_by(Branch.code)).all()
    failed = db.scalars(select(Order).where(Order.status == "failed").order_by(Order.created_at.desc()).limit(50)).all()
    return {
        "integration": IntegrationOut.model_validate(integ).model_dump(mode="json"),
        "branches": [{"id": b.id, "code": b.code, "name": b.name, "location_ref": b.pos_location_ref,
                      "active": b.is_active} for b in branches],
        "failed_orders": [{"id": o.id, "order_number": o.order_number, "branch_id": o.branch_id,
                           "channel": o.channel, "total": str(o.total), "created_at": o.created_at.isoformat()}
                          for o in failed],
    }


@pos_router.post("/branches/{branch_id}/menu-sync")
def menu_sync(branch_id: int, db: Session = Depends(get_db),
              p: Principal = Depends(require_roles("integration_engineer", "operations"))):
    branch = get_or_404(db, Branch, branch_id)
    result = pos.menu_sync(db, branch, p.subject)
    db.commit()
    return result


@pos_router.post("/branches/{branch_id}/transaction-sync")
def transaction_sync(branch_id: int, business_date: date, db: Session = Depends(get_db),
                     p: Principal = Depends(require_roles("integration_engineer", "operations", "finance"))):
    branch = get_or_404(db, Branch, branch_id)
    result = pos.transaction_sync(db, branch, business_date, p.subject)
    db.commit()
    return result
