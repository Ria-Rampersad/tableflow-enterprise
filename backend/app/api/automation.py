"""Internal Automation Tools - called from the UI and by n8n workflows (client-credentials token)."""
from __future__ import annotations

import hmac
from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Paging, get_or_404, paginate
from app.config import get_settings
from app.database import get_db
from app.integrations.base import AdapterError
from app.models import AuditLog, Branch, Notification, utcnow
from app.security.auth import Principal, get_current_principal, require_roles
from app.services import automation, incidents
from app.services import reconciliation as recon

router = APIRouter(prefix="/automation", tags=["Automation"])
admin = APIRouter(tags=["Audit & Notifications"])


def _yesterday() -> date:
    return (utcnow() + timedelta(hours=2)).date() - timedelta(days=1)


@router.get("/daily-summary")
def daily_summary(business_date: date | None = None, db: Session = Depends(get_db),
                  _: Principal = Depends(require_roles("finance", "operations"))):
    return automation.daily_summary(db, business_date or _yesterday())


@router.post("/daily-reconciliation", summary="Reconcile all branches for a day (default: yesterday)")
def daily_reconciliation(business_date: date | None = None, db: Session = Depends(get_db),
                         p: Principal = Depends(require_roles("finance", "operations"))):
    d = business_date or _yesterday()
    run = recon.run(db, d, None, p.subject)
    db.commit()
    return {"run_id": run.id, "business_date": d.isoformat(), "total_orders": run.total_orders,
            "matched": run.matched, "discrepancies": run.discrepancies,
            "discrepancy_value": str(run.discrepancy_value), "status": run.status}


@router.post("/discrepancy-scan")
def discrepancy_scan(stale_minutes: int = 30, raise_incident: bool = False, db: Session = Depends(get_db),
                     p: Principal = Depends(require_roles("operations", "finance"))):
    result = automation.discrepancy_scan(db, stale_minutes)
    if raise_incident and result["total_issues"]:
        inc = incidents.create_incident(
            db, title=f"Order/payment discrepancies detected ({result['total_issues']})", severity="SEV3",
            category="reconciliation", source="automated", actor=p.subject,
            description=f"{len(result['stuck_orders'])} stuck orders, {len(result['uncaptured_payments'])} "
                        f"uncaptured payments, {result['failed_loyalty_syncs']} failed loyalty syncs, "
                        f"{result['failed_webhook_events']} failed webhooks.")
        result["incident"] = inc.reference
    db.commit()
    return result


@router.post("/integration-health-check")
def health_check(db: Session = Depends(get_db),
                 p: Principal = Depends(require_roles("operations", "integration_engineer"))):
    out = automation.integration_health_check(db, p.subject)
    db.commit()
    return {"checked_at": utcnow().isoformat(), "results": out,
            "down": [r["integration"] for r in out if r.get("status") == "down"]}


@router.get("/low-stock")
def low_stock(db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    items = automation.low_stock(db)
    db.commit()
    return {"count": len(items), "items": items}


@router.post("/finance-journal/{branch_id}")
def finance_journal(branch_id: int, business_date: date | None = None, db: Session = Depends(get_db),
                    p: Principal = Depends(require_roles("finance"))):
    branch = get_or_404(db, Branch, branch_id)
    try:
        res = automation.post_finance_journal(db, business_date or _yesterday(), branch, p.subject)
    except AdapterError as exc:
        db.commit()
        raise HTTPException(502, str(exc)) from exc
    db.commit()
    return res


@admin.get("/notifications", summary="Outbox of alerts sent to (or recorded for) n8n")
def notifications(paging: Paging = Depends(), workflow: str | None = None, db: Session = Depends(get_db),
                  _: Principal = Depends(get_current_principal)):
    q = select(Notification).order_by(Notification.created_at.desc())
    if workflow:
        q = q.where(Notification.workflow == workflow)
    total, rows = paginate(db, q, paging)
    return {"total": total, "items": [{"id": n.id, "workflow": n.workflow, "event_type": n.event_type,
                                       "status": n.status, "payload": n.payload, "target_url": n.target_url,
                                       "error": n.error, "created_at": n.created_at.isoformat()} for n in rows]}


@admin.get("/audit-logs")
def audit_logs(paging: Paging = Depends(), entity_type: str | None = None, actor: str | None = None,
               db: Session = Depends(get_db), _: Principal = Depends(require_roles("admin", "finance"))):
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if actor:
        q = q.where(AuditLog.actor.ilike(f"%{actor}%"))
    total, rows = paginate(db, q, paging)
    return {"total": total, "items": [{"id": a.id, "actor": a.actor, "action": a.action,
                                       "entity_type": a.entity_type, "entity_id": a.entity_id,
                                       "details": a.details, "ip_address": a.ip_address,
                                       "correlation_id": a.correlation_id, "created_at": a.created_at.isoformat()}
                                      for a in rows]}


@admin.post("/alerts/sink", status_code=202,
            summary="Local alert sink: n8n posts Slack-style alerts here when no real channel is configured")
def alert_sink(payload: dict = Body(...), x_alert_token: str | None = Header(default=None, alias="X-Alert-Token"),
               db: Session = Depends(get_db)):
    if not x_alert_token or not hmac.compare_digest(x_alert_token, get_settings().alert_sink_token):
        raise HTTPException(401, "Invalid alert token")
    n = Notification(workflow="n8n_alert", event_type=str(payload.get("channel", "alert")), payload=payload,
                     status="delivered")
    db.add(n)
    db.commit()
    return {"delivered": True, "id": n.id}
