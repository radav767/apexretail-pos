from decimal import Decimal
from typing import Literal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    company_id: UUID
    name: str = Field(min_length=1, max_length=120)
    parent_id: UUID | None = None
    image_url: str | None = Field(default=None, max_length=500)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: UUID | None = None
    image_url: str | None = Field(default=None, max_length=500)
    active: bool | None = None


class CategoryOut(BaseModel):
    id: UUID
    company_id: UUID
    parent_id: UUID | None = None
    name: str
    image_url: str | None = None
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
    product_type: Literal[
        "standard", "non_stock", "service", "composite", "bundle", "variable_weight"
    ] = "standard"
    image_url: str | None = Field(default=None, max_length=500)
    unit: Literal["each", "kg", "g", "litre", "ml"] = "each"
    purchase_unit: str | None = Field(default=None, max_length=20)
    units_per_purchase: Decimal = Field(default=Decimal("1"), gt=0)
    track_inventory: bool = True
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100)
    tax_exempt: bool = False
    cost_price: Decimal | None = Field(default=None, ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)
    stock_qty: Decimal = Field(default=Decimal("0"), ge=0)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)


class ProductUpdate(BaseModel):
    category_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    sku: str | None = Field(default=None, max_length=80)
    barcode: str | None = Field(default=None, max_length=80)
    product_type: Literal[
        "standard", "non_stock", "service", "composite", "bundle", "variable_weight"
    ] | None = None
    image_url: str | None = Field(default=None, max_length=500)
    unit: Literal["each", "kg", "g", "litre", "ml"] | None = None
    purchase_unit: str | None = Field(default=None, max_length=20)
    units_per_purchase: Decimal | None = Field(default=None, gt=0)
    track_inventory: bool | None = None
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100)
    tax_exempt: bool | None = None
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
    product_type: str = "standard"
    image_url: str | None = None
    unit: str
    purchase_unit: str | None = None
    units_per_purchase: Decimal = Decimal("1")
    track_inventory: bool = True
    tax_rate: Decimal | None = None
    tax_exempt: bool = False
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


class ProductComponentWrite(BaseModel):
    component_product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(default="each", min_length=1, max_length=20)


class ProductComponentOut(BaseModel):
    id: UUID
    company_id: UUID
    composite_product_id: UUID
    component_product_id: UUID
    component_name: str
    quantity: Decimal
    unit: str
    component_cost: Decimal
    total_cost: Decimal


class ProductVariantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sku: str | None = Field(default=None, max_length=80)
    barcode: str | None = Field(default=None, max_length=80)
    attributes: dict[str, str] = Field(default_factory=dict)
    cost_price: Decimal | None = Field(default=None, ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)


class ProductVariantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sku: str | None = Field(default=None, max_length=80)
    barcode: str | None = Field(default=None, max_length=80)
    attributes: dict[str, str] | None = None
    cost_price: Decimal | None = Field(default=None, ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)
    active: bool | None = None


class ProductVariantOut(ProductVariantCreate):
    id: UUID
    company_id: UUID
    product_id: UUID
    active: bool

    model_config = ConfigDict(from_attributes=True)


class ProductPriceLevelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    price: Decimal = Field(ge=0)
    minimum_quantity: Decimal = Field(default=Decimal("1"), gt=0)


class ProductPriceLevelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    price: Decimal | None = Field(default=None, ge=0)
    minimum_quantity: Decimal | None = Field(default=None, gt=0)
    active: bool | None = None


class ProductPriceLevelOut(ProductPriceLevelCreate):
    id: UUID
    company_id: UUID
    product_id: UUID
    active: bool

    model_config = ConfigDict(from_attributes=True)


class ProductImportRow(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    sku: str | None = Field(default=None, max_length=80)
    barcode: str | None = Field(default=None, max_length=80)
    category_id: UUID | None = None
    product_type: Literal[
        "standard", "non_stock", "service", "composite", "bundle", "variable_weight"
    ] = "standard"
    unit: Literal["each", "kg", "g", "litre", "ml"] = "each"
    cost_price: Decimal | None = Field(default=None, ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)


class ProductImportRequest(BaseModel):
    company_id: UUID
    branch_id: UUID | None = None
    rows: list[ProductImportRow] = Field(min_length=1, max_length=1000)
