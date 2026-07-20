from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class SaleItemCreate(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0)


class SaleCreate(BaseModel):
    company_id: UUID
    payment_method: str = "cash"
    amount_received: Decimal | None = None
    items: list[SaleItemCreate]


class SaleOut(BaseModel):
    id: UUID
    company_id: UUID
    receipt_number: str
    total_amount: Decimal
    amount_received: Decimal
    change_due: Decimal
    payment_method: str
    status: str

    class Config:
        from_attributes = True
