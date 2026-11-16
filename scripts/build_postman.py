"""Generate the Postman collection + environments in /postman.

Each request carries Postman test scripts (status code + key assertions) so the
collection doubles as an API regression suite runnable with Newman:

    npx newman run postman/TableFlow_Enterprise.postman_collection.json \
        -e postman/TableFlow_Local.postman_environment.json
"""
import json
import uuid
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "postman"


def tests(*lines):
    return [{"listen": "test", "script": {"type": "text/javascript", "exec": list(lines)}}]


def prereq(*lines):
    return [{"listen": "prerequest", "script": {"type": "text/javascript", "exec": list(lines)}}]


def status(code):
    codes = code if isinstance(code, list) else [code]
    return f"pm.test('status is {code}', () => pm.expect(pm.response.code).to.be.oneOf({json.dumps(codes)}));"


def req(name, method, path, body=None, expect=200, auth="bearer", headers=None, form=None, extra_tests=(),
        pre=(), desc=""):
    h = [{"key": k, "value": v} for k, v in (headers or {}).items()]
    item = {"name": name, "request": {"method": method, "header": h, "description": desc,
                                      "url": {"raw": "{{base_url}}" + path, "host": ["{{base_url}}"],
                                              "path": [p for p in path.split("?")[0].split("/") if p]}}}
    if "?" in path:
        item["request"]["url"]["query"] = [{"key": kv.split("=")[0], "value": kv.split("=")[1]}
                                           for kv in path.split("?")[1].split("&")]
    if auth == "bearer":
        item["request"]["auth"] = {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]}
    else:
        item["request"]["auth"] = {"type": "noauth"}
    if body is not None:
        item["request"]["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2),
                                   "options": {"raw": {"language": "json"}}}
    if form is not None:
        item["request"]["body"] = {"mode": "urlencoded",
                                   "urlencoded": [{"key": k, "value": v} for k, v in form.items()]}
    item["event"] = tests(status(expect), *extra_tests) + (prereq(*pre) if pre else [])
    return item


def folder(name, items, desc=""):
    return {"name": name, "description": desc, "item": items}


uber_pre = (
    "pm.collectionVariables.set('uber_order_id', 'ue-' + Date.now());",
)
uber_body = {
    "id": "{{uber_order_id}}", "display_id": "PM123",
    "store": {"id": "uber-store-1", "external_reference_id": "DBN-UML"},
    "eater": {"first_name": "Thabo", "last_name": "Nkosi", "phone": "+27821234567"},
    "cart": {"items": [{"external_data": "CHK-QTR", "quantity": 2,
                        "price": {"unit_price": {"amount": 6990, "currency_code": "ZAR"}}}],
             "special_instructions": "Extra peri-peri"},
    "payment": {"charges": {"total": {"amount": 13980, "currency_code": "ZAR"}}},
    "placed_at": "2026-11-16T12:30:00+02:00",
}
mrd_body = {"orderReference": "{{mrd_ref}}", "restaurant": {"branchCode": "DBN-PNT"},
            "customer": {"name": "Ayanda Zulu", "mobile": "0731234567"},
            "lines": [{"productCode": "BRG-CLS", "qty": 1, "unitPrice": 74.90}], "orderTotal": 74.90,
            "createdAt": "2026-11-16T12:31:00+02:00"}

collection = {
    "info": {"_postman_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "tableflow")), "name": "TableFlow Enterprise API",
             "description": "All major TableFlow endpoints with test assertions. Run '00 Auth' first - it stores "
                            "{{token}} for the rest. Vendor integrations are SIMULATED.",
             "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
    "variable": [{"key": "uber_order_id", "value": ""}, {"key": "mrd_ref", "value": ""},
                 {"key": "order_id", "value": "1"}, {"key": "payment_id", "value": "1"},
                 {"key": "incident_id", "value": "1"}, {"key": "branch_id", "value": "1"},
                 {"key": "run_id", "value": "1"}, {"key": "integration_id", "value": "1"},
                 {"key": "account_id", "value": "1"}],
    "item": [
        folder("00 Health & Auth", [
            req("Liveness", "GET", "/health", auth="none"),
            req("Readiness", "GET", "/health/ready", auth="none",
                extra_tests=["pm.test('db ok', () => pm.expect(pm.response.json().database.ok).to.be.true);"]),
            req("Metrics", "GET", "/metrics", auth="none"),
            req("Login - wrong password (negative)", "POST", "/api/v1/auth/login", auth="none", expect=401,
                form={"username": "{{admin_email}}", "password": "wrong-password"}),
            req("Login (OAuth2 password grant)", "POST", "/api/v1/auth/login", auth="none",
                form={"username": "{{admin_email}}", "password": "{{admin_password}}"},
                extra_tests=["const t = pm.response.json().access_token; pm.expect(t).to.be.a('string');",
                             "pm.collectionVariables.set('token', t);"]),
            req("Client credentials (n8n)", "POST", "/api/v1/auth/token", auth="none",
                form={"grant_type": "client_credentials", "client_id": "{{client_id}}",
                      "client_secret": "{{client_secret}}", "scope": "automation:run reports:read"},
                extra_tests=["pm.expect(pm.response.json().scopes).to.include('automation:run');"]),
            req("Who am I", "GET", "/api/v1/auth/me"),
            req("Unauthenticated request (negative)", "GET", "/api/v1/branches", auth="none", expect=401),
        ]),
        folder("01 Branches", [
            req("List branches", "GET", "/api/v1/branches",
                extra_tests=["const b = pm.response.json(); pm.expect(b.length).to.be.above(0);",
                             "pm.collectionVariables.set('branch_id', b[0].id);"]),
            req("Create branch - invalid (negative)", "POST", "/api/v1/branches", expect=422,
                body={"code": "bad", "name": "X", "city": "Durban", "province": "Natal"}),
            req("Create branch", "POST", "/api/v1/branches", expect=[201, 409],
                body={"code": "DBN-WTF", "name": "Westwood Mall", "city": "Westville", "province": "KwaZulu-Natal",
                      "pos_location_ref": "LOC300", "digital_channels": ["uber_eats", "mr_d"]}),
            req("Assign POS / channels (PATCH)", "PATCH", "/api/v1/branches/{{branch_id}}",
                body={"pos_location_ref": "LOC101", "digital_channels": ["uber_eats", "mr_d"]}),
            req("Branch performance", "GET", "/api/v1/branches/{{branch_id}}/performance"),
            req("Branch integration health", "GET", "/api/v1/branches/{{branch_id}}/integration-health"),
        ]),
        folder("02 Digital ordering (partners)", [
            req("Uber Eats - new order", "POST", "/api/v1/partners/uber-eats/orders", auth="none", expect=202,
                headers={"X-API-Key": "{{uber_api_key}}"}, body=uber_body, pre=uber_pre,
                extra_tests=["pm.collectionVariables.set('order_id', pm.response.json().order_id);",
                             "pm.test('not duplicate', () => pm.expect(pm.response.json().duplicate).to.be.false);"]),
            req("Uber Eats - same order again (duplicate prevention)", "POST", "/api/v1/partners/uber-eats/orders",
                auth="none", expect=202, headers={"X-API-Key": "{{uber_api_key}}"}, body=uber_body,
                extra_tests=["pm.test('duplicate', () => pm.expect(pm.response.json().duplicate).to.be.true);"]),
            req("Uber Eats - missing API key (negative)", "POST", "/api/v1/partners/uber-eats/orders", auth="none",
                expect=401, body=uber_body),
            req("Mr D - new order", "POST", "/api/v1/partners/mr-d/orders", auth="none", expect=202,
                headers={"X-API-Key": "{{mrd_api_key}}"}, body=mrd_body,
                pre=["pm.collectionVariables.set('mrd_ref', 'MRD-' + Date.now());"]),
            req("Mr D - cancel order", "POST", "/api/v1/partners/mr-d/orders/{{mrd_ref}}/cancel", auth="none",
                headers={"X-API-Key": "{{mrd_api_key}}"}, body={"reason": "Driver unavailable"}),
        ]),
        folder("03 Orders & POS", [
            req("List orders (filters)", "GET", "/api/v1/orders?channel=uber_eats&limit=10"),
            req("Get order", "GET", "/api/v1/orders/{{order_id}}"),
            req("Create in-store order", "POST", "/api/v1/orders", expect=201,
                body={"branch_id": "{{branch_id}}", "channel": "in_store", "customer_phone": "0821112233",
                      "items": [{"sku": "CHK-HLF", "quantity": 1}, {"sku": "SIDE-CHP", "quantity": 2}]},
                extra_tests=["pm.collectionVariables.set('order_id', pm.response.json().order.id);",
                             "pm.test('sent to POS', () => pm.expect(pm.response.json().pos_forwarded).to.be.true);"]),
            req("Create order - unknown SKU (negative)", "POST", "/api/v1/orders", expect=422,
                body={"branch_id": "{{branch_id}}", "items": [{"sku": "NOPE", "quantity": 1}]}),
            req("Update status -> preparing", "PATCH", "/api/v1/orders/{{order_id}}/status",
                body={"status": "preparing"}),
            req("Invalid transition (negative)", "PATCH", "/api/v1/orders/{{order_id}}/status", expect=409,
                body={"status": "accepted"}),
            req("POS status", "GET", "/api/v1/pos/status"),
            req("Menu sync", "POST", "/api/v1/pos/branches/{{branch_id}}/menu-sync"),
            req("Transaction sync", "POST", "/api/v1/pos/branches/{{branch_id}}/transaction-sync?business_date=2026-11-15"),
        ]),
        folder("04 Payments", [
            req("Create order for payment", "POST", "/api/v1/orders", expect=201,
                body={"branch_id": "{{branch_id}}", "items": [{"sku": "MEAL-DUO", "quantity": 1}]},
                extra_tests=["pm.collectionVariables.set('order_id', pm.response.json().order.id);",
                             "pm.collectionVariables.set('order_total', pm.response.json().order.total);",
                             "pm.collectionVariables.set('idem', 'pm-' + Date.now());"]),
            req("Initiate payment (idempotent)", "POST", "/api/v1/payments", expect=201,
                headers={"Idempotency-Key": "{{idem}}"},
                body={"order_id": "{{order_id}}", "amount": "{{order_total}}", "card_token": "tok_visa_approved"},
                extra_tests=["pm.collectionVariables.set('payment_id', pm.response.json().id);",
                             "pm.expect(pm.response.json().provider_reference).to.match(/^TJ/);"]),
            req("Replay same Idempotency-Key", "POST", "/api/v1/payments", expect=200,
                headers={"Idempotency-Key": "{{idem}}"},
                body={"order_id": "{{order_id}}", "amount": "{{order_total}}", "card_token": "tok_visa_approved"},
                extra_tests=["pm.expect(pm.response.headers.get('Idempotent-Replayed')).to.eql('true');"]),
            req("Get payment (captured by webhook)", "GET", "/api/v1/payments/{{payment_id}}",
                extra_tests=["pm.expect(pm.response.json().status).to.eql('captured');"]),
            req("Partial refund", "POST", "/api/v1/payments/{{payment_id}}/refunds", expect=201,
                body={"amount": "20.00", "reason": "Missing side"}),
            req("Over-refund (negative)", "POST", "/api/v1/payments/{{payment_id}}/refunds", expect=422,
                body={"amount": "99999.00", "reason": "Too much"}),
            req("Create order (for decline test)", "POST", "/api/v1/orders", expect=201,
                body={"branch_id": "{{branch_id}}", "items": [{"sku": "CHK-QTR", "quantity": 1}]},
                extra_tests=["pm.collectionVariables.set('order_id2', pm.response.json().order.id);"]),
            req("Pay with declined token", "POST", "/api/v1/payments", expect=201,
                headers={"Idempotency-Key": "decl-{{$timestamp}}"},
                body={"order_id": "{{order_id2}}", "amount": "69.90", "card_token": "tok_declined"},
                extra_tests=["pm.expect(pm.response.json().status).to.eql('failed');"]),
            req("List failed payments", "GET", "/api/v1/payments?status=failed&limit=5"),
        ]),
        folder("05 Webhooks", [
            req("Inbound TJ webhook - bad signature (negative)", "POST", "/api/v1/webhooks/inbound/transaction-junction",
                auth="none", expect=401, headers={"X-TJ-Signature": "t=1,v1=bad"},
                body={"id": "evt_bad", "type": "payment.captured", "data": {}}),
            req("Simulate signed gateway callback", "POST",
                "/api/v1/payments/{{payment_id}}/simulate-callback?event_type=payment.captured"),
            req("Webhook events", "GET", "/api/v1/webhooks/events?limit=10"),
            req("Rejected events", "GET", "/api/v1/webhooks/events?status=rejected"),
            req("List subscriptions", "GET", "/api/v1/webhooks/subscriptions"),
            req("Register subscription", "POST", "/api/v1/webhooks/subscriptions", expect=201,
                body={"name": "Finance ERP", "target_url": "https://erp.example.invalid/hook",
                      "event_types": ["payment.failed"]}),
        ]),
        folder("06 Loyalty", [
            req("List accounts", "GET", "/api/v1/loyalty/accounts?limit=5",
                extra_tests=["pm.collectionVariables.set('account_id', pm.response.json().items[0].id);"]),
            req("Account history", "GET", "/api/v1/loyalty/accounts/{{account_id}}"),
            req("Redeem points", "POST", "/api/v1/loyalty/accounts/{{account_id}}/redeem", expect=[201, 422],
                body={"points": 10}),
            req("Failed syncs", "GET", "/api/v1/loyalty/transactions?sync_status=failed"),
        ]),
        folder("07 Integration monitoring", [
            req("List integrations", "GET", "/api/v1/integrations",
                extra_tests=["const i = pm.response.json().find(x => x.name === 'micros_simphony');",
                             "pm.collectionVariables.set('integration_id', i.id);"]),
            req("Simulate outage", "PATCH", "/api/v1/integrations/{{integration_id}}", body={"simulate_outage": True}),
            req("Health check (fails during outage)", "POST", "/api/v1/integrations/{{integration_id}}/health-check",
                extra_tests=["pm.expect(pm.response.json().ok).to.be.false;"]),
            req("End outage", "PATCH", "/api/v1/integrations/{{integration_id}}",
                body={"simulate_outage": False, "status": "healthy"}),
            req("Integration logs", "GET", "/api/v1/integrations/{{integration_id}}/logs?limit=10"),
            req("All failed calls", "GET", "/api/v1/integrations/logs/failed?limit=10"),
        ]),
        folder("08 Incidents", [
            req("Create incident", "POST", "/api/v1/incidents", expect=201,
                body={"title": "Simphony latency at Sandton", "severity": "SEV2", "category": "pos"},
                extra_tests=["pm.collectionVariables.set('incident_id', pm.response.json().id);"]),
            req("Investigate", "PATCH", "/api/v1/incidents/{{incident_id}}", body={"status": "investigating"}),
            req("Add note", "POST", "/api/v1/incidents/{{incident_id}}/notes", body={"message": "Vendor ticket raised"}),
            req("Escalate", "POST", "/api/v1/incidents/{{incident_id}}/escalate", body={"reason": "Peak trading"}),
            req("Resolve without notes (negative)", "PATCH", "/api/v1/incidents/{{incident_id}}", expect=422,
                body={"status": "resolved"}),
            req("Resolve", "PATCH", "/api/v1/incidents/{{incident_id}}",
                body={"status": "resolved", "root_cause": "Vendor cache node", "resolution_notes": "Vendor restarted"}),
            req("Open incidents", "GET", "/api/v1/incidents?open_only=true"),
            req("Resolution report", "GET", "/api/v1/incidents/report"),
        ]),
        folder("09 Reconciliation & automation", [
            req("Run reconciliation", "POST", "/api/v1/reconciliation/runs", expect=201,
                body={"business_date": "2026-11-15"},
                extra_tests=["pm.collectionVariables.set('run_id', pm.response.json().id);"]),
            req("Run detail", "GET", "/api/v1/reconciliation/runs/{{run_id}}"),
            req("Export CSV", "GET", "/api/v1/reconciliation/runs/{{run_id}}/export"),
            req("List runs", "GET", "/api/v1/reconciliation/runs"),
            req("Daily summary", "GET", "/api/v1/automation/daily-summary"),
            req("Discrepancy scan", "POST", "/api/v1/automation/discrepancy-scan"),
            req("Integration health check (all)", "POST", "/api/v1/automation/integration-health-check"),
            req("Low stock", "GET", "/api/v1/automation/low-stock"),
            req("Post finance journal", "POST", "/api/v1/automation/finance-journal/{{branch_id}}"),
            req("Notifications outbox", "GET", "/api/v1/notifications?limit=10"),
            req("Audit log", "GET", "/api/v1/audit-logs?limit=10"),
        ]),
        folder("10 Dashboard & reports", [
            req("Dashboard summary", "GET", "/api/v1/dashboard/summary",
                extra_tests=["pm.expect(pm.response.json().total_sales_zar).to.be.above(0);"]),
            req("Revenue trend", "GET", "/api/v1/dashboard/revenue-trend"),
            req("Branch performance", "GET", "/api/v1/dashboard/branch-performance"),
            req("Daily transactions", "GET", "/api/v1/dashboard/daily-transactions"),
            req("Report list", "GET", "/api/v1/reports"),
            *[req(f"Report: {r}", "GET", f"/api/v1/reports/{r}") for r in
              ["daily-sales", "monthly-sales", "branch-performance", "payment-success", "order-volumes",
               "failed-transactions", "integration-performance", "loyalty-activity", "top-products"]],
            req("Report as CSV", "GET", "/api/v1/reports/daily-sales?format=csv"),
        ]),
    ],
}

env_vals = {"base_url": "http://localhost:8000", "admin_email": "admin@tableflow.local",
            "admin_password": "TableFlow!2026", "client_id": "n8n-automation",
            "client_secret": "dev-n8n-secret-change-me", "uber_api_key": "dev-uber-key-change-me",
            "mrd_api_key": "dev-mrd-key-change-me"}


def env(name, overrides):
    vals = {**env_vals, **overrides}
    return {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, name)), "name": name, "_postman_variable_scope": "environment",
            "values": [{"key": k, "value": v, "type": "secret" if "password" in k or "secret" in k or "key" in k
                        else "default", "enabled": True} for k, v in vals.items()]}


OUT.mkdir(exist_ok=True)
(OUT / "TableFlow_Enterprise.postman_collection.json").write_text(json.dumps(collection, indent=2))
(OUT / "TableFlow_Local.postman_environment.json").write_text(json.dumps(env("TableFlow - Local", {}), indent=2))
(OUT / "TableFlow_Docker.postman_environment.json").write_text(
    json.dumps(env("TableFlow - Docker (via frontend proxy)", {"base_url": "http://localhost:8080"}), indent=2))
count = sum(len(f["item"]) for f in collection["item"])
print(f"wrote collection with {count} requests")
