"""Incident Management endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Paging, get_or_404, paginate
from app.database import get_db
from app.models import Incident
from app.schemas import IncidentCreate, IncidentDetail, IncidentNote, IncidentOut, IncidentUpdate
from app.security.auth import Principal, get_current_principal, require_roles
from app.services import incidents as svc
from app.services.reporting import bounds

router = APIRouter(prefix="/incidents", tags=["Incidents"])
WRITE_ROLES = ("operations", "integration_engineer", "finance", "branch_manager")


def _detail(db: Session, inc_id: int) -> Incident:
    inc = db.scalar(select(Incident).where(Incident.id == inc_id).options(selectinload(Incident.events)))
    if not inc:
        raise HTTPException(404, "Incident not found")
    return inc


@router.get("")
def list_incidents(paging: Paging = Depends(), status: str | None = None, severity: str | None = None,
                   category: str | None = None, open_only: bool = False, db: Session = Depends(get_db),
                   _: Principal = Depends(get_current_principal)):
    q = select(Incident).order_by(Incident.opened_at.desc())
    if status:
        q = q.where(Incident.status == status)
    if open_only:
        q = q.where(Incident.status.in_(("open", "investigating", "mitigated")))
    if severity:
        q = q.where(Incident.severity == severity)
    if category:
        q = q.where(Incident.category == category)
    total, rows = paginate(db, q, paging)
    return {"total": total, "items": [IncidentOut.model_validate(i) for i in rows]}


@router.post("", response_model=IncidentDetail, status_code=201)
def create(body: IncidentCreate, db: Session = Depends(get_db), p: Principal = Depends(require_roles(*WRITE_ROLES))):
    inc = svc.create_incident(db, actor=p.subject, **body.model_dump())
    db.commit()
    return _detail(db, inc.id)


@router.get("/report")
def resolution_report(start: date | None = None, end: date | None = None, db: Session = Depends(get_db),
                      _: Principal = Depends(get_current_principal)):
    s, e, sd, ed = bounds(start, end)
    rows = db.scalars(select(Incident).where(Incident.opened_at >= s, Incident.opened_at < e)).all()
    resolved = [i for i in rows if i.resolved_at]

    def mins(i):
        a, b = i.opened_at, i.resolved_at
        if a.tzinfo is None or b.tzinfo is None:
            a, b = a.replace(tzinfo=None), b.replace(tzinfo=None)
        return (b - a).total_seconds() / 60

    by_sev: dict[str, dict] = {}
    for i in rows:
        d = by_sev.setdefault(i.severity, {"severity": i.severity, "opened": 0, "resolved": 0, "mttr_minutes": []})
        d["opened"] += 1
        if i.resolved_at:
            d["resolved"] += 1
            d["mttr_minutes"].append(mins(i))
    for d in by_sev.values():
        m = d.pop("mttr_minutes")
        d["mttr_minutes"] = round(sum(m) / len(m), 1) if m else None
    cats = dict(db.execute(select(Incident.category, func.count(Incident.id))
                           .where(Incident.opened_at >= s, Incident.opened_at < e).group_by(Incident.category)).all())
    return {"period": {"start": sd.isoformat(), "end": ed.isoformat()}, "total": len(rows),
            "resolved": len(resolved), "automated": sum(1 for i in rows if i.source == "automated"),
            "by_severity": sorted(by_sev.values(), key=lambda x: x["severity"]), "by_category": cats}


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: int, db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    return _detail(db, incident_id)


@router.patch("/{incident_id}", response_model=IncidentDetail)
def update(incident_id: int, body: IncidentUpdate, db: Session = Depends(get_db),
           p: Principal = Depends(require_roles(*WRITE_ROLES))):
    inc = get_or_404(db, Incident, incident_id, "Incident")
    try:
        svc.update_incident(db, inc, body.model_dump(exclude_unset=True), p.subject)
    except svc.IncidentError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return _detail(db, incident_id)


@router.post("/{incident_id}/notes", response_model=IncidentDetail)
def add_note(incident_id: int, body: IncidentNote, db: Session = Depends(get_db),
             p: Principal = Depends(require_roles(*WRITE_ROLES))):
    inc = get_or_404(db, Incident, incident_id, "Incident")
    svc.add_event(db, inc, "note", body.message, p.subject)
    db.commit()
    return _detail(db, incident_id)


@router.post("/{incident_id}/escalate", response_model=IncidentDetail)
def escalate(incident_id: int, reason: str = Body("", embed=True), db: Session = Depends(get_db),
             p: Principal = Depends(require_roles(*WRITE_ROLES))):
    inc = get_or_404(db, Incident, incident_id, "Incident")
    try:
        svc.escalate(db, inc, p.subject, reason)
    except svc.IncidentError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return _detail(db, incident_id)
