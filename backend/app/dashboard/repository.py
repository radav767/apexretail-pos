from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.accounting import (
    AGGREGATE_SELECT,
    REPORTING_TIMEZONE_NAME,
    available_metric,
    build_metrics,
    percentage_change,
    preceding_period,
    quantize_money,
    quantize_quantity,
    resolve_date_range,
    transaction_filters,
    transaction_population_cte,
    unavailable_metric,
    utc_bounds,
)
from app.models.company_settings import CompanySetting
from app.models.product import Product
from app.models.sale import Sale
from app.models.shop import Shop


def build_phase2_metrics(
    *,
    gross_sales: Any,
    refunds: Any,
    cost_of_sales: Any,
    discounts: Any = None,
    discounts_known: bool = False,
) -> dict[str, dict[str, Any]]:
    return build_metrics({
        "gross_sales": gross_sales,
        "refunds": refunds,
        "net_sales": quantize_money(gross_sales) - quantize_money(refunds),
        "cost_of_sales": cost_of_sales,
        "gross_profit": (
            quantize_money(gross_sales)
            - quantize_money(refunds)
            - quantize_money(cost_of_sales)
        ),
        "discounts": discounts,
        "original_sale_count": 1,
        "known_discount_count": 1 if discounts_known else 0,
    })


def resolve_phase2_date_range(
    range_key: str,
    *,
    date_from: date | None,
    date_to: date | None,
    today: date | None = None,
) -> tuple[date, date]:
    return resolve_date_range(
        range_key, date_from=date_from, date_to=date_to, today=today
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

        shops, setting = await self._context(company_id, shop_id)
        summary = await self._aggregate(company_id, start_date, end_date, shop_id)
        return self._base_response(
            range_key, start_date, end_date, shop_id, shops, setting, summary
        )

    async def _context(self, company_id: UUID, shop_id: UUID | None):
        shops_result = await self.db.execute(
            select(Shop).where(
                Shop.company_id == company_id, Shop.deleted.is_(False)
            ).order_by(Shop.created_at.asc())
        )
        shops = shops_result.scalars().all()
        if shop_id is not None and shop_id not in {shop.id for shop in shops}:
            raise HTTPException(404, "Shop not found for this company")
        settings_result = await self.db.execute(
            select(CompanySetting).where(
                CompanySetting.company_id == company_id,
                CompanySetting.deleted.is_(False),
            )
        )
        return shops, settings_result.scalar_one_or_none()

    @staticmethod
    def _params(company_id, start_date, end_date, shop_id):
        start_at, end_at = utc_bounds(start_date, end_date)
        return {
            "company_id": company_id,
            "start_at": start_at,
            "end_at": end_at,
            "shop_id": shop_id,
            "report_date_from": start_date,
            "report_date_to": end_date,
        }

    async def _aggregate(self, company_id, start_date, end_date, shop_id):
        sql = transaction_population_cte(transaction_filters()) + AGGREGATE_SELECT
        result = await self.db.execute(
            text(sql), self._params(company_id, start_date, end_date, shop_id)
        )
        return dict(result.mappings().first() or {})

    @staticmethod
    def _base_response(
        range_key, start_date, end_date, shop_id, shops, setting, summary
    ):
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
                gross_sales=summary.get("gross_sales"),
                refunds=summary.get("refunds"),
                cost_of_sales=summary.get("cost_of_sales"),
                discounts=summary.get("discounts"),
                discounts_known=(
                    summary.get("original_sale_count", 0)
                    == summary.get("known_discount_count", 0)
                ),
            ),
        }

    async def get_phase3_summary(
        self, company_id: UUID, *, range_key: str, granularity: str,
        date_from: date | None = None, date_to: date | None = None,
        shop_id: UUID | None = None, top_limit: int = 10,
    ):
        start_date, end_date = resolve_date_range(
            range_key, date_from=date_from, date_to=date_to
        )
        shops, setting = await self._context(company_id, shop_id)
        current = await self._aggregate(company_id, start_date, end_date, shop_id)
        previous_from, previous_to = preceding_period(start_date, end_date)
        previous = await self._aggregate(
            company_id, previous_from, previous_to, shop_id
        )
        params = self._params(company_id, start_date, end_date, shop_id)
        response = self._base_response(
            range_key, start_date, end_date, shop_id, shops, setting, current
        )
        response.update({
            "granularity": granularity,
            "comparison": {
                "date_from": previous_from,
                "date_to": previous_to,
                "metrics": {
                    key: percentage_change(current.get(key), previous.get(key))
                    for key in (
                        "gross_sales", "net_sales", "cost_of_sales",
                        "gross_profit", "discounts", "refunds",
                    )
                },
            },
            "trends": await self._trends(params, granularity),
            "top_products": await self._ranked(params, "product", top_limit),
            "top_categories": await self._ranked(params, "category", top_limit),
            "payment_methods": await self._breakdown(params, "payment"),
            "shop_breakdown": await self._breakdown(params, "shop"),
            "cashier_breakdown": await self._breakdown(params, "cashier"),
            "discount_breakdown": await self._discount_breakdown(params),
            "refund_breakdown": await self._refund_breakdown(params),
        })
        discounts_comparable = (
            int(current.get("original_sale_count") or 0)
            == int(current.get("known_discount_count") or 0)
            and int(previous.get("original_sale_count") or 0)
            == int(previous.get("known_discount_count") or 0)
        )
        if not discounts_comparable:
            response["comparison"]["metrics"]["discounts"] = {
                "available": False, "amount": None, "percentage": None,
                "reason": response["metrics"]["discounts"]["reason"],
            }
        return response

    async def _trends(self, params, granularity):
        bucket = {"day": "day", "week": "week", "month": "month"}[granularity]
        interval = {"day": "1 day", "week": "1 week", "month": "1 month"}[granularity]
        cte = transaction_population_cte(transaction_filters())
        result = await self.db.execute(text(cte + f"""
            , bucketed AS (
                SELECT date_trunc('{bucket}', created_at AT TIME ZONE
                           '{REPORTING_TIMEZONE_NAME}')::date AS bucket_start,
                    SUM(gross_sales) AS gross_sales, SUM(refunds) AS refunds,
                    SUM(net_sales) AS net_sales, SUM(cost_of_sales) AS cost_of_sales,
                    SUM(gross_profit) AS gross_profit, SUM(discounts) AS discounts,
                    SUM(original_sale_count) AS original_sale_count,
                    SUM(known_discount_count) AS known_discount_count
                FROM transaction_population GROUP BY bucket_start
            ), buckets AS (
                SELECT generate_series(
                    date_trunc('{bucket}', CAST(:report_date_from AS date)),
                    date_trunc('{bucket}', CAST(:report_date_to AS date)),
                    interval '{interval}'
                )::date AS bucket_start
            )
            SELECT buckets.bucket_start AS period_start,
                COALESCE(gross_sales, 0) AS gross_sales,
                COALESCE(refunds, 0) AS refunds,
                COALESCE(net_sales, 0) AS net_sales,
                COALESCE(cost_of_sales, 0) AS cost_of_sales,
                COALESCE(gross_profit, 0) AS gross_profit,
                COALESCE(discounts, 0) AS discounts,
                COALESCE(original_sale_count, 0) AS original_sale_count,
                COALESCE(known_discount_count, 0) AS known_discount_count
            FROM buckets LEFT JOIN bucketed USING (bucket_start)
            ORDER BY buckets.bucket_start
        """), params)
        rows = result.mappings().all()
        points = []
        for raw in rows:
            row = dict(raw)
            bucket_start = row["period_start"]
            if granularity == "day":
                bucket_end = bucket_start
            elif granularity == "week":
                bucket_end = bucket_start + timedelta(days=6)
            else:
                next_month = (bucket_start.replace(day=28) + timedelta(days=4)).replace(day=1)
                bucket_end = next_month - timedelta(days=1)
            points.append({
                "period_start": max(bucket_start, params["report_date_from"]),
                "period_end": min(bucket_end, params["report_date_to"]),
                "metrics": build_metrics(row),
            })
        return points

    async def _ranked(self, params, kind, limit):
        cte = transaction_population_cte(transaction_filters())
        if kind == "product":
            identity = "si.product_id"
            name = "MAX(si.product_name)"
            joins = ""
        else:
            identity = "c.id"
            name = "COALESCE(MAX(c.name), 'Uncategorised')"
            joins = "LEFT JOIN products p ON p.id = si.product_id LEFT JOIN categories c ON c.id = p.category_id AND c.company_id = :company_id"
        result = await self.db.execute(text(cte + f"""
            SELECT {identity} AS id, {name} AS name,
                COALESCE(SUM(si.line_total), 0) AS revenue,
                COALESCE(SUM(si.quantity), 0) AS quantity,
                COALESCE(SUM(si.line_total - si.line_cost), 0) AS gross_profit
            FROM transaction_population tp
            JOIN sale_items si ON si.sale_id = tp.id {joins}
            GROUP BY {identity}
            ORDER BY revenue DESC, name ASC LIMIT :top_limit
        """), {**params, "top_limit": limit})
        return [{
            "id": row["id"], "name": row["name"],
            "revenue": quantize_money(row["revenue"]),
            "quantity": quantize_quantity(row["quantity"]),
            "gross_profit": quantize_money(row["gross_profit"]),
        } for row in result.mappings().all()]

    async def _breakdown(self, params, kind):
        fields = {
            "payment": ("COALESCE(tp.payment_method, 'unknown')", "MAX(COALESCE(tp.payment_method, 'Unknown'))", ""),
            "shop": ("COALESCE(tp.shop_id::text, 'unassigned')", "COALESCE(MAX(tp.shop_name_snapshot), MAX(sh.name), 'Unassigned shop')", "LEFT JOIN shops sh ON sh.id = tp.shop_id AND sh.company_id = :company_id"),
            "cashier": ("COALESCE(tp.employee_id::text, tp.cashier_name, 'unassigned')", "COALESCE(MAX(tp.cashier_name), MAX(e.name), 'Unassigned cashier')", "LEFT JOIN employees e ON e.id = tp.employee_id AND e.company_id = :company_id"),
        }
        key, name, join = fields[kind]
        cte = transaction_population_cte(transaction_filters())
        result = await self.db.execute(text(cte + f"""
            SELECT {key} AS key, {name} AS name, COUNT(*) AS transactions,
                SUM(gross_sales) AS gross_sales, SUM(refunds) AS refunds,
                SUM(net_sales) AS net_sales, SUM(gross_profit) AS gross_profit,
                SUM(discounts) AS discounts,
                SUM(original_sale_count) AS original_sale_count,
                SUM(known_discount_count) AS known_discount_count
            FROM transaction_population tp {join}
            GROUP BY {key} ORDER BY net_sales DESC, name ASC
        """), params)
        return [self._breakdown_row(dict(row)) for row in result.mappings().all()]

    @staticmethod
    def _breakdown_row(row):
        return {
            "key": str(row["key"]), "name": row["name"],
            "transactions": int(row.get("transactions") or 0),
            "gross_sales": quantize_money(row.get("gross_sales")),
            "refunds": quantize_money(row.get("refunds")),
            "net_sales": quantize_money(row.get("net_sales")),
            "gross_profit": quantize_money(row.get("gross_profit")),
            "discounts": (
                available_metric(row.get("discounts"))
                if int(row.get("original_sale_count") or 0)
                   == int(row.get("known_discount_count") or 0)
                else unavailable_metric(
                    reason="One or more sales in this group lack a discount snapshot.",
                    missing_persistence="sales.discount_amount",
                )
            ),
        }

    async def _discount_breakdown(self, params):
        cte = transaction_population_cte(transaction_filters())
        result = await self.db.execute(text(cte + """
            SELECT CASE
                WHEN discount_amount IS NULL THEN 'unavailable'
                WHEN discount_amount > 0 THEN 'discounted'
                ELSE 'no_discount' END AS key,
                CASE WHEN discount_amount IS NULL THEN 'Unavailable'
                     WHEN discount_amount > 0 THEN 'Discounted sales'
                     ELSE 'No discount' END AS name,
                COUNT(*) AS transactions, SUM(gross_sales) AS gross_sales,
                SUM(refunds) AS refunds, SUM(net_sales) AS net_sales,
                SUM(gross_profit) AS gross_profit, SUM(discounts) AS discounts,
                SUM(original_sale_count) AS original_sale_count,
                SUM(known_discount_count) AS known_discount_count
            FROM transaction_population WHERE original_sale_id IS NULL
            GROUP BY key, name ORDER BY key
        """), params)
        return [self._breakdown_row(dict(row)) for row in result.mappings().all()]

    async def _refund_breakdown(self, params):
        cte = transaction_population_cte(transaction_filters())
        result = await self.db.execute(text(cte + """
            SELECT COALESCE(refund_method, 'unspecified') AS key,
                COALESCE(refund_method, 'Unspecified refund method') AS name,
                COUNT(*) AS transactions, 0 AS gross_sales,
                SUM(refunds) AS refunds, SUM(net_sales) AS net_sales,
                SUM(gross_profit) AS gross_profit, 0 AS discounts,
                0 AS original_sale_count, 0 AS known_discount_count
            FROM transaction_population WHERE original_sale_id IS NOT NULL
            GROUP BY key, name ORDER BY refunds DESC, name ASC
        """), params)
        return [self._breakdown_row(dict(row)) for row in result.mappings().all()]

    async def get_drilldown(
        self, company_id, *, range_key, date_from=None, date_to=None,
        shop_id=None, metric="net_sales", limit=50, offset=0,
    ):
        start_date, end_date = resolve_date_range(
            range_key, date_from=date_from, date_to=date_to
        )
        shops, _setting = await self._context(company_id, shop_id)
        params = self._params(company_id, start_date, end_date, shop_id)
        conditions = {
            "gross_sales": "tp.original_sale_id IS NULL",
            "refunds": "tp.original_sale_id IS NOT NULL",
            "net_sales": "TRUE", "cost_of_sales": "TRUE", "gross_profit": "TRUE",
            "discounts": "tp.original_sale_id IS NULL",
        }
        condition = conditions[metric]
        cte = transaction_population_cte(transaction_filters())
        count_result = await self.db.execute(
            text(cte + f"SELECT COUNT(*) FROM transaction_population tp WHERE {condition}"), params
        )
        total = int(count_result.scalar_one())
        result = await self.db.execute(text(cte + f"""
            SELECT tp.*, COALESCE(tp.shop_name_snapshot, sh.name, 'Unassigned shop') AS shop_name
            FROM transaction_population tp
            LEFT JOIN shops sh ON sh.id = tp.shop_id AND sh.company_id = :company_id
            WHERE {condition} ORDER BY tp.created_at DESC, tp.id DESC
            LIMIT :limit OFFSET :offset
        """), {**params, "limit": limit, "offset": offset})
        rows = []
        for raw in result.mappings().all():
            row = dict(raw)
            rows.append({
                **{key: row[key] for key in (
                    "id", "receipt_number", "created_at", "shop_id",
                    "shop_name", "payment_method", "status", "original_sale_id",
                )},
                "cashier_name": row.get("cashier_name") or "Unassigned cashier",
                **{key: quantize_money(row.get(key)) for key in (
                    "gross_sales", "refunds", "net_sales", "cost_of_sales", "gross_profit",
                )},
                "discounts": (
                    available_metric(row.get("discounts"))
                    if row.get("discount_amount") is not None
                       or row.get("original_sale_id") is not None
                    else unavailable_metric(
                        reason="This sale has no discount snapshot.",
                        missing_persistence="sales.discount_amount",
                    )
                ),
            })
        return {"total": total, "limit": limit, "offset": offset, "rows": rows}
