"""Financial Reconciliation endpoints."""
from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Paging, paginate
from app.database import get_db
from app.models import ReconciliationRecord, ReconciliationRun, SettlementRecord
from app.schemas import ReconciliationRecordOut, ReconciliationRequest, ReconciliationRunDetail, ReconciliationRunOut
from app.security.auth import Principal, get_current_principal, require_roles
from app.services import audit
from app.services import reconciliation as svc

router = APIRouter(prefix="/reconciliation", tags=["Financial Reconciliation"])


def _detail(run: ReconciliationRun) -> ReconciliationRunDetail:
    d = ReconciliationRunDetail.model_validate(run)
    d.records = [ReconciliationRecordOut.model_validate(r) for r in run.records if r.issue_type != "matched"]
    d.summary = dict(Counter(r.issue_type for r in run.records))
    return d


@router.post("/runs", response_model=ReconciliationRunDetail, status_code=201)
def start_run(body: ReconciliationRequest, db: Session = Depends(get_db),
              p: Principal = Depends(require_roles("finance", "operations"))):
    run = svc.run(db, body.business_date, body.branch_id, p.subject)
    db.commit()
    run = db.scalar(select(ReconciliationRun).where(ReconciliationRun.id == run.id)
                    .options(selectinload(ReconciliationRun.records)))
    return _detail(run)


@router.get("/runs")
def list_runs(paging: Paging = Depends(), db: Session = Depends(get_db),
              _: Principal = Depends(get_current_principal)):
    total, rows = paginate(db, select(ReconciliationRun).order_by(ReconciliationRun.started_at.desc()), paging)
    return {"total": total, "items": [ReconciliationRunOut.model_validate(r) for r in rows]}


@router.get("/runs/{run_id}", response_model=ReconciliationRunDetail)
def get_run(run_id: int, db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    run = db.scalar(select(ReconciliationRun).where(ReconciliationRun.id == run_id)
                    .options(selectinload(ReconciliationRun.records)))
    if not run:
        raise HTTPException(404, "Run not found")
    return _detail(run)


@router.get("/runs/{run_id}/export", summary="Download reconciliation report as CSV")
def export_run(run_id: int, db: Session = Depends(get_db), _: Principal = Depends(require_roles("finance"))):
    rows = db.scalars(select(ReconciliationRecord).where(ReconciliationRecord.run_id == run_id)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["record_id", "issue_type", "branch_id", "order_id", "payment_id", "expected", "actual", "difference",
                "details", "resolved"])
    for r in rows:
        w.writerow([r.id, r.issue_type, r.branch_id, r.order_id, r.payment_id, r.expected_amount, r.actual_amount,
                    r.difference, r.details, r.resolved])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=reconciliation_{run_id}.csv"})


@router.patch("/records/{record_id}/resolve", response_model=ReconciliationRecordOut)
def resolve_record(record_id: int, db: Session = Depends(get_db), p: Principal = Depends(require_roles("finance"))):
    rec = db.get(ReconciliationRecord, record_id)
    if not rec:
        raise HTTPException(404, "Record not found")
    rec.resolved = True
    audit.record(db, p.subject, "reconciliation.record_resolved", "reconciliation_record", rec.id,
                 {"issue": rec.issue_type})
    db.commit()
    return rec


@router.post("/settlements/import", summary="Import a provider settlement CSV "
             "(columns: provider_reference,branch_code,amount,fee,business_date)")
async def import_settlements(file: UploadFile = File(...), db: Session = Depends(get_db),
                             p: Principal = Depends(require_roles("finance"))):
    text = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    required = {"provider_reference", "branch_code", "amount", "business_date"}
    if not reader.fieldnames or not required <= set(reader.fieldnames):
        raise HTTPException(422, f"CSV must contain columns {sorted(required)}")
    inserted, skipped, errors = 0, 0, []
    existing = set(db.scalars(select(SettlementRecord.provider_reference)))
    for i, row in enumerate(reader, start=2):
        try:
            amount = Decimal(row["amount"])
            fee = Decimal(row.get("fee") or "0")
            bdate = date.fromisoformat(row["business_date"])
        except (InvalidOperation, ValueError) as exc:
            errors.append(f"line {i}: {exc}")
            continue
        if row["provider_reference"] in existing:
            skipped += 1
            continue
        db.add(SettlementRecord(provider="transaction_junction", provider_reference=row["provider_reference"],
                                branch_code=row["branch_code"], amount=amount, fee=fee, business_date=bdate))
        existing.add(row["provider_reference"])
        inserted += 1
    audit.record(db, p.subject, "settlement.imported", "settlement_records", None,
                 {"file": file.filename, "inserted": inserted, "skipped": skipped, "errors": len(errors)})
    db.commit()
    return {"inserted": inserted, "skipped_duplicates": skipped, "errors": errors}
