from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.repository import DashboardRepository
from app.dashboard.schema import DashboardSummary
from app.dashboard.service import DashboardService
from app.db.session import get_db


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def get_service(db: AsyncSession = Depends(get_db)):
    return DashboardService(DashboardRepository(db))


@router.get(
    "/summary/{company_id}",
    response_model=DashboardSummary,
)
async def dashboard_summary(
    company_id: UUID,
    service: DashboardService = Depends(get_service),
):
    return await service.get_summary(company_id)
