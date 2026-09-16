from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class BranchCreate(BaseModel):
    company_id: UUID
    shop_id: UUID | None = None
    name: str = Field(min_length=1, max_length=120)


class InventoryBranchOut(BaseModel):
    id: UUID
    shop_id: UUID
    shop_name: str
    name: str


class BranchInventoryOut(BaseModel):
    branch_id: UUID
    branch_name: str
    shop_id: UUID
    shop_name: str

    product_id: UUID
    product_name: str
    sku: str | None
    unit: str

    quantity: Decimal
    reorder_level: Decimal
    cost_price: Decimal | None
    stock_value: Decimal | None
    low_stock: bool
