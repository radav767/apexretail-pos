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
    DeviceAssignmentRequest,
    DeviceDecommissionRequest,
    DeviceDeleteRequest,
    DeviceDeleteOut,
    DeviceDeletionImpactOut,
    DeviceBranchCreate,
)
from app.devices.service import DeviceService
from app.inventory.branch_repository import BranchInventoryRepository
from app.inventory.branch_service import BranchInventoryService
from app.inventory.branch_schema import InventoryBranchOut, BranchCreate


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
        require_body_permission("manage_devices")
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


@router.post("/branches", response_model=InventoryBranchOut)
async def create_device_branch(
    data: DeviceBranchCreate,
    db: AsyncSession = Depends(get_db),
    actor: AuthActor = Depends(require_body_permission("manage_devices")),
    _entitlement: None = Depends(require_billable_body_company),
):
    return await BranchInventoryService(BranchInventoryRepository(db)).create_branch(
        BranchCreate(company_id=data.company_id, shop_id=data.shop_id, name=data.name),
        actor=actor,
    )


@router.get("/branches/{company_id}", response_model=list[InventoryBranchOut])
async def list_device_branches(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    _actor: AuthActor = Depends(require_path_permission("manage_devices")),
):
    return await BranchInventoryService(BranchInventoryRepository(db)).branches(company_id)


@router.get(
    "/{company_id}",
    response_model=list[DeviceOut],
)
async def list_devices(
    company_id: UUID,
    service: DeviceService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_path_permission("manage_devices")
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
async def update_device(
    company_id: UUID,
    device_id: UUID,
    data: DeviceUpdate,
    service: DeviceService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_path_permission("manage_devices")
    ),
):
    return await service.update(
        company_id,
        device_id,
        data,
        actor=_actor,
    )


@router.post(
    "/{company_id}/{device_id}/reassign",
    response_model=DeviceOut,
)
async def reassign_device(
    company_id: UUID,
    device_id: UUID,
    data: DeviceAssignmentRequest,
    service: DeviceService = Depends(get_service),
    actor: AuthActor = Depends(require_path_permission("manage_devices")),
):
    return await service.reassign(company_id, device_id, data, actor)


@router.post(
    "/{company_id}/{device_id}/decommission",
    response_model=DeviceOut,
)
async def decommission_device(
    company_id: UUID,
    device_id: UUID,
    data: DeviceDecommissionRequest,
    service: DeviceService = Depends(get_service),
    actor: AuthActor = Depends(require_path_permission("manage_devices")),
):
    return await service.decommission(company_id, device_id, data, actor)


@router.get(
    "/{company_id}/{device_id}/deletion-impact",
    response_model=DeviceDeletionImpactOut,
)
async def device_deletion_impact(
    company_id: UUID,
    device_id: UUID,
    service: DeviceService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("manage_devices")),
):
    return await service.deletion_impact(company_id, device_id)


@router.delete(
    "/{company_id}/{device_id}",
    response_model=DeviceDeleteOut,
)
async def delete_device_permanently(
    company_id: UUID,
    device_id: UUID,
    data: DeviceDeleteRequest,
    service: DeviceService = Depends(get_service),
    actor: AuthActor = Depends(require_path_permission("manage_devices")),
):
    return await service.delete_permanently(company_id, device_id, data, actor)
