from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceRegister(BaseModel):
    company_id: UUID
    device_key: str = Field(min_length=1, max_length=255)
    name: str = Field(default="Web POS Device", min_length=1, max_length=120)
    platform: str = Field(default="web", max_length=50)
    app_version: str = Field(default="1.0.0", max_length=50)
    device_fingerprint: str | None = Field(default=None, max_length=255)


class DeviceActivationRequest(BaseModel):
    company_id: UUID
    device_id: UUID | None = None
    friendly_name: str = Field(min_length=1, max_length=120)
    pos_number: int | None = Field(default=None, ge=1, le=999999)
    shop_id: UUID
    branch_id: UUID


class DeviceActivationRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device: "DeviceOut"
    activation_code: str
    activation_code_expires_at: datetime


class DeviceActivationClaim(BaseModel):
    company_id: UUID
    activation_code: str = Field(min_length=6, max_length=32)
    device_key: str = Field(min_length=1, max_length=255)
    device_fingerprint: str = Field(min_length=1, max_length=255)
    name: str = Field(default="POS Device", min_length=1, max_length=120)
    platform: str = Field(default="android", max_length=50)
    app_version: str = Field(default="1.0.0", max_length=50)


class DeviceHeartbeat(BaseModel):
    company_id: UUID
    device_id: UUID | None = None
    device_key: str | None = Field(default=None, max_length=255)
    platform: str | None = Field(default=None, max_length=50)
    app_version: str | None = Field(default=None, max_length=50)


class DeviceUpdate(BaseModel):
    friendly_name: str | None = Field(default=None, max_length=120)
    pos_number: int | None = Field(default=None, ge=1, le=999999)
    shop_id: UUID | None = None
    branch_id: UUID | None = None
    status: Literal["active", "deactivated", "removed"] | None = None
    deactivation_reason: str | None = Field(default=None, max_length=500)


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    shop_id: UUID | None
    branch_id: UUID | None

    shop_name: str | None
    shop_address_line_1: str | None = None
    shop_address_line_2: str | None = None
    shop_city: str | None = None
    shop_state_province: str | None = None
    shop_country: str | None = None
    shop_phone: str | None = None
    shop_tax_vat_number: str | None = None
    branch_name: str | None

    name: str
    friendly_name: str | None = None
    pos_number: int | None = None
    device_key: str
    platform: str | None
    app_version: str | None
    last_seen_at: datetime | None = None
    last_seen_platform: str | None = None
    last_seen_app_version: str | None = None
    status: str
    claimed_at: datetime | None = None
    deactivated_at: datetime | None = None
    deactivation_reason: str | None = None
    removed_at: datetime | None = None
    pending_shop_id: UUID | None = None
    pending_branch_id: UUID | None = None
    active: bool


DeviceActivationRequestOut.model_rebuild()
