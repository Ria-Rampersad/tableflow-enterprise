"""Contract tests: n8n workflow files, Postman collection and SQL migrations agree with the running code.

These are static/structural checks. They do NOT prove the workflows run inside
n8n (that needs an n8n instance - see documentation/testing/TEST_REPORT.md).
"""
import json
import re
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.database import Base, engine
from app.main import app
from app.services.notifications import WORKFLOW_PATHS
from tests.conftest import IS_PG

ROOT = Path(__file__).resolve().parents[2]
N8N = sorted((ROOT / "automation" / "n8n").glob("*.json"))


def _route_patterns():
    # Read routes from the OpenAPI spec: newer FastAPI versions nest included routers, so
    # app.routes is not a flat list (found when this test first ran).
    pats = []
    for path, ops in app.openapi()["paths"].items():
        regex = "^" + re.sub(r"\{[^/]+\}", "[^/]+", path) + "$"
        pats.append((regex, {m.upper() for m in ops}))
    return pats


ROUTES = _route_patterns()


def route_exists(method: str, path: str) -> bool:
    path = path.split("?")[0]
    return any(re.match(rx, path) and method in methods for rx, methods in ROUTES)


def test_eight_n8n_workflows_present():
    names = {p.stem for p in N8N}
    assert len(N8N) == 8, names


@pytest.mark.parametrize("wf", N8N, ids=lambda p: p.stem)
def test_n8n_workflow_structure_and_api_calls(wf):
    data = json.loads(wf.read_text())
    assert data["name"] and isinstance(data["nodes"], list) and data["nodes"]
    names = [n["name"] for n in data["nodes"]]
    assert len(names) == len(set(names)), "node names must be unique"
    for src, conns in data["connections"].items():
        assert src in names
        for branch in conns["main"]:
            for c in branch:
                assert c["node"] in names, f"connection to missing node {c['node']}"
    triggers = [n for n in data["nodes"] if n["type"] in ("n8n-nodes-base.webhook", "n8n-nodes-base.scheduleTrigger")]
    assert len(triggers) == 1
    for n in data["nodes"]:
        if n["type"] == "n8n-nodes-base.webhook":
            assert n["parameters"]["path"] in WORKFLOW_PATHS.values()
        if n["type"] == "n8n-nodes-base.httpRequest":
            url = re.sub(r"\{\{.*?\}\}", "1", n["parameters"]["url"].replace("{{ $env.TABLEFLOW_API_URL }}",
                                                                              "TABLEFLOW_API"))
            m = re.search(r"/api/v1/[^\"'}\s]+|/health[^\"'}\s]*", url)
            if m and "TABLEFLOW_API" in url:
                assert route_exists(n["parameters"].get("method", "GET"), m.group(0)), f"{wf.stem}: {url}"


def test_every_outbox_workflow_has_an_n8n_webhook():
    paths = {n["parameters"]["path"] for wf in N8N for n in json.loads(wf.read_text())["nodes"]
             if n["type"] == "n8n-nodes-base.webhook"}
    assert set(WORKFLOW_PATHS.values()) <= paths


@pytest.mark.regression
def test_postman_collection_requests_match_routes():
    coll = json.loads((ROOT / "postman" / "TableFlow_Enterprise.postman_collection.json").read_text())
    missing = []

    def walk(items):
        for it in items:
            if "item" in it:
                walk(it["item"])
            else:
                req = it["request"]
                raw = req["url"]["raw"] if isinstance(req["url"], dict) else req["url"]
                path = re.sub(r"\{\{[^}]+\}\}", "1", raw.replace("{{base_url}}", ""))
                if not route_exists(req["method"], path):
                    missing.append(f"{req['method']} {raw}")
    walk(coll["item"])
    assert not missing, missing


@pytest.mark.skipif(not IS_PG, reason="schema drift check needs PostgreSQL + migrations")
@pytest.mark.regression
def test_migrated_schema_matches_orm_models():
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        db_cols = {c["name"] for c in insp.get_columns(table.name)}
        assert {c.name for c in table.columns} == db_cols, table.name


@pytest.mark.skipif(not IS_PG, reason="trigger exists only in PostgreSQL migration")
def test_audit_log_is_append_only_in_postgres():
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError, match="append-only"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE audit_logs SET actor='tamper' WHERE id = (SELECT min(id) FROM audit_logs)"))


@pytest.mark.skipif(not IS_PG, reason="views exist only in PostgreSQL migration")
def test_reporting_views_query():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM vw_daily_branch_sales")).scalar() > 0
        conn.execute(text("SELECT * FROM vw_payment_success_daily LIMIT 1"))
        conn.execute(text("SELECT * FROM vw_integration_health_daily LIMIT 1"))
