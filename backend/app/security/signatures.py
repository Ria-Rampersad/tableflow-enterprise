"""Webhook signature creation and verification (HMAC-SHA256).

Each provider signs the *raw request body* with a shared secret. We recompute
the signature and compare in constant time. For Transaction Junction-style
webhooks we also sign a timestamp to block replay attacks:

    X-TJ-Signature: t=1731744000,v1=<hex hmac of "t.body">

Uber Eats-style and Mr D-style webhooks sign only the body:

    X-Uber-Signature: <hex hmac of body>
    X-MrD-Signature:  sha256=<hex hmac of body>

These header formats are modelled on common industry patterns; they are NOT the
vendors' published specifications (which require partner access).
"""
from __future__ import annotations

import hashlib
import hmac
import time

from app.config import get_settings


class SignatureError(Exception):
    pass


def _hmac(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def secret_for(source: str) -> str:
    s = get_settings()
    return {
        "transaction_junction": s.webhook_secret_transaction_junction,
        "uber_eats": s.webhook_secret_uber_eats,
        "mr_d": s.webhook_secret_mr_d,
    }[source]


def sign(source: str, body: bytes, timestamp: int | None = None) -> dict[str, str]:
    """Produce the header a provider would send. Used by simulators, scripts and tests."""
    secret = secret_for(source)
    if source == "transaction_junction":
        ts = timestamp or int(time.time())
        return {"X-TJ-Signature": f"t={ts},v1={_hmac(secret, f'{ts}.'.encode() + body)}"}
    if source == "uber_eats":
        return {"X-Uber-Signature": _hmac(secret, body)}
    if source == "mr_d":
        return {"X-MrD-Signature": f"sha256={_hmac(secret, body)}"}
    raise ValueError(source)


def verify(source: str, body: bytes, headers: dict[str, str]) -> None:
    """Raise SignatureError if the signature is missing, wrong or too old."""
    h = {k.lower(): v for k, v in headers.items()}
    secret = secret_for(source)
    if source == "transaction_junction":
        raw = h.get("x-tj-signature")
        if not raw:
            raise SignatureError("missing X-TJ-Signature header")
        try:
            parts = dict(p.split("=", 1) for p in raw.split(","))
            ts = int(parts["t"])
            provided = parts["v1"]
        except (ValueError, KeyError) as exc:
            raise SignatureError("malformed signature header") from exc
        if abs(time.time() - ts) > get_settings().webhook_tolerance_seconds:
            raise SignatureError("timestamp outside tolerance (possible replay)")
        expected = _hmac(secret, f"{ts}.".encode() + body)
    elif source == "uber_eats":
        provided = h.get("x-uber-signature", "")
        expected = _hmac(secret, body)
    elif source == "mr_d":
        provided = h.get("x-mrd-signature", "").removeprefix("sha256=")
        expected = _hmac(secret, body)
    else:
        raise SignatureError(f"unknown source {source}")
    if not provided or not hmac.compare_digest(provided, expected):
        raise SignatureError("signature mismatch")
