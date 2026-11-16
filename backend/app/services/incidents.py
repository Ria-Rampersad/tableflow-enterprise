"""Incident management: create, assign, escalate, resolve, auto-raise from integration failures."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentEvent, Integration, User, utcnow
from app.services import audit
from app.services.notifications import notify

INTEGRATION_CATEGORY = {"pos": "pos", "payment": "payment", "ordering": "ordering", "loyalty": "loyalty",
                        "finance": "reconciliation", "backoffice": "infrastructure"}
SEVERITY_FOR_KIND = {"payment": "SEV1", "pos": "SEV2", "ordering": "SEV2", "loyalty": "SEV3",
                     "finance": "SEV3", "backoffice": "SEV4"}

ALLOWED_TRANSITIONS = {
    "open": {"investigating", "mitigated", "resolved"},
    "investigating": {"mitigated", "resolved", "open"},
    "mitigated": {"resolved", "investigating"},
    "resolved": {"closed", "investigating"},
    "closed": set(),
}


class IncidentError(ValueError):
    pass


def add_event(db: Session, incident: Incident, event_type: str, message: str, actor: str = "system") -> IncidentEvent:
    ev = IncidentEvent(incident_id=incident.id, event_type=event_type, message=message, actor=actor)
    db.add(ev)
    return ev


def create_incident(db: Session, *, title: str, severity: str, category: str, description: str = "",
                    source: str = "manual", branch_id=None, integration_id=None, actor: str = "system") -> Incident:
    inc = Incident(reference="PENDING", title=title, severity=severity, category=category, description=description,
                   source=source, branch_id=branch_id, integration_id=integration_id)
    db.add(inc)
    db.flush()
    inc.reference = f"INC-{inc.id:05d}"
    add_event(db, inc, "created", f"Incident created ({severity}) via {source}", actor)
    audit.record(db, actor, "incident.created", "incident", inc.id, {"severity": severity, "title": title})
    if severity in ("SEV1", "SEV2"):
        notify(db, "incident_escalation", "incident.created",
               {"id": inc.id, "reference": inc.reference, "title": title, "severity": severity, "category": category})
    return inc


def auto_raise_integration_incident(db: Session, integ: Integration, error: str) -> Incident:
    """Called by the IntegrationRunner when an integration crosses the failure threshold."""
    existing = db.scalar(
        select(Incident).where(Incident.integration_id == integ.id, Incident.status.in_(("open", "investigating")))
    )
    if existing:
        add_event(db, existing, "note", f"Integration still failing: {error}")
        return existing
    return create_incident(
        db,
        title=f"{integ.display_name} integration down",
        severity=SEVERITY_FOR_KIND.get(integ.kind, "SEV3"),
        category=INTEGRATION_CATEGORY.get(integ.kind, "other"),
        description=f"Automatically raised after {integ.consecutive_failures} consecutive failed calls. "
                    f"Last error: {error}",
        source="automated",
        integration_id=integ.id,
    )


def update_incident(db: Session, inc: Incident, changes: dict, actor: str) -> Incident:
    if "status" in changes and changes["status"] and changes["status"] != inc.status:
        new = changes["status"]
        if new not in ALLOWED_TRANSITIONS[inc.status]:
            raise IncidentError(f"Cannot move incident from {inc.status} to {new}")
        add_event(db, inc, "status_change", f"{inc.status} -> {new}", actor)
        inc.status = new
        if new in ("resolved", "closed") and not inc.resolved_at:
            inc.resolved_at = utcnow()
    if changes.get("severity") and changes["severity"] != inc.severity:
        add_event(db, inc, "note", f"Severity changed {inc.severity} -> {changes['severity']}", actor)
        inc.severity = changes["severity"]
    if changes.get("assigned_to_id") is not None and changes["assigned_to_id"] != inc.assigned_to_id:
        user = db.get(User, changes["assigned_to_id"])
        if not user:
            raise IncidentError("Assignee not found")
        inc.assigned_to_id = user.id
        add_event(db, inc, "assignment", f"Assigned to {user.full_name}", actor)
    for field in ("root_cause", "resolution_notes"):
        if changes.get(field):
            setattr(inc, field, changes[field])
            add_event(db, inc, "note", f"{field.replace('_', ' ').capitalize()} updated", actor)
    audit.record(db, actor, "incident.updated", "incident", inc.id, {k: v for k, v in changes.items() if v is not None})
    return inc


def escalate(db: Session, inc: Incident, actor: str, reason: str = "") -> Incident:
    if inc.status in ("resolved", "closed"):
        raise IncidentError("Cannot escalate a resolved incident")
    inc.escalation_level += 1
    levels = {1: "Solutions Engineering lead", 2: "Head of Engineering", 3: "CTO / vendor executive"}
    target = levels.get(inc.escalation_level, "Executive")
    add_event(db, inc, "escalation", f"Escalated to level {inc.escalation_level} ({target}). {reason}".strip(), actor)
    notify(db, "incident_escalation", "incident.escalated",
           {"id": inc.id, "reference": inc.reference, "title": inc.title, "severity": inc.severity,
            "escalation_level": inc.escalation_level, "escalated_to": target, "reason": reason})
    audit.record(db, actor, "incident.escalated", "incident", inc.id, {"level": inc.escalation_level})
    return inc
