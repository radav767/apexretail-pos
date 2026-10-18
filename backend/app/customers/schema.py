from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreditPolicy(BaseModel):
    credit_enabled: bool = False
    unlimited_credit: bool = False
    credit_limit: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    credit_terms_days: int = Field(default=0, ge=0, le=3650)

    @model_validator(mode="after")
    def validate_policy(self):
        if self.unlimited_credit and not self.credit_enabled:
            raise ValueError("Unlimited credit requires credit to be enabled")
        if self.unlimited_credit and self.credit_limit is not None:
            raise ValueError("Unlimited credit cannot also have a monetary limit")
        if self.credit_enabled and not self.unlimited_credit and self.credit_limit is None:
            raise ValueError("A monetary credit limit is required when credit is enabled")
        return self


class CustomerCreate(CreditPolicy):
    company_id: UUID
    customer_code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=1000)
    active: bool = True
    price_level_name: str | None = Field(default=None,max_length=80)


class CustomerUpdate(BaseModel):
    customer_code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=1000)
    credit_enabled: bool | None = None
    unlimited_credit: bool | None = None
    credit_limit: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    credit_terms_days: int | None = Field(default=None, ge=0, le=3650)
    active: bool | None = None
    price_level_name: str | None = Field(default=None,max_length=80)


class CustomerOut(BaseModel):
    id: UUID
    company_id: UUID
    customer_code: str
    name: str
    phone: str | None
    email: str | None
    address: str | None
    credit_enabled: bool
    unlimited_credit: bool
    credit_limit: Decimal | None
    credit_terms_days: int
    price_level_name: str | None = None
    active: bool
    outstanding_balance: Decimal = Decimal("0.00")
    available_credit: Decimal | None = None
    model_config = ConfigDict(from_attributes=True)


class CustomerTransactionOut(BaseModel):
    transaction_type: str
    transaction_id: UUID
    sale_id: UUID | None = None
    receipt_number: str | None = None
    amount: Decimal
    payment_method: str | None = None
    branch_id: UUID
    occurred_at: datetime
    due_date: date | None = None
    reference: str | None = None
    actor_id: UUID | None = None
    actor_name: str = "Unknown"
