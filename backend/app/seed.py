"""Seed realistic demo data for a fictional South African chicken restaurant group.

"Shisa Flame Chicken" (fictional) - 12 branches across KZN, Gauteng, Western Cape,
Eastern Cape and Free State; ~60 days of trading in ZAR with deliberate, realistic
defects (declined cards, duplicate captures, settlement short-pays, POS gaps,
failed loyalty syncs, rejected webhooks) so that monitoring, reconciliation and
incident tooling have something real to find.

No real customer data: names and numbers are generated. Demo passwords come from
SEED_DEMO_PASSWORD (default documented in README) and must never be used in production.

Usage:  python -m app.seed [--reset] [--days 60] [--if-empty]
"""
from __future__ import annotations

import argparse
import os
import random
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, insert, select, text

from app.database import Base, SessionLocal, engine
from app.models import (
    ApiClient,
    AuditLog,
    Branch,
    Customer,
    Incident,
    IncidentEvent,
    Integration,
    IntegrationLog,
    InventoryItem,
    LoyaltyAccount,
    LoyaltyTransaction,
    Notification,
    Order,
    OrderItem,
    Payment,
    PosTransaction,
    Product,
    Refund,
    Role,
    SettlementRecord,
    User,
    WebhookEvent,
    WebhookSubscription,
)
from app.security.auth import hash_password

SAST = timezone(timedelta(hours=2))
CENT = Decimal("0.01")
RNG = random.Random(20261116)

ROLES = [
    ("admin", "Full platform administration"),
    ("finance", "Reconciliation, refunds, financial reports"),
    ("operations", "Order operations, incidents, automation"),
    ("branch_manager", "Branch-level orders, payments and performance"),
    ("integration_engineer", "Integration configuration, retries, webhooks"),
]

BRANCHES = [
    # code, name, city, province, address, channels, weight(volume)
    ("DBN-UML", "Umhlanga Gateway", "Umhlanga", "KwaZulu-Natal", "1 Palm Blvd, Umhlanga Ridge", ["uber_eats", "mr_d"], 1.4),
    ("DBN-MSG", "Musgrave Centre", "Durban", "KwaZulu-Natal", "115 Musgrave Rd, Berea", ["uber_eats", "mr_d"], 1.2),
    ("DBN-PNT", "Pinetown Pavilion", "Pinetown", "KwaZulu-Natal", "Old Main Rd, Pinetown", ["mr_d"], 0.9),
    ("PMB-LBT", "Liberty Midlands", "Pietermaritzburg", "KwaZulu-Natal", "50 Sanctuary Rd, PMB", ["uber_eats", "mr_d"], 0.8),
    ("BLT-LFS", "Ballito Lifestyle", "Ballito", "KwaZulu-Natal", "Ballito Dr, Ballito", ["mr_d"], 0.7),
    ("JHB-RSB", "Rosebank Mall", "Johannesburg", "Gauteng", "50 Bath Ave, Rosebank", ["uber_eats", "mr_d"], 1.3),
    ("JHB-SDN", "Sandton City", "Sandton", "Gauteng", "83 Rivonia Rd, Sandhurst", ["uber_eats", "mr_d"], 1.3),
    ("JHB-SWT", "Maponya Mall", "Soweto", "Gauteng", "2127 Chris Hani Rd, Klipspruit", ["mr_d"], 1.1),
    ("PTA-MNL", "Menlyn Maine", "Pretoria", "Gauteng", "Corner Aramist & Corobay Ave", ["uber_eats", "mr_d"], 1.0),
    ("CPT-CNW", "Canal Walk", "Cape Town", "Western Cape", "Century Blvd, Century City", ["uber_eats", "mr_d"], 1.1),
    ("GQB-BWK", "Boardwalk", "Gqeberha", "Eastern Cape", "Marine Dr, Summerstrand", ["mr_d"], 0.7),
    ("BFN-MIM", "Mimosa Mall", "Bloemfontein", "Free State", "131 Kellner St, Brandwag", ["mr_d"], 0.6),
]

PRODUCTS = [
    ("CHK-QTR", "Quarter Chicken & Chips", "Flame-Grilled Chicken", "69.90"),
    ("CHK-HLF", "Half Chicken & Chips", "Flame-Grilled Chicken", "104.90"),
    ("CHK-FUL", "Full Chicken", "Flame-Grilled Chicken", "164.90"),
    ("CHK-WNG6", "6 Peri Wings", "Flame-Grilled Chicken", "59.90"),
    ("CHK-WNG12", "12 Peri Wings", "Flame-Grilled Chicken", "109.90"),
    ("BRG-CLS", "Classic Chicken Burger", "Burgers", "74.90"),
    ("BRG-PRI", "Peri-Peri Prego Burger", "Burgers", "84.90"),
    ("BRG-DBL", "Double Stack Burger", "Burgers", "99.90"),
    ("WRP-CHK", "Grilled Chicken Wrap", "Wraps & Bowls", "69.90"),
    ("BWL-RCE", "Spicy Rice Bowl", "Wraps & Bowls", "64.90"),
    ("BWL-SAL", "Chicken Caesar Salad", "Wraps & Bowls", "72.90"),
    ("MEAL-FAM", "Family Feast (2 chickens, 4 sides)", "Family Meals", "359.90"),
    ("MEAL-DUO", "Date Night Duo", "Family Meals", "219.90"),
    ("SIDE-CHP", "Regular Chips", "Sides", "29.90"),
    ("SIDE-PAP", "Pap & Chakalaka", "Sides", "27.90"),
    ("SIDE-COR", "Flame-Grilled Corn", "Sides", "24.90"),
    ("SIDE-SLW", "Coleslaw", "Sides", "22.90"),
    ("SIDE-RLL", "Portuguese Roll", "Sides", "9.90"),
    ("DRK-CAN", "Soft Drink 330ml", "Drinks", "21.90"),
    ("DRK-ICT", "Iced Tea 500ml", "Drinks", "26.90"),
    ("DRK-WTR", "Still Water 500ml", "Drinks", "17.90"),
    ("DST-SOF", "Soft Serve Cone", "Desserts", "14.90"),
    ("DST-BRW", "Chocolate Brownie", "Desserts", "32.90"),
    ("KID-MEAL", "Kiddies Meal", "Kids", "49.90"),
]

INTEGRATIONS = [
    ("micros_simphony", "Oracle MICROS Simphony", "pos", "Oracle Hospitality", "https://simphony.example.invalid/api"),
    ("transaction_junction", "Transaction Junction", "payment", "Transaction Junction", "https://tj.example.invalid"),
    ("uber_eats", "Uber Eats", "ordering", "Uber Technologies", "https://uber.example.invalid"),
    ("mr_d", "Mr D", "ordering", "Takealot Group", "https://mrd.example.invalid"),
    ("loyalty_platform", "Loyalty Platform", "loyalty", "Loyalty CRM (fictional)", "https://loyalty.example.invalid"),
    ("finance_gl", "Finance General Ledger", "finance", "GL system (fictional)", "https://gl.example.invalid"),
    ("backoffice_inventory", "Back-office Inventory", "backoffice", "BOH system (fictional)", "https://boh.example.invalid"),
]

FIRST = ["Thabo", "Sipho", "Ayanda", "Lerato", "Nomvula", "Priya", "Kavitha", "Ravi", "Johan", "Annelie", "Pieter",
         "Zanele", "Mandla", "Lindiwe", "Bongani", "Naledi", "Kyle", "Megan", "Fatima", "Yusuf", "Themba", "Refilwe",
         "Sanele", "Nicole", "Tshepo", "Busisiwe", "Arjun", "Leah", "Musa", "Palesa", "Ethan", "Chloe"]
LAST = ["Naidoo", "Dlamini", "Mokoena", "van der Merwe", "Pillay", "Nkosi", "Botha", "Khumalo", "Govender", "Mthembu",
        "Smith", "Ndlovu", "Pretorius", "Moodley", "Zulu", "Molefe", "Jacobs", "Petersen", "Sithole", "Reddy"]
DECLINES = [("05 Do not honour", 5), ("51 Insufficient funds", 4), ("54 Expired card", 1),
            ("91 Issuer or switch inoperative", 1)]

INVENTORY = [("Fresh chicken (whole)", "kg", 120, 60), ("Peri-peri basting sauce", "L", 40, 15),
             ("Potato chips (frozen)", "kg", 150, 50), ("Burger buns", "units", 400, 150),
             ("Portuguese rolls", "units", 300, 120), ("Cooking oil", "L", 80, 30),
             ("Soft drink cans", "units", 600, 200), ("Packaging (delivery bags)", "units", 800, 250)]


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, ROUND_HALF_UP)


def vat_split(total: Decimal) -> tuple[Decimal, Decimal]:
    vat = (total * Decimal("0.15") / Decimal("1.15")).quantize(CENT, ROUND_HALF_UP)
    return total - vat, vat


def reset_schema() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def is_empty() -> bool:
    with SessionLocal() as db:
        return not db.scalar(select(func.count(Branch.id)))


def seed(days: int = 60) -> dict:
    now = datetime.now(timezone.utc)
    today = now.astimezone(SAST).date()
    demo_pw = hash_password(os.getenv("SEED_DEMO_PASSWORD", "TableFlow!2026"))
    db = SessionLocal()
    try:
        # ---- reference data (ORM) -----------------------------------------------------------
        roles = {name: Role(name=name, description=desc) for name, desc in ROLES}
        db.add_all(roles.values())
        branches = []
        for i, (code, name, city, prov, addr, channels, _w) in enumerate(BRANCHES, start=1):
            branches.append(Branch(code=code, name=name, city=city, province=prov, address=addr,
                                   phone=f"0{RNG.choice([31, 11, 12, 21, 41, 51, 33, 32])}{RNG.randint(1000000, 9999999)}",
                                   pos_system="micros_simphony", pos_location_ref=f"LOC{100 + i}",
                                   payment_provider="transaction_junction", digital_channels=channels,
                                   opened_on=date(2015 + i % 9, 1 + i % 12, 1)))
        db.add_all(branches)
        products = [Product(sku=s, name=n, category=c, price=Decimal(p), pos_item_ref=f"{1000 + i}")
                    for i, (s, n, c, p) in enumerate(PRODUCTS, start=1)]
        db.add_all(products)
        db.flush()
        users = [
            User(email="admin@tableflow.local", full_name="Adikar (Platform Admin)", password_hash=demo_pw,
                 role_id=roles["admin"].id),
            User(email="finance@tableflow.local", full_name="Priya Govender (Finance)", password_hash=demo_pw,
                 role_id=roles["finance"].id),
            User(email="ops@tableflow.local", full_name="Sipho Dlamini (Operations)", password_hash=demo_pw,
                 role_id=roles["operations"].id),
            User(email="manager.umhlanga@tableflow.local", full_name="Lerato Mokoena (Branch Manager)",
                 password_hash=demo_pw, role_id=roles["branch_manager"].id, branch_id=branches[0].id),
            User(email="engineer@tableflow.local", full_name="Kyle Naidoo (Integration Engineer)",
                 password_hash=demo_pw, role_id=roles["integration_engineer"].id),
        ]
        db.add_all(users)
        db.add(ApiClient(client_id="n8n-automation", name="n8n workflow engine",
                         client_secret_hash=hash_password(os.getenv("N8N_CLIENT_SECRET", "dev-n8n-secret-change-me")),
                         scopes="automation:run reports:read integrations:manage"))
        integs = {n: Integration(name=n, display_name=d, kind=k, provider=p, base_url=u, mode="simulated",
                                 config={"simulate_outage": False, "failure_rate": 0.0})
                  for n, d, k, p, u in INTEGRATIONS}
        db.add_all(integs.values())
        for wf, events in [("tableflow-failed-payment", ["payment.failed"]),
                           ("tableflow-pos-failure", ["pos.order_forward_failed", "pos.menu_sync_failed"]),
                           ("tableflow-new-order", ["order.received"]),
                           ("tableflow-loyalty-update", ["loyalty.points_earned", "loyalty.sync_failed"]),
                           ("tableflow-incident-escalation", ["incident.created", "incident.escalated"])]:
            db.add(WebhookSubscription(name=f"n8n: {wf}", target_url=f"http://n8n:5678/webhook/{wf}",
                                       event_types=events, secret_env_var="N8N_WEBHOOK_SHARED_SECRET"))
        for b in branches:
            for item, unit, par, reorder in INVENTORY:
                level = par * RNG.uniform(0.25, 1.1)
                db.add(InventoryItem(branch_id=b.id, item_name=item, unit=unit, quantity_on_hand=money(level),
                                     reorder_level=Decimal(reorder)))
        db.flush()

        # ---- customers & loyalty ------------------------------------------------------------
        customers, accounts = [], {}
        phones = set()
        for i in range(1, 451):
            while True:
                phone = f"+27{RNG.choice([60, 61, 62, 63, 71, 72, 73, 74, 76, 79, 81, 82, 83, 84])}{RNG.randint(1000000, 9999999)}"
                if phone not in phones:
                    phones.add(phone)
                    break
            fn, ln = RNG.choice(FIRST), RNG.choice(LAST)
            customers.append({"id": i, "full_name": f"{fn} {ln}", "phone": phone,
                              "email": f"{fn.lower()}.{ln.lower().replace(' ', '')}{i}@example.com",
                              "marketing_opt_in": RNG.random() < 0.4,
                              "created_at": now - timedelta(days=RNG.randint(60, 900))})
            if i <= 320:
                accounts[i] = {"id": i, "customer_id": i, "member_number": f"SF{100000 + i}", "points_balance": 0,
                               "lifetime_points": 0, "tier": "Bronze", "created_at": customers[-1]["created_at"]}
        db.execute(insert(Customer), customers)

        # ---- orders, payments, POS, settlements, loyalty (Core bulk inserts) ----------------
        orders, items, payments, pos_tx, settles, ltx, logs, refunds = [], [], [], [], [], [], [], []
        oid = iid = pid = lid = 0
        int_ids = {n: i.id for n, i in integs.items()}
        prod_list = products
        weights = [b[6] for b in BRANCHES]

        def add_log(integ, op, status, ms, attempt, ts, etype, eid, branch_id, http=200, err=None):
            nonlocal lid
            lid += 1
            logs.append({"id": lid, "integration_id": int_ids[integ], "branch_id": branch_id, "operation": op,
                         "direction": "outbound", "status": status, "http_status": http, "response_ms": ms,
                         "attempt": attempt, "correlation_id": f"seed{lid:08x}", "entity_type": etype,
                         "entity_id": eid, "request_payload": None, "response_payload": None,
                         "error_message": err, "created_at": ts})

        for day_offset in range(days - 1, -1, -1):
            d = today - timedelta(days=day_offset)
            weekend = d.weekday() >= 4
            for bidx, branch in enumerate(branches):
                n_orders = int(RNG.gauss(13, 3) * weights[bidx] * (1.35 if weekend else 1.0))
                for _ in range(max(n_orders, 3)):
                    hour = RNG.choices(range(10, 22), weights=[2, 5, 9, 7, 4, 3, 4, 8, 10, 8, 5, 2])[0]
                    created = datetime(d.year, d.month, d.day, hour, RNG.randint(0, 59), RNG.randint(0, 59),
                                       tzinfo=SAST).astimezone(timezone.utc)
                    if created > now:
                        continue
                    oid += 1
                    channels = ["in_store"] * 6 + ["web"] + list(branch.digital_channels) * 2
                    channel = RNG.choice(channels)
                    n_lines = RNG.choices([1, 2, 3, 4], weights=[3, 4, 2, 1])[0]
                    total = Decimal("0")
                    for prod in RNG.sample(prod_list, n_lines):
                        qty = RNG.choices([1, 2, 3], weights=[8, 3, 1])[0]
                        iid += 1
                        lt = prod.price * qty
                        total += lt
                        items.append({"id": iid, "order_id": oid, "product_id": prod.id, "quantity": qty,
                                      "unit_price": prod.price, "line_total": lt})
                    cust_id = RNG.randint(1, 450) if RNG.random() < (0.85 if channel != "in_store" else 0.45) else None
                    age_min = (now - created).total_seconds() / 60
                    r = RNG.random()
                    if r < 0.03:
                        status = "cancelled"
                    elif r < 0.04:
                        status = "failed"
                    elif age_min < 25:
                        status = RNG.choice(["accepted", "preparing", "ready"])
                    else:
                        status = "completed"
                    sub, vat = vat_split(total)
                    ext = None
                    if channel == "uber_eats":
                        ext = f"{RNG.getrandbits(32):08x}-{RNG.getrandbits(16):04x}-4{RNG.getrandbits(12):03x}-a{RNG.getrandbits(12):03x}-{RNG.getrandbits(48):012x}"
                    elif channel == "mr_d":
                        ext = f"MRD-{RNG.randint(10000000, 99999999)}"
                    check = None if status == "failed" else f"SIM-{branch.pos_location_ref}-{1000 + oid % 9000}{oid}"
                    orders.append({"id": oid, "order_number": f"TF-{d:%y%m%d}-{oid:06X}", "branch_id": branch.id,
                                   "customer_id": cust_id, "channel": channel, "external_ref": ext, "status": status,
                                   "subtotal": sub, "vat": vat, "total": total, "pos_check_ref": check, "notes": "",
                                   "cancel_reason": "Customer cancelled on app" if status == "cancelled" else None,
                                   "created_at": created, "updated_at": created + timedelta(minutes=25)})
                    # POS forward log
                    if status == "failed":
                        for att in (1, 2, 3):
                            add_log("micros_simphony", "create_check", "failed" if att == 3 else "retrying",
                                    10000, att, created, "order", oid, branch.id, 504,
                                    "Oracle MICROS Simphony timed out after 10s")
                    else:
                        add_log("micros_simphony", "create_check", "success", RNG.randint(60, 260), 1, created,
                                "order", oid, branch.id)
                    if status in ("cancelled", "failed"):
                        continue
                    # POS transaction (closed check) - with occasional gaps / mismatches
                    pr = RNG.random()
                    if status == "completed" and pr > 0.006 and d < today:
                        pos_total = total if pr > 0.008 else total - Decimal("10.00")
                        pos_tx.append({"branch_id": branch.id, "check_number": check, "order_id": oid,
                                       "total": pos_total, "tender_type": "card", "business_date": d,
                                       "synced_at": created + timedelta(hours=6)})
                    # Payments
                    pay_ts = created + timedelta(seconds=RNG.randint(20, 240))
                    if RNG.random() < 0.045:
                        pid += 1
                        reason = RNG.choices([x[0] for x in DECLINES], weights=[x[1] for x in DECLINES])[0]
                        payments.append({"id": pid, "order_id": oid, "provider": "transaction_junction",
                                         "provider_reference": f"TJ{RNG.getrandbits(56):014X}",
                                         "idempotency_key": f"seed-{pid}", "amount": total, "currency": "ZAR",
                                         "method": "card", "status": "failed", "failure_reason": reason,
                                         "refunded_amount": Decimal("0"), "created_at": pay_ts, "updated_at": pay_ts})
                        add_log("transaction_junction", "authorise", "failed", RNG.randint(300, 900), 1, pay_ts,
                                "payment", pid, branch.id, 402, reason)
                        if RNG.random() < 0.25:
                            continue  # customer walked away -> missing payment (reconciliation will flag)
                        pay_ts += timedelta(minutes=2)
                    pid += 1
                    amount = total
                    if RNG.random() < 0.003 and total > Decimal("60"):
                        # amount mismatch (only on orders large enough to stay positive - the DB CHECK
                        # constraint ck_payment_amount_positive rejected the first version of this seed)
                        amount = total - Decimal(RNG.choice(["5.00", "10.00", "29.90"]))
                    ref = f"TJ{RNG.getrandbits(56):014X}"
                    pstatus = "captured" if age_min > 5 else "authorised"
                    payments.append({"id": pid, "order_id": oid, "provider": "transaction_junction",
                                     "provider_reference": ref, "idempotency_key": f"seed-{pid}", "amount": amount,
                                     "currency": "ZAR", "method": RNG.choice(["card", "tap", "tap"]),
                                     "status": pstatus, "failure_reason": None, "refunded_amount": Decimal("0"),
                                     "created_at": pay_ts, "updated_at": pay_ts})
                    add_log("transaction_junction", "authorise", "success", RNG.randint(250, 700), 1, pay_ts,
                            "payment", pid, branch.id)
                    refs = [(ref, amount, pid)]
                    if RNG.random() < 0.0025:  # duplicate capture (double tap / retry without idempotency)
                        pid += 1
                        dref = f"TJ{RNG.getrandbits(56):014X}"
                        payments.append({"id": pid, "order_id": oid, "provider": "transaction_junction",
                                         "provider_reference": dref, "idempotency_key": f"seed-{pid}",
                                         "amount": amount, "currency": "ZAR", "method": "tap", "status": "captured",
                                         "failure_reason": None, "refunded_amount": Decimal("0"),
                                         "created_at": pay_ts + timedelta(seconds=3),
                                         "updated_at": pay_ts + timedelta(seconds=3)})
                        refs.append((dref, amount, pid))
                    if RNG.random() < 0.004 and pstatus == "captured":
                        refunds.append({"payment_id": pid, "amount": amount, "reason": "Order quality complaint",
                                        "status": "completed", "provider_reference": f"RF{RNG.getrandbits(48):012X}",
                                        "requested_by": "finance@tableflow.local",
                                        "created_at": pay_ts + timedelta(hours=3)})
                        payments[-1]["status"] = "refunded"
                        payments[-1]["refunded_amount"] = amount
                    # Settlement (T+1) with occasional short-pay / missing line
                    if d < today:
                        for sref, samount, _p in refs:
                            sr = RNG.random()
                            if sr < 0.004:
                                continue
                            settles.append({"provider": "transaction_junction", "provider_reference": sref,
                                            "branch_code": branch.code,
                                            "amount": samount if sr > 0.007 else samount - Decimal("1.50"),
                                            "fee": (samount * Decimal("0.0175")).quantize(CENT), "business_date": d,
                                            "imported_at": created + timedelta(days=1)})
                    # Loyalty earn
                    if cust_id in accounts and pstatus == "captured":
                        pts = int(amount // 10)
                        if pts:
                            acc = accounts[cust_id]
                            failed = RNG.random() < 0.02
                            ltx.append({"account_id": cust_id, "order_id": oid, "type": "earn", "points": pts,
                                        "sync_status": "failed" if failed else "synced",
                                        "external_ref": None if failed else f"LP{RNG.getrandbits(40):010X}",
                                        "error": "Loyalty Platform timed out after 10s" if failed else None,
                                        "attempts": 3 if failed else 1, "created_at": pay_ts + timedelta(minutes=1)})
                            acc["points_balance"] += pts
                            acc["lifetime_points"] += pts
        # a few settlement lines with no matching payment (e.g. another merchant ID misrouted)
        for k in range(3):
            d = today - timedelta(days=RNG.randint(1, 10))
            settles.append({"provider": "transaction_junction", "provider_reference": f"TJUNKNOWN{k:06d}",
                            "branch_code": RNG.choice(branches).code, "amount": money(RNG.uniform(60, 400)),
                            "fee": Decimal("1.20"), "business_date": d, "imported_at": now})
        # redemptions
        for acc in RNG.sample(list(accounts.values()), 60):
            if acc["points_balance"] >= 50:
                pts = RNG.choice([50, 100, 150]) if acc["points_balance"] >= 150 else 50
                acc["points_balance"] -= pts
                ltx.append({"account_id": acc["id"], "order_id": None, "type": "redeem", "points": pts,
                            "sync_status": "synced", "external_ref": f"LP{RNG.getrandbits(40):010X}", "error": None,
                            "attempts": 1, "created_at": now - timedelta(days=RNG.randint(0, 20))})
        for acc in accounts.values():
            lp = acc["lifetime_points"]
            acc["tier"] = "Gold" if lp >= 1500 else "Silver" if lp >= 500 else "Bronze"

        db.execute(insert(LoyaltyAccount), list(accounts.values()))
        for chunk_start in range(0, len(orders), 2000):
            db.execute(insert(Order), orders[chunk_start:chunk_start + 2000])
        for tbl, rows in ((OrderItem, items), (Payment, payments), (Refund, refunds), (PosTransaction, pos_tx),
                          (SettlementRecord, settles), (LoyaltyTransaction, ltx), (IntegrationLog, logs)):
            for chunk_start in range(0, len(rows), 3000):
                db.execute(insert(tbl), rows[chunk_start:chunk_start + 3000])

        # ---- integration health snapshot ---------------------------------------------------
        for name, integ in integs.items():
            integ.total_requests = sum(1 for entry in logs if entry["integration_id"] == integ.id)
            integ.total_failures = sum(1 for entry in logs if entry["integration_id"] == integ.id
                                       and entry["status"] == "failed")
            integ.avg_response_ms = {"micros_simphony": 160, "transaction_junction": 470, "uber_eats": 210,
                                     "mr_d": 240, "loyalty_platform": 130, "finance_gl": 380,
                                     "backoffice_inventory": 150}[name]
            integ.last_success_at = now - timedelta(minutes=RNG.randint(1, 30))
        integs["loyalty_platform"].status = "degraded"
        integs["loyalty_platform"].config = {"simulate_outage": False, "failure_rate": 0.15}
        integs["loyalty_platform"].last_error = "Loyalty Platform timed out after 10s"
        integs["loyalty_platform"].last_failure_at = now - timedelta(hours=2)

        # ---- webhook events (recent 10 days) -------------------------------------------------
        recent = [p for p in payments if p["status"] in ("captured", "refunded")
                  and p["created_at"] > now - timedelta(days=10)]
        wh = []
        for p in recent:
            wh.append({"source": "transaction_junction", "event_id": f"evt_{p['id']:010d}", "event_type": "payment.captured",
                       "payload": {"type": "payment.captured", "data": {"transactionId": p["provider_reference"],
                                                                        "amount": str(p["amount"])}},
                       "signature_valid": True, "status": "processed", "attempts": 1 + (RNG.random() < 0.05),
                       "error": None, "received_at": p["created_at"] + timedelta(seconds=4),
                       "processed_at": p["created_at"] + timedelta(seconds=4)})
        for k in range(6):
            ts = now - timedelta(days=RNG.randint(0, 6), hours=RNG.randint(0, 12))
            wh.append({"source": "transaction_junction", "event_id": f"rejected-seed{k:04d}", "event_type": "payment.captured",
                       "payload": {"note": "signature computed with rotated secret"}, "signature_valid": False,
                       "status": "rejected", "attempts": 1, "error": "signature mismatch", "received_at": ts,
                       "processed_at": None})
        for k in range(4):
            ts = now - timedelta(days=RNG.randint(0, 5))
            wh.append({"source": "transaction_junction", "event_id": f"evt_failed{k:04d}", "event_type": "payment.captured",
                       "payload": {"type": "payment.captured", "data": {"transactionId": f"TJMISSING{k:05d}",
                                                                        "amount": "89.80"}},
                       "signature_valid": True, "status": "failed", "attempts": 1,
                       "error": f"Unknown transactionId TJMISSING{k:05d}", "received_at": ts, "processed_at": None})
        db.execute(insert(WebhookEvent), wh)

        # ---- historic incidents --------------------------------------------------------------
        def incident(title, sev, cat, days_ago, hours_open, status, root, resolution, integ=None, branch=None,
                     source="automated", events=()):
            opened = now - timedelta(days=days_ago, hours=RNG.randint(0, 6))
            inc = Incident(reference="TMP", title=title, severity=sev, category=cat, status=status, source=source,
                           description=root or "", integration_id=integs[integ].id if integ else None,
                           branch_id=branch.id if branch else None, opened_at=opened,
                           root_cause=root if status in ("resolved", "closed") else None,
                           resolution_notes=resolution,
                           resolved_at=opened + timedelta(hours=hours_open) if status in ("resolved", "closed") else None,
                           assigned_to_id=users[4].id, escalation_level=1 if sev == "SEV1" else 0)
            db.add(inc)
            db.flush()
            inc.reference = f"INC-{inc.id:05d}"
            db.add(IncidentEvent(incident_id=inc.id, event_type="created", message=f"Incident created ({sev}) via {source}",
                                 actor="system", created_at=opened))
            for minutes, etype, msg, actor in events:
                db.add(IncidentEvent(incident_id=inc.id, event_type=etype, message=msg, actor=actor,
                                     created_at=opened + timedelta(minutes=minutes)))

        eng = "engineer@tableflow.local"
        incident("Transaction Junction gateway timeouts - card payments failing", "SEV1", "payment", 18, 1.6, "closed",
                 "Upstream switch maintenance window not communicated; TLS handshake timeouts from 19:02-20:38 SAST.",
                 "Failed-over customers to tap-on-terminal; replayed 37 captured webhooks; agreed maintenance comms "
                 "SLA with provider.", integ="transaction_junction",
                 events=[(4, "assignment", "Assigned to Kyle Naidoo", eng),
                         (9, "escalation", "Escalated to level 1 (Solutions Engineering lead)", eng),
                         (35, "status_change", "investigating -> mitigated", eng),
                         (96, "status_change", "mitigated -> resolved", eng)])
        incident("Simphony check creation failing at Liberty Midlands (PMB-LBT)", "SEV2", "pos", 11, 3.2, "resolved",
                 "New menu items (Spicy Rice Bowl) not mapped to Simphony menu item numbers after menu change.",
                 "Mapped items, ran menu sync, retried 14 failed orders from Integration Monitoring.",
                 integ="micros_simphony", branch=branches[3],
                 events=[(12, "note", "Integration logs show HTTP 422 'Menu items not mapped'", eng),
                         (150, "status_change", "investigating -> resolved", eng)])
        incident("Duplicate Uber Eats orders after provider retry storm", "SEV3", "ordering", 7, 2.0, "closed",
                 "Provider retried order webhook 4x within 2s; duplicates blocked by (channel, external_ref) "
                 "constraint - no customer impact, alert noise only.",
                 "Confirmed idempotency working; tuned alert to ignore duplicate acknowledgements.", integ="uber_eats",
                 source="manual")
        incident("Webhook signature failures after secret rotation", "SEV2", "payment", 3, 0.8, "resolved",
                 "Gateway rotated webhook signing secret before we deployed the new value.",
                 "Updated WEBHOOK_SECRET_TRANSACTION_JUNCTION via secret manager; replayed rejected events.",
                 integ="transaction_junction")
        incident("Loyalty platform intermittent timeouts", "SEV3", "loyalty", 0, 0, "investigating", None, None,
                 integ="loyalty_platform",
                 events=[(20, "note", "~15% of earn calls timing out; points kept locally as failed for retry", eng)])
        incident("Reconciliation variance on Sandton City settlement", "SEV3", "reconciliation", 1, 0, "open", None, None,
                 branch=branches[6], source="automated")

        # ---- audit + notifications samples ---------------------------------------------------
        db.add_all([
            AuditLog(actor="system:seed", action="seed.completed", entity_type="database", details={"days": days}),
            Notification(workflow="failed_payment", event_type="payment.failed", status="recorded",
                         payload={"branch": "JHB-SDN", "amount": "164.90", "reason": "51 Insufficient funds"}),
            Notification(workflow="pos_failure", event_type="pos.order_forward_failed", status="recorded",
                         payload={"branch": "PMB-LBT", "error": "Menu items not mapped in Simphony: BWL-RCE"}),
        ])
        db.commit()

        if engine.dialect.name == "postgresql":  # explicit ids were used -> realign sequences
            with engine.begin() as conn:
                for table in Base.metadata.sorted_tables:
                    if "id" in table.c:
                        # table names come from ORM metadata, never from user input
                        sql = (f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "  # noqa: S608
                               f"COALESCE((SELECT MAX(id) FROM {table.name}), 0) + 1, false)")
                        conn.execute(text(sql))
        return {"branches": len(branches), "orders": len(orders), "order_items": len(items),
                "payments": len(payments), "settlements": len(settles), "pos_transactions": len(pos_tx),
                "loyalty_transactions": len(ltx), "integration_logs": len(logs), "webhook_events": len(wh)}
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop and recreate all tables first (dev only)")
    ap.add_argument("--create-schema", action="store_true", help="create tables via ORM (SQLite/dev)")
    ap.add_argument("--if-empty", action="store_true", help="only seed when there are no branches")
    ap.add_argument("--days", type=int, default=60)
    a = ap.parse_args()
    if a.reset:
        reset_schema()
    elif a.create_schema:
        Base.metadata.create_all(engine)
    if a.if_empty and not is_empty():
        print("database already seeded - skipping")
    else:
        print(seed(a.days))
