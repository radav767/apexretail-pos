from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


PaymentMethod = Literal["cash", "card", "mobile"]


class ReceivableOut(BaseModel):
    id: UUID
    company_id: UUID
    sale_id: UUID
    customer_id: UUID
    shop_id: UUID
    branch_id: UUID
    cashier_employee_id: UUID | None
    device_id: UUID | None
    currency_code: str
    original_amount: Decimal
    amount_settled: Decimal
    outstanding_balance: Decimal
    due_date: date
    status: str
    created_at: datetime
    customer_name: str | None = None
    customer_code: str | None = None
    sale_receipt_number: str | None = None
    model_config = ConfigDict(from_attributes=True)


class SettlementCreate(BaseModel):
    company_id: UUID
    receivable_id: UUID
    branch_id: UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_method: PaymentMethod
    reference: str | None = Field(default=None, max_length=160)
    note: str | None = Field(default=None, max_length=1000)
    received_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=100)


class SettlementOut(BaseModel):
    id: UUID
    company_id: UUID
    receivable_id: UUID
    customer_id: UUID
    shop_id: UUID
    branch_id: UUID
    actor_user_id: UUID | None
    cashier_employee_id: UUID | None
    device_id: UUID | None
    amount: Decimal
    payment_method: str
    reference: str | None
    note: str | None
    received_at: datetime
    idempotency_key: str
    receipt_number: str
    created_at: datetime
    outstanding_balance: Decimal | None = None
    model_config = ConfigDict(from_attributes=True)
