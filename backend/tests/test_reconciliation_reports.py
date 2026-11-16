"""Modules 1, 9, 11, 12: dashboard, automation tools, reconciliation, reporting."""
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Branch, Order, OrderItem, Payment, PosTransaction, Product, SettlementRecord
from app.services import reconciliation

SCENARIO_DATE = date(2025, 3, 3)  # isolated day with no seed data


def _ts(hour):
    return datetime(2025, 3, 3, hour, 0, tzinfo=timezone(timedelta(hours=2))).astimezone(timezone.utc)


@pytest.fixture
def scenario(db):
    """Build one business day containing every discrepancy type the engine detects."""
    branch = db.query(Branch).filter_by(code="JHB-SDN").one()
    prod = db.query(Product).filter_by(sku="CHK-HLF").one()
    created = []

    def order(total, status="completed", check=True):
        o = Order(order_number=f"T-{uuid.uuid4().hex[:8]}", branch_id=branch.id, channel="in_store",
                  status=status, subtotal=total, vat=Decimal("0"), total=total, created_at=_ts(12),
                  pos_check_ref=f"CHK-{uuid.uuid4().hex[:6]}" if check else None,
                  items=[OrderItem(product_id=prod.id, quantity=1, unit_price=total, line_total=total)])
        db.add(o)
        db.flush()
        created.append(o)
        return o

    def payment(o, amount, status="captured", settle=True, settle_amount=None):
        ref = f"TJ{uuid.uuid4().hex[:12].upper()}"
        p = Payment(order_id=o.id, amount=amount, status=status, provider_reference=ref, created_at=_ts(12))
        db.add(p)
        if settle and status == "captured":
            db.add(SettlementRecord(provider="transaction_junction", provider_reference=ref, branch_code=branch.code,
                                    amount=settle_amount if settle_amount is not None else amount,
                                    business_date=SCENARIO_DATE))
        return p

    def pos(o, total=None):
        db.add(PosTransaction(branch_id=branch.id, check_number=o.pos_check_ref, order_id=o.id,
                              total=total if total is not None else o.total, business_date=SCENARIO_DATE))

    ok = order(Decimal("100.00")); payment(ok, Decimal("100.00")); pos(ok)                       # matched
    o2 = order(Decimal("80.00")); pos(o2)                                                         # missing_payment
    o3 = order(Decimal("90.00")); payment(o3, Decimal("90.00"), status="failed"); pos(o3)        # failed_payment
    o4 = order(Decimal("70.00")); payment(o4, Decimal("70.00")); payment(o4, Decimal("70.00")); pos(o4)  # duplicate
    o5 = order(Decimal("120.00")); payment(o5, Decimal("110.00")); pos(o5)                       # amount_mismatch
    o6 = order(Decimal("60.00")); payment(o6, Decimal("60.00"))                                   # missing_pos_record
    o7 = order(Decimal("50.00")); payment(o7, Decimal("50.00")); pos(o7, Decimal("40.00"))       # pos_amount_mismatch
    o8 = order(Decimal("40.00")); payment(o8, Decimal("40.00"), settle=False); pos(o8)           # missing_settlement
    o9 = order(Decimal("30.00")); payment(o9, Decimal("30.00"), settle_amount=Decimal("28.50")); pos(o9)  # settle mm
    order(Decimal("999.00"), status="cancelled")                                                  # ignored
    db.add(SettlementRecord(provider="transaction_junction", provider_reference=f"TJORPHAN{uuid.uuid4().hex[:6]}",
                            branch_code=branch.code, amount=Decimal("55.00"), business_date=SCENARIO_DATE))  # unknown
    db.commit()
    return branch, created


@pytest.mark.regression
def test_reconciliation_matching_logic_detects_every_issue_type(db, scenario):
    branch, _ = scenario
    run = reconciliation.run(db, SCENARIO_DATE, branch.id, "pytest")
    db.commit()
    issues = sorted(r.issue_type for r in run.records)
    assert issues == sorted(["missing_payment", "failed_payment", "duplicate_payment", "amount_mismatch",
                             "missing_pos_record", "pos_amount_mismatch", "missing_settlement",
                             "settlement_mismatch", "unknown_settlement"])
    assert run.total_orders == 9 and run.matched == 1
    mm = next(r for r in run.records if r.issue_type == "amount_mismatch")
    assert mm.expected_amount == Decimal("120.00") and mm.difference == Decimal("-10.00")
    sm = next(r for r in run.records if r.issue_type == "settlement_mismatch")
    assert sm.difference == Decimal("-1.50")


def test_reconciliation_api_run_export_resolve(client, auth, scenario):
    branch, _ = scenario
    r = client.post("/api/v1/reconciliation/runs", json={"business_date": SCENARIO_DATE.isoformat(),
                                                         "branch_id": branch.id}, headers=auth("finance"))
    assert r.status_code == 201
    run = r.json()
    assert run["discrepancies"] >= 9 and run["summary"]["duplicate_payment"] >= 1
    csv_r = client.get(f"/api/v1/reconciliation/runs/{run['id']}/export", headers=auth("finance"))
    assert csv_r.headers["content-type"].startswith("text/csv") and "duplicate_payment" in csv_r.text
    rec_id = run["records"][0]["id"]
    assert client.patch(f"/api/v1/reconciliation/records/{rec_id}/resolve",
                        headers=auth("finance")).json()["resolved"] is True
    assert client.post("/api/v1/reconciliation/runs", json={"business_date": "2025-03-03"},
                       headers=auth("branch_manager")).status_code == 403


def test_settlement_csv_import(client, auth):
    ref = f"TJCSV{uuid.uuid4().hex[:8]}"
    csv_text = (f"provider_reference,branch_code,amount,fee,business_date\n{ref},DBN-UML,145.70,2.55,2025-03-04\n"
                f"{ref},DBN-UML,145.70,2.55,2025-03-04\nBAD,DBN-UML,notanumber,0,2025-03-04\n")
    r = client.post("/api/v1/reconciliation/settlements/import", headers=auth("finance"),
                    files={"file": ("settlement.csv", io.BytesIO(csv_text.encode()), "text/csv")})
    assert r.status_code == 200
    assert r.json()["inserted"] == 1 and r.json()["skipped_duplicates"] == 1 and len(r.json()["errors"]) == 1
    bad = client.post("/api/v1/reconciliation/settlements/import", headers=auth("finance"),
                      files={"file": ("x.csv", io.BytesIO(b"foo,bar\n1,2\n"), "text/csv")})
    assert bad.status_code == 422


def test_dashboard_summary_and_trend(client, auth):
    s = client.get("/api/v1/dashboard/summary", headers=auth()).json()
    assert s["branches"] >= 12 and s["total_orders"] > 0 and s["total_sales_zar"] > 0
    assert 0 < s["payments"]["success_rate"] <= 100
    assert s["integration_health"]["total"] == 7
    trend = client.get("/api/v1/dashboard/revenue-trend", headers=auth()).json()
    assert trend and {"date", "orders", "revenue"} <= trend[0].keys()
    perf = client.get("/api/v1/dashboard/branch-performance", headers=auth()).json()
    assert perf == sorted(perf, key=lambda b: -b["revenue"])
    tx = client.get("/api/v1/dashboard/daily-transactions", headers=auth()).json()
    assert tx and "failed" in tx[0]


@pytest.mark.parametrize("name", ["daily-sales", "monthly-sales", "branch-performance", "payment-success",
                                  "order-volumes", "failed-transactions", "integration-performance",
                                  "loyalty-activity", "top-products"])
def test_every_report_json_and_csv(client, auth, name):
    r = client.get(f"/api/v1/reports/{name}", headers=auth("finance"))
    assert r.status_code == 200 and isinstance(r.json()["rows"], list)
    c = client.get(f"/api/v1/reports/{name}", params={"format": "csv"}, headers=auth("finance"))
    assert c.status_code == 200 and c.headers["content-type"].startswith("text/csv")


def test_unknown_report_404(client, auth):
    assert client.get("/api/v1/reports/nope", headers=auth()).status_code == 404


def test_automation_tools(client, auth, db):
    ds = client.get("/api/v1/automation/daily-summary", headers=auth("finance")).json()
    assert {"business_date", "total_sales_zar", "branches", "top_products"} <= ds.keys()
    scan = client.post("/api/v1/automation/discrepancy-scan", params={"raise_incident": True},
                       headers=auth("operations")).json()
    assert "stuck_orders" in scan and (scan["total_issues"] == 0 or scan["incident"].startswith("INC-"))
    low = client.get("/api/v1/automation/low-stock", headers=auth()).json()
    assert low["count"] == len(low["items"]) and all(i["on_hand"] <= i["reorder_level"] for i in low["items"])
    rec = client.post("/api/v1/automation/daily-reconciliation", headers=auth("finance")).json()
    assert rec["status"] == "completed"
    b = db.query(Branch).filter_by(code="DBN-UML").one()
    j = client.post(f"/api/v1/automation/finance-journal/{b.id}", headers=auth("finance")).json()
    lines = j["lines"]
    assert sum(Decimal(x["debit"]) for x in lines) == sum(Decimal(x["credit"]) for x in lines)
    notes = client.get("/api/v1/notifications", headers=auth()).json()
    assert notes["total"] > 0


def test_health_ready_metrics(client):
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/health/ready").json()
    assert ready["status"] == "ready" and ready["database"]["ok"]
    m = client.get("/metrics").json()
    assert m["total_requests"] > 0 and "p95" in m["latency_ms"]


def test_errors_carry_correlation_id(client, auth):
    r = client.get("/api/v1/orders/999999", headers=auth(**{"X-Request-ID": "trace-abc-123"}))
    assert r.status_code == 404 and r.headers["X-Request-ID"] == "trace-abc-123"
    assert r.json()["error"]["correlation_id"] == "trace-abc-123"


def test_openapi_documents_all_modules(client):
    spec = client.get("/openapi.json").json()
    tags = {t for p in spec["paths"].values() for op in p.values() for t in op.get("tags", [])}
    assert {"Authentication", "Branches", "Orders", "Digital Ordering Partners", "Payments", "Loyalty",
            "Integration Monitoring", "POS Integration Hub", "Webhooks", "Incidents", "Financial Reconciliation",
            "Dashboard & Reports", "Automation", "Health & Monitoring"} <= tags
    assert len(spec["paths"]) >= 60
