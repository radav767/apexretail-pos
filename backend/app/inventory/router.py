from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.inventory.repository import InventoryRepository
from app.inventory.schema import (
    GRNCreate,
    InventoryMovementOut,
    InventoryProductOut,
    InventoryValuationOut,
    StockAdjustmentCreate,
    StockTakeCreate,
)
from app.inventory.service import InventoryService


router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"],
)


def get_service(
    db: AsyncSession = Depends(get_db),
):
    return InventoryService(InventoryRepository(db))


@router.get(
    "/overview/{company_id}",
    response_model=list[InventoryProductOut],
)
async def inventory_overview(
    company_id: UUID,
    service: InventoryService = Depends(get_service),
):
    return await service.overview(company_id)


@router.get(
    "/valuation/{company_id}",
    response_model=InventoryValuationOut,
)
async def inventory_valuation(
    company_id: UUID,
    service: InventoryService = Depends(get_service),
):
    return await service.valuation(company_id)


@router.get(
    "/history/{company_id}",
    response_model=list[InventoryMovementOut],
)
async def inventory_history(
    company_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    service: InventoryService = Depends(get_service),
):
    return await service.history(company_id, limit)


@router.post(
    "/grn",
    response_model=InventoryMovementOut,
)
async def receive_stock(
    data: GRNCreate,
    service: InventoryService = Depends(get_service),
):
    return await service.receive_stock(data)


@router.post(
    "/adjustments",
    response_model=InventoryMovementOut,
)
async def adjust_stock(
    data: StockAdjustmentCreate,
    service: InventoryService = Depends(get_service),
):
    return await service.adjust_stock(data)


@router.post(
    "/stock-take",
    response_model=list[InventoryMovementOut],
)
async def stock_take(
    data: StockTakeCreate,
    service: InventoryService = Depends(get_service),
):
    return await service.stock_take(data)
