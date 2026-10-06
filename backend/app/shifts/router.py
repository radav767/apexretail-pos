from datetime import datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import AuthActor, get_auth_actor, require_path_permission
from app.db.session import get_db
from app.shifts.repository import ShiftRepository
from app.shifts.schema import ShiftClose, ShiftOpen, ShiftOut, ShiftPage
from app.shifts.service import ShiftService


router = APIRouter(prefix="/shifts", tags=["Cashier Shifts"])


def get_service(db=Depends(get_db)):
    return ShiftService(ShiftRepository(db))


@router.post("/open", response_model=ShiftOut)
async def open_shift(data: ShiftOpen, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.open(data, actor)


@router.get("/current", response_model=ShiftOut | None)
async def current_shift(service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.current(actor)


@router.post("/{shift_id}/close", response_model=ShiftOut)
async def close_shift(shift_id: UUID, data: ShiftClose, service: ShiftService = Depends(get_service), actor: AuthActor = Depends(get_auth_actor)):
    return await service.close(shift_id, data, actor)


@router.get("/company/{company_id}", response_model=ShiftPage)
async def shift_history(company_id: UUID, branch_id: UUID | None = None, employee_id: UUID | None = None, device_id: UUID | None = None, status: str | None = Query(default=None, pattern="^(open|closed)$"), start_at: datetime | None = None, end_at: datetime | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), service: ShiftService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("reports"))):
    items, total = await service.history(company_id, actor, branch_id=branch_id, employee_id=employee_id, device_id=device_id, status=status, start_at=start_at, end_at=end_at, limit=page_size, offset=(page-1)*page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total, "total_pages": ceil(total/page_size) if total else 0}
