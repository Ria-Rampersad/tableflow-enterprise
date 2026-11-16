"""Transaction Junction-style payment gateway adapter - SIMULATED.

Transaction Junction is a South African payment switch. This adapter models a
typical card-present/card-not-present flow (authorise -> capture -> settle,
plus refunds) using ISO 8583-style response codes. It is a sandbox-ready
*architecture*, not a live integration: no merchant account or TJ credentials
exist in this project.

Test card tokens drive deterministic outcomes (like a vendor sandbox):

    tok_visa_approved        -> 00 Approved
    tok_mc_approved          -> 00 Approved
    tok_declined             -> 05 Do not honour         (permanent)
    tok_insufficient_funds   -> 51 Insufficient funds    (permanent)
    tok_expired              -> 54 Expired card          (permanent)
    tok_issuer_unavailable   -> 91 Issuer unavailable    (retryable)
"""
from __future__ import annotations

import hashlib
from decimal import Decimal

from app.integrations.base import AdapterError, SimulatedAdapter

RESPONSE_CODES = {
    "tok_visa_approved": ("00", "Approved"),
    "tok_mc_approved": ("00", "Approved"),
    "tok_declined": ("05", "Do not honour"),
    "tok_insufficient_funds": ("51", "Insufficient funds"),
    "tok_expired": ("54", "Expired card"),
    "tok_issuer_unavailable": ("91", "Issuer or switch inoperative"),
}


class TransactionJunctionAdapter(SimulatedAdapter):
    name = "transaction_junction"

    @staticmethod
    def make_reference(idempotency_key: str) -> str:
        # Deterministic: the same idempotency key always maps to the same gateway reference.
        return "TJ" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:14].upper()

    def authorise(self, *, amount: Decimal, currency: str, card_token: str, merchant_ref: str, idempotency_key: str) -> dict:
        latency = self._simulate_transport()
        if currency != "ZAR":
            raise AdapterError("Only ZAR is supported for this merchant", 400, retryable=False)
        code, text = RESPONSE_CODES.get(card_token, ("14", "Invalid card number"))
        ref = self.make_reference(idempotency_key)
        if code == "91":
            raise AdapterError(f"{code} {text}", 502, retryable=True, payload={"responseCode": code})
        if code != "00":
            raise AdapterError(f"{code} {text}", 402, retryable=False,
                               payload={"transactionId": ref, "responseCode": code, "responseText": text})
        return {"_latency_ms": latency, "transactionId": ref, "responseCode": code, "responseText": text,
                "authCode": ref[-6:], "amount": str(amount), "currency": currency, "merchantRef": merchant_ref,
                "status": "AUTHORISED"}

    def refund(self, *, transaction_id: str, amount: Decimal, reason: str) -> dict:
        latency = self._simulate_transport()
        if amount <= 0:
            raise AdapterError("Refund amount must be positive", 400, retryable=False)
        ref = "RF" + hashlib.sha256(f"{transaction_id}:{amount}:{reason}".encode()).hexdigest()[:12].upper()
        return {"_latency_ms": latency, "refundId": ref, "originalTransactionId": transaction_id,
                "amount": str(amount), "status": "REFUNDED", "responseCode": "00"}
