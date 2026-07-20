from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.inventory.branch_repository import (
    BranchInventoryRepository,
)
from app.inventory.branch_schema import (
    BranchInventoryOut,
    InventoryBranchOut,
)
from app.inventory.branch_service import (
    BranchInventoryService,
)


router = APIRouter(
    prefix="/inventory",
    tags=["Branch Inventory"],
)


def get_service(
    db: AsyncSession = Depends(get_db),
):
    return BranchInventoryService(
        BranchInventoryRepository(db)
    )


@router.get(
    "/branches/{company_id}",
    response_model=list[InventoryBranchOut],
)
async def list_inventory_branches(
    company_id: UUID,
    service: BranchInventoryService = Depends(get_service),
):
    return await service.branches(company_id)


@router.get(
    "/branch-overview/{company_id}",
    response_model=list[BranchInventoryOut],
)
async def branch_inventory_overview(
    company_id: UUID,
    branch_id: UUID | None = Query(default=None),
    service: BranchInventoryService = Depends(get_service),
):
    return await service.overview(
        company_id,
        branch_id,
    )
