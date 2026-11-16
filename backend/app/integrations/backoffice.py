"""Back-office and financial-system adapters - SIMULATED.

* `FinanceSystemAdapter` posts a daily sales journal (debits/credits) to a
  general-ledger system, the kind of hand-off Finance normally does manually
  from a spreadsheet. Journals must balance or they are rejected.
* `BackOfficeAdapter` pulls stock levels from a back-of-house inventory system
  and is the data source for the low-stock workflow.
"""
from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

from app.integrations.base import AdapterError, SimulatedAdapter


class FinanceSystemAdapter(SimulatedAdapter):
    name = "finance_gl"

    def post_journal(self, *, business_date: date, branch_code: str, lines: list[dict]) -> dict:
        latency = self._simulate_transport()
        debits = sum(Decimal(str(line["debit"])) for line in lines)
        credits = sum(Decimal(str(line["credit"])) for line in lines)
        if debits != credits:
            raise AdapterError(f"Journal does not balance (Dr {debits} / Cr {credits})", 422, retryable=False)
        ref = "JNL-" + hashlib.sha1(f"{business_date}:{branch_code}".encode()).hexdigest()[:8].upper()  # noqa: S324
        return {"_latency_ms": latency, "journalRef": ref, "status": "POSTED", "lineCount": len(lines),
                "total": str(debits)}


class BackOfficeAdapter(SimulatedAdapter):
    name = "backoffice_inventory"

    def get_stock_levels(self, *, branch_code: str, items: list[dict]) -> dict:
        latency = self._simulate_transport()
        return {"_latency_ms": latency, "branch": branch_code, "items": items}
