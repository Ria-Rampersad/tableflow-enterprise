"""Operational reporting and dashboard aggregates (PostgreSQL + SQLite compatible).

Reports run against the operational database for "today/this month" views.
Heavier historical analytics belong in Snowflake (see /snowflake) so that
analytical queries never compete with order processing for database resources.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import (
    Branch,
    Integration,
    IntegrationLog,
    LoyaltyTransaction,
    Order,
    OrderItem,
    Payment,
    Product,
    WebhookEvent,
)
from app.monitoring.metrics import metrics

REVENUE_STATUSES = ("accepted", "preparing", "ready", "completed", "sent_to_pos")


def _is_pg(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def day_expr(db: Session, col):
    if _is_pg(db):
        return func.to_char(func.timezone("Africa/Johannesburg", col), "YYYY-MM-DD")
    return func.strftime("%Y-%m-%d", col, "+2 hours")


def month_expr(db: Session, col):
    if _is_pg(db):
        return func.to_char(func.timezone("Africa/Johannesburg", col), "YYYY-MM")
    return func.strftime("%Y-%m", col, "+2 hours")


def bounds(start: date | None, end: date | None) -> tuple[datetime, datetime, date, date]:
    end = end or datetime.now(timezone.utc).date()
    start = start or end - timedelta(days=29)
    s = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc) - timedelta(hours=2)
    e = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) - timedelta(hours=2)
    return s, e, start, end


def _f(v) -> float:
    return float(v or 0)


def _order_filter(q, s, e, branch_id):
    q = q.where(Order.created_at >= s, Order.created_at < e)
    return q.where(Order.branch_id == branch_id) if branch_id else q


def dashboard_summary(db: Session, start: date | None, end: date | None, branch_id: int | None) -> dict:
    s, e, sd, ed = bounds(start, end)
    revenue_case = case((Order.status.in_(REVENUE_STATUSES), Order.total), else_=0)
    o = db.execute(_order_filter(select(func.count(Order.id), func.coalesce(func.sum(revenue_case), 0)), s, e,
                                 branch_id)).one()
    pay_q = select(Payment.status, func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0)).join(Order)
    pay_q = _order_filter(pay_q, s, e, branch_id).group_by(Payment.status)
    pay = {row[0]: {"count": row[1], "amount": _f(row[2])} for row in db.execute(pay_q)}
    successful = sum(pay.get(k, {}).get("count", 0) for k in ("captured", "refunded", "partially_refunded"))
    failed = pay.get("failed", {}).get("count", 0)
    pending = sum(pay.get(k, {}).get("count", 0) for k in ("initiated", "authorised"))
    integ = db.scalars(select(Integration).order_by(Integration.kind, Integration.name)).all()
    wh_failed = db.scalar(select(func.count(WebhookEvent.id)).where(WebhookEvent.status.in_(("failed", "rejected")),
                                                                    WebhookEvent.received_at >= s,
                                                                    WebhookEvent.received_at < e))
    api_calls = db.scalar(select(func.count(IntegrationLog.id)).where(IntegrationLog.created_at >= s,
                                                                      IntegrationLog.created_at < e))
    snap = metrics.snapshot()
    healthy = sum(1 for i in integ if i.status == "healthy")
    return {
        "period": {"start": sd.isoformat(), "end": ed.isoformat(), "branch_id": branch_id},
        "branches": db.scalar(select(func.count(Branch.id)).where(Branch.is_active.is_(True))),
        "total_orders": o[0],
        "total_sales_zar": round(_f(o[1]), 2),
        "average_order_value_zar": round(_f(o[1]) / o[0], 2) if o[0] else 0,
        "payments": {"successful": successful, "failed": failed, "pending": pending,
                     "success_rate": round(successful / (successful + failed) * 100, 2) if successful + failed else 0},
        "integration_health": {"healthy": healthy, "total": len(integ),
                               "items": [{"id": i.id, "name": i.display_name, "status": i.status, "kind": i.kind,
                                          "avg_response_ms": i.avg_response_ms} for i in integ]},
        "api_request_volume": {"integration_calls": api_calls, "api_requests_since_start": snap["total_requests"]},
        "failed_webhook_events": wh_failed,
        "system": {"uptime_seconds": snap["uptime_seconds"], "latency_ms": snap["latency_ms"],
                   "error_rate": snap["error_rate"]},
    }


def revenue_trend(db: Session, start, end, branch_id) -> list[dict]:
    s, e, *_ = bounds(start, end)
    d = day_expr(db, Order.created_at).label("day")
    q = select(d, Order.channel, func.count(Order.id), func.sum(Order.total)).where(Order.status.in_(REVENUE_STATUSES))
    q = _order_filter(q, s, e, branch_id).group_by(d, Order.channel).order_by(d)
    rows: dict[str, dict] = {}
    for day, channel, cnt, total in db.execute(q):
        r = rows.setdefault(day, {"date": day, "orders": 0, "revenue": 0.0})
        r["orders"] += cnt
        r["revenue"] = round(r["revenue"] + _f(total), 2)
        r[channel] = round(_f(total), 2)
    return list(rows.values())


def branch_performance(db: Session, start, end) -> list[dict]:
    s, e, *_ = bounds(start, end)
    rev = case((Order.status.in_(REVENUE_STATUSES), Order.total), else_=0)
    q = (select(Branch.id, Branch.code, Branch.name, Branch.city, Branch.province, func.count(Order.id),
                func.coalesce(func.sum(rev), 0),
                func.sum(case((Order.status == "failed", 1), else_=0)),
                func.sum(case((Order.status == "cancelled", 1), else_=0)))
         .join(Order, (Order.branch_id == Branch.id) & (Order.created_at >= s) & (Order.created_at < e), isouter=True)
         .group_by(Branch.id).order_by(func.coalesce(func.sum(rev), 0).desc()))
    failed_pay = dict(db.execute(
        select(Order.branch_id, func.count(Payment.id)).join(Payment).where(
            Payment.status == "failed", Order.created_at >= s, Order.created_at < e).group_by(Order.branch_id)).all())
    out = []
    for bid, code, name, city, prov, cnt, revenue, failed_orders, cancelled in db.execute(q):
        out.append({"branch_id": bid, "code": code, "name": name, "city": city, "province": prov, "orders": cnt,
                    "revenue": round(_f(revenue), 2), "avg_ticket": round(_f(revenue) / cnt, 2) if cnt else 0,
                    "failed_orders": int(failed_orders or 0), "cancelled_orders": int(cancelled or 0),
                    "failed_payments": failed_pay.get(bid, 0)})
    return out


def daily_transactions(db: Session, start, end, branch_id) -> list[dict]:
    s, e, *_ = bounds(start, end)
    d = day_expr(db, Payment.created_at).label("day")
    q = (select(d, func.count(Payment.id),
                func.sum(case((Payment.status.in_(("captured", "refunded", "partially_refunded")), 1), else_=0)),
                func.sum(case((Payment.status == "failed", 1), else_=0)),
                func.sum(case((Payment.status.in_(("initiated", "authorised")), 1), else_=0)),
                func.sum(case((Payment.status.in_(("captured", "partially_refunded")), Payment.amount), else_=0)))
         .join(Order).where(Payment.created_at >= s, Payment.created_at < e))
    if branch_id:
        q = q.where(Order.branch_id == branch_id)
    q = q.group_by(d).order_by(d)
    return [{"date": day, "transactions": n, "successful": int(ok or 0), "failed": int(f or 0),
             "pending": int(p or 0), "captured_value": round(_f(v), 2)} for day, n, ok, f, p, v in db.execute(q)]


def monthly_sales(db: Session, branch_id: int | None = None) -> list[dict]:
    m = month_expr(db, Order.created_at).label("month")
    q = select(m, func.count(Order.id), func.sum(Order.total)).where(Order.status.in_(REVENUE_STATUSES))
    if branch_id:
        q = q.where(Order.branch_id == branch_id)
    q = q.group_by(m).order_by(m)
    return [{"month": mo, "orders": c, "revenue": round(_f(t), 2)} for mo, c, t in db.execute(q)]


def payment_success(db: Session, start, end) -> list[dict]:
    s, e, *_ = bounds(start, end)
    q = (select(Branch.code, Branch.name,
                func.sum(case((Payment.status.in_(("captured", "refunded", "partially_refunded")), 1), else_=0)),
                func.sum(case((Payment.status == "failed", 1), else_=0)), func.count(Payment.id))
         .select_from(Payment).join(Order).join(Branch)
         .where(Payment.created_at >= s, Payment.created_at < e).group_by(Branch.code, Branch.name))
    out = []
    for code, name, ok, failed, total in db.execute(q):
        ok, failed = int(ok or 0), int(failed or 0)
        out.append({"branch": code, "name": name, "successful": ok, "failed": failed, "total": total,
                    "success_rate": round(ok / (ok + failed) * 100, 2) if ok + failed else 0})
    return sorted(out, key=lambda r: r["success_rate"])


def order_volumes(db: Session, start, end) -> list[dict]:
    s, e, *_ = bounds(start, end)
    q = (select(Order.channel, Order.status, func.count(Order.id)).where(Order.created_at >= s, Order.created_at < e)
         .group_by(Order.channel, Order.status))
    out: dict[str, dict] = {}
    for ch, st, c in db.execute(q):
        out.setdefault(ch, {"channel": ch, "total": 0})
        out[ch][st] = c
        out[ch]["total"] += c
    return list(out.values())


def failed_transactions(db: Session, start, end, limit: int = 200) -> list[dict]:
    s, e, *_ = bounds(start, end)
    q = (select(Payment.id, Payment.created_at, Payment.amount, Payment.failure_reason, Order.order_number,
                Branch.code, Order.channel)
         .join(Order, Payment.order_id == Order.id).join(Branch, Order.branch_id == Branch.id)
         .where(Payment.status == "failed", Payment.created_at >= s, Payment.created_at < e)
         .order_by(Payment.created_at.desc()).limit(limit))
    return [{"payment_id": pid, "created_at": ts.isoformat() if ts else None, "amount": _f(a), "reason": r,
             "order_number": on, "branch": b, "channel": ch} for pid, ts, a, r, on, b, ch in db.execute(q)]


def integration_performance(db: Session, start, end) -> list[dict]:
    s, e, *_ = bounds(start, end)
    q = (select(Integration.display_name, Integration.status, func.count(IntegrationLog.id),
                func.sum(case((IntegrationLog.status == "failed", 1), else_=0)),
                func.sum(case((IntegrationLog.status == "retrying", 1), else_=0)),
                func.avg(IntegrationLog.response_ms), func.max(IntegrationLog.response_ms))
         .join(IntegrationLog, (IntegrationLog.integration_id == Integration.id) & (IntegrationLog.created_at >= s)
               & (IntegrationLog.created_at < e), isouter=True)
         .group_by(Integration.id, Integration.display_name, Integration.status))
    out = []
    for name, status, calls, failed, retries, avg, mx in db.execute(q):
        calls, failed = calls or 0, int(failed or 0)
        out.append({"integration": name, "status": status, "calls": calls, "failed": failed,
                    "retries": int(retries or 0), "avg_ms": round(_f(avg)), "max_ms": mx or 0,
                    "availability_pct": round((calls - failed) / calls * 100, 2) if calls else 100.0})
    return out


def loyalty_activity(db: Session, start, end) -> list[dict]:
    s, e, *_ = bounds(start, end)
    d = day_expr(db, LoyaltyTransaction.created_at).label("day")
    q = (select(d, func.sum(case((LoyaltyTransaction.type == "earn", LoyaltyTransaction.points), else_=0)),
                func.sum(case((LoyaltyTransaction.type == "redeem", LoyaltyTransaction.points), else_=0)),
                func.sum(case((LoyaltyTransaction.sync_status == "failed", 1), else_=0)))
         .where(LoyaltyTransaction.created_at >= s, LoyaltyTransaction.created_at < e).group_by(d).order_by(d))
    return [{"date": day, "points_earned": int(a or 0), "points_redeemed": int(b or 0), "failed_syncs": int(f or 0)}
            for day, a, b, f in db.execute(q)]


def top_products(db: Session, start, end, branch_id=None, limit: int = 10) -> list[dict]:
    s, e, *_ = bounds(start, end)
    q = (select(Product.sku, Product.name, func.sum(OrderItem.quantity), func.sum(OrderItem.line_total))
         .join(OrderItem.product).join(Order, OrderItem.order_id == Order.id)
         .where(Order.status.in_(REVENUE_STATUSES)))
    q = _order_filter(q, s, e, branch_id).group_by(Product.sku, Product.name)
    q = q.order_by(func.sum(OrderItem.line_total).desc()).limit(limit)
    return [{"sku": sku, "name": n, "quantity": int(qty or 0), "revenue": round(_f(r), 2)} for sku, n, qty, r in db.execute(q)]


def to_decimal(v) -> Decimal:
    return Decimal(str(v or 0))
