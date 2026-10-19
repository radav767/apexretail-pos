from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import AuthActor, require_path_permission
from app.reports.repository import ReportsRepository
from app.reports.schema import SalesHistoryQuery, SalesHistoryResponse, InventoryValuationResponse, FinancialSummaryResponse
from app.reports.service import ReportsService
from app.financial_access import enforce_actor_branch


router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)

HARARE_TZ = ZoneInfo("Africa/Harare")


def get_reports_service(db: AsyncSession = Depends(get_db)):
    return ReportsService(ReportsRepository(db))


def scoped_branch(actor, branch_id):
    if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
        branch_id = branch_id or actor.employee.branch_id
        enforce_actor_branch(actor, branch_id)
    return branch_id


@router.get("/financial-summary/{company_id}", response_model=FinancialSummaryResponse)
async def financial_summary(
    company_id: UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    branch_id: UUID | None = None,
    shop_id: UUID | None = None,
    service: ReportsService = Depends(get_reports_service),
    actor: AuthActor = Depends(require_path_permission("profits_view")),
):
    if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
        if branch_id is not None:
            enforce_actor_branch(actor, branch_id)
        branch_id = actor.employee.branch_id
    return await service.financial_summary(
        company_id, date_from=date_from, date_to=date_to,
        branch_id=branch_id, shop_id=shop_id,
    )


@router.get("/sales-history/{company_id}", response_model=SalesHistoryResponse)
async def sales_history_v4(
    company_id: UUID,
    query: SalesHistoryQuery = Depends(),
    service: ReportsService = Depends(get_reports_service),
    _actor: AuthActor = Depends(require_path_permission("profits_view")),
):
    query.branch_id = scoped_branch(_actor, query.branch_id)
    return await service.sales_history(company_id, query)


@router.get("/sales-history/{company_id}/export.csv")
async def sales_history_v4_csv(
    company_id: UUID,
    query: SalesHistoryQuery = Depends(),
    service: ReportsService = Depends(get_reports_service),
    _actor: AuthActor = Depends(require_path_permission("profits_view")),
):
    query.branch_id = scoped_branch(_actor, query.branch_id)
    content = await service.sales_history_csv(company_id, query)
    return Response(content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sales-history.csv"})


@router.get("/inventory-valuation/{company_id}", response_model=InventoryValuationResponse)
async def inventory_valuation_v4(
    company_id: UUID, branch_id: UUID | None = None, category_id: UUID | None = None,
    product_id: UUID | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    service: ReportsService = Depends(get_reports_service),
    _actor: AuthActor = Depends(require_path_permission("inventory_valuation")),
):
    branch_id = scoped_branch(_actor, branch_id)
    return await service.inventory_valuation(company_id, branch_id=branch_id, category_id=category_id, product_id=product_id, limit=limit, offset=offset)


@router.get("/inventory-valuation/{company_id}/export.csv")
async def inventory_valuation_v4_csv(
    company_id: UUID, branch_id: UUID | None = None, category_id: UUID | None = None, product_id: UUID | None = None,
    service: ReportsService = Depends(get_reports_service),
    _actor: AuthActor = Depends(require_path_permission("inventory_valuation")),
):
    branch_id = scoped_branch(_actor, branch_id)
    content = await service.inventory_csv(company_id, branch_id=branch_id, category_id=category_id, product_id=product_id, limit=100, offset=0)
    return Response(content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=inventory-valuation.csv"})


def money(value: Any) -> float:
    return float(
        Decimal(str(value or 0)).quantize(Decimal("0.01"))
    )


def quantity(value: Any) -> float:
    return float(
        Decimal(str(value or 0)).quantize(Decimal("0.001"))
    )


@router.get("/sales/{company_id}")
async def sales_report(
    company_id: UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    branch_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _actor: AuthActor = Depends(require_path_permission("reports")),
):
    branch_id = scoped_branch(_actor, branch_id)
    today = datetime.now(HARARE_TZ).date()

    start_date = date_from or today
    end_date = date_to or start_date

    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="End date cannot be before start date",
        )

    if (end_date - start_date).days > 366:
        raise HTTPException(
            status_code=400,
            detail="Report range cannot exceed 366 days",
        )

    start_at = datetime.combine(
        start_date,
        time.min,
        tzinfo=HARARE_TZ,
    ).astimezone(timezone.utc)

    end_at = datetime.combine(
        end_date + timedelta(days=1),
        time.min,
        tzinfo=HARARE_TZ,
    ).astimezone(timezone.utc)

    params: dict[str, Any] = {
        "company_id": company_id,
        "start_at": start_at,
        "end_at": end_at,
    }

    filters = """
        s.company_id = :company_id
        AND LOWER(s.status) = 'completed'
        AND s.created_at >= :start_at
        AND s.created_at < :end_at
    """

    if branch_id is not None:
        filters += "\nAND s.branch_id = :branch_id"
        params["branch_id"] = branch_id

    async def get_rows(sql: str):
        result = await db.execute(text(sql), params)
        return result.mappings().all()

    async def get_row(sql: str):
        result = await db.execute(text(sql), params)
        return result.mappings().first()

    summary = await get_row(
        f"""
        SELECT
            COALESCE(SUM(s.total_amount), 0) AS gross_sales,
            COUNT(*) AS transactions,
            COALESCE(AVG(s.total_amount), 0) AS average_sale
        FROM sales AS s
        WHERE {filters}
        """
    )

    cost_summary = await get_row(
        f"""
        SELECT
            COALESCE(SUM(si.line_cost), 0) AS cost_of_sales,
            COALESCE(SUM(si.quantity), 0) AS items_sold
        FROM sale_items AS si
        INNER JOIN sales AS s
            ON s.id = si.sale_id
        WHERE {filters}
        """
    )

    payment_rows = await get_rows(
        f"""
        SELECT
            LOWER(s.payment_method) AS payment_method,
            COUNT(*) AS transactions,
            COALESCE(SUM(s.total_amount), 0) AS sales
        FROM sales AS s
        WHERE {filters}
        GROUP BY LOWER(s.payment_method)
        ORDER BY sales DESC
        """
    )

    branch_sales_rows = await get_rows(
        f"""
        SELECT
            s.branch_id,
            COALESCE(b.name, 'Unassigned') AS branch_name,
            COUNT(*) AS transactions,
            COALESCE(SUM(s.total_amount), 0) AS sales
        FROM sales AS s
        LEFT JOIN branches AS b
            ON b.id = s.branch_id
        WHERE {filters}
        GROUP BY
            s.branch_id,
            b.name
        ORDER BY sales DESC
        """
    )

    branch_cost_rows = await get_rows(
        f"""
        SELECT
            s.branch_id,
            COALESCE(SUM(si.line_cost), 0) AS cost
        FROM sale_items AS si
        INNER JOIN sales AS s
            ON s.id = si.sale_id
        WHERE {filters}
        GROUP BY s.branch_id
        """
    )

    cashier_sales_rows = await get_rows(
        f"""
        SELECT
            s.employee_id,
            COALESCE(
                NULLIF(s.cashier_name, ''),
                e.name,
                'Unassigned'
            ) AS cashier_name,
            COUNT(*) AS transactions,
            COALESCE(SUM(s.total_amount), 0) AS sales
        FROM sales AS s
        LEFT JOIN employees AS e
            ON e.id = s.employee_id
        WHERE {filters}
        GROUP BY
            s.employee_id,
            COALESCE(
                NULLIF(s.cashier_name, ''),
                e.name,
                'Unassigned'
            )
        ORDER BY sales DESC
        """
    )

    cashier_cost_rows = await get_rows(
        f"""
        SELECT
            s.employee_id,
            COALESCE(SUM(si.line_cost), 0) AS cost
        FROM sale_items AS si
        INNER JOIN sales AS s
            ON s.id = si.sale_id
        WHERE {filters}
        GROUP BY s.employee_id
        """
    )

    product_rows = await get_rows(
        f"""
        SELECT
            si.product_id,
            si.product_name,
            COALESCE(SUM(si.quantity), 0) AS quantity,
            COALESCE(SUM(si.line_total), 0) AS sales,
            COALESCE(SUM(si.line_cost), 0) AS cost
        FROM sale_items AS si
        INNER JOIN sales AS s
            ON s.id = si.sale_id
        WHERE {filters}
        GROUP BY
            si.product_id,
            si.product_name
        ORDER BY sales DESC
        LIMIT 100
        """
    )

    gross_sales = money(summary["gross_sales"])
    cost_of_sales = money(cost_summary["cost_of_sales"])

    branch_costs = {
        str(row["branch_id"] or ""): money(row["cost"])
        for row in branch_cost_rows
    }

    cashier_costs = {
        str(row["employee_id"] or ""): money(row["cost"])
        for row in cashier_cost_rows
    }

    return {
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "branch_id": str(branch_id) if branch_id else None,
        "summary": {
            "gross_sales": gross_sales,
            "cost_of_sales": cost_of_sales,
            "gross_profit": money(
                Decimal(str(gross_sales))
                - Decimal(str(cost_of_sales))
            ),
            "transactions": int(summary["transactions"] or 0),
            "average_sale": money(summary["average_sale"]),
            "items_sold": quantity(cost_summary["items_sold"]),
        },
        "payment_methods": [
            {
                "payment_method": row["payment_method"] or "unknown",
                "transactions": int(row["transactions"] or 0),
                "sales": money(row["sales"]),
            }
            for row in payment_rows
        ],
        "branches": [
            {
                "branch_id": str(row["branch_id"] or ""),
                "branch_name": row["branch_name"],
                "transactions": int(row["transactions"] or 0),
                "sales": money(row["sales"]),
                "cost": branch_costs.get(
                    str(row["branch_id"] or ""),
                    0,
                ),
                "profit": money(
                    Decimal(str(row["sales"] or 0))
                    - Decimal(
                        str(
                            branch_costs.get(
                                str(row["branch_id"] or ""),
                                0,
                            )
                        )
                    )
                ),
            }
            for row in branch_sales_rows
        ],
        "cashiers": [
            {
                "employee_id": str(row["employee_id"] or ""),
                "cashier_name": row["cashier_name"],
                "transactions": int(row["transactions"] or 0),
                "sales": money(row["sales"]),
                "cost": cashier_costs.get(
                    str(row["employee_id"] or ""),
                    0,
                ),
                "profit": money(
                    Decimal(str(row["sales"] or 0))
                    - Decimal(
                        str(
                            cashier_costs.get(
                                str(row["employee_id"] or ""),
                                0,
                            )
                        )
                    )
                ),
            }
            for row in cashier_sales_rows
        ],
        "products": [
            {
                "product_id": str(row["product_id"]),
                "product_name": row["product_name"],
                "quantity": quantity(row["quantity"]),
                "sales": money(row["sales"]),
                "cost": money(row["cost"]),
                "profit": money(
                    Decimal(str(row["sales"] or 0))
                    - Decimal(str(row["cost"] or 0))
                ),
            }
            for row in product_rows
        ],
    }
