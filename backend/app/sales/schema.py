from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class SaleItemCreate(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    selling_unit: str | None = Field(default=None, max_length=20)
    unit_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    line_total: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


class SaleCreate(BaseModel):
    company_id: UUID
    branch_id: UUID | None = None
    employee_id: UUID | None = None
    device_id: UUID | None = None
    device_key: str | None = Field(default=None, max_length=255)
    payment_method: str = "cash"
    amount_received: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    discount_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    client_sale_id: UUID | None = None
    client_created_at: datetime | None = None
    items: list[SaleItemCreate]


class SaleOut(BaseModel):
    id: UUID
    company_id: UUID
    original_sale_id: UUID | None = None

    client_sale_id: UUID | None = None
    client_created_at: datetime | None = None

    shop_id: UUID | None = None
    branch_id: UUID | None = None
    employee_id: UUID | None = None
    device_id: UUID | None = None
    cashier_name: str | None = None
    shop_name_snapshot: str | None = None
    shop_address_snapshot: dict | None = None
    branch_name_snapshot: str | None = None
    pos_name_snapshot: str | None = None
    pos_number_snapshot: str | None = None
    receipt_footer_snapshot: str | None = None

    receipt_number: str

    subtotal_amount: Decimal

    tax_name: str | None = None

    tax_rate: Decimal

    tax_amount: Decimal

    tax_inclusive: bool
    total_amount: Decimal
    discount_amount: Decimal | None = None
    amount_received: Decimal
    change_due: Decimal
    payment_method: str
    status: str
    created_at: datetime
    refund_reason: str | None = None
    refund_method: str | None = None
    reprint_count: int = 0
    last_reprinted_at: datetime | None = None

    class Config:
        from_attributes = True


class SaleItemOut(BaseModel):
    id: UUID
    product_id: UUID
    original_sale_item_id: UUID | None = None
    product_name: str
    quantity: Decimal
    refunded_quantity: Decimal = Decimal("0")
    refundable_quantity: Decimal = Decimal("0")
    selling_unit: str = "each"
    unit_price: Decimal
    line_total: Decimal

    class Config:
        from_attributes = True


class SaleReceiptOut(SaleOut):
    items: list[SaleItemOut]


class RefundItemCreate(BaseModel):
    sale_item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class RefundCreate(BaseModel):
    company_id: UUID
    original_sale_id: UUID
    branch_id: UUID | None = None
    employee_id: UUID | None = None
    device_id: UUID | None = None
    device_key: str | None = Field(default=None, max_length=255)
    reason: str = Field(min_length=1, max_length=500)
    refund_method: str | None = Field(default=None, max_length=40)
    items: list[RefundItemCreate] = Field(min_length=1)
