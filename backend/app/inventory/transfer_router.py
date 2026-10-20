from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    require_billable_body_company,
    require_body_permission,
    get_auth_actor,
    require_permission,
)
from app.db.session import get_db
from app.inventory.schema import InventoryMovementOut
from app.inventory.transfer_repository import TransferRepository
from app.inventory.transfer_schema import TransferCreate
from app.inventory.transfer_service import TransferService
from app.financial_access import enforce_actor_branch
from app.products.router import can_view_product_cost


router = APIRouter(
    prefix="/inventory",
    tags=["Stock Transfers"],
)


def get_service(
    db: AsyncSession = Depends(get_db),
):
    return TransferService(TransferRepository(db))


@router.get("/transfers/capabilities")
async def transfer_capabilities(actor: AuthActor = Depends(get_auth_actor)):
    await require_permission("inventory_transfer")(actor)
    return {"idempotency":"audit-v1"}


@router.post(
    "/transfers",
    response_model=list[InventoryMovementOut],
)
async def create_stock_transfer(
    data: TransferCreate,
    service: TransferService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_body_permission("inventory_transfer")
    ),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    enforce_actor_branch(_actor, data.source_branch_id)
    rows = await service.transfer(data, actor=_actor) if isinstance(service, TransferService) else await service.transfer(data)
    if not can_view_product_cost(_actor):
        return [InventoryMovementOut.model_validate(row).model_copy(update={"unit_cost":None}) for row in rows]
    return rows
