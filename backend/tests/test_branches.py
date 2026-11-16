"""Module 2: Restaurant Branch Management."""


def test_list_branches_filters(client, auth):
    r = client.get("/api/v1/branches", headers=auth("operations"))
    assert r.status_code == 200 and len(r.json()) >= 12
    kzn = client.get("/api/v1/branches", params={"province": "KwaZulu-Natal"}, headers=auth()).json()
    assert kzn and all(b["province"] == "KwaZulu-Natal" for b in kzn)


def test_create_branch_validation_and_duplicates(client, auth):
    body = {"code": "DBN-GTW", "name": "Gateway Theatre of Shopping", "city": "Umhlanga",
            "province": "KwaZulu-Natal", "pos_location_ref": "LOC201", "digital_channels": ["uber_eats"]}
    r = client.post("/api/v1/branches", json=body, headers=auth())
    assert r.status_code == 201 and r.json()["code"] == "DBN-GTW"
    assert client.post("/api/v1/branches", json=body, headers=auth()).status_code == 409
    bad = {**body, "code": "bad code", "province": "Natal"}
    err = client.post("/api/v1/branches", json=bad, headers=auth())
    assert err.status_code == 422
    assert {d["loc"][-1] for d in err.json()["error"]["details"]} == {"code", "province"}


def test_operations_cannot_create_branch(client, auth):
    body = {"code": "CPT-VAW", "name": "V&A Waterfront", "city": "Cape Town", "province": "Western Cape"}
    assert client.post("/api/v1/branches", json=body, headers=auth("operations")).status_code == 403


def test_patch_assign_pos_and_payment_and_audit(client, auth):
    branches = client.get("/api/v1/branches", headers=auth()).json()
    b = next(x for x in branches if x["code"] == "BFN-MIM")
    r = client.patch(f"/api/v1/branches/{b['id']}", json={"pos_location_ref": "LOC999",
                                                          "digital_channels": ["mr_d", "uber_eats"]},
                     headers=auth("operations"))
    assert r.status_code == 200 and r.json()["pos_location_ref"] == "LOC999"
    logs = client.get("/api/v1/audit-logs", params={"entity_type": "branch"}, headers=auth()).json()["items"]
    assert any(entry["action"] == "branch.updated" and entry["entity_id"] == str(b["id"]) for entry in logs)


def test_put_replaces_branch(client, auth):
    b = next(x for x in client.get("/api/v1/branches", headers=auth()).json() if x["code"] == "GQB-BWK")
    body = {"code": "GQB-BWK", "name": "Boardwalk Casino", "city": "Gqeberha", "province": "Eastern Cape",
            "pos_location_ref": "LOC111", "digital_channels": ["mr_d"]}
    r = client.put(f"/api/v1/branches/{b['id']}", json=body, headers=auth())
    assert r.status_code == 200 and r.json()["name"] == "Boardwalk Casino"


def test_branch_performance_and_integration_health(client, auth):
    b = client.get("/api/v1/branches", headers=auth()).json()[0]
    perf = client.get(f"/api/v1/branches/{b['id']}/performance", headers=auth()).json()
    assert {"summary", "trend", "transactions", "top_products"} <= perf.keys()
    health = client.get(f"/api/v1/branches/{b['id']}/integration-health", headers=auth()).json()
    assert "recent_failures" in health
    assert client.get("/api/v1/branches/999999", headers=auth()).status_code == 404
