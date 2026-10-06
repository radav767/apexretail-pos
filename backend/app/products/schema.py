from decimal import Decimal
from typing import Literal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    company_id: UUID
    name: str = Field(min_length=1, max_length=120)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None


class CategoryOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    active: bool

    model_config = ConfigDict(from_attributes=True)


class ProductCreate(BaseModel):
    company_id: UUID
    branch_id: UUID | None = None
    create_request_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
    )
    category_id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    sku: str | None = Field(default=None, max_length=80)
    barcode: str | None = Field(default=None, max_length=80)
    unit: Literal["each", "kg", "g", "litre", "ml"] = "each"
    cost_price: Decimal | None = Field(default=None, ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)
    stock_qty: Decimal = Field(default=Decimal("0"), ge=0)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)


class ProductUpdate(BaseModel):
    category_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    sku: str | None = Field(default=None, max_length=80)
    barcode: str | None = Field(default=None, max_length=80)
    unit: Literal["each", "kg", "g", "litre", "ml"] | None = None
    cost_price: Decimal | None = Field(default=None, ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)
    stock_qty: Decimal | None = Field(default=None, ge=0)
    reorder_level: Decimal | None = Field(default=None, ge=0)
    active: bool | None = None


class ProductOut(BaseModel):
    id: UUID
    company_id: UUID
    category_id: UUID | None
    name: str
    sku: str | None
    barcode: str | None
    unit: str
    cost_price: Decimal | None
    selling_price: Decimal | None
    stock_qty: Decimal
    reorder_level: Decimal
    active: bool
    archived_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductBarcodeLookupOut(ProductOut):
    branch_id: UUID
    branch_stock_qty: Decimal
