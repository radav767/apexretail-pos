from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExpenseCategoryCreate(BaseModel):
    company_id: UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class ExpenseCategoryOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    description: str | None
    active: bool
    model_config = ConfigDict(from_attributes=True)


class ExpenseCreate(BaseModel):
    company_id: UUID
    category_id: UUID
    branch_id: UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    occurred_at: datetime
    payment_method: Literal["cash", "card", "mobile"]
    description: str = Field(min_length=1, max_length=1000)
    reference: str | None = Field(default=None, max_length=160)
    idempotency_key: str = Field(min_length=8, max_length=100)


class ExpenseOut(BaseModel):
    id: UUID
    company_id: UUID
    category_id: UUID
    shop_id: UUID
    branch_id: UUID
    actor_user_id: UUID | None
    employee_id: UUID | None
    amount: Decimal
    currency_code: str
    occurred_at: datetime
    payment_method: str
    description: str
    reference: str | None
    idempotency_key: str
    created_at: datetime
    category_name: str | None = None
    model_config = ConfigDict(from_attributes=True)
