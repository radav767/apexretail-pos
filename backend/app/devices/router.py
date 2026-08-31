from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    require_billable_body_company,
    require_billable_path_company,
    require_body_permission,
    require_body_owner,
    require_path_permission,
)
from app.db.session import get_db
from app.devices.repository import DeviceRepository
from app.devices.schema import (
    DeviceActivationClaim,
    DeviceActivationRequest,
    DeviceActivationRequestOut,
    DeviceHeartbeat,
    DeviceOut,
    DeviceRegister,
    DeviceUpdate,
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
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    return await service.register(data)


@router.post(
    "/activate/request",
    response_model=DeviceActivationRequestOut,
)
async def request_device_activation(
    data: DeviceActivationRequest,
    service: DeviceService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_body_permission("settings")
    ),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    return await service.request_activation(data)


@router.post(
    "/activate/claim",
    response_model=DeviceOut,
)
async def claim_device_activation(
    data: DeviceActivationClaim,
    service: DeviceService = Depends(get_service),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    return await service.claim_activation(data)


@router.post(
    "/heartbeat",
    response_model=DeviceOut,
)
async def device_heartbeat(
    data: DeviceHeartbeat,
    service: DeviceService = Depends(get_service),
):
    return await service.heartbeat(data)


@router.get(
    "/{company_id}",
    response_model=list[DeviceOut],
)
async def list_devices(
    company_id: UUID,
    service: DeviceService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_path_permission("settings")
    ),
    _entitlement: None = Depends(
        require_billable_path_company
    ),
):
    return await service.list_devices(company_id)


@router.patch(
    "/{company_id}/{device_id}",
    response_model=DeviceOut,
)
@router.patch(
    "/{company_id}/{device_id}/assignment",
    response_model=DeviceOut,
)
async def update_device(
    company_id: UUID,
    device_id: UUID,
    data: DeviceUpdate,
    service: DeviceService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_path_permission("settings")
    ),
):
    return await service.update(
        company_id,
        device_id,
        data,
        actor=_actor,
    )
