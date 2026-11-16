"""Transactional outbox for n8n notifications.

Business code calls `notify(...)` inside its database transaction. That only
*inserts* a row into `notifications` - it never makes a network call while a
customer's order or payment is being processed. A background dispatcher
(`dispatch_pending`) then POSTs pending rows to n8n asynchronously.

Why an outbox? If n8n is down, orders and payments must still succeed; the
alert is retried later instead of being lost or blocking the request.

If `N8N_WEBHOOK_BASE_URL` is empty the row is stored with status `recorded` so
the alert is still visible in the Automation screen (local demo mode).
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Notification
from app.monitoring.logging import log

logger = logging.getLogger("tableflow.notifications")

# Workflow key -> n8n webhook path (must match the Webhook node path in automation/n8n/*.json)
WORKFLOW_PATHS = {
    "failed_payment": "tableflow-failed-payment",
    "pos_failure": "tableflow-pos-failure",
    "new_order": "tableflow-new-order",
    "loyalty_update": "tableflow-loyalty-update",
    "incident_escalation": "tableflow-incident-escalation",
}


def notify(db: Session, workflow: str, event_type: str, payload: dict) -> Notification:
    base = get_settings().n8n_webhook_base_url.rstrip("/")
    target = f"{base}/{WORKFLOW_PATHS[workflow]}" if base else ""
    n = Notification(
        workflow=workflow,
        event_type=event_type,
        payload=payload,
        status="pending" if target else "recorded",
        target_url=target,
    )
    db.add(n)
    return n


async def dispatch_pending(limit: int = 50) -> int:
    """POST pending notifications to n8n. Returns number successfully sent."""
    settings = get_settings()
    with SessionLocal() as db:
        rows = db.scalars(
            select(Notification).where(Notification.status == "pending").order_by(Notification.id).limit(limit)
        ).all()
        if not rows:
            return 0
        sent = 0
        async with httpx.AsyncClient(timeout=settings.n8n_timeout_seconds) as client:
            for n in rows:
                try:
                    r = await client.post(n.target_url, json={"event_type": n.event_type, **n.payload})
                    r.raise_for_status()
                    n.status, n.error = "sent", None
                    sent += 1
                except httpx.HTTPError as exc:
                    n.status, n.error = "failed", str(exc)[:500]
                    log(logger, logging.WARNING, "n8n notification failed", workflow=n.workflow, error=str(exc))
        db.commit()
        return sent


async def dispatcher_loop(interval_seconds: float = 10.0) -> None:  # pragma: no cover - long-running task
    while True:
        try:
            await dispatch_pending()
        except Exception as exc:  # noqa: BLE001 - never let the loop die
            log(logger, logging.ERROR, "notification dispatcher error", error=str(exc))
        await asyncio.sleep(interval_seconds)
