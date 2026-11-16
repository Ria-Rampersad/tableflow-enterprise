"""Loyalty platform adapter - SIMULATED.

Represents an external loyalty/CRM platform that is the system of record for
points. TableFlow keeps a local ledger (`loyalty_transactions`) and pushes each
earn/redeem to the platform. If the push fails the local row is marked
`failed`, surfaced in the Loyalty screen, and can be retried - points are never
silently lost.

Business rule: 1 point per R10 spent (rounded down), redeem value R0.10/point.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal

from app.integrations.base import AdapterError, SimulatedAdapter

RAND_PER_POINT = Decimal("10")


def points_for_amount(amount: Decimal) -> int:
    return int(amount // RAND_PER_POINT)


class LoyaltyAdapter(SimulatedAdapter):
    name = "loyalty_platform"

    def post_transaction(self, *, member_number: str, txn_type: str, points: int, reference: str) -> dict:
        latency = self._simulate_transport()
        if not member_number:
            raise AdapterError("Member not found on loyalty platform", 404, retryable=False)
        if points <= 0:
            raise AdapterError("Points must be positive", 400, retryable=False)
        ext = "LP" + hashlib.md5(f"{member_number}:{reference}:{txn_type}".encode()).hexdigest()[:10].upper()  # noqa: S324
        return {"_latency_ms": latency, "transactionRef": ext, "member": member_number, "type": txn_type,
                "points": points, "status": "POSTED"}
