from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ShiftOpeningBalance(BaseModel):
    currency_code: str = Field(min_length=1, max_length=8)
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=4)

    @field_validator("currency_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


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
        return value.strip().upper()


class ShiftClose(BaseModel):
    counted_balances: list[ShiftClosingCount]
    closing_note: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=100)
    confirmed: bool


class ShiftCurrencyOut(BaseModel):
    currency_code: str
    currency_name: str
    symbol: str
    decimal_places: int
    opening_float: Decimal
    cash_sales: Decimal
    cash_refunds: Decimal
    cash_settlements: Decimal
    cash_expenses: Decimal
    cash_paid_out: Decimal
    expected_cash: Decimal
    counted_cash: Decimal | None
    variance: Decimal | None


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
    status: str
    opened_at: datetime
    closed_at: datetime | None
    opening_note: str | None
    closing_note: str | None
    currencies: list[ShiftCurrencyOut]
    summary: dict


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
