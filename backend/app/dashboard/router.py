from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    ensure_company_access,
    get_auth_actor,
)
from app.dashboard.repository import DashboardRepository
from app.dashboard.schema import (
    DashboardPhase2Summary,
    DashboardDrilldown,
    DashboardPhase3Summary,
    DashboardSummary,
)
from app.dashboard.service import DashboardService
from app.db.session import get_db
from app.employees.permissions import has_permission


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def get_service(db: AsyncSession = Depends(get_db)):
    return DashboardService(DashboardRepository(db))


async def require_dashboard_reports_access(
    company_id: UUID,
    actor: AuthActor = Depends(get_auth_actor),
) -> AuthActor:
    ensure_company_access(actor, company_id)
    if actor.role in {"owner", "administrator"}:
        return actor
    if has_permission(actor.permissions, "profits_view"):
        raise HTTPException(403, "Use branch-scoped financial reports for this employee")
    raise HTTPException(403, "Permission denied")


@router.get(
    "/summary/{company_id}",
    response_model=DashboardSummary,
)
async def dashboard_summary(
    company_id: UUID,
    service: DashboardService = Depends(get_service),
    _actor: AuthActor = Depends(get_auth_actor),
):
    ensure_company_access(_actor, company_id)
    if _actor.actor_type == "employee" and _actor.role not in {"owner", "administrator"}:
        if not has_permission(_actor.permissions, "revenue_view"):
            raise HTTPException(403, "Revenue permission denied")
        if _actor.employee is None:
            raise HTTPException(403, "Branch access denied")
        result = await service.get_summary(company_id, branch_id=_actor.employee.branch_id)
        if not has_permission(_actor.permissions, "inventory_valuation_view"):
            result = {**result, "stock_value": None}
        return result
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


@router.get("/analytics-v3/{company_id}", response_model=DashboardPhase3Summary)
async def dashboard_analytics_phase3(
    company_id: UUID,
    range_key: Literal["today", "yesterday", "last_7_days", "last_month", "custom"] = Query(default="today"),
    granularity: Literal["day", "week", "month"] = Query(default="day"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    shop_id: UUID | None = Query(default=None),
    top_limit: int = Query(default=10, ge=1, le=50),
    service: DashboardService = Depends(get_service),
    _actor: AuthActor = Depends(require_dashboard_reports_access),
):
    return await service.get_phase3_summary(
        company_id, range_key=range_key, granularity=granularity,
        date_from=date_from, date_to=date_to, shop_id=shop_id,
        top_limit=top_limit,
    )


@router.get("/analytics-v3/{company_id}/sales", response_model=DashboardDrilldown)
async def dashboard_analytics_drilldown(
    company_id: UUID,
    range_key: Literal["today", "yesterday", "last_7_days", "last_month", "custom"] = Query(default="today"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    shop_id: UUID | None = Query(default=None),
    metric: Literal["gross_sales", "refunds", "net_sales", "cost_of_sales", "gross_profit", "discounts"] = Query(default="net_sales"),
    dimension: Literal[
        "product", "category", "payment", "shop", "cashier",
        "discount", "refund",
    ] | None = Query(default=None),
    dimension_key: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: DashboardService = Depends(get_service),
    _actor: AuthActor = Depends(require_dashboard_reports_access),
):
    return await service.get_drilldown(
        company_id, range_key=range_key, date_from=date_from,
        date_to=date_to, shop_id=shop_id, metric=metric,
        dimension=dimension, dimension_key=dimension_key,
        limit=limit, offset=offset,
    )


@router.get("/analytics-v3/{company_id}/export.csv")
async def dashboard_analytics_export(
    company_id: UUID,
    section: Literal[
        "trends", "top_products", "top_categories", "payment_methods",
        "shop_breakdown", "cashier_breakdown", "discount_breakdown",
        "refund_breakdown",
    ] = Query(default="trends"),
    range_key: Literal["today", "yesterday", "last_7_days", "last_month", "custom"] = Query(default="today"),
    granularity: Literal["day", "week", "month"] = Query(default="day"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    shop_id: UUID | None = Query(default=None),
    top_limit: int = Query(default=10, ge=1, le=50),
    service: DashboardService = Depends(get_service),
    _actor: AuthActor = Depends(require_dashboard_reports_access),
):
    content = await service.export_phase3(
        company_id, section=section, range_key=range_key,
        granularity=granularity, date_from=date_from, date_to=date_to,
        shop_id=shop_id, top_limit=top_limit,
    )
    return Response(
        content=content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="dashboard-{section}.csv"'},
    )


@router.get("/analytics-v3/{company_id}/sales.csv")
async def dashboard_analytics_drilldown_export(
    company_id: UUID,
    range_key: Literal["today", "yesterday", "last_7_days", "last_month", "custom"] = Query(default="today"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    shop_id: UUID | None = Query(default=None),
    metric: Literal["gross_sales", "refunds", "net_sales", "cost_of_sales", "gross_profit", "discounts"] = Query(default="net_sales"),
    dimension: Literal[
        "product", "category", "payment", "shop", "cashier",
        "discount", "refund",
    ] | None = Query(default=None),
    dimension_key: str | None = Query(default=None, max_length=255),
    service: DashboardService = Depends(get_service),
    _actor: AuthActor = Depends(require_dashboard_reports_access),
):
    content = await service.export_drilldown(
        company_id, range_key=range_key, date_from=date_from,
        date_to=date_to, shop_id=shop_id, metric=metric,
        dimension=dimension, dimension_key=dimension_key,
    )
    return Response(
        content=content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="dashboard-sales.csv"'},
    )
