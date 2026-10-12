from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CurrencyCreate(BaseModel):
    company_id: UUID
    code: str = Field(min_length=1, max_length=8)
    display_name: str = Field(min_length=1, max_length=80)
    symbol: str = Field(min_length=1, max_length=10)
    decimal_places: int = Field(default=2, ge=0, le=4)
    active: bool = True
    is_base: bool = False
    cash_accepted: bool = True
    card_accepted: bool = True
    mobile_accepted: bool = True
    display_order: int = 0

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class CurrencyUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    symbol: str | None = Field(default=None, min_length=1, max_length=10)
    decimal_places: int | None = Field(default=None, ge=0, le=4)
    active: bool | None = None
    cash_accepted: bool | None = None
    card_accepted: bool | None = None
    mobile_accepted: bool | None = None
    display_order: int | None = None


class MultiCurrencyUpdate(BaseModel):
    enabled: bool


class CurrencyOut(BaseModel):
    id: UUID
    company_id: UUID
    code: str
    display_name: str
    symbol: str
    decimal_places: int
    active: bool
    is_base: bool
    cash_accepted: bool
    card_accepted: bool
    mobile_accepted: bool
    display_order: int
    current_rate: Decimal | None = None
    current_rate_id: UUID | None = None
    rate_effective_at: datetime | None = None
    previous_rate: Decimal | None = None
    previous_rate_effective_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class ExchangeRateCreate(BaseModel):
    company_id: UUID
    currency_id: UUID
    foreign_units_per_base: Decimal = Field(gt=0, max_digits=20, decimal_places=10)
    effective_at: datetime
    note: str | None = Field(default=None, max_length=500)


class ExchangeRateOut(BaseModel):
    id: UUID
    company_id: UUID
    currency_id: UUID
    currency_code: str
    foreign_units_per_base: Decimal
    effective_at: datetime
    created_by_user_id: UUID | None
    note: str | None
    created_at: datetime
    base_currency_code: str
    actor_id: UUID | None = None
    actor_name: str = "Unknown"
    model_config = ConfigDict(from_attributes=True)


class ExchangeRatePage(BaseModel):
    items: list[ExchangeRateOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class CurrencySnapshot(BaseModel):
    base_currency_code: str
    payment_currency_code: str
    exchange_rate_id: UUID | None
    exchange_rate_snapshot: Decimal
    original_amount: Decimal
    base_amount: Decimal


class PosCurrencyConfigOut(BaseModel):
    company_id: UUID
    version: int
    generated_at: datetime
    multi_currency_enabled: bool
    base_currency_code: str
    currencies: list[CurrencyOut]
