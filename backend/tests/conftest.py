"""Shared test fixtures.

By default tests run against an in-memory SQLite database (fast, no services).
Set TEST_DATABASE_URL to a PostgreSQL URL to run the *same* suite against
PostgreSQL using the real SQL migrations (this is what CI does):

    TEST_DATABASE_URL=postgresql+psycopg://tableflow:tableflow@localhost:5432/tableflow_test pytest
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest

TEST_DB = os.getenv("TEST_DATABASE_URL", "sqlite://")
os.environ.update({
    "DATABASE_URL": TEST_DB,
    "ENVIRONMENT": "test",
    "RETRY_BASE_DELAY_SECONDS": "0",
    "JWT_SECRET_KEY": "test-secret-key-0123456789abcdef",
    "N8N_WEBHOOK_BASE_URL": "",
    "LOG_LEVEL": "WARNING",
    "SEED_DEMO_PASSWORD": "TableFlow!2026",
    "ALERT_SINK_TOKEN": "dev-alert-sink-token",
})

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Integration  # noqa: E402
from app.monitoring.ratelimit import limiter  # noqa: E402
from app.seed import seed  # noqa: E402

IS_PG = TEST_DB.startswith("postgresql")
PASSWORD = "TableFlow!2026"
USERS = {
    "admin": "admin@tableflow.local",
    "finance": "finance@tableflow.local",
    "operations": "ops@tableflow.local",
    "branch_manager": "manager.umhlanga@tableflow.local",
    "integration_engineer": "engineer@tableflow.local",
}


@pytest.fixture(scope="session", autouse=True)
def database():
    if IS_PG:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        from app.migrate import migrate

        migrate(verbose=False)
    else:
        Base.metadata.create_all(engine)
    seed(days=5)
    yield


@pytest.fixture(autouse=True)
def healthy_integrations():
    """Every test starts with all simulated integrations healthy and no rate-limit history."""
    limiter.reset()
    with SessionLocal() as db:
        for integ in db.scalars(select(Integration)):
            integ.config = {"simulate_outage": False, "failure_rate": 0.0, "latency_ms": 50}
            integ.status = "healthy"
            integ.consecutive_failures = 0
        db.commit()
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def tokens(client):
    out = {}
    for role, email in USERS.items():
        r = client.post("/api/v1/auth/login", data={"username": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        out[role] = r.json()["access_token"]
    limiter.reset()
    return out


@pytest.fixture
def auth(tokens):
    def _h(role: str = "admin", **extra) -> dict:
        return {"Authorization": f"Bearer {tokens[role]}", **extra}

    return _h


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def set_integration(name: str, **cfg):
    with SessionLocal() as s:
        integ = s.scalar(select(Integration).where(Integration.name == name))
        integ.config = {**(integ.config or {}), **cfg}
        s.commit()


def uber_payload(branch_code="DBN-UML", items=(("CHK-QTR", 2, 6990), ("DRK-CAN", 1, 2190)), ext=None,
                 phone="+27821234567", total=None):
    lines = [{"external_data": sku, "quantity": q, "price": {"unit_price": {"amount": c, "currency_code": "ZAR"}}}
             for sku, q, c in items]
    t = total if total is not None else sum(q * c for _, q, c in items)
    return {
        "id": ext or str(uuid.uuid4()),
        "display_id": "A1B2C",
        "store": {"id": "uber-store-1", "external_reference_id": branch_code},
        "eater": {"first_name": "Thabo", "last_name": "Nkosi", "phone": phone},
        "cart": {"items": lines, "special_instructions": "Extra peri-peri"},
        "payment": {"charges": {"total": {"amount": t, "currency_code": "ZAR"}}},
        "placed_at": "2026-11-16T12:30:00+02:00",
    }


def mrd_payload(branch_code="DBN-PNT", ext=None, lines=(("BRG-CLS", 1, "74.90"), ("SIDE-CHP", 1, "29.90"))):
    return {
        "orderReference": ext or f"MRD-{uuid.uuid4().int % 10**8:08d}",
        "restaurant": {"branchCode": branch_code},
        "customer": {"name": "Ayanda Zulu", "mobile": "0731234567"},
        "lines": [{"productCode": s, "qty": q, "unitPrice": float(p)} for s, q, p in lines],
        "orderTotal": float(sum(Decimal(p) * q for _, q, p in lines)),
        "createdAt": "2026-11-16T12:31:00+02:00",
    }


UBER_KEY = {"X-API-Key": "dev-uber-key-change-me"}
MRD_KEY = {"X-API-Key": "dev-mrd-key-change-me"}


@pytest.fixture
def make_order(client, auth, db):
    """Create an in-store order at DBN-UML and return its JSON."""

    def _make(items=None, branch_code="DBN-UML", phone="0821112233"):
        from app.models import Branch

        branch = db.scalar(select(Branch).where(Branch.code == branch_code))
        body = {"branch_id": branch.id, "channel": "in_store", "customer_phone": phone, "customer_name": "Test Guest",
                "items": items or [{"sku": "CHK-HLF", "quantity": 1}, {"sku": "SIDE-CHP", "quantity": 2}]}
        r = client.post("/api/v1/orders", json=body, headers=auth("operations"))
        assert r.status_code == 201, r.text
        return r.json()["order"]

    return _make
