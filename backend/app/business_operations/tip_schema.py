from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class TipConfigInput(BaseModel):
    enabled: bool = False
    policy: Literal["staff", "shared", "business"] = "staff"
    weights: dict[UUID, int] = Field(default_factory=dict, max_length=500)
    business_retention_confirmed: bool = False
    service_product_id: UUID | None = None
    legacy_queues_reviewed: bool = False


class TipInput(BaseModel):
    request_id: UUID
    shift_id: UUID
    kind: Literal["collect", "reverse", "payout"]
    sale_id: UUID | None = None
    original_id: UUID | None = None
    employee_id: UUID | None = None
    payment_method: Literal["cash", "card", "mobile"]
    currency_code: str = Field(min_length=1, max_length=8)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    reason: str = Field(min_length=3, max_length=500)
    reference: str = Field(default="", max_length=120)
    confirmed: bool

    @field_validator("currency_code")
    @classmethod
    def currency(cls, value): return value.strip().upper()
