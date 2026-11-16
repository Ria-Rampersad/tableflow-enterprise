"""FastAPI application factory.

Wires together: structured logging, correlation IDs, request metrics, CORS,
consistent JSON error responses, all routers under /api/v1, and the
background notification dispatcher. Swagger UI: /docs  - ReDoc: /redoc
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    auth,
    automation,
    branches,
    health,
    incidents,
    integrations,
    loyalty,
    orders,
    payments,
    reconciliation,
    reports,
    simulate,
    webhooks,
)
from app.config import get_settings
from app.database import Base, engine
from app.monitoring.logging import configure_logging, correlation_id_var, log
from app.monitoring.metrics import metrics
from app.services.orders import BusinessRuleError

logger = logging.getLogger("tableflow.api")

DESCRIPTION = """
**TableFlow Enterprise** - restaurant operations, payments, integrations & automation platform
(portfolio project; all vendor integrations are **simulated**).

Authenticate with **Authorize** (OAuth2 password flow) using a seeded user, e.g.
`admin@tableflow.local` / `TableFlow!2026`. Partner endpoints use the `X-API-Key` header;
inbound webhooks are verified by HMAC signature.
"""


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.auto_create_schema:
        Base.metadata.create_all(engine)
    task = None
    if settings.n8n_webhook_base_url and settings.environment != "test":
        from app.services.notifications import dispatcher_loop

        task = asyncio.create_task(dispatcher_loop())
    log(logger, logging.INFO, "TableFlow API started", environment=settings.environment)
    yield
    if task:
        task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TableFlow Enterprise API", version="1.0.0", description=DESCRIPTION, lifespan=lifespan,
                  openapi_tags=[{"name": "Authentication", "description": "OAuth 2.0 password + client credentials"}])

    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["X-Request-ID", "Idempotent-Replayed"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        corr = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token = correlation_id_var.set(corr)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = corr
            return response
        finally:
            ms = (time.perf_counter() - started) * 1000
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            metrics.record(request.method, path, status, ms)
            if not request.url.path.startswith(("/health", "/metrics")):
                log(logger, logging.INFO if status < 500 else logging.ERROR, "request",
                    method=request.method, path=request.url.path, status=status, duration_ms=round(ms, 2))
            correlation_id_var.reset(token)

    def error(status: int, code: str, message, details=None):
        return JSONResponse(status_code=status, content={"error": {
            "code": code, "message": message, "details": details, "correlation_id": correlation_id_var.get()}})

    @app.exception_handler(BusinessRuleError)
    async def business_error(_: Request, exc: BusinessRuleError):
        return error(exc.status_code, exc.code, str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return error(422, "VALIDATION_ERROR", "Request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        resp = error(exc.status_code, f"HTTP_{exc.status_code}", exc.detail)
        for k, v in (exc.headers or {}).items():
            resp.headers[k] = v
        return resp

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("unhandled error", extra={"extra_fields": {"error": str(exc)}})
        return error(500, "INTERNAL_ERROR", "An unexpected error occurred. Quote the correlation_id to support.")

    app.include_router(health.router)
    api_prefix = "/api/v1"
    for r in (auth.router, branches.router, orders.router, orders.partners, payments.router, loyalty.router,
              integrations.router, integrations.pos_router, webhooks.router, incidents.router,
              reconciliation.router, reports.router, automation.router, automation.admin, simulate.router):
        app.include_router(r, prefix=api_prefix)
    return app


app = create_app()
