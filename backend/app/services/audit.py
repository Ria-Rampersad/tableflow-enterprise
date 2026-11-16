"""Audit trail. Every state-changing business action writes one row here.

The audit log answers "who changed what, when, from where" - essential for
financial systems (refunds, reconciliation sign-off) and for incident reviews.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.monitoring.logging import correlation_id_var


def record(db: Session, actor: str, action: str, entity_type: str, entity_id=None, details: dict | None = None,
           ip: str | None = None) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details,
        ip_address=ip,
        correlation_id=correlation_id_var.get(),
    )
    db.add(entry)
    return entry
