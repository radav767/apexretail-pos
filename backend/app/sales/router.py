from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.sales.schema import SaleCreate, SaleOut
from app.sales.repository import SalesRepository
from app.sales.service import SalesService


router = APIRouter(prefix="/sales", tags=["Sales"])


def get_service(db: AsyncSession = Depends(get_db)):
    return SalesService(SalesRepository(db))


@router.post("", response_model=SaleOut)
async def create_sale(data: SaleCreate, service: SalesService = Depends(get_service)):
    return await service.create_sale(data)
