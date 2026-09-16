from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


EmployeeRole = Literal["owner", "administrator", "manager", "cashier"]


class EmployeeCreate(BaseModel):
    company_id: UUID
    shop_id: UUID
    branch_id: UUID

    name: str = Field(
        min_length=1,
        max_length=160,
    )

    email: str | None = Field(
        default=None,
        max_length=160,
    )

    phone: str | None = Field(
        default=None,
        max_length=60,
    )

    pin: str = Field(
        pattern=r"^\d{4}$",
    )

    role: EmployeeRole = "cashier"

    permissions: dict[str, bool] = Field(
        default_factory=dict,
    )


class EmployeeUpdate(BaseModel):
    shop_id: UUID | None = None
    branch_id: UUID | None = None

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
    )

    email: str | None = Field(
        default=None,
        max_length=160,
    )

    phone: str | None = Field(
        default=None,
        max_length=60,
    )

    pin: str | None = Field(
        default=None,
        pattern=r"^\d{4}$",
    )

    role: EmployeeRole | None = None

    permissions: dict[str, bool] | None = None

    active: bool | None = None


class EmployeeOut(BaseModel):
    id: UUID
    company_id: UUID
    shop_id: UUID
    branch_id: UUID

    shop_name: str
    branch_name: str

    name: str
    email: str | None
    phone: str | None
    role: str
    permissions: dict[str, bool]
    active: bool

    model_config = ConfigDict(
        from_attributes=True,
    )


class PinLoginRequest(BaseModel):
    company_id: UUID
    branch_id: UUID | None = None
    shop_id: UUID | None = None
    device_id: UUID | None = None
    device_key: str | None = Field(default=None, min_length=1, max_length=255)
    session_token: str | None = Field(default=None, min_length=1, max_length=512)
    takeover: bool = False

    pin: str = Field(
        pattern=r"^\d{4}$",
    )


class PinLoginOut(BaseModel):
    id: UUID
    company_id: UUID
    shop_id: UUID | None = None
    branch_id: UUID | None = None

    name: str
    role: str
    permissions: dict[str, bool]
    access_token: str
    device_id: UUID | None = None
    device_key: str | None = None
    assignment_revision: int | None = None
    selection_required: bool = False
    shops: list[dict] = Field(default_factory=list)
    terminals: list[dict] = Field(default_factory=list)
