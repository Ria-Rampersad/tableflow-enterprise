"""Loyalty Management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import Paging, get_or_404, paginate
from app.database import get_db
from app.models import Customer, LoyaltyAccount, LoyaltyTransaction
from app.schemas import LoyaltyAccountOut, LoyaltyTxnOut, RedeemRequest
from app.security.auth import Principal, get_current_principal, require_roles
from app.services import loyalty as svc

router = APIRouter(prefix="/loyalty", tags=["Loyalty"])


def _acc_out(a: LoyaltyAccount) -> LoyaltyAccountOut:
    return LoyaltyAccountOut(id=a.id, member_number=a.member_number, customer_name=a.customer.full_name,
                             phone=a.customer.phone, points_balance=a.points_balance,
                             lifetime_points=a.lifetime_points, tier=a.tier)


@router.get("/accounts")
def list_accounts(paging: Paging = Depends(), search: str | None = None, tier: str | None = None,
                  db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    q = select(LoyaltyAccount).join(Customer).order_by(LoyaltyAccount.lifetime_points.desc())
    if search:
        q = q.where(or_(Customer.full_name.ilike(f"%{search}%"), Customer.phone.ilike(f"%{search}%"),
                        LoyaltyAccount.member_number.ilike(f"%{search}%")))
    if tier:
        q = q.where(LoyaltyAccount.tier == tier)
    total, rows = paginate(db, q, paging)
    return {"total": total, "items": [_acc_out(a) for a in rows]}


@router.get("/accounts/{account_id}")
def get_account(account_id: int, db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    acc = get_or_404(db, LoyaltyAccount, account_id, "Loyalty account")
    txns = db.scalars(select(LoyaltyTransaction).where(LoyaltyTransaction.account_id == account_id)
                      .order_by(LoyaltyTransaction.created_at.desc()).limit(100)).all()
    return {"account": _acc_out(acc), "transactions": [LoyaltyTxnOut.model_validate(t) for t in txns]}


@router.post("/accounts/{account_id}/redeem", response_model=LoyaltyTxnOut, status_code=201)
def redeem(account_id: int, body: RedeemRequest, db: Session = Depends(get_db),
           p: Principal = Depends(require_roles("operations", "branch_manager"))):
    acc = get_or_404(db, LoyaltyAccount, account_id, "Loyalty account")
    try:
        txn = svc.redeem(db, acc, body.points, body.order_id, p.subject)
    except svc.BusinessRuleError:
        db.rollback()
        raise
    db.commit()
    return txn


@router.get("/transactions")
def list_transactions(paging: Paging = Depends(), sync_status: str | None = None, db: Session = Depends(get_db),
                      _: Principal = Depends(get_current_principal)):
    q = select(LoyaltyTransaction).order_by(LoyaltyTransaction.created_at.desc())
    if sync_status:
        q = q.where(LoyaltyTransaction.sync_status == sync_status)
    total, rows = paginate(db, q, paging)
    return {"total": total, "items": [LoyaltyTxnOut.model_validate(t) for t in rows]}


@router.post("/transactions/{txn_id}/retry", response_model=LoyaltyTxnOut)
def retry(txn_id: int, db: Session = Depends(get_db),
          p: Principal = Depends(require_roles("operations", "integration_engineer"))):
    txn = get_or_404(db, LoyaltyTransaction, txn_id, "Loyalty transaction")
    if txn.sync_status != "failed":
        raise HTTPException(409, "Only failed loyalty transactions can be retried")
    svc.retry_sync(db, txn, p.subject)
    db.commit()
    return txn
