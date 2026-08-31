from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    get_auth_actor,
    require_billable_body_company,
    require_billable_path_company,
)
from app.models import PosSession
from datetime import datetime, timezone
from app.db.session import get_db
from app.employees.repository import EmployeeRepository
from app.employees.schema import (
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    PinLoginOut,
    PinLoginRequest,
)
from app.employees.service import EmployeeService


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
    await db.commit()
    return {"ok": True}


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
):
    return await service.create(data)


@router.get(
    "/{company_id}",
    response_model=list[EmployeeOut],
)
async def list_employees(
    company_id: UUID,
    service: EmployeeService = Depends(get_service),
):
    return await service.list_employees(
        company_id,
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
):
    return await service.update(
        company_id,
        employee_id,
        data,
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
):
    return await service.delete(
        company_id,
        employee_id,
    )
