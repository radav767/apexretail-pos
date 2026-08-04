from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.sale import Sale
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate, SaleOut
from app.sales.service import SalesService


router = APIRouter(
    prefix="/sales",
    tags=["Sales"],
)


def get_service(
    db: AsyncSession = Depends(get_db),
) -> SalesService:
    return SalesService(SalesRepository(db))


@router.post(
    "",
    response_model=SaleOut,
)
async def create_sale(
    data: SaleCreate,
    service: SalesService = Depends(get_service),
):
    return await service.create_sale(data)


# This specific route must remain above /{company_id}.
@router.get(
    "/history/{company_id}",
    response_model=list[SaleOut],
)
async def list_sales_history_by_date(
    company_id: UUID,
    sale_date: date = Query(...),
    branch_id: UUID | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """
    Return transactions for one selected Zimbabwe calendar date.
    """

    zimbabwe_timezone = timezone(timedelta(hours=2))

    local_start = datetime.combine(
        sale_date,
        time.min,
        tzinfo=zimbabwe_timezone,
    )

    local_end = local_start + timedelta(days=1)

    utc_start = local_start.astimezone(timezone.utc)
    utc_end = local_end.astimezone(timezone.utc)

    statement = select(Sale).where(
        Sale.company_id == company_id,
        Sale.created_at >= utc_start,
        Sale.created_at < utc_end,
    )

    if branch_id is not None:
        statement = statement.where(
            Sale.branch_id == branch_id,
        )

    statement = (
        statement
        .order_by(Sale.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(statement)

    return list(result.scalars().all())


@router.get(
    "/{company_id}",
    response_model=list[SaleOut],
)
async def list_sales(
    company_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    service: SalesService = Depends(get_service),
):
    return await service.list_sales(
        company_id,
        limit,
    )
