"""Digital ordering adapters: Uber Eats and Mr D - SIMULATED.

Each provider sends orders in its own JSON shape. The adapter's job is
*mapping*: translate the provider payload into TableFlow's canonical order
(`CanonicalOrder`) and translate our status changes back into the provider's
vocabulary. Validation of business rules happens in `services/orders.py`, so
both providers share one set of rules.

Payload shapes are modelled on public descriptions of these platforms and are
labelled simulations; real partner API contracts require onboarding.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import ValidationError

from app.integrations.base import AdapterError, SimulatedAdapter
from app.schemas import CanonicalOrder

UBER_STATUS = {"accepted": "ACCEPTED", "preparing": "ACCEPTED", "ready": "READY_FOR_PICKUP",
               "completed": "COMPLETED", "cancelled": "DENIED", "failed": "DENIED"}
MRD_STATUS = {"accepted": "CONFIRMED", "preparing": "IN_KITCHEN", "ready": "READY",
              "completed": "COLLECTED", "cancelled": "REJECTED", "failed": "REJECTED"}


def _cents(value) -> Decimal:
    return (Decimal(int(value)) / 100).quantize(Decimal("0.01"))


class UberEatsAdapter(SimulatedAdapter):
    name = "uber_eats"

    @staticmethod
    def to_canonical(payload: dict) -> CanonicalOrder:
        try:
            return CanonicalOrder(
                channel="uber_eats",
                external_ref=payload["id"],
                display_ref=payload.get("display_id", ""),
                branch_code=payload["store"]["external_reference_id"],
                customer_name=" ".join(filter(None, [payload.get("eater", {}).get("first_name"),
                                                     payload.get("eater", {}).get("last_name")])) or None,
                customer_phone=payload.get("eater", {}).get("phone"),
                items=[
                    {"sku": i["external_data"], "quantity": i["quantity"],
                     "unit_price": _cents(i["price"]["unit_price"]["amount"])}
                    for i in payload["cart"]["items"]
                ],
                total=_cents(payload["payment"]["charges"]["total"]["amount"]),
                notes=payload["cart"].get("special_instructions", ""),
                placed_at=datetime.fromisoformat(payload["placed_at"]) if payload.get("placed_at") else None,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise AdapterError(f"Invalid Uber Eats payload: {exc}", 422, retryable=False) from exc

    def push_status(self, *, external_ref: str, status: str) -> dict:
        latency = self._simulate_transport()
        return {"_latency_ms": latency, "order_id": external_ref, "state": UBER_STATUS.get(status, status.upper())}


class MrDAdapter(SimulatedAdapter):
    name = "mr_d"

    @staticmethod
    def to_canonical(payload: dict) -> CanonicalOrder:
        try:
            return CanonicalOrder(
                channel="mr_d",
                external_ref=payload["orderReference"],
                display_ref=payload["orderReference"],
                branch_code=payload["restaurant"]["branchCode"],
                customer_name=payload.get("customer", {}).get("name"),
                customer_phone=payload.get("customer", {}).get("mobile"),
                items=[
                    {"sku": line["productCode"], "quantity": line["qty"], "unit_price": Decimal(str(line["unitPrice"]))}
                    for line in payload["lines"]
                ],
                total=Decimal(str(payload["orderTotal"])),
                notes=payload.get("instructions", ""),
                placed_at=datetime.fromisoformat(payload["createdAt"]) if payload.get("createdAt") else None,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise AdapterError(f"Invalid Mr D payload: {exc}", 422, retryable=False) from exc

    def push_status(self, *, external_ref: str, status: str) -> dict:
        latency = self._simulate_transport()
        return {"_latency_ms": latency, "orderReference": external_ref, "status": MRD_STATUS.get(status, status.upper())}


ORDERING_ADAPTERS = {"uber_eats": UberEatsAdapter, "mr_d": MrDAdapter}
