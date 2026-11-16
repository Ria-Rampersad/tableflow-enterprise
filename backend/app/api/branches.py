"""Restaurant branch management."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_or_404
from app.database import get_db
from app.models import Branch, IntegrationLog, Order
from app.schemas import BranchCreate, BranchOut, BranchUpdate
from app.security.auth import Principal, get_current_principal, require_roles
from app.services import audit, reporting

router = APIRouter(prefix="/branches", tags=["Branches"])


@router.get("", response_model=list[BranchOut])
def list_branches(province: str | None = None, active: bool | None = None, db: Session = Depends(get_db),
                  _: Principal = Depends(get_current_principal)):
    q = select(Branch).order_by(Branch.province, Branch.name)
    if province:
        q = q.where(Branch.province == province)
    if active is not None:
        q = q.where(Branch.is_active.is_(active))
    return db.scalars(q).all()


@router.post("", response_model=BranchOut, status_code=201)
def create_branch(body: BranchCreate, db: Session = Depends(get_db), p: Principal = Depends(require_roles("admin"))):
    if db.scalar(select(Branch).where(Branch.code == body.code)):
        raise HTTPException(409, f"Branch code {body.code} already exists")
    branch = Branch(**body.model_dump())
    db.add(branch)
    db.flush()
    audit.record(db, p.subject, "branch.created", "branch", branch.id, body.model_dump(mode="json"))
    db.commit()
    return branch


@router.get("/{branch_id}", response_model=BranchOut)
def get_branch(branch_id: int, db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    return get_or_404(db, Branch, branch_id)


@router.put("/{branch_id}", response_model=BranchOut, summary="Replace branch details (full update)")
def replace_branch(branch_id: int, body: BranchCreate, db: Session = Depends(get_db),
                   p: Principal = Depends(require_roles("admin"))):
    branch = get_or_404(db, Branch, branch_id)
    if body.code != branch.code and db.scalar(select(Branch).where(Branch.code == body.code)):
        raise HTTPException(409, f"Branch code {body.code} already exists")
    for k, v in body.model_dump().items():
        setattr(branch, k, v)
    audit.record(db, p.subject, "branch.replaced", "branch", branch.id, body.model_dump(mode="json"))
    db.commit()
    return branch


@router.patch("/{branch_id}", response_model=BranchOut, summary="Partially update branch (e.g. assign POS / payment)")
def update_branch(branch_id: int, body: BranchUpdate, db: Session = Depends(get_db),
                  p: Principal = Depends(require_roles("admin", "operations"))):
    branch = get_or_404(db, Branch, branch_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(branch, k, v)
    audit.record(db, p.subject, "branch.updated", "branch", branch.id, changes)
    db.commit()
    return branch


@router.get("/{branch_id}/performance")
def branch_performance(branch_id: int, start: date | None = None, end: date | None = None,
                       db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    branch = get_or_404(db, Branch, branch_id)
    return {
        "branch": BranchOut.model_validate(branch).model_dump(mode="json"),
        "summary": reporting.dashboard_summary(db, start, end, branch_id),
        "trend": reporting.revenue_trend(db, start, end, branch_id),
        "transactions": reporting.daily_transactions(db, start, end, branch_id),
        "top_products": reporting.top_products(db, start, end, branch_id),
    }


@router.get("/{branch_id}/integration-health")
def branch_integration_health(branch_id: int, limit: int = Query(50, le=200), db: Session = Depends(get_db),
                              _: Principal = Depends(get_current_principal)):
    get_or_404(db, Branch, branch_id)
    logs = db.scalars(select(IntegrationLog).where(IntegrationLog.branch_id == branch_id)
                      .order_by(IntegrationLog.created_at.desc()).limit(limit)).all()
    failed = [entry for entry in logs if entry.status == "failed"]
    stuck = db.scalars(select(Order).where(Order.branch_id == branch_id, Order.status == "failed")).all()
    return {
        "recent_calls": len(logs),
        "recent_failures": len(failed),
        "orders_failed_to_reach_pos": [{"id": o.id, "order_number": o.order_number, "total": str(o.total)} for o in stuck],
        "last_errors": [{"integration": entry.integration.display_name, "operation": entry.operation,
                         "error": entry.error_message, "at": entry.created_at.isoformat()} for entry in failed[:10]],
    }
