"""Demo-only simulators (disabled when ENVIRONMENT=production).

Let the UI generate realistic provider traffic without putting partner API keys
or webhook secrets in the browser. Each simulator builds the provider-shaped
payload and pushes it through the *same* code path a real provider call takes
(adapter mapping -> validation -> ingest -> background POS forwarding, or
signature verification -> webhook pipeline).
"""
from __future__ import annotations

import json
import random
import uuid
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.orders import _ingest_partner
from app.config import get_settings
from app.database import get_db
from app.models import Branch, Order, Product
from app.security import signatures
from app.security.auth import Principal, require_roles
from app.webhooks import processor

router = APIRouter(prefix="/simulate", tags=["Demo Simulators"])


def _guard():
    if get_settings().environment == "production":
        raise HTTPException(404, "Not found")


class PartnerOrderSim(BaseModel):
    provider: str = Field(pattern="^(uber_eats|mr_d)$")
    branch_code: str = "DBN-UML"
    items: int = Field(2, ge=1, le=6)
    repeat_external_ref: str | None = None  # send a previous ref again to demo duplicate prevention
    corrupt_total: bool = False             # demo validation failure


class CancelSim(BaseModel):
    order_id: int


@router.post("/partner-order", dependencies=[Depends(_guard)])
def partner_order(body: PartnerOrderSim, background: BackgroundTasks, db: Session = Depends(get_db),
                  _: Principal = Depends(require_roles("integration_engineer", "operations"))):
    products = db.scalars(select(Product).where(Product.is_active.is_(True))).all()
    chosen = random.sample(products, body.items)
    lines = [(p, random.choice([1, 1, 2])) for p in chosen]
    total = sum((p.price * q for p, q in lines), Decimal("0"))
    if body.corrupt_total:
        total += Decimal("10.00")
    if body.provider == "uber_eats":
        payload = {
            "id": body.repeat_external_ref or str(uuid.uuid4()), "display_id": uuid.uuid4().hex[:5].upper(),
            "store": {"id": "uber-store", "external_reference_id": body.branch_code},
            "eater": {"first_name": "Naledi", "last_name": "Molefe", "phone": f"+2782{random.randint(1000000, 9999999)}"},
            "cart": {"items": [{"external_data": p.sku, "quantity": q,
                                "price": {"unit_price": {"amount": int(p.price * 100), "currency_code": "ZAR"}}}
                               for p, q in lines], "special_instructions": ""},
            "payment": {"charges": {"total": {"amount": int(total * 100), "currency_code": "ZAR"}}},
        }
    else:
        payload = {
            "orderReference": body.repeat_external_ref or f"MRD-{random.randint(10**7, 10**8 - 1)}",
            "restaurant": {"branchCode": body.branch_code},
            "customer": {"name": "Bongani Khumalo", "mobile": f"07{random.randint(10**7, 10**8 - 1)}"},
            "lines": [{"productCode": p.sku, "qty": q, "unitPrice": float(p.price)} for p, q in lines],
            "orderTotal": float(total),
        }
    result = _ingest_partner(body.provider, payload, background, db)
    return {"provider_payload": payload, "result": result}


@router.post("/provider-cancel", dependencies=[Depends(_guard)])
def provider_cancel(body: CancelSim, db: Session = Depends(get_db),
                    _: Principal = Depends(require_roles("integration_engineer", "operations"))):
    order = db.get(Order, body.order_id)
    if not order or order.channel not in ("uber_eats", "mr_d"):
        raise HTTPException(404, "Digital order not found")
    if order.channel == "uber_eats":
        source = "uber_eats"
        raw = json.dumps({"event_id": str(uuid.uuid4()), "event_type": "orders.cancel",
                          "meta": {"resource_id": order.external_ref, "reason": "Eater cancelled"}}).encode()
    else:
        source = "mr_d"
        raw = json.dumps({"eventId": str(uuid.uuid4()), "eventType": "ORDER_CANCELLED",
                          "orderReference": order.external_ref, "reason": "Customer cancelled"}).encode()
    event, code = processor.handle(db, source, raw, signatures.sign(source, raw))
    db.commit()
    return {"http_status": code, "event_status": event.status, "error": event.error}


@router.post("/bad-signature-webhook", dependencies=[Depends(_guard)])
def bad_signature(db: Session = Depends(get_db),
                  _: Principal = Depends(require_roles("integration_engineer", "operations"))):
    raw = json.dumps({"id": f"evt_{uuid.uuid4().hex[:12]}", "type": "payment.captured",
                      "data": {"transactionId": "TJFORGED", "amount": "999.00"}}).encode()
    event, code = processor.handle(db, "transaction_junction", raw, {"X-TJ-Signature": "t=0,v1=forged"})
    db.commit()
    return {"http_status": code, "event_status": event.status, "error": event.error}


@router.get("/branches-with-channel", dependencies=[Depends(_guard)])
def branches_with_channel(provider: str, db: Session = Depends(get_db),
                          _: Principal = Depends(require_roles("integration_engineer", "operations"))):
    return [b.code for b in db.scalars(select(Branch).order_by(Branch.code)) if provider in (b.digital_channels or [])]
