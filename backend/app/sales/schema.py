from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class SaleItemCreate(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0)


class SaleCreate(BaseModel):
    company_id: UUID
    branch_id: UUID | None = None
    employee_id: UUID | None = None
    payment_method: str = "cash"
    amount_received: Decimal | None = None
    client_sale_id: UUID | None = None
    client_created_at: datetime | None = None
    items: list[SaleItemCreate]


class SaleOut(BaseModel):
    id: UUID
    company_id: UUID

    client_sale_id: UUID | None = None
    client_created_at: datetime | None = None

    shop_id: UUID | None = None
    branch_id: UUID | None = None
    employee_id: UUID | None = None
    cashier_name: str | None = None

    receipt_number: str

    subtotal_amount: Decimal

    tax_name: str | None = None

    tax_rate: Decimal

    tax_amount: Decimal

    tax_inclusive: bool
    total_amount: Decimal
    amount_received: Decimal
    change_due: Decimal
    payment_method: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
