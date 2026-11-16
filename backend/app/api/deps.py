"""Shared API helpers."""
from __future__ import annotations

from fastapi import HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class Paging:
    def __init__(self, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        self.limit = limit
        self.offset = offset


def paginate(db: Session, stmt, paging: Paging) -> tuple[int, list]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(stmt.limit(paging.limit).offset(paging.offset)).unique().all()
    return total, rows


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("X-Forwarded-For")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


def get_or_404(db: Session, model, obj_id: int, name: str | None = None):
    obj = db.get(model, obj_id)
    if not obj:
        raise HTTPException(404, f"{name or model.__name__} {obj_id} not found")
    return obj
