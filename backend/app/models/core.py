"""Core business entities: users, roles, branches, products, customers, orders, payments."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# JSONB on PostgreSQL (indexable, binary), plain JSON on SQLite for tests.
JSONType = JSON().with_variant(JSONB(), "postgresql")
Money = Numeric(12, 2)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    role: Mapped[Role] = relationship(lazy="joined")


class ApiClient(Base):
    """Machine-to-machine clients that use the OAuth 2.0 client-credentials grant (e.g. n8n)."""

    __tablename__ = "api_clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String(80), unique=True)
    client_secret_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    scopes: Mapped[str] = mapped_column(String(500), default="")  # space separated
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (
        CheckConstraint("pos_system IN ('micros_simphony','none')", name="ck_branch_pos_system"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80))
    province: Mapped[str] = mapped_column(String(80))
    address: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    pos_system: Mapped[str] = mapped_column(String(40), default="micros_simphony")
    pos_location_ref: Mapped[str] = mapped_column(String(60), default="")
    payment_provider: Mapped[str] = mapped_column(String(60), default="transaction_junction")
    digital_channels: Mapped[list] = mapped_column(JSONType, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    opened_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price >= 0", name="ck_product_price_positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    price: Mapped[Decimal] = mapped_column(Money)
    pos_item_ref: Mapped[str] = mapped_column(String(40), default="")  # Simphony menu item number
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    loyalty_account: Mapped[LoyaltyAccount | None] = relationship(back_populates="customer", uselist=False)


ORDER_STATUSES = ("received", "sent_to_pos", "accepted", "preparing", "ready", "completed", "cancelled", "failed")
ORDER_CHANNELS = ("in_store", "uber_eats", "mr_d", "web")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("channel", "external_ref", name="uq_order_channel_external_ref"),  # duplicate prevention
        CheckConstraint("total >= 0", name="ck_order_total_positive"),
        CheckConstraint(f"status IN {ORDER_STATUSES}", name="ck_order_status"),
        CheckConstraint(f"channel IN {ORDER_CHANNELS}", name="ck_order_channel"),
        Index("ix_orders_branch_created", "branch_id", "created_at"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_created_at", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(30), unique=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    channel: Mapped[str] = mapped_column(String(20))
    external_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="received")
    subtotal: Mapped[Decimal] = mapped_column(Money)  # excl. VAT
    vat: Mapped[Decimal] = mapped_column(Money)
    total: Mapped[Decimal] = mapped_column(Money)  # incl. 15% VAT
    pos_check_ref: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    branch: Mapped[Branch] = relationship(lazy="joined")
    customer: Mapped[Customer | None] = relationship()
    items: Mapped[list[OrderItem]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[list[Payment]] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_item_qty"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Money)
    line_total: Mapped[Decimal] = mapped_column(Money)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(lazy="joined")


PAYMENT_STATUSES = ("initiated", "authorised", "captured", "failed", "refunded", "partially_refunded")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        CheckConstraint(f"status IN {PAYMENT_STATUSES}", name="ck_payment_status"),
        Index("ix_payments_status_created", "status", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="transaction_junction")
    provider_reference: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="ZAR")
    method: Mapped[str] = mapped_column(String(20), default="card")  # card | tap | cash | provider
    status: Mapped[str] = mapped_column(String(20), default="initiated")
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refunded_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    order: Mapped[Order] = relationship(back_populates="payments")
    refunds: Mapped[list[Refund]] = relationship(back_populates="payment")


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_refund_amount_positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | completed | failed
    provider_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    payment: Mapped[Payment] = relationship(back_populates="refunds")


class LoyaltyAccount(Base):
    __tablename__ = "loyalty_accounts"
    __table_args__ = (CheckConstraint("points_balance >= 0", name="ck_loyalty_balance_non_negative"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), unique=True)
    member_number: Mapped[str] = mapped_column(String(30), unique=True)
    points_balance: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_points: Mapped[int] = mapped_column(Integer, default=0)
    tier: Mapped[str] = mapped_column(String(20), default="Bronze")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped[Customer] = relationship(back_populates="loyalty_account", lazy="joined")


class LoyaltyTransaction(Base):
    __tablename__ = "loyalty_transactions"
    __table_args__ = (
        CheckConstraint("type IN ('earn','redeem','adjust')", name="ck_loyalty_txn_type"),
        CheckConstraint("sync_status IN ('pending','synced','failed')", name="ck_loyalty_sync_status"),
        UniqueConstraint("account_id", "order_id", "type", name="uq_loyalty_once_per_order"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("loyalty_accounts.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    type: Mapped[str] = mapped_column(String(10))
    points: Mapped[int] = mapped_column(Integer)
    sync_status: Mapped[str] = mapped_column(String(10), default="pending")
    external_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    account: Mapped[LoyaltyAccount] = relationship()
