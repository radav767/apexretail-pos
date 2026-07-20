from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


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
    cost_price: Decimal
    stock_value: Decimal
    low_stock: bool
