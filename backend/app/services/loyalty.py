"""Loyalty points: earn on captured payment, redeem, retry failed platform syncs.

  BR-LOY-01 1 point per R10 of captured payment (rounded down).
  BR-LOY-02 Points are earned once per order (unique constraint).
  BR-LOY-03 A redemption is only applied after the loyalty platform confirms it.
  BR-LOY-04 An earn that fails to sync is kept locally as `failed` and can be retried.
  Tiers: Bronze < 500 lifetime points <= Silver < 1500 <= Gold.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.base import IntegrationRunner, get_integration
from app.integrations.loyalty import LoyaltyAdapter, points_for_amount
from app.models import LoyaltyAccount, LoyaltyTransaction, Order
from app.services import audit
from app.services.notifications import notify
from app.services.orders import BusinessRuleError


def tier_for(lifetime: int) -> str:
    return "Gold" if lifetime >= 1500 else "Silver" if lifetime >= 500 else "Bronze"


def _push(db: Session, txn: LoyaltyTransaction, account: LoyaltyAccount) -> bool:
    integ = get_integration(db, "loyalty_platform")
    adapter = LoyaltyAdapter(integ)
    txn.attempts += 1
    result = IntegrationRunner(db).call(
        integ, f"loyalty_{txn.type}",
        lambda: adapter.post_transaction(member_number=account.member_number, txn_type=txn.type, points=txn.points,
                                         reference=f"LT{txn.id}"),
        request_payload={"member": account.member_number, "type": txn.type, "points": txn.points},
        entity_type="loyalty_transaction", entity_id=txn.id,
    )
    if result.ok:
        txn.sync_status, txn.external_ref, txn.error = "synced", result.data["transactionRef"], None
    else:
        txn.sync_status, txn.error = "failed", result.error
    return result.ok


def earn_for_order(db: Session, order: Order, amount: Decimal) -> LoyaltyTransaction | None:
    if not order.customer_id:
        return None
    account = db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.customer_id == order.customer_id))
    if not account:
        return None
    points = points_for_amount(amount)
    if points <= 0:
        return None
    if db.scalar(select(LoyaltyTransaction).where(LoyaltyTransaction.account_id == account.id,
                                                  LoyaltyTransaction.order_id == order.id,
                                                  LoyaltyTransaction.type == "earn")):
        return None  # BR-LOY-02
    txn = LoyaltyTransaction(account_id=account.id, order_id=order.id, type="earn", points=points)
    db.add(txn)
    db.flush()
    account.points_balance += points
    account.lifetime_points += points
    account.tier = tier_for(account.lifetime_points)
    ok = _push(db, txn, account)
    notify(db, "loyalty_update", "loyalty.points_earned" if ok else "loyalty.sync_failed",
           {"member_number": account.member_number, "points": points, "balance": account.points_balance,
            "order_number": order.order_number, "sync_status": txn.sync_status})
    return txn


def redeem(db: Session, account: LoyaltyAccount, points: int, order_id: int | None, actor: str) -> LoyaltyTransaction:
    if points > account.points_balance:
        raise BusinessRuleError(f"Insufficient points: balance {account.points_balance}, requested {points}",
                                "INSUFFICIENT_POINTS")
    txn = LoyaltyTransaction(account_id=account.id, order_id=order_id, type="redeem", points=points)
    db.add(txn)
    db.flush()
    if not _push(db, txn, account):  # BR-LOY-03
        raise BusinessRuleError(f"Loyalty platform did not confirm redemption: {txn.error}", "LOYALTY_SYNC_FAILED", 502)
    account.points_balance -= points
    audit.record(db, actor, "loyalty.redeemed", "loyalty_account", account.id, {"points": points})
    notify(db, "loyalty_update", "loyalty.points_redeemed",
           {"member_number": account.member_number, "points": points, "balance": account.points_balance})
    return txn


def retry_sync(db: Session, txn: LoyaltyTransaction, actor: str) -> LoyaltyTransaction:
    if txn.sync_status != "failed":
        raise BusinessRuleError("Only failed loyalty transactions can be retried", "NOT_RETRYABLE", 409)
    account = db.get(LoyaltyAccount, txn.account_id)
    _push(db, txn, account)
    audit.record(db, actor, "loyalty.sync_retried", "loyalty_transaction", txn.id, {"result": txn.sync_status})
    return txn
