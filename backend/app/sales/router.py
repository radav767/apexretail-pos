from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate, SaleOut
from app.sales.service import SalesService


router = APIRouter(prefix="/sales", tags=["Sales"])


def get_service(db: AsyncSession = Depends(get_db)):
    return SalesService(SalesRepository(db))


@router.post("", response_model=SaleOut)
async def create_sale(
    data: SaleCreate,
    service: SalesService = Depends(get_service),
):
    return await service.create_sale(data)


@router.get("/{company_id}", response_model=list[SaleOut])
async def list_sales(
    company_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    service: SalesService = Depends(get_service),
):
    return await service.list_sales(company_id, limit)
