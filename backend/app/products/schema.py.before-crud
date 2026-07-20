from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel


class CategoryCreate(BaseModel):
    company_id: UUID
    name: str


class CategoryOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    active: bool

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    company_id: UUID
    category_id: UUID | None = None
    name: str
    sku: str | None = None
    barcode: str | None = None
    unit: str = "each"
    cost_price: Decimal = Decimal("0")
    selling_price: Decimal = Decimal("0")
    stock_qty: Decimal = Decimal("0")
    reorder_level: Decimal = Decimal("0")


class ProductOut(BaseModel):
    id: UUID
    company_id: UUID
    category_id: UUID | None
    name: str
    sku: str | None
    barcode: str | None
    unit: str
    cost_price: Decimal
    selling_price: Decimal
    stock_qty: Decimal
    reorder_level: Decimal
    active: bool

    class Config:
        from_attributes = True
