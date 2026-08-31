from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    require_billable_body_company,
    require_body_permission,
)
from app.db.session import get_db
from app.inventory.schema import InventoryMovementOut
from app.inventory.transfer_repository import TransferRepository
from app.inventory.transfer_schema import TransferCreate
from app.inventory.transfer_service import TransferService


router = APIRouter(
    prefix="/inventory",
    tags=["Stock Transfers"],
)


def get_service(
    db: AsyncSession = Depends(get_db),
):
    return TransferService(TransferRepository(db))


@router.post(
    "/transfers",
    response_model=list[InventoryMovementOut],
)
async def create_stock_transfer(
    data: TransferCreate,
    service: TransferService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_body_permission("manage_inventory")
    ),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    return await service.transfer(data)
