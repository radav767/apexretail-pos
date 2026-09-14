from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException


REPORTING_TIMEZONE = ZoneInfo("Africa/Harare")
REPORTING_TIMEZONE_NAME = "Africa/Harare"
RANGE_KEYS = {"today", "yesterday", "last_7_days", "last_month", "custom"}
GRANULARITIES = {"day", "week", "month"}


def quantize_money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def quantize_quantity(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.001"))


def available_metric(value: Any) -> dict[str, Any]:
    return {
        "available": True,
        "value": quantize_money(value),
        "reason": None,
        "missing_persistence": None,
    }


def unavailable_metric(*, reason: str, missing_persistence: str) -> dict[str, Any]:
    return {
        "available": False,
        "value": None,
        "reason": reason,
        "missing_persistence": missing_persistence,
    }


def discount_metric(value: Any, *, original_count: int, known_count: int):
    if original_count == known_count:
        return available_metric(value)
    return unavailable_metric(
        reason=(
            "Discount reporting is unavailable for this range because one or "
            "more sales lack an explicit discount snapshot."
        ),
        missing_persistence="sales.discount_amount",
    )


def build_metrics(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "gross_sales": available_metric(row.get("gross_sales")),
        "net_sales": available_metric(row.get("net_sales")),
        "cost_of_sales": available_metric(row.get("cost_of_sales")),
        "gross_profit": available_metric(row.get("gross_profit")),
        "discounts": discount_metric(
            row.get("discounts"),
            original_count=int(row.get("original_sale_count") or 0),
            known_count=int(row.get("known_discount_count") or 0),
        ),
        "refunds": available_metric(row.get("refunds")),
    }


def resolve_date_range(
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
        first_current = current_day.replace(day=1)
        last_previous = first_current - timedelta(days=1)
        return last_previous.replace(day=1), last_previous
    if range_key == "custom":
        if date_from is None or date_to is None:
            raise HTTPException(400, "Custom date range requires date_from and date_to")
        if date_to < date_from:
            raise HTTPException(400, "End date cannot be before start date")
        if (date_to - date_from).days >= 366:
            raise HTTPException(400, "Report range cannot exceed 366 days")
        return date_from, date_to
    raise HTTPException(400, "Unsupported dashboard range")


def preceding_period(start_date: date, end_date: date) -> tuple[date, date]:
    length = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    return previous_end - timedelta(days=length - 1), previous_end


def utc_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start_at = datetime.combine(start_date, time.min, tzinfo=REPORTING_TIMEZONE)
    end_at = datetime.combine(
        end_date + timedelta(days=1), time.min, tzinfo=REPORTING_TIMEZONE
    )
    return start_at.astimezone(timezone.utc), end_at.astimezone(timezone.utc)


def percentage_change(current: Any, previous: Any) -> dict[str, Any]:
    current_amount = quantize_money(current)
    previous_amount = quantize_money(previous)
    amount = current_amount - previous_amount
    percentage = None
    if previous_amount != 0:
        percentage = ((amount / abs(previous_amount)) * 100).quantize(
            Decimal("0.01")
        )
    return {"available": True, "amount": amount, "percentage": percentage}


def transaction_population_cte(filters: str) -> str:
    """Canonical transaction accounting population used by every report path."""
    return f"""
        WITH eligible_sales AS (
            SELECT s.* FROM sales AS s WHERE {filters}
        ), item_costs AS (
            SELECT si.sale_id, COALESCE(SUM(si.line_cost), 0) AS cost_of_sales
            FROM sale_items AS si
            INNER JOIN eligible_sales AS eligible ON eligible.id = si.sale_id
            GROUP BY si.sale_id
        ), transaction_population AS (
            SELECT
                s.id, s.company_id, s.shop_id, s.employee_id,
                s.receipt_number, s.cashier_name, s.shop_name_snapshot,
                s.payment_method,
                s.refund_method, s.refund_reason, s.status,
                s.original_sale_id, s.discount_amount, s.created_at,
                CASE WHEN s.original_sale_id IS NULL
                    THEN s.total_amount ELSE 0 END AS gross_sales,
                CASE WHEN s.original_sale_id IS NOT NULL
                    THEN -s.total_amount ELSE 0 END AS refunds,
                s.total_amount AS net_sales,
                COALESCE(item_costs.cost_of_sales, 0) AS cost_of_sales,
                s.total_amount - COALESCE(item_costs.cost_of_sales, 0)
                    AS gross_profit,
                CASE WHEN s.original_sale_id IS NULL
                    THEN s.discount_amount ELSE 0 END AS discounts,
                CASE WHEN s.original_sale_id IS NULL THEN 1 ELSE 0 END
                    AS original_sale_count,
                CASE WHEN s.original_sale_id IS NULL
                          AND s.discount_amount IS NOT NULL THEN 1 ELSE 0 END
                    AS known_discount_count
            FROM eligible_sales AS s
            LEFT JOIN item_costs ON item_costs.sale_id = s.id
        )
    """


def transaction_filters(prefix: str = "") -> str:
    return f"""
        s.company_id = :{prefix}company_id
        AND s.created_at >= :{prefix}start_at
        AND s.created_at < :{prefix}end_at
        AND (
            (s.original_sale_id IS NULL AND LOWER(s.status) IN
                ('completed', 'partially_refunded', 'refunded'))
            OR
            (s.original_sale_id IS NOT NULL AND LOWER(s.status) = 'refunded')
        )
        AND (CAST(:{prefix}shop_id AS uuid) IS NULL
             OR s.shop_id = CAST(:{prefix}shop_id AS uuid))
    """


AGGREGATE_SELECT = """
    SELECT
        COALESCE(SUM(gross_sales), 0) AS gross_sales,
        COALESCE(SUM(refunds), 0) AS refunds,
        COALESCE(SUM(net_sales), 0) AS net_sales,
        COALESCE(SUM(cost_of_sales), 0) AS cost_of_sales,
        COALESCE(SUM(gross_profit), 0) AS gross_profit,
        COALESCE(SUM(discounts), 0) AS discounts,
        COALESCE(SUM(original_sale_count), 0) AS original_sale_count,
        COALESCE(SUM(known_discount_count), 0) AS known_discount_count,
        COUNT(*) AS transaction_count
    FROM transaction_population
"""
