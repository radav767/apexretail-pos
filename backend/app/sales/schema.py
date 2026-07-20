from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel


class SaleItemCreate(BaseModel):
    product_id: UUID
    quantity: Decimal


class SaleCreate(BaseModel):
    company_id: UUID
    payment_method: str = "cash"
    items: list[SaleItemCreate]


class SaleOut(BaseModel):
    id: UUID
    company_id: UUID
    total_amount: Decimal
    payment_method: str
    status: str

    class Config:
        from_attributes = True
