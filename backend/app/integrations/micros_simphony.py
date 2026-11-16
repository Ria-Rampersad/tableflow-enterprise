"""Oracle MICROS Simphony POS adapter - SIMULATED.

Models the operations a restaurant integration needs from Simphony:
check (order) creation, check status updates, menu retrieval and the pull of
closed checks for a business date. Payload field names follow the style of
Simphony's cloud APIs (checkRef, checkNum, menuItemId, revenueCenter) but this
is a portfolio simulation, not Oracle's published contract. Swapping to a real
sandbox means implementing the same methods with HTTP calls against the
authorised Simphony endpoint using OAuth 2.0 client credentials.
"""
from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

from app.integrations.base import AdapterError, SimulatedAdapter


class MicrosSimphonyAdapter(SimulatedAdapter):
    name = "micros_simphony"

    def create_check(self, *, location_ref: str, order_number: str, channel: str, items: list[dict], total: Decimal) -> dict:
        latency = self._simulate_transport()
        if not location_ref:
            raise AdapterError("Unknown Simphony location (locRef missing)", 400, retryable=False)
        unmapped = [i["sku"] for i in items if not i.get("pos_item_ref")]
        if unmapped:
            raise AdapterError(f"Menu items not mapped in Simphony: {', '.join(unmapped)}", 422, retryable=False)
        digest = int(hashlib.sha1(order_number.encode()).hexdigest()[:6], 16)  # noqa: S324 - demo check number, not security
        check_num = 1000 + digest % 9000
        return {
            "_latency_ms": latency,
            "checkRef": f"SIM-{location_ref}-{check_num}",
            "checkNum": check_num,
            "revenueCenter": 2 if channel in ("uber_eats", "mr_d") else 1,
            "orderType": "Delivery" if channel in ("uber_eats", "mr_d") else "Dine In",
            "totalDue": str(total),
            "status": "OPEN",
        }

    def update_check_status(self, *, check_ref: str, status: str) -> dict:
        latency = self._simulate_transport()
        if not check_ref:
            raise AdapterError("checkRef required", 400, retryable=False)
        return {"_latency_ms": latency, "checkRef": check_ref, "status": status.upper()}

    def get_menu(self, *, location_ref: str, products: list[dict]) -> dict:
        latency = self._simulate_transport()
        return {
            "_latency_ms": latency,
            "locRef": location_ref,
            "menuItems": [
                {
                    "menuItemId": p["pos_item_ref"],
                    "name": {"en-US": p["name"]},
                    "familyGroup": p["category"],
                    "prices": [{"price": str(p["price"]), "priceSequence": 1}],
                    "active": p["is_active"],
                }
                for p in products
            ],
        }

    def get_closed_checks(self, *, location_ref: str, business_date: date, open_checks: list[dict]) -> dict:
        """Return checks the POS closed on `business_date`. `open_checks` are the checks we created there."""
        latency = self._simulate_transport()
        return {
            "_latency_ms": latency,
            "locRef": location_ref,
            "busDt": business_date.isoformat(),
            "checks": [
                {"checkRef": c["check_ref"], "checkNum": c["check_ref"].rsplit("-", 1)[-1],
                 "totalDue": str(c["total"]), "tenderType": c.get("tender", "card"), "status": "CLOSED"}
                for c in open_checks
            ],
        }
