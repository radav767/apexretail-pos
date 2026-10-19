from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GRNCreate(BaseModel):
    company_id: UUID
    branch_id: UUID | None = None
    product_id: UUID
    quantity: Decimal = Field(gt=0)
    received_unit: str | None = Field(default=None, max_length=20)
    reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
    )
    unit_cost: Decimal | None = Field(default=None, ge=0)
    reference: str | None = Field(default=None, max_length=80)
    supplier: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)


class StockAdjustmentCreate(BaseModel):
    company_id: UUID
    branch_id: UUID | None = None
    product_id: UUID
    adjustment_type: Literal["add", "remove", "set"]
    quantity: Decimal = Field(ge=0)
    reason: str = Field(min_length=1, max_length=160)
    reference: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=1000)
    manager_authorization_token: str | None = Field(default=None, max_length=200)


class StockTakeItem(BaseModel):
    product_id: UUID
    physical_qty: Decimal = Field(ge=0)


class StockTakeCreate(BaseModel):
    company_id: UUID
    branch_id: UUID | None = None
    items: list[StockTakeItem] = Field(min_length=1)
    reference: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=1000)



class StockTransferItem(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0)


class StockTransferCreate(BaseModel):
    company_id: UUID
    source_branch_id: UUID
    destination_branch_id: UUID
    items: list[StockTransferItem] = Field(min_length=1)
    reference: str | None = Field(
        default=None,
        max_length=80,
    )
    notes: str | None = Field(
        default=None,
        max_length=1000,
    )


class InventoryMovementOut(BaseModel):
    id: UUID
    company_id: UUID
    shop_id: UUID | None = None
    branch_id: UUID | None = None
    product_id: UUID
    variant_id: UUID | None = None
    product_name: str
    movement_type: str
    quantity: Decimal
    before_qty: Decimal
    after_qty: Decimal
    unit_cost: Decimal | None
    reference: str | None
    supplier: str | None
    reason: str | None
    notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryProductOut(BaseModel):
    product_id: UUID
    name: str
    sku: str | None
    unit: str
    purchase_unit: str | None = None
    units_per_purchase: Decimal = Decimal("1")
    cost_price: Decimal | None
    selling_price: Decimal | None
    stock_qty: Decimal
    reorder_level: Decimal
    stock_value: Decimal | None
    low_stock: bool


class InventoryValuationOut(BaseModel):
    total_products: int
    total_quantity: Decimal
    total_cost_value: Decimal | None
    low_stock_products: int
