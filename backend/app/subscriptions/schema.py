from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionSnapshotOut(BaseModel):
    status: str
    display_status: str
    display_status_label: str
    plan: str | None
    effective_until: datetime | None
    offline_grace_expires_at: datetime
    snapshot_token: str
    snapshot_expires_at: datetime
    writes_allowed: bool
    message: str | None = None


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_id: UUID
    plan: str | None
    status: str
    display_status: str
    display_status_label: str
    plan_label: str
    trial_started_at: datetime | None
    trial_ends_at: datetime | None
    trial_days_remaining: int | None
    current_period_started_at: datetime | None
    current_period_ends_at: datetime | None
    grace_ends_at: datetime | None
    subscription_started_at: datetime | None
    renewal_or_expiry_at: datetime | None
    provider: str | None
    provider_reference: str | None
    status_reason: str | None
    snapshot: SubscriptionSnapshotOut


class SubscriptionHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    plan: str | None
    status: str
    provider: str | None
    provider_reference: str | None
    payload: dict[str, Any] | None
    note: str | None
    created_at: datetime


class SubscriptionBillingSummaryOut(BaseModel):
    billing_period: str | None
    currency: str
    unit_price: Decimal
    terminal_count: int
    total_amount: Decimal
    included_device_ids: list[UUID]


class SubscriptionBillingOptionOut(BaseModel):
    billing_period: str
    currency: str
    unit_price: Decimal
    terminal_count: int
    total_amount: Decimal


class SubscriptionUsageOut(BaseModel):
    active_terminals: int
    billable_terminals: int
    licensed_terminal_allowance: int | None
    available_terminal_slots: int | None
    allowance_enforced: bool


class SubscriptionCheckoutSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_reference: str
    provider: str
    status: str
    billing_period: str | None
    billing_currency: str | None
    unit_price: Decimal | None
    terminal_count: int | None
    total_amount: Decimal | None
    paynow_reference: str | None
    checkout_url: str | None
    poll_url: str | None
    payment_status: str | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SubscriptionPageOut(BaseModel):
    current: SubscriptionOut
    usage: SubscriptionUsageOut
    billing_preview: SubscriptionBillingSummaryOut
    billing_options: list[SubscriptionBillingOptionOut]
    latest_checkout: SubscriptionCheckoutSessionOut | None = None
    history: list[SubscriptionHistoryOut]
    activation_available: bool
    activation_message: str | None
    provider_name: str | None
    checkout_configured: bool
    webhook_configured: bool
    payment_configuration_required: list[str] = Field(default_factory=list)
    available_plans: list[str] = Field(default_factory=lambda: ["monthly", "yearly"])


class SubscriptionActivateRequest(BaseModel):
    company_id: UUID
    plan: str = Field(pattern="^(monthly|yearly)$")


class SubscriptionActivateOut(BaseModel):
    activation_available: bool
    provider: str | None
    checkout_url: str | None
    checkout_session_id: str | None = None
    checkout_session_reference: str | None = None
    message: str


class SubscriptionWebhookIn(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    provider_event_id: str = Field(min_length=1, max_length=160)
    event_type: str = Field(min_length=1, max_length=120)
    company_id: UUID | None = None
    payload: dict[str, Any] | None = None


class SubscriptionWebhookOut(BaseModel):
    processed: bool
    duplicate: bool
    company_id: UUID | None = None
    status: str | None = None
