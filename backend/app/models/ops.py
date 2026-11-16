"""Operational entities: integrations, logs, webhooks, incidents, reconciliation, POS data, audit."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.core import JSONType, Money, utcnow


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (
        CheckConstraint("kind IN ('pos','payment','ordering','loyalty','finance','backoffice')", name="ck_integration_kind"),
        CheckConstraint("mode IN ('simulated','sandbox','live')", name="ck_integration_mode"),
        CheckConstraint("status IN ('healthy','degraded','down','disabled')", name="ck_integration_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)  # e.g. micros_simphony
    display_name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(80))
    mode: Mapped[str] = mapped_column(String(20), default="simulated")
    status: Mapped[str] = mapped_column(String(20), default="healthy")
    base_url: Mapped[str] = mapped_column(String(255), default="")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    total_failures: Mapped[int] = mapped_column(Integer, default=0)
    avg_response_ms: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Simulation knobs: {"simulate_outage": bool, "failure_rate": 0.0-1.0, "latency_ms": int}
    config: Mapped[dict] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IntegrationLog(Base):
    __tablename__ = "integration_logs"
    __table_args__ = (
        CheckConstraint("status IN ('success','failed','retrying','retried_ok')", name="ck_integration_log_status"),
        Index("ix_integration_logs_integration_created", "integration_id", "created_at"),
        Index("ix_integration_logs_status", "status"),
        Index("ix_integration_logs_entity", "entity_type", "entity_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    operation: Mapped[str] = mapped_column(String(60))  # e.g. create_order, menu_sync
    direction: Mapped[str] = mapped_column(String(10), default="outbound")
    status: Mapped[str] = mapped_column(String(15))
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_ms: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    correlation_id: Mapped[str] = mapped_column(String(64), default="")
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    response_payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    integration: Mapped[Integration] = relationship(lazy="joined")


class WebhookSubscription(Base):
    """Outbound webhook registrations (who we notify) - e.g. n8n endpoints, finance system."""

    __tablename__ = "webhook_subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    target_url: Mapped[str] = mapped_column(String(500))
    event_types: Mapped[list] = mapped_column(JSONType, default=list)
    secret_env_var: Mapped[str] = mapped_column(String(80), default="")  # name of env var, never the secret itself
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookEvent(Base):
    """Inbound webhook events received from providers."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("source", "event_id", name="uq_webhook_source_event"),  # duplicate prevention
        CheckConstraint("status IN ('received','processed','failed','duplicate','rejected')", name="ck_webhook_status"),
        Index("ix_webhook_events_status", "status"),
        Index("ix_webhook_events_received", "received_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40))
    event_id: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSONType)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(15), default="received")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PosTransaction(Base):
    """Checks pulled from the POS (Simphony) during transaction synchronisation."""

    __tablename__ = "pos_transactions"
    __table_args__ = (
        UniqueConstraint("branch_id", "check_number", name="uq_pos_branch_check"),
        Index("ix_pos_tx_business_date", "business_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"))
    check_number: Mapped[str] = mapped_column(String(40))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    total: Mapped[Decimal] = mapped_column(Money)
    tender_type: Mapped[str] = mapped_column(String(20), default="card")
    business_date: Mapped[date] = mapped_column(Date)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SettlementRecord(Base):
    """Lines from the payment provider settlement report (what the acquirer says it paid us)."""

    __tablename__ = "settlement_records"
    __table_args__ = (
        UniqueConstraint("provider", "provider_reference", name="uq_settlement_provider_ref"),
        Index("ix_settlement_business_date", "business_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    provider_reference: Mapped[str] = mapped_column(String(80))
    branch_code: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Money)
    fee: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    business_date: Mapped[date] = mapped_column(Date)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (UniqueConstraint("branch_id", "item_name", name="uq_inventory_branch_item"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    item_name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(20), default="kg")
    quantity_on_hand: Mapped[Decimal] = mapped_column(Money)
    reorder_level: Mapped[Decimal] = mapped_column(Money)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


INCIDENT_SEVERITIES = ("SEV1", "SEV2", "SEV3", "SEV4")
INCIDENT_STATUSES = ("open", "investigating", "mitigated", "resolved", "closed")


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(f"severity IN {INCIDENT_SEVERITIES}", name="ck_incident_severity"),
        CheckConstraint(f"status IN {INCIDENT_STATUSES}", name="ck_incident_status"),
        Index("ix_incidents_status_severity", "status", "severity"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(5))
    status: Mapped[str] = mapped_column(String(15), default="open")
    category: Mapped[str] = mapped_column(String(40))  # payment | pos | ordering | loyalty | reconciliation | infrastructure
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | automated
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    integration_id: Mapped[int | None] = mapped_column(ForeignKey("integrations.id", ondelete="SET NULL"), nullable=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    events: Mapped[list[IncidentEvent]] = relationship(back_populates="incident", order_by="IncidentEvent.created_at")


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(30))  # created | status_change | assignment | escalation | note
    message: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="events")


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="running")  # running | completed | failed
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    matched: Mapped[int] = mapped_column(Integer, default=0)
    discrepancies: Mapped[int] = mapped_column(Integer, default=0)
    discrepancy_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    run_by: Mapped[str] = mapped_column(String(255), default="system")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    records: Mapped[list[ReconciliationRecord]] = relationship(back_populates="run", cascade="all, delete-orphan")


RECON_ISSUES = (
    "matched",
    "missing_payment",
    "failed_payment",
    "duplicate_payment",
    "amount_mismatch",
    "missing_pos_record",
    "pos_amount_mismatch",
    "missing_settlement",
    "settlement_mismatch",
    "unknown_settlement",
)


class ReconciliationRecord(Base):
    __tablename__ = "reconciliation_records"
    __table_args__ = (
        CheckConstraint(f"issue_type IN {RECON_ISSUES}", name="ck_recon_issue_type"),
        Index("ix_recon_records_run_issue", "run_id", "issue_type"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("reconciliation_runs.id", ondelete="CASCADE"))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    issue_type: Mapped[str] = mapped_column(String(30))
    expected_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    actual_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    difference: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    details: Mapped[str] = mapped_column(Text, default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    run: Mapped[ReconciliationRun] = relationship(back_populates="records")


class Notification(Base):
    """Outbox of alerts sent (or attempted) to n8n / downstream channels."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_created", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60))
    workflow: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(20))  # sent | failed | recorded (no n8n configured)
    target_url: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_created", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
