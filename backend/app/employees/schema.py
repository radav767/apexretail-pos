from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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

    role: str = Field(default="cashier", min_length=1, max_length=80)
    role_id: UUID | None = None
    device_restricted: bool = False
    device_ids: list[UUID] = Field(default_factory=list)

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

    role: str | None = Field(default=None, min_length=1, max_length=80)
    role_id: UUID | None = None
    device_restricted: bool | None = None
    device_ids: list[UUID] | None = None

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
    role_id: UUID | None = None
    role_name: str | None = None
    permissions: dict[str, bool]
    device_restricted: bool = False
    device_ids: list[UUID] = Field(default_factory=list)
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


class RoleCreate(BaseModel):
    company_id: UUID
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=240)
    permissions: dict[str, bool] = Field(default_factory=dict)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=240)
    permissions: dict[str, bool] | None = None
    active: bool | None = None


class RoleOut(BaseModel):
    id: UUID | None = None
    company_id: UUID | None = None
    name: str
    description: str | None = None
    permissions: dict[str, bool]
    active: bool = True
    system: bool = False


class ManagerAuthorizationCreate(BaseModel):
    company_id: UUID
    manager_pin: str = Field(pattern=r"^\d{4}$")
    action: str = Field(min_length=2, max_length=80)
    reason: str = Field(min_length=3, max_length=500)
    context: dict = Field(default_factory=dict)


class ManagerAuthorizationOut(BaseModel):
    authorization_token: str
    action: str
    approver_employee_id: UUID
    expires_at: datetime


class AuditEventOut(BaseModel):
    id: UUID
    actor_employee_id: UUID | None = None
    actor_user_id: UUID | None = None
    device_id: UUID | None = None
    actor_name: str | None = None
    action: str
    reason: str | None = None
    details: dict | None = None
    created_at: datetime
