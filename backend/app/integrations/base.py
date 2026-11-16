"""Shared integration plumbing: errors, simulation knobs, retries, logging, health.

Every outbound call to a third-party system goes through `IntegrationRunner.call`.
That single choke-point gives us, for free on every adapter:

* exponential-backoff retries for *retryable* errors (timeouts, 5xx, 429),
* no retry for *permanent* errors (4xx validation, declined card),
* an `integration_logs` row per attempt (request, response, latency, error),
* rolling health stats on the `integrations` row (status, failures, avg latency),
* automatic incident creation after N consecutive failures.

IMPORTANT: all adapters in this project run in **simulated** mode. They model
the behaviour and payload shapes of the real systems closely enough to build and
test the integration logic, but they do not talk to Oracle, Transaction
Junction, Uber Eats or Mr D. See documentation/04_INTEGRATION_ENGINEERING_HANDBOOK.md.
"""
from __future__ import annotations

import logging
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Integration, IntegrationLog, utcnow
from app.monitoring.logging import correlation_id_var, log

logger = logging.getLogger("tableflow.integrations")


class AdapterError(Exception):
    def __init__(self, message: str, http_status: int = 500, retryable: bool = True, payload: dict | None = None):
        super().__init__(message)
        self.http_status = http_status
        self.retryable = retryable
        self.payload = payload or {}


@dataclass
class CallResult:
    ok: bool
    data: dict[str, Any] | None
    error: str | None
    attempts: int
    log_id: int | None


class SimulatedAdapter:
    """Base for simulated vendor adapters. Reads failure knobs from the integration row's config."""

    name: str = "base"

    def __init__(self, integration: Integration):
        self.integration = integration
        self.config = integration.config or {}

    def _simulate_transport(self) -> int:
        """Mimic network behaviour: outages, random failures, latency. Returns simulated latency in ms."""
        latency = int(self.config.get("latency_ms", random.randint(40, 220)))
        if self.config.get("simulate_outage"):
            raise AdapterError(f"{self.integration.display_name} unavailable (HTTP 503)", 503, retryable=True)
        rate = float(self.config.get("failure_rate", 0.0))
        if rate and random.random() < rate:
            raise AdapterError(f"{self.integration.display_name} timed out after 10s", 504, retryable=True)
        return latency

    def ping(self) -> dict:
        latency = self._simulate_transport()
        return {"status": "ok", "latency_ms": latency, "mode": self.integration.mode}


def get_integration(db: Session, name: str) -> Integration:
    integ = db.scalar(select(Integration).where(Integration.name == name))
    if not integ:
        raise LookupError(f"Integration '{name}' is not registered")
    return integ


class IntegrationRunner:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def call(
        self,
        integration: Integration,
        operation: str,
        fn: Callable[[], dict],
        *,
        request_payload: dict | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        branch_id: int | None = None,
        max_attempts: int | None = None,
    ) -> CallResult:
        attempts = max_attempts or self.settings.retry_max_attempts
        delay = self.settings.retry_base_delay_seconds
        corr = correlation_id_var.get() if correlation_id_var.get() != "-" else uuid.uuid4().hex[:16]
        last_err: AdapterError | None = None
        last_log: IntegrationLog | None = None

        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                data = fn()
                elapsed = int((time.perf_counter() - started) * 1000) + int(data.pop("_latency_ms", 0))
                last_log = self._log(integration, operation, "success" if attempt == 1 else "retried_ok", 200,
                                     elapsed, attempt, corr, entity_type, entity_id, branch_id, request_payload, data, None)
                self._record_success(integration, elapsed)
                log(logger, logging.INFO, "integration call succeeded", integration=integration.name,
                    operation=operation, attempt=attempt, response_ms=elapsed)
                return CallResult(True, data, None, attempt, last_log.id)
            except AdapterError as err:
                elapsed = int((time.perf_counter() - started) * 1000)
                last_err = err
                final = (not err.retryable) or attempt == attempts
                last_log = self._log(integration, operation, "failed" if final else "retrying", err.http_status,
                                     elapsed, attempt, corr, entity_type, entity_id, branch_id, request_payload,
                                     err.payload or None, str(err))
                log(logger, logging.WARNING, "integration call failed", integration=integration.name,
                    operation=operation, attempt=attempt, retryable=err.retryable, error=str(err))
                if final:
                    break
                if delay:
                    time.sleep(delay * (2 ** (attempt - 1)))  # 0.2s, 0.4s, 0.8s ...

        assert last_err is not None
        self._record_failure(integration, str(last_err), permanent=not last_err.retryable)
        return CallResult(False, None, str(last_err), attempt, last_log.id if last_log else None)

    # ------------------------------------------------------------ internals
    def _log(self, integ, operation, status, http_status, ms, attempt, corr, etype, eid, branch_id, req, resp, err):
        entry = IntegrationLog(
            integration_id=integ.id, operation=operation, status=status, http_status=http_status,
            response_ms=ms, attempt=attempt, correlation_id=corr, entity_type=etype, entity_id=eid,
            branch_id=branch_id, request_payload=req, response_payload=resp, error_message=err,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def _record_success(self, integ: Integration, ms: int) -> None:
        integ.total_requests += 1
        integ.consecutive_failures = 0
        integ.last_success_at = utcnow()
        integ.avg_response_ms = int((integ.avg_response_ms * 0.8) + (ms * 0.2)) if integ.avg_response_ms else ms
        if integ.status != "disabled":
            integ.status = "healthy"

    def _record_failure(self, integ: Integration, error: str, permanent: bool) -> None:
        integ.total_requests += 1
        integ.total_failures += 1
        integ.last_failure_at = utcnow()
        integ.last_error = error
        if permanent:
            # A declined card or bad payload is a business failure, not an integration-health problem.
            return
        integ.consecutive_failures += 1
        threshold = self.settings.incident_failure_threshold
        integ.status = "down" if integ.consecutive_failures >= threshold else "degraded"
        if integ.consecutive_failures == threshold:
            from app.services.incidents import auto_raise_integration_incident  # avoid import cycle

            auto_raise_integration_incident(self.db, integ, error)
