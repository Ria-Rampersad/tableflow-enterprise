"""Webhook Management: inbound provider webhooks, event history, replay, outbound subscriptions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Paging, get_or_404, paginate
from app.database import get_db
from app.models import WebhookEvent, WebhookSubscription
from app.schemas import WebhookEventOut, WebhookSubscriptionIn, WebhookSubscriptionOut
from app.security.auth import Principal, get_current_principal, require_roles
from app.services import audit
from app.webhooks import processor

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

SOURCES = {"transaction-junction": "transaction_junction", "uber-eats": "uber_eats", "mr-d": "mr_d"}


@router.post("/inbound/{provider}", summary="Receive a signed provider webhook (no bearer token - HMAC verified)")
async def inbound(provider: str, request: Request, db: Session = Depends(get_db)):
    source = SOURCES.get(provider)
    if not source:
        raise HTTPException(404, "Unknown webhook source")
    body = await request.body()  # raw bytes: required for signature verification
    event, code = processor.handle(db, source, body, dict(request.headers))
    db.commit()
    return JSONResponse(status_code=code, content={
        "received": code == 200, "event_id": event.event_id, "status": event.status,
        "error": event.error})


@router.get("/events")
def list_events(paging: Paging = Depends(), source: str | None = None, status: str | None = None,
                event_type: str | None = None, db: Session = Depends(get_db),
                _: Principal = Depends(get_current_principal)):
    q = select(WebhookEvent).order_by(WebhookEvent.received_at.desc())
    if source:
        q = q.where(WebhookEvent.source == source)
    if status:
        q = q.where(WebhookEvent.status == status)
    if event_type:
        q = q.where(WebhookEvent.event_type == event_type)
    total, rows = paginate(db, q, paging)
    return {"total": total, "items": [WebhookEventOut.model_validate(e) for e in rows]}


@router.get("/events/{event_pk}", response_model=WebhookEventOut)
def get_event(event_pk: int, db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    return get_or_404(db, WebhookEvent, event_pk, "Webhook event")


@router.post("/events/{event_pk}/replay", response_model=WebhookEventOut)
def replay(event_pk: int, db: Session = Depends(get_db),
           p: Principal = Depends(require_roles("integration_engineer", "operations"))):
    ev = get_or_404(db, WebhookEvent, event_pk, "Webhook event")
    try:
        processor.replay(db, ev)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    audit.record(db, p.subject, "webhook.replayed", "webhook_event", ev.id, {"result": ev.status})
    db.commit()
    return ev


@router.get("/subscriptions", response_model=list[WebhookSubscriptionOut])
def list_subscriptions(db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    return db.scalars(select(WebhookSubscription).order_by(WebhookSubscription.id)).all()


@router.post("/subscriptions", response_model=WebhookSubscriptionOut, status_code=201,
             summary="Register an outbound webhook target (e.g. an n8n workflow)")
def create_subscription(body: WebhookSubscriptionIn, db: Session = Depends(get_db),
                        p: Principal = Depends(require_roles("integration_engineer"))):
    sub = WebhookSubscription(**body.model_dump())
    db.add(sub)
    db.flush()
    audit.record(db, p.subject, "webhook.subscription_created", "webhook_subscription", sub.id, body.model_dump())
    db.commit()
    return sub


@router.put("/subscriptions/{sub_id}", response_model=WebhookSubscriptionOut)
def update_subscription(sub_id: int, body: WebhookSubscriptionIn, db: Session = Depends(get_db),
                        p: Principal = Depends(require_roles("integration_engineer"))):
    sub = get_or_404(db, WebhookSubscription, sub_id, "Subscription")
    for k, v in body.model_dump().items():
        setattr(sub, k, v)
    audit.record(db, p.subject, "webhook.subscription_updated", "webhook_subscription", sub.id, body.model_dump())
    db.commit()
    return sub
