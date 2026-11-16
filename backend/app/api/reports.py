"""Executive Dashboard and Reporting & Analytics endpoints."""
from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import Principal, get_current_principal, require_roles
from app.services import reporting

router = APIRouter(tags=["Dashboard & Reports"])


@router.get("/dashboard/summary")
def summary(start: date | None = None, end: date | None = None, branch_id: int | None = None,
            db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    return reporting.dashboard_summary(db, start, end, branch_id)


@router.get("/dashboard/revenue-trend")
def trend(start: date | None = None, end: date | None = None, branch_id: int | None = None,
          db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    return reporting.revenue_trend(db, start, end, branch_id)


@router.get("/dashboard/branch-performance")
def branches(start: date | None = None, end: date | None = None, db: Session = Depends(get_db),
             _: Principal = Depends(get_current_principal)):
    return reporting.branch_performance(db, start, end)


@router.get("/dashboard/daily-transactions")
def daily_tx(start: date | None = None, end: date | None = None, branch_id: int | None = None,
             db: Session = Depends(get_db), _: Principal = Depends(get_current_principal)):
    return reporting.daily_transactions(db, start, end, branch_id)


REPORTS = {
    "daily-sales": lambda db, s, e, b: reporting.revenue_trend(db, s, e, b),
    "monthly-sales": lambda db, s, e, b: reporting.monthly_sales(db, b),
    "branch-performance": lambda db, s, e, b: reporting.branch_performance(db, s, e),
    "payment-success": lambda db, s, e, b: reporting.payment_success(db, s, e),
    "order-volumes": lambda db, s, e, b: reporting.order_volumes(db, s, e),
    "failed-transactions": lambda db, s, e, b: reporting.failed_transactions(db, s, e),
    "integration-performance": lambda db, s, e, b: reporting.integration_performance(db, s, e),
    "loyalty-activity": lambda db, s, e, b: reporting.loyalty_activity(db, s, e),
    "top-products": lambda db, s, e, b: reporting.top_products(db, s, e, b),
}


@router.get("/reports", summary="List available reports")
def list_reports(_: Principal = Depends(get_current_principal)):
    return sorted(REPORTS)


@router.get("/reports/{name}")
def run_report(name: str, start: date | None = None, end: date | None = None, branch_id: int | None = None,
               format: str = Query("json", pattern="^(json|csv)$"), db: Session = Depends(get_db),
               _: Principal = Depends(require_roles("finance", "operations", "branch_manager"))):
    if name not in REPORTS:
        raise HTTPException(404, f"Unknown report. Available: {', '.join(sorted(REPORTS))}")
    rows = REPORTS[name](db, start, end, branch_id)
    if format == "csv":
        buf = io.StringIO()
        if rows:
            keys = sorted({k for r in rows for k in r})
            w = csv.DictWriter(buf, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename={name}.csv"})
    return {"report": name, "rows": rows}
