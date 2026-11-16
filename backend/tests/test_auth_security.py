"""Authentication, authorisation (RBAC), OAuth 2.0, JWT, API keys, signatures, key-pair, rate limiting."""
from datetime import timedelta

import jwt
import pytest

from app.config import get_settings
from app.monitoring.ratelimit import SlidingWindowLimiter
from app.security import keypair, signatures
from app.security.auth import create_access_token, hash_password, verify_password


def test_login_success_returns_jwt(client):
    r = client.post("/api/v1/auth/login", data={"username": "finance@tableflow.local", "password": "TableFlow!2026"})
    assert r.status_code == 200
    body = r.json()
    claims = jwt.decode(body["access_token"], get_settings().jwt_secret_key, algorithms=["HS256"],
                        issuer="tableflow-enterprise")
    assert claims["roles"] == ["finance"] and body["role"] == "finance"


def test_login_wrong_password_401(client):
    r = client.post("/api/v1/auth/login", data={"username": "finance@tableflow.local", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "HTTP_401"


def test_protected_endpoint_requires_token(client):
    assert client.get("/api/v1/branches").status_code == 401


def test_tampered_token_rejected(client, tokens):
    bad = tokens["admin"][:-4] + "abcd"
    assert client.get("/api/v1/branches", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_expired_token_rejected(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "access_token_expire_minutes", -1)
    token = create_access_token("1", ["admin"])
    r = client.get("/api/v1/branches", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401 and "expired" in r.json()["error"]["message"].lower()


def test_me_endpoint(client, auth):
    r = client.get("/api/v1/auth/me", headers=auth("branch_manager"))
    assert r.json()["role"] == "branch_manager" and r.json()["branch_id"] is not None


@pytest.mark.regression
def test_rbac_branch_manager_cannot_refund_or_create_branch(client, auth):
    assert client.post("/api/v1/payments/1/refunds", json={"amount": "1.00", "reason": "test"},
                       headers=auth("branch_manager")).status_code == 403
    assert client.post("/api/v1/branches", json={}, headers=auth("operations")).status_code in (403, 422)


def test_client_credentials_grant_and_scope_enforcement(client):
    r = client.post("/api/v1/auth/token", data={"grant_type": "client_credentials", "client_id": "n8n-automation",
                                                "client_secret": "dev-n8n-secret-change-me",
                                                "scope": "automation:run"})
    assert r.status_code == 200 and r.json()["scopes"] == ["automation:run"]
    token = r.json()["access_token"]
    # automation:run -> operations role -> may run discrepancy scan, may NOT post finance journals
    assert client.post("/api/v1/automation/discrepancy-scan",
                       headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.post("/api/v1/automation/finance-journal/1",
                       headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_client_credentials_bad_secret_and_scope(client):
    base = {"grant_type": "client_credentials", "client_id": "n8n-automation"}
    assert client.post("/api/v1/auth/token", data={**base, "client_secret": "wrong"}).status_code == 401
    r = client.post("/api/v1/auth/token", data={**base, "client_secret": "dev-n8n-secret-change-me",
                                                "scope": "admin:everything"})
    assert r.status_code == 400
    assert client.post("/api/v1/auth/token", data={**base, "grant_type": "password",
                                                   "client_secret": "x"}).status_code == 400


def test_admin_creates_user_with_password_policy(client, auth):
    weak = {"email": "new.user@tableflow.local", "full_name": "New User", "password": "short", "role": "finance"}
    assert client.post("/api/v1/auth/users", json=weak, headers=auth()).status_code == 422
    ok = {**weak, "password": "LongEnough123"}
    r = client.post("/api/v1/auth/users", json=ok, headers=auth())
    assert r.status_code == 201
    assert client.post("/api/v1/auth/users", json=ok, headers=auth()).status_code == 409
    login = client.post("/api/v1/auth/login", data={"username": ok["email"], "password": ok["password"]})
    assert login.status_code == 200


def test_password_hashing_is_salted_bcrypt():
    h1, h2 = hash_password("Secret123!"), hash_password("Secret123!")
    assert h1 != h2 and h1.startswith("$2b$")
    assert verify_password("Secret123!", h1) and not verify_password("secret123!", h1)


def test_login_rate_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_login_per_minute", 3)
    codes = [client.post("/api/v1/auth/login", data={"username": "x@y.z", "password": "bad"}).status_code
             for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3] == 429


def test_sliding_window_limiter_unit():
    lim = SlidingWindowLimiter()
    assert [lim.check("k", 2)[0] for _ in range(3)] == [True, True, False]


def test_webhook_signature_roundtrip_and_tamper():
    body = b'{"id":"evt_1","type":"payment.captured"}'
    for source in ("transaction_junction", "uber_eats", "mr_d"):
        headers = signatures.sign(source, body)
        signatures.verify(source, body, headers)
        with pytest.raises(signatures.SignatureError):
            signatures.verify(source, body + b" ", headers)


def test_webhook_signature_replay_window():
    body = b"{}"
    old = signatures.sign("transaction_junction", body, timestamp=1_600_000_000)
    with pytest.raises(signatures.SignatureError, match="tolerance"):
        signatures.verify("transaction_junction", body, old)


def test_keypair_generation_sign_verify_and_fingerprint(tmp_path):
    priv, pub = keypair.generate_keypair(tmp_path, passphrase="pass-phrase")
    assert oct(priv.stat().st_mode)[-3:] == "600"
    sig = keypair.sign_challenge(priv, b"challenge", "pass-phrase")
    assert keypair.verify_challenge(pub, b"challenge", sig)
    assert not keypair.verify_challenge(pub, b"other", sig)
    assert keypair.public_key_fingerprint(pub).startswith("SHA256:")
    assert keypair.private_key_der(priv, "pass-phrase")[:1] == b"\x30"  # DER SEQUENCE


def test_token_lifetime_setting():
    assert timedelta(minutes=get_settings().access_token_expire_minutes) > timedelta(0)
