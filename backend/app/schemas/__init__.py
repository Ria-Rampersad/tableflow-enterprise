"""Pydantic request/response models.

Pydantic validates every inbound payload before it reaches business logic:
wrong types, missing fields, negative quantities, malformed phone numbers and
unknown enum values all return HTTP 422 with a precise error message.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PHONE_PATTERN = r"^\+?27\d{9}$|^0\d{9}$"  # South African mobile/landline
# Pattern instead of EmailStr: EmailStr rejects reserved domains such as the internal demo domain
# "tableflow.local" (defect found by test_admin_creates_user_with_password_policy).
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ auth
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str | None = None
    scopes: list[str] | None = None


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    role: str
    branch_id: int | None

    @classmethod
    def from_user(cls, u) -> UserOut:
        return cls(id=u.id, email=u.email, full_name=u.full_name, role=u.role.name, branch_id=u.branch_id)


class UserCreate(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=128)
    role: Literal["admin", "finance", "operations", "branch_manager", "integration_engineer"]
    branch_id: int | None = None

    @field_validator("password")
    @classmethod
    def strong(cls, v: str) -> str:
        if not (any(c.isdigit() for c in v) and any(c.isalpha() for c in v)):
            raise ValueError("password must contain letters and digits")
        return v


# ------------------------------------------------------------------ branches
class BranchBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    city: str = Field(min_length=2, max_length=80)
    province: Literal[
        "Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
        "Mpumalanga", "North West", "Northern Cape", "Western Cape",
    ]
    address: str = ""
    phone: str = ""
    pos_system: Literal["micros_simphony", "none"] = "micros_simphony"
    pos_location_ref: str = ""
    payment_provider: Literal["transaction_junction"] = "transaction_junction"
    digital_channels: list[Literal["uber_eats", "mr_d", "web"]] = []
    is_active: bool = True
    opened_on: date | None = None


class BranchCreate(BranchBase):
    code: str = Field(pattern=r"^[A-Z]{3}-[A-Z0-9]{2,6}$", examples=["DBN-UML"])


class BranchUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    pos_location_ref: str | None = None
    pos_system: Literal["micros_simphony", "none"] | None = None
    payment_provider: Literal["transaction_junction"] | None = None
    digital_channels: list[Literal["uber_eats", "mr_d", "web"]] | None = None
    is_active: bool | None = None


class BranchOut(BranchBase, ORMModel):
    id: int
    code: str
    province: str


# ------------------------------------------------------------------ orders
class OrderItemIn(BaseModel):
    sku: str
    quantity: int = Field(gt=0, le=50)
    unit_price: Decimal | None = Field(default=None, ge=0)


class CanonicalOrder(BaseModel):
    """The single internal shape every channel's order is mapped into."""

    channel: Literal["in_store", "uber_eats", "mr_d", "web"]
    external_ref: str | None = None
    display_ref: str = ""
    branch_code: str
    customer_name: str | None = None
    customer_phone: str | None = None
    items: list[OrderItemIn] = Field(min_length=1)
    total: Decimal | None = None
    notes: str = ""
    placed_at: datetime | None = None


class OrderCreate(BaseModel):
    """Direct order creation (in-store / web) through the internal API."""

    branch_id: int
    channel: Literal["in_store", "web"] = "in_store"
    customer_phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    customer_name: str | None = None
    items: list[OrderItemIn] = Field(min_length=1)
    notes: str = ""


class OrderStatusUpdate(BaseModel):
    status: Literal["accepted", "preparing", "ready", "completed", "cancelled"]
    reason: str | None = None

    @model_validator(mode="after")
    def reason_for_cancel(self):
        if self.status == "cancelled" and not self.reason:
            raise ValueError("reason is required when cancelling an order")
        return self


class OrderItemOut(ORMModel):
    sku: str
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderOut(ORMModel):
    id: int
    order_number: str
    branch_id: int
    branch_name: str
    channel: str
    external_ref: str | None
    status: str
    subtotal: Decimal
    vat: Decimal
    total: Decimal
    pos_check_ref: str | None
    customer_id: int | None
    created_at: datetime
    items: list[OrderItemOut] = []
    payment_status: str | None = None


class OrderIngestResult(BaseModel):
    order: OrderOut
    duplicate: bool = False
    pos_forwarded: bool = False
    message: str = ""


# ------------------------------------------------------------------ payments
class PaymentCreate(BaseModel):
    order_id: int
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: Literal["ZAR"] = "ZAR"
    method: Literal["card", "tap"] = "card"
    card_token: str = Field(min_length=3, max_length=60, examples=["tok_visa_approved"])


class PaymentOut(ORMModel):
    id: int
    order_id: int
    provider: str
    provider_reference: str | None
    idempotency_key: str | None
    amount: Decimal
    currency: str
    method: str
    status: str
    failure_reason: str | None
    refunded_amount: Decimal
    created_at: datetime


class RefundCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=3, max_length=255)


class RefundOut(ORMModel):
    id: int
    payment_id: int
    amount: Decimal
    reason: str
    status: str
    provider_reference: str | None
    created_at: datetime


# ------------------------------------------------------------------ loyalty
class RedeemRequest(BaseModel):
    points: int = Field(gt=0, le=100000)
    order_id: int | None = None


class LoyaltyAccountOut(BaseModel):
    id: int
    member_number: str
    customer_name: str
    phone: str
    points_balance: int
    lifetime_points: int
    tier: str


class LoyaltyTxnOut(ORMModel):
    id: int
    account_id: int
    order_id: int | None
    type: str
    points: int
    sync_status: str
    external_ref: str | None
    error: str | None
    attempts: int
    created_at: datetime


# ------------------------------------------------------------------ integrations
class IntegrationOut(ORMModel):
    id: int
    name: str
    display_name: str
    kind: str
    provider: str
    mode: str
    status: str
    last_success_at: datetime | None
    last_failure_at: datetime | None
    consecutive_failures: int
    total_requests: int
    total_failures: int
    avg_response_ms: int
    last_error: str | None
    config: dict


class IntegrationConfigUpdate(BaseModel):
    simulate_outage: bool | None = None
    failure_rate: float | None = Field(default=None, ge=0, le=1)
    latency_ms: int | None = Field(default=None, ge=0, le=30000)
    status: Literal["healthy", "disabled"] | None = None


class IntegrationLogOut(ORMModel):
    id: int
    integration_id: int
    operation: str
    direction: str
    status: str
    http_status: int | None
    response_ms: int
    attempt: int
    correlation_id: str
    entity_type: str | None
    entity_id: int | None
    request_payload: dict | None
    response_payload: dict | None
    error_message: str | None
    created_at: datetime


# ------------------------------------------------------------------ webhooks
class WebhookSubscriptionIn(BaseModel):
    name: str = Field(min_length=3)
    target_url: str = Field(pattern=r"^https?://")
    event_types: list[str] = Field(min_length=1)
    secret_env_var: str = ""
    is_active: bool = True


class WebhookSubscriptionOut(WebhookSubscriptionIn, ORMModel):
    id: int


class WebhookEventOut(ORMModel):
    id: int
    source: str
    event_id: str
    event_type: str
    payload: dict
    signature_valid: bool
    status: str
    attempts: int
    error: str | None
    received_at: datetime
    processed_at: datetime | None


# ------------------------------------------------------------------ incidents
class IncidentCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = ""
    severity: Literal["SEV1", "SEV2", "SEV3", "SEV4"]
    category: Literal["payment", "pos", "ordering", "loyalty", "reconciliation", "infrastructure", "other"]
    branch_id: int | None = None
    integration_id: int | None = None


class IncidentUpdate(BaseModel):
    status: Literal["open", "investigating", "mitigated", "resolved", "closed"] | None = None
    severity: Literal["SEV1", "SEV2", "SEV3", "SEV4"] | None = None
    assigned_to_id: int | None = None
    root_cause: str | None = None
    resolution_notes: str | None = None

    @model_validator(mode="after")
    def resolution_requires_notes(self):
        if self.status in ("resolved", "closed") and not self.resolution_notes:
            raise ValueError("resolution_notes are required to resolve or close an incident")
        return self


class IncidentNote(BaseModel):
    message: str = Field(min_length=2)


class IncidentEventOut(ORMModel):
    id: int
    event_type: str
    message: str
    actor: str
    created_at: datetime


class IncidentOut(ORMModel):
    id: int
    reference: str
    title: str
    description: str
    severity: str
    status: str
    category: str
    source: str
    branch_id: int | None
    integration_id: int | None
    assigned_to_id: int | None
    escalation_level: int
    root_cause: str | None
    resolution_notes: str | None
    opened_at: datetime
    resolved_at: datetime | None


class IncidentDetail(IncidentOut):
    events: list[IncidentEventOut] = []


# ------------------------------------------------------------------ reconciliation
class ReconciliationRequest(BaseModel):
    business_date: date
    branch_id: int | None = None


class ReconciliationRecordOut(ORMModel):
    id: int
    branch_id: int | None
    order_id: int | None
    payment_id: int | None
    issue_type: str
    expected_amount: Decimal | None
    actual_amount: Decimal | None
    difference: Decimal | None
    details: str
    resolved: bool


class ReconciliationRunOut(ORMModel):
    id: int
    business_date: date
    branch_id: int | None
    status: str
    total_orders: int
    matched: int
    discrepancies: int
    discrepancy_value: Decimal
    run_by: str
    started_at: datetime
    completed_at: datetime | None


class ReconciliationRunDetail(ReconciliationRunOut):
    summary: dict[str, int] = {}
    records: list[ReconciliationRecordOut] = []


class Page(BaseModel):
    total: int
    items: list
