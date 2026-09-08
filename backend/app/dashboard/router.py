from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    ensure_company_access,
    get_auth_actor,
)
from app.dashboard.repository import DashboardRepository
from app.dashboard.schema import (
    DashboardPhase2Summary,
    DashboardSummary,
)
from app.dashboard.service import DashboardService
from app.db.session import get_db


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def get_service(db: AsyncSession = Depends(get_db)):
    return DashboardService(DashboardRepository(db))


async def require_dashboard_reports_access(
    company_id: UUID,
    actor: AuthActor = Depends(get_auth_actor),
) -> AuthActor:
    ensure_company_access(actor, company_id)
    if actor.actor_type == "user":
        return actor
    if actor.role in {"owner", "administrator"}:
        return actor
    if actor.permissions and actor.permissions.get("reports"):
        return actor
    raise HTTPException(403, "Permission denied")


@router.get(
    "/summary/{company_id}",
    response_model=DashboardSummary,
)
async def dashboard_summary(
    company_id: UUID,
    service: DashboardService = Depends(get_service),
):
    return await service.get_summary(company_id)


@router.get(
    "/summary-v2/{company_id}",
    response_model=DashboardPhase2Summary,
)
async def dashboard_summary_phase2(
    company_id: UUID,
    range_key: Literal[
        "today",
        "yesterday",
        "last_7_days",
        "last_month",
        "custom",
    ] = Query(default="today"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    shop_id: UUID | None = Query(default=None),
    service: DashboardService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_dashboard_reports_access
    ),
):
    return await service.get_phase2_summary(
        company_id,
        range_key=range_key,
        date_from=date_from,
        date_to=date_to,
        shop_id=shop_id,
    )
