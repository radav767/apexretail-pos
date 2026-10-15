from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    get_optional_auth_actor,
    require_billable_body_company,
)
from app.db.session import get_db
from app.models.sale import Sale
from app.sales.repository import SalesRepository
from app.sales.schema import RefundCreate, SaleCreate, SaleOut, SaleReceiptOut
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
    actor: AuthActor | None = Depends(
        get_optional_auth_actor
    ),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    return await service.create_sale(data, actor=actor)


@router.post(
    "/refunds",
    response_model=SaleOut,
)
async def create_refund(
    data: RefundCreate,
    service: SalesService = Depends(get_service),
    actor: AuthActor | None = Depends(
        get_optional_auth_actor
    ),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    return await service.create_refund(
        data,
        actor=actor,
    )


# This route lets a POS reconcile an ambiguous transport timeout before it
# permits another submission.  It must remain above /{company_id}.
@router.get(
    "/by-client-id/{company_id}/{client_sale_id}",
    response_model=SaleOut,
)
async def sale_by_client_id(
    company_id: UUID,
    client_sale_id: UUID,
    service: SalesService = Depends(get_service),
    actor: AuthActor | None = Depends(get_optional_auth_actor),
):
    return await service.by_client_sale_id(
        company_id,
        client_sale_id,
        actor,
    )


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
    actor: AuthActor | None = Depends(get_optional_auth_actor),
):
    """
    Return transactions for one selected Zimbabwe calendar date.
    """

    if actor is not None:
        if actor.company_id != company_id:
            raise HTTPException(403, "Forbidden")
        if (
            actor.actor_type == "employee"
            and (
                not actor.permissions
                or not (
                    actor.permissions.get("sales")
                    or actor.permissions.get("refunds")
                )
            )
        ):
            raise HTTPException(403, "Permission denied")

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
    "/receipt/{company_id}/{sale_id}",
    response_model=SaleReceiptOut,
)
async def get_sale_receipt(
    company_id: UUID,
    sale_id: UUID,
    mark_reprint: bool = Query(default=True),
    service: SalesService = Depends(get_service),
    actor: AuthActor | None = Depends(
        get_optional_auth_actor
    ),
):
    if mark_reprint:
        return await service.get_sale_receipt(
            company_id,
            sale_id,
            actor=actor,
        )

    return await service.get_sale_receipt(
        company_id,
        sale_id,
        actor=actor,
        mark_reprint=False,
    )


@router.get(
    "/{company_id}",
    response_model=list[SaleOut],
)
async def list_sales(
    company_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    service: SalesService = Depends(get_service),
    actor: AuthActor | None = Depends(get_optional_auth_actor),
):
    if actor is not None:
        if actor.company_id != company_id:
            raise HTTPException(403, "Forbidden")
        if (
            actor.actor_type == "employee"
            and (
                not actor.permissions
                or not (
                    actor.permissions.get("sales")
                    or actor.permissions.get("refunds")
                )
            )
        ):
            raise HTTPException(403, "Permission denied")
    return await service.list_sales(
        company_id,
        limit,
    )
