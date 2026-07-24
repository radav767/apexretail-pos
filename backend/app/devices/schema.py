from uuid import UUID

from pydantic import BaseModel, Field


class DeviceRegister(BaseModel):
    company_id: UUID
    device_key: str = Field(min_length=1, max_length=255)
    name: str = Field(default="Web POS Device", min_length=1, max_length=120)
    platform: str = Field(default="web", max_length=50)
    app_version: str = Field(default="1.0.0", max_length=50)


class DeviceAssignmentUpdate(BaseModel):
    shop_id: UUID
    branch_id: UUID


class DeviceOut(BaseModel):
    id: UUID
    company_id: UUID
    shop_id: UUID | None
    branch_id: UUID | None

    shop_name: str | None
    branch_name: str | None

    name: str
    device_key: str
    platform: str | None
    app_version: str | None
    active: bool
