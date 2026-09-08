from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_settings import CompanySetting
from app.models.product import Product
from app.models.sale import Sale
from app.models.shop import Shop


REPORTING_TIMEZONE = ZoneInfo("Africa/Harare")
REPORTING_TIMEZONE_NAME = "Africa/Harare"


def quantize_money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def available_metric(value: Any) -> dict[str, Any]:
    return {
        "available": True,
        "value": quantize_money(value),
        "reason": None,
        "missing_persistence": None,
    }


def unavailable_metric(
    *,
    reason: str,
    missing_persistence: str,
) -> dict[str, Any]:
    return {
        "available": False,
        "value": None,
        "reason": reason,
        "missing_persistence": missing_persistence,
    }


def build_phase2_metrics(
    *,
    gross_sales: Any,
    refunds: Any,
    cost_of_sales: Any,
    discounts: Any = None,
    discounts_known: bool = False,
) -> dict[str, dict[str, Any]]:
    gross_sales_amount = quantize_money(gross_sales)
    refunds_amount = quantize_money(refunds)
    net_sales_amount = gross_sales_amount - refunds_amount
    cost_of_sales_amount = quantize_money(cost_of_sales)
    discounts_amount = quantize_money(discounts)

    discount_metric = (
        available_metric(discounts_amount)
        if discounts_known
        else unavailable_metric(
            reason=(
                "Discount reporting is unavailable for this range because "
                "one or more sales lack an explicit discount snapshot."
            ),
            missing_persistence="sales.discount_amount",
        )
    )

    return {
        "gross_sales": available_metric(gross_sales_amount),
        "net_sales": available_metric(net_sales_amount),
        "cost_of_sales": available_metric(cost_of_sales_amount),
        "gross_profit": available_metric(
            net_sales_amount - cost_of_sales_amount
        ),
        "discounts": discount_metric,
        "refunds": available_metric(refunds_amount),
    }


def resolve_phase2_date_range(
    range_key: str,
    *,
    date_from: date | None,
    date_to: date | None,
    today: date | None = None,
) -> tuple[date, date]:
    current_day = today or datetime.now(REPORTING_TIMEZONE).date()

    if range_key == "today":
        return current_day, current_day

    if range_key == "yesterday":
        previous_day = current_day - timedelta(days=1)
        return previous_day, previous_day

    if range_key == "last_7_days":
        return current_day - timedelta(days=6), current_day

    if range_key == "last_month":
        first_day_of_current_month = current_day.replace(day=1)
        last_day_of_previous_month = (
            first_day_of_current_month - timedelta(days=1)
        )
        first_day_of_previous_month = (
            last_day_of_previous_month.replace(day=1)
        )
        return (
            first_day_of_previous_month,
            last_day_of_previous_month,
        )

    if range_key == "custom":
        if date_from is None or date_to is None:
            raise HTTPException(
                status_code=400,
                detail="Custom date range requires date_from and date_to",
            )
        if date_to < date_from:
            raise HTTPException(
                status_code=400,
                detail="End date cannot be before start date",
            )
        if (date_to - date_from).days >= 366:
            raise HTTPException(
                status_code=400,
                detail="Report range cannot exceed 366 days",
            )
        return date_from, date_to

    raise HTTPException(
        status_code=400,
        detail="Unsupported dashboard range",
    )


class DashboardRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_summary(self, company_id):
        now = datetime.now(timezone.utc)
        start_today = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        end_today = start_today + timedelta(days=1)

        sales_result = await self.db.execute(
            select(
                func.coalesce(func.sum(Sale.total_amount), 0),
                func.count(Sale.id),
            ).where(
                Sale.company_id == company_id,
                Sale.status == "completed",
                Sale.created_at >= start_today,
                Sale.created_at < end_today,
            )
        )
        today_sales, today_transactions = sales_result.one()

        products_result = await self.db.execute(
            select(func.count(Product.id)).where(
                Product.company_id == company_id,
                Product.active == True,
                Product.deleted == False,
            )
        )
        total_products = products_result.scalar_one()

        low_stock_result = await self.db.execute(
            select(func.count(Product.id)).where(
                Product.company_id == company_id,
                Product.active == True,
                Product.deleted == False,
                Product.stock_qty <= Product.reorder_level,
            )
        )
        low_stock_products = low_stock_result.scalar_one()

        stock_value_result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(Product.stock_qty * Product.cost_price),
                    0,
                )
            ).where(
                Product.company_id == company_id,
                Product.active == True,
                Product.deleted == False,
            )
        )
        stock_value = stock_value_result.scalar_one()

        return {
            "today_sales": today_sales,
            "today_transactions": today_transactions,
            "total_products": total_products,
            "low_stock_products": low_stock_products,
            "stock_value": stock_value,
        }

    async def get_phase2_summary(
        self,
        company_id: UUID,
        *,
        range_key: str,
        date_from: date | None = None,
        date_to: date | None = None,
        shop_id: UUID | None = None,
    ):
        start_date, end_date = resolve_phase2_date_range(
            range_key,
            date_from=date_from,
            date_to=date_to,
        )

        start_at = datetime.combine(
            start_date,
            time.min,
            tzinfo=REPORTING_TIMEZONE,
        ).astimezone(timezone.utc)
        end_at = datetime.combine(
            end_date + timedelta(days=1),
            time.min,
            tzinfo=REPORTING_TIMEZONE,
        ).astimezone(timezone.utc)

        params: dict[str, Any] = {
            "company_id": company_id,
            "start_at": start_at,
            "end_at": end_at,
        }

        transaction_filters = """
            s.company_id = :company_id
            AND s.created_at >= :start_at
            AND s.created_at < :end_at
            AND (
                (
                    s.original_sale_id IS NULL
                    AND LOWER(s.status) IN (
                        'completed',
                        'partially_refunded',
                        'refunded'
                    )
                )
                OR (
                    s.original_sale_id IS NOT NULL
                    AND LOWER(s.status) = 'refunded'
                )
            )
        """

        if shop_id is not None:
            transaction_filters += "\nAND s.shop_id = :shop_id"
            params["shop_id"] = shop_id

        shops_result = await self.db.execute(
            select(Shop).where(
                Shop.company_id == company_id,
                Shop.deleted.is_(False),
            ).order_by(Shop.created_at.asc())
        )
        shops = shops_result.scalars().all()

        if shop_id is not None and shop_id not in {
            shop.id for shop in shops
        }:
            raise HTTPException(
                status_code=404,
                detail="Shop not found for this company",
            )

        sales_result = await self.db.execute(
            text(
                f"""
                SELECT
                    COALESCE(SUM(
                        CASE
                            WHEN s.original_sale_id IS NULL
                            THEN s.total_amount
                            ELSE 0
                        END
                    ), 0) AS gross_sales,
                    COALESCE(-SUM(
                        CASE
                            WHEN s.original_sale_id IS NOT NULL
                            THEN s.total_amount
                            ELSE 0
                        END
                    ), 0) AS refunds,
                    COALESCE(SUM(
                        CASE
                            WHEN s.original_sale_id IS NULL
                            THEN s.discount_amount
                            ELSE 0
                        END
                    ), 0) AS discounts,
                    COUNT(*) FILTER (
                        WHERE s.original_sale_id IS NULL
                    ) AS original_sale_count,
                    COUNT(s.discount_amount) FILTER (
                        WHERE s.original_sale_id IS NULL
                    ) AS known_discount_count
                FROM sales AS s
                WHERE {transaction_filters}
                """
            ),
            params,
        )
        sales_summary = sales_result.mappings().first() or {}

        costs_result = await self.db.execute(
            text(
                f"""
                SELECT
                    COALESCE(SUM(si.line_cost), 0) AS cost_of_sales
                FROM sale_items AS si
                INNER JOIN sales AS s
                    ON s.id = si.sale_id
                WHERE {transaction_filters}
                """
            ),
            params,
        )
        costs_summary = costs_result.mappings().first() or {}

        settings_result = await self.db.execute(
            select(CompanySetting).where(
                CompanySetting.company_id == company_id,
                CompanySetting.deleted.is_(False),
            )
        )
        setting = settings_result.scalar_one_or_none()

        return {
            "range_key": range_key,
            "date_from": start_date,
            "date_to": end_date,
            "reporting_timezone": REPORTING_TIMEZONE_NAME,
            "shop_id": shop_id,
            "currency_symbol": (
                setting.currency_symbol if setting else "$"
            ),
            "decimal_places": (
                int(setting.decimal_places)
                if setting is not None
                else 2
            ),
            "shops": [
                {
                    "id": shop.id,
                    "name": shop.name,
                }
                for shop in shops
            ],
            "metrics": build_phase2_metrics(
                gross_sales=sales_summary.get("gross_sales"),
                refunds=sales_summary.get("refunds"),
                cost_of_sales=costs_summary.get("cost_of_sales"),
                discounts=sales_summary.get("discounts"),
                discounts_known=(
                    sales_summary.get("original_sale_count", 0)
                    == sales_summary.get("known_discount_count", 0)
                ),
            ),
        }
