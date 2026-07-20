from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GRNCreate(BaseModel):
    company_id: UUID
    product_id: UUID

    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)

    reference: str | None = Field(default=None, max_length=80)
    supplier: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)


class StockAdjustmentCreate(BaseModel):
    company_id: UUID
    product_id: UUID

    adjustment_type: Literal["add", "remove", "set"]
    quantity: Decimal = Field(ge=0)

    reason: str = Field(min_length=1, max_length=160)
    reference: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=1000)


class InventoryMovementOut(BaseModel):
    id: UUID
    company_id: UUID
    product_id: UUID
    product_name: str
    movement_type: str

    quantity: Decimal
    before_qty: Decimal
    after_qty: Decimal
    unit_cost: Decimal

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

    cost_price: Decimal
    selling_price: Decimal
    stock_qty: Decimal
    reorder_level: Decimal
    stock_value: Decimal

    low_stock: bool


class InventoryValuationOut(BaseModel):
    total_products: int
    total_quantity: Decimal
    total_cost_value: Decimal
    low_stock_products: int
