"""Health, readiness and metrics endpoints (no auth - used by Docker, load balancers and CI)."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Integration
from app.monitoring.metrics import metrics

router = APIRouter(tags=["Health & Monitoring"])


@router.get("/health", summary="Liveness: the process is up")
def health():
    return {"status": "ok", "service": get_settings().app_name, "environment": get_settings().environment}


@router.get("/health/ready", summary="Readiness: database reachable + integration summary")
def ready(db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        db_ok, db_err = True, None
    except Exception as exc:  # noqa: BLE001
        db_ok, db_err = False, str(exc)[:200]
    db_ms = round((time.perf_counter() - started) * 1000, 2)
    integ = []
    if db_ok:
        integ = [{"name": i.name, "status": i.status, "mode": i.mode}
                 for i in db.scalars(select(Integration).order_by(Integration.name))]
    body = {"status": "ready" if db_ok else "not_ready",
            "database": {"ok": db_ok, "latency_ms": db_ms, "error": db_err},
            "integrations": integ,
            "degraded": [i["name"] for i in integ if i["status"] in ("degraded", "down")]}
    return JSONResponse(body, status_code=200 if db_ok else 503)


@router.get("/metrics", summary="Request volume, latency percentiles, error rate, uptime")
def get_metrics():
    return metrics.snapshot()
