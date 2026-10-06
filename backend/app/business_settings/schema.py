from decimal import Decimal
from typing import Literal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanySettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    owner_name: str | None = Field(default=None, max_length=160)
    business_type: str | None = Field(default=None, min_length=1, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=80)

    address: str | None = Field(default=None, max_length=1000)
    contact_email: str | None = Field(default=None, max_length=255)

    currency_code: str | None = Field(default=None, min_length=1, max_length=10)
    currency_symbol: str | None = Field(default=None, min_length=1, max_length=10)
    decimal_places: int | None = Field(default=None, ge=0, le=4)

    tax_name: str | None = Field(default=None, min_length=1, max_length=40)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100)
    tax_inclusive: bool | None = None

    receipt_header: str | None = Field(default=None, max_length=2000)
    receipt_footer: str | None = Field(default=None, max_length=2000)

    paper_size: Literal["58mm", "80mm"] | None = None
    auto_print: bool | None = None
    payment_methods: list[str] | None = None
    multi_currency_enabled: bool | None = None
    shift_enforcement_enabled: bool | None = None
    shift_required_from: datetime | None = None
    reporting_timezone: str | None = Field(default=None, min_length=1, max_length=80)


class CompanySettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_id: UUID

    name: str
    owner_name: str | None
    owner_email: str
    business_type: str
    country: str | None
    phone: str | None

    address: str | None
    contact_email: str | None

    currency_code: str
    currency_symbol: str
    decimal_places: int

    tax_name: str
    tax_rate: Decimal
    tax_inclusive: bool

    receipt_header: str | None
    receipt_footer: str | None

    paper_size: str
    auto_print: bool
    payment_methods: list[str]
    base_currency_id: UUID | None = None
    currency_config_version: int = 1
    multi_currency_enabled: bool = False
    shift_enforcement_enabled: bool = False
    shift_required_from: datetime | None = None
    reporting_timezone: str = "Africa/Harare"


class CompanyProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_id: UUID
    name: str
    owner_name: str | None
    owner_email: str
    business_type: str
    country: str | None
    phone: str | None
    contact_email: str | None


class CompanyProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    owner_name: str | None = Field(default=None, max_length=160)
    business_type: str | None = Field(default=None, min_length=1, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=80)
    contact_email: str | None = Field(default=None, max_length=255)


class ReceiptSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_id: UUID
    receipt_header: str | None
    receipt_footer: str | None
    paper_size: str
    auto_print: bool
    tax_name: str
    tax_rate: Decimal
    tax_inclusive: bool
    payment_methods: list[str]


class ReceiptSettingsUpdate(BaseModel):
    receipt_header: str | None = Field(default=None, max_length=2000)
    receipt_footer: str | None = Field(default=None, max_length=2000)
    paper_size: Literal["58mm", "80mm"] | None = None
    auto_print: bool | None = None
    tax_name: str | None = Field(default=None, min_length=1, max_length=40)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100)
    tax_inclusive: bool | None = None
    payment_methods: list[str] | None = None


class ShopSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    state_province: str | None
    country: str | None
    phone: str | None
    tax_vat_number: str | None
    active: bool


class ShopSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    address_line_1: str | None = Field(default=None, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state_province: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=80)
    tax_vat_number: str | None = Field(default=None, max_length=120)
