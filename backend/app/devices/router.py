from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.devices.repository import DeviceRepository
from app.devices.schema import (
    DeviceAssignmentUpdate,
    DeviceOut,
    DeviceRegister,
)
from app.devices.service import DeviceService


router = APIRouter(
    prefix="/devices",
    tags=["Devices"],
)


def get_service(
    db: AsyncSession = Depends(get_db),
):
    return DeviceService(DeviceRepository(db))


@router.post(
    "/register",
    response_model=DeviceOut,
)
async def register_device(
    data: DeviceRegister,
    service: DeviceService = Depends(get_service),
):
    return await service.register(data)


@router.get(
    "/{company_id}",
    response_model=list[DeviceOut],
)
async def list_devices(
    company_id: UUID,
    service: DeviceService = Depends(get_service),
):
    return await service.list_devices(company_id)


@router.patch(
    "/{company_id}/{device_id}/assignment",
    response_model=DeviceOut,
)
async def assign_device(
    company_id: UUID,
    device_id: UUID,
    data: DeviceAssignmentUpdate,
    service: DeviceService = Depends(get_service),
):
    return await service.assign(
        company_id,
        device_id,
        data,
    )
