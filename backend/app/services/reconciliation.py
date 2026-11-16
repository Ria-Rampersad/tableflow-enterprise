"""Financial reconciliation engine.

Compares four sources for one business date (optionally one branch):

    A. Internal orders              (orders table - what TableFlow recorded)
    B. Internal payments            (payments table - what we authorised/captured)
    C. POS transactions             (pos_transactions - what Micros Simphony closed)
    D. Provider settlement records  (settlement_records - what the acquirer paid out)

Matching logic per order (non-cancelled):
    1. No captured payment and no failed payment         -> missing_payment
    2. Only failed payment(s)                            -> failed_payment
    3. More than one captured payment                    -> duplicate_payment
    4. Captured amount != order total                    -> amount_mismatch
    5. Order sent to POS but no POS check found          -> missing_pos_record
    6. POS check total != order total                    -> pos_amount_mismatch
    7. Captured payment has no settlement line           -> missing_settlement
    8. Settlement amount != captured amount              -> settlement_mismatch
    9. Otherwise                                         -> matched
Then, per settlement line whose reference matches no payment -> unknown_settlement.

An order can produce more than one issue (e.g. duplicate payment AND missing
settlement). It is counted as `matched` only if it produced no issue.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Branch,
    Order,
    PosTransaction,
    ReconciliationRecord,
    ReconciliationRun,
    SettlementRecord,
    utcnow,
)
from app.services import audit
from app.services.incidents import create_incident

ZERO = Decimal("0.00")
INCIDENT_VALUE_THRESHOLD = Decimal("500.00")  # raise an incident if discrepancies exceed R500


def day_bounds(d: date) -> tuple[datetime, datetime]:
    # Business day in SAST (UTC+2): 00:00-24:00 local == 22:00 previous day to 22:00 UTC.
    start = datetime.combine(d, time.min, tzinfo=timezone.utc) - timedelta(hours=2)
    return start, start + timedelta(days=1)


def run(db: Session, business_date: date, branch_id: int | None, actor: str) -> ReconciliationRun:
    run = ReconciliationRun(business_date=business_date, branch_id=branch_id, run_by=actor, status="running")
    db.add(run)
    db.flush()
    start, end = day_bounds(business_date)

    q = (select(Order).where(Order.created_at >= start, Order.created_at < end, Order.status != "cancelled")
         .options(selectinload(Order.payments)))
    if branch_id:
        q = q.where(Order.branch_id == branch_id)
    order_list = db.scalars(q).all()

    pos_q = select(PosTransaction).where(PosTransaction.business_date == business_date)
    if branch_id:
        pos_q = pos_q.where(PosTransaction.branch_id == branch_id)
    pos_by_order = {p.order_id: p for p in db.scalars(pos_q) if p.order_id}

    settle_q = select(SettlementRecord).where(SettlementRecord.business_date == business_date)
    if branch_id:
        code = db.get(Branch, branch_id).code
        settle_q = settle_q.where(SettlementRecord.branch_code == code)
    settlements = {s.provider_reference: s for s in db.scalars(settle_q)}
    seen_refs: set[str] = set()

    records: list[ReconciliationRecord] = []

    def add(issue, order=None, payment=None, expected=None, actual=None, details=""):
        diff = (actual or ZERO) - (expected or ZERO) if (expected is not None or actual is not None) else None
        records.append(ReconciliationRecord(
            run_id=run.id, branch_id=order.branch_id if order else None, order_id=order.id if order else None,
            payment_id=payment.id if payment else None, issue_type=issue, expected_amount=expected,
            actual_amount=actual, difference=diff, details=details))

    matched = 0
    for order in order_list:
        before = len(records)
        captured = [p for p in order.payments if p.status in ("captured", "partially_refunded", "refunded")]
        failed = [p for p in order.payments if p.status == "failed"]
        net = sum((p.amount - p.refunded_amount for p in captured), ZERO)

        if not captured and not failed:
            if order.status in ("completed", "ready", "accepted", "preparing"):
                add("missing_payment", order, expected=order.total, actual=ZERO,
                    details=f"Order {order.order_number} ({order.status}) has no payment")
        elif not captured and failed:
            add("failed_payment", order, failed[-1], order.total, ZERO,
                f"Payment failed: {failed[-1].failure_reason or 'unknown'}")
        else:
            if len(captured) > 1:
                add("duplicate_payment", order, captured[-1], order.total, net,
                    f"{len(captured)} captured payments: " + ", ".join(p.provider_reference or "?" for p in captured))
            elif net != order.total and not any(p.status in ("refunded", "partially_refunded") for p in captured):
                add("amount_mismatch", order, captured[0], order.total, net,
                    f"Order total R{order.total} vs captured R{net}")

        if order.pos_check_ref:
            pos = pos_by_order.get(order.id)
            if not pos:
                add("missing_pos_record", order, expected=order.total, actual=ZERO,
                    details=f"POS check {order.pos_check_ref} not found in Simphony sync")
            elif pos.total != order.total:
                add("pos_amount_mismatch", order, expected=order.total, actual=pos.total,
                    details=f"POS check {pos.check_number} total R{pos.total}")

        for p in captured:
            if not p.provider_reference:
                continue
            seen_refs.add(p.provider_reference)
            s = settlements.get(p.provider_reference)
            if not s:
                add("missing_settlement", order, p, p.amount, ZERO,
                    f"{p.provider_reference} not on settlement report")
            elif s.amount != p.amount:
                add("settlement_mismatch", order, p, p.amount, s.amount,
                    f"Settled R{s.amount} vs captured R{p.amount}")

        if len(records) == before:
            matched += 1

    for ref, s in settlements.items():
        if ref not in seen_refs:
            add("unknown_settlement", expected=ZERO, actual=s.amount,
                details=f"Settlement {ref} ({s.branch_code}) has no matching TableFlow payment")

    db.add_all(records)
    run.total_orders = len(order_list)
    run.matched = matched
    run.discrepancies = len(records)
    run.discrepancy_value = sum((abs(r.difference or ZERO) for r in records), ZERO)
    run.status = "completed"
    run.completed_at = utcnow()
    audit.record(db, actor, "reconciliation.run", "reconciliation_run", run.id,
                 {"date": business_date.isoformat(), "discrepancies": run.discrepancies})

    summary = dict(Counter(r.issue_type for r in records))
    # The n8n daily-reconciliation workflow reads this run's result from the API response;
    # large discrepancies additionally raise an incident so they are tracked to closure.
    if run.discrepancy_value > INCIDENT_VALUE_THRESHOLD:
        create_incident(db, title=f"Reconciliation discrepancies {business_date} (R{run.discrepancy_value})",
                        severity="SEV3", category="reconciliation", source="automated", branch_id=branch_id,
                        description=f"Run #{run.id}: {run.discrepancies} discrepancies. Breakdown: {summary}")
    return run
