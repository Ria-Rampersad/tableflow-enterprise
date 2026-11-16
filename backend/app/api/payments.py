"""Payment Integration Hub endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Paging, get_or_404, paginate
from app.database import SessionLocal, get_db
from app.models import Order, Payment, Refund
from app.schemas import PaymentCreate, PaymentOut, RefundCreate, RefundOut
from app.security.auth import Principal, get_current_principal, require_roles
from app.services import payments as svc
from app.services.reporting import bounds
from app.webhooks import processor

router = APIRouter(prefix="/payments", tags=["Payments"])


def _simulate_gateway_callback(payment_id: int, event_type: str = "payment.captured") -> None:
    """The simulated gateway 'calls us back' with a signed webhook, exercising the real verification path."""
    with SessionLocal() as db:
        payment = db.scalar(select(Payment).where(Payment.id == payment_id).options(selectinload(Payment.order)))
        if not payment or payment.status != "authorised":
            return
        body, headers = svc.build_gateway_webhook(payment, event_type)
        processor.handle(db, "transaction_junction", body, headers)
        db.commit()


@router.get("")
def list_payments(paging: Paging = Depends(), status: str | None = None, branch_id: int | None = None,
                  start: date | None = None, end: date | None = None, db: Session = Depends(get_db),
                  _: Principal = Depends(get_current_principal)):
    q = select(Payment).join(Order).order_by(Payment.created_at.desc())
    if status:
        q = q.where(Payment.status == status)
    if branch_id:
        q = q.where(Order.branch_id == branch_id)
    if start or end:
        s, e, *_ = bounds(start, end)
        q = q.where(Payment.created_at >= s, Payment.created_at < e)
    total, rows = paginate(db, q, paging)
    return {"total": total, "items": [PaymentOut.model_validate(p) for p in rows]}


@router.post("", response_model=PaymentOut, status_code=201,
             summary="Initiate a payment (idempotent). Test tokens: tok_visa_approved, tok_declined, "
                     "tok_insufficient_funds, tok_expired, tok_issuer_unavailable")
def create_payment(body: PaymentCreate, response: Response, background: BackgroundTasks,
                   idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=80),
                   auto_capture: bool = True,
                   db: Session = Depends(get_db),
                   p: Principal = Depends(require_roles("operations", "branch_manager", "finance"))):
    payment, replayed = svc.create_payment(db, body, idempotency_key, p.subject)
    db.commit()
    if replayed:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    elif payment.status == "authorised" and auto_capture:
        background.add_task(_simulate_gateway_callback, payment.id)
    return payment


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: int, db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    return get_or_404(db, Payment, payment_id)


@router.post("/{payment_id}/refunds", response_model=RefundOut, status_code=201)
def refund(payment_id: int, body: RefundCreate, db: Session = Depends(get_db),
           p: Principal = Depends(require_roles("finance"))):
    payment = get_or_404(db, Payment, payment_id)
    try:
        r = svc.refund_payment(db, payment, body.amount, body.reason, p.subject)
    except svc.BusinessRuleError:
        db.commit()  # keep the failed refund row + audit entry
        raise
    db.commit()
    return r


@router.get("/{payment_id}/refunds", response_model=list[RefundOut])
def list_refunds(payment_id: int, db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    get_or_404(db, Payment, payment_id)
    return db.scalars(select(Refund).where(Refund.payment_id == payment_id)).all()


@router.post("/{payment_id}/simulate-callback", summary="Demo: make the simulated gateway send a signed webhook")
def simulate_callback(payment_id: int, event_type: str = "payment.captured", db: Session = Depends(get_db),
                      _: Principal = Depends(require_roles("integration_engineer", "operations"))):
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).options(selectinload(Payment.order)))
    if not payment:
        raise HTTPException(404, "Payment not found")
    body, headers = svc.build_gateway_webhook(payment, event_type)
    event, code = processor.handle(db, "transaction_junction", body, headers)
    db.commit()
    return {"http_status": code, "event_id": event.event_id, "status": event.status, "error": event.error,
            "payment_status": db.get(Payment, payment_id).status}
