from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field
from app.sales.schema import SaleCreate


class ProfileInput(BaseModel):
    profile: Literal["retail", "restaurant", "bar", "hospitality", "pharmacy", "wholesale", "general"]
    tip_product_id: UUID | None = None
    service_product_id: UUID | None = None


class TableInput(BaseModel):
    branch_id: UUID
    name: str = Field(min_length=1, max_length=60)
    floor: str = Field(default="Main floor", min_length=1, max_length=60)
    seats: int = Field(default=4, ge=1, le=100)
    x: int = Field(default=0, ge=0, le=20)
    y: int = Field(default=0, ge=0, le=20)
    active: bool = True


class RoomInput(BaseModel):
    branch_id: UUID
    name: str = Field(min_length=1, max_length=60)
    active: bool = True


class GuestInput(BaseModel):
    room_id: UUID
    customer_id: UUID


class OrderInput(BaseModel):
    branch_id: UUID
    device_id: UUID
    request_id: UUID
    kind: Literal["restaurant", "room_service", "quotation"] = "restaurant"
    table_id: UUID | None = None
    guest_id: UUID | None = None
    customer_id: UUID | None = None
    waiter_id: UUID | None = None
    notes: str = Field(default="", max_length=500)


class VersionInput(BaseModel):
    version: int = Field(ge=1)


class OrderItemInput(VersionInput):
    product_id: UUID
    variant_id: UUID | None = None
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    notes: str = Field(default="", max_length=500)


class ItemUpdate(VersionInput):
    quantity: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    notes: str = Field(default="", max_length=500)


class MoveInput(VersionInput):
    table_id: UUID | None = None
    waiter_id: UUID | None = None


class SplitQuantity(BaseModel):
    item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class SplitInput(VersionInput):
    # Keep the existing whole-line client contract.
    item_ids: list[UUID] = Field(default_factory=list, max_length=200)
    quantities: list[SplitQuantity] = Field(default_factory=list, max_length=200)
    request_id: UUID


class MergeInput(VersionInput):
    source_id: UUID
    source_version: int = Field(ge=1)


class SettlementInput(VersionInput):
    payment: SaleCreate
    charge_to_room: bool = False


class BatchInput(BaseModel):
    branch_id: UUID
    product_id: UUID
    code: str = Field(min_length=1, max_length=80)
    expires_on: date
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class KitchenStateInput(BaseModel):
    status: Literal["preparing", "ready", "served", "acknowledged"]


class OfflineDraftInput(BaseModel):
    """Unpaid drafts only. No offline payment or kitchen acknowledgement."""
    request_id: UUID
    employee_id: UUID
    captured_at: datetime
    order: OrderInput
    items: list[OrderItemInput] = Field(min_length=1, max_length=200)


class OfflineEditInput(BaseModel):
    request_id: UUID
    employee_id: UUID
    device_id: UUID
    captured_at: datetime
    order_id: UUID
    item_id: UUID
    change: ItemUpdate


class BatchStockInput(BatchInput):
    request_id: UUID
    operation: Literal["receive", "supplier_return", "dispose"]
    reason: str = Field(min_length=3, max_length=160)
    received_unit: str | None = Field(default=None, max_length=20)
