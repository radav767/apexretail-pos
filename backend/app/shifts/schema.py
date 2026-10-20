from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from app.sales.schema import SaleCreate


class ShiftOpeningBalance(BaseModel):
    currency_code: str = Field(min_length=1, max_length=8)
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=4)

    @field_validator("currency_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("A currency code is required")
        return normalized


class ShiftOpen(BaseModel):
    opening_balances: list[ShiftOpeningBalance] = Field(default_factory=list)
    opening_note: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=100)


class ShiftClosingCount(BaseModel):
    currency_code: str = Field(min_length=1, max_length=8)
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=4)

    @field_validator("currency_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("A currency code is required")
        return normalized


class ShiftClose(BaseModel):
    counted_balances: list[ShiftClosingCount]
    closing_note: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=100)
    confirmed: bool
    exception_reason: str | None = Field(default=None, max_length=1000)


class CashMovementCreate(BaseModel):
    movement_type: str = Field(pattern="^(cash_in|cash_out)$")
    currency_code: str = Field(min_length=1, max_length=8)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=100)
    manager_authorization_token: str | None = Field(default=None, max_length=200)

    @field_validator("currency_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("A currency code is required")
        return normalized

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("A reason is required")
        return normalized

    @field_validator("idempotency_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 8:
            raise ValueError("Idempotency key must contain at least 8 characters")
        return normalized


# Backward-compatible public names used by the completed Phase 4 clients.
ShiftCashMovementCreate = CashMovementCreate


class ShiftCurrencyOut(BaseModel):
    currency_code: str
    currency_name: str
    symbol: str
    decimal_places: int
    cash_accepted: bool
    opening_float: Decimal
    cash_sales: Decimal
    cash_refunds: Decimal
    cash_settlements: Decimal
    cash_expenses: Decimal
    cash_in: Decimal
    cash_out: Decimal
    cash_paid_out: Decimal
    expected_cash: Decimal
    counted_cash: Decimal | None
    variance: Decimal | None


class CashMovementOut(BaseModel):
    id: UUID
    company_id: UUID
    shift_id: UUID
    branch_id: UUID
    device_id: UUID
    employee_id: UUID
    actor_name: str | None = None
    movement_type: str
    currency_code: str
    amount: Decimal
    base_amount: Decimal | None = None
    exchange_rate_snapshot: Decimal | None = None
    reason: str
    idempotency_key: str
    created_at: datetime


ShiftCashMovementOut = CashMovementOut


class ShiftOut(BaseModel):
    id: UUID
    shift_number: str
    company_id: UUID
    shop_id: UUID
    branch_id: UUID
    device_id: UUID
    employee_id: UUID
    cashier_name: str | None = None
    cashier_role: str | None = None
    shop_name: str | None = None
    branch_name: str | None = None
    register_name: str | None = None
    business_name: str | None = None
    closing_user_name: str | None = None
    report_generated_at: datetime | None = None
    offline_shift_token: str | None = None
    status: str
    opened_at: datetime
    closed_at: datetime | None
    opening_note: str | None
    closing_note: str | None
    currencies: list[ShiftCurrencyOut]
    cash_movements: list[CashMovementOut] = Field(default_factory=list)
    summary: dict
    tips: dict | None = None


class ShiftPage(BaseModel):
    items: list[ShiftOut]
    page: int
    page_size: int
    total: int
    total_pages: int
    summary: dict = Field(default_factory=dict)


class ShiftFilterOptions(BaseModel):
    cashiers: list[dict]
    branches: list[dict]
    devices: list[dict]


class OfflineSaleResolutionCreate(BaseModel):
    action: str = Field(pattern="^(post_to_original_shift|retain_quarantined)$")
    reason: str = Field(min_length=3, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=100)
    sale: SaleCreate


class OfflineSaleResolutionOut(BaseModel):
    id: UUID
    company_id: UUID
    client_sale_id: UUID
    original_shift_id: UUID
    original_employee_id: UUID
    original_device_id: UUID
    sale_id: UUID | None
    action: str
    reason: str
    payload_sha256: str
    resolver_name: str
    created_at: datetime


class OfflineSaleResolutionPage(BaseModel):
    items: list[OfflineSaleResolutionOut]
    page: int
    page_size: int
    total: int
    total_pages: int
