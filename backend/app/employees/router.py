from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth.dependencies import (
    AuthActor,
    get_auth_actor,
    require_billable_body_company,
    require_billable_path_company,
    require_body_permission,
    require_path_permission,
)
from app.models import AuditEvent, Device, PosSession
from datetime import datetime, timezone
from app.db.session import get_db
from app.employees.repository import EmployeeRepository
from app.employees.schema import (
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    PinLoginOut,
    PinLoginRequest,
    AuditEventOut,
    ManagerAuthorizationCreate,
    ManagerAuthorizationOut,
    RoleCreate,
    RoleOut,
    RoleUpdate,
)
from app.employees.service import EmployeeService
from app.employees.admin_service import EmployeeAdminService
from app.employees.manager_approval import issue_manager_authorization


router = APIRouter(
    prefix="/employees",
    tags=["Employees"],
)


def get_service(
    db: AsyncSession = Depends(get_db),
):
    return EmployeeService(
        EmployeeRepository(db),
    )


@router.post(
    "/pin-login",
    response_model=PinLoginOut,
)
async def employee_pin_login(
    data: PinLoginRequest,
    service: EmployeeService = Depends(get_service),
):
    return await service.pin_login(data)

@router.post("/session/logout")
async def employee_session_logout(actor: AuthActor = Depends(get_auth_actor), db: AsyncSession = Depends(get_db)):
    if actor.actor_type != "employee":
        return {"ok": True}
    rows = await db.execute(__import__('sqlalchemy').select(PosSession).where(PosSession.employee_id == actor.employee.id, PosSession.revoked_at.is_(None)))
    now = datetime.now(timezone.utc)
    for session in rows.scalars().all():
        session.revoked_at = now; session.revoke_reason = "logout"
    db.add(AuditEvent(company_id=actor.company_id, actor_employee_id=actor.employee.id, device_id=actor.pos_session.device_id if actor.pos_session else None, action="employee_logout"))
    await db.commit()
    return {"ok": True}


@router.get("/permissions/catalog")
async def permission_catalog(
    _actor: AuthActor = Depends(get_auth_actor), db: AsyncSession = Depends(get_db),
):
    return await EmployeeAdminService(db).permission_catalog()


@router.get("/roles/{company_id}", response_model=list[RoleOut])
async def list_roles(
    company_id: UUID, db: AsyncSession = Depends(get_db),
    _actor: AuthActor = Depends(require_path_permission("employees_manage")),
):
    return await EmployeeAdminService(db).list_roles(company_id)


@router.get("/devices/{company_id}")
async def employee_device_options(
    company_id: UUID, db: AsyncSession = Depends(get_db),
    actor: AuthActor = Depends(require_path_permission("employees_manage")),
):
    # Employee administrators need names for assignment, never device keys or
    # activation secrets. Full device management remains separately guarded.
    query = select(Device.id, Device.name, Device.friendly_name, Device.pos_number).where(
        Device.company_id == company_id, Device.active == True,
        Device.deleted == False, Device.removed_at.is_(None),
    )
    if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
        query = query.where(Device.branch_id == actor.employee.branch_id)
    return [dict(row) for row in (await db.execute(query)).mappings().all()]


@router.post("/roles", response_model=RoleOut)
async def create_role(
    data: RoleCreate, db: AsyncSession = Depends(get_db),
    actor: AuthActor = Depends(require_body_permission("roles_manage")),
):
    return await EmployeeAdminService(db).create_role(data, actor)


@router.patch("/roles/{company_id}/{role_id}", response_model=RoleOut)
async def update_role(
    company_id: UUID, role_id: UUID, data: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: AuthActor = Depends(require_path_permission("roles_manage")),
):
    return await EmployeeAdminService(db).update_role(company_id, role_id, data, actor)


@router.get("/activity/{company_id}", response_model=list[AuditEventOut])
async def employee_activity(
    company_id: UUID, action: str | None = None, employee_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=500), db: AsyncSession = Depends(get_db),
    _actor: AuthActor = Depends(require_path_permission("audit_logs_view")),
):
    return await EmployeeAdminService(db).audit_log(company_id, action, employee_id, limit, actor=_actor)


@router.post("/manager-authorizations", response_model=ManagerAuthorizationOut)
async def create_manager_authorization(
    data: ManagerAuthorizationCreate, db: AsyncSession = Depends(get_db),
    actor: AuthActor = Depends(get_auth_actor),
):
    return await issue_manager_authorization(db, actor, data)


@router.post(
    "",
    response_model=EmployeeOut,
)
async def create_employee(
    data: EmployeeCreate,
    service: EmployeeService = Depends(get_service),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
    actor: AuthActor = Depends(require_body_permission("employees_manage")),
):
    return await service.create(data, actor)


@router.get(
    "/{company_id}",
    response_model=list[EmployeeOut],
)
async def list_employees(
    company_id: UUID,
    service: EmployeeService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("employees_manage")),
):
    return await service.list_employees(
        company_id,
        actor=_actor,
    )


@router.patch(
    "/{company_id}/{employee_id}",
    response_model=EmployeeOut,
)
async def update_employee(
    company_id: UUID,
    employee_id: UUID,
    data: EmployeeUpdate,
    service: EmployeeService = Depends(get_service),
    _entitlement: None = Depends(
        require_billable_path_company
    ),
    actor: AuthActor = Depends(require_path_permission("employees_manage")),
):
    return await service.update(
        company_id,
        employee_id,
        data,
        actor,
    )


@router.delete(
    "/{company_id}/{employee_id}",
)
async def delete_employee(
    company_id: UUID,
    employee_id: UUID,
    service: EmployeeService = Depends(get_service),
    _entitlement: None = Depends(
        require_billable_path_company
    ),
    actor: AuthActor = Depends(require_path_permission("employees_manage")),
):
    return await service.delete(
        company_id,
        employee_id,
        actor,
    )
