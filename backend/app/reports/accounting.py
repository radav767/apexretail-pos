from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.dashboard.accounting import (
    REPORTING_TIMEZONE_NAME,
    unavailable_metric,
    utc_bounds,
)


MONEY_QUANTUM = Decimal("0.01")


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def known_money(value: Any, known: bool, *, reason: str, field: str):
    if not known:
        return unavailable_metric(reason=reason, missing_persistence=field)
    return {"available": True, "value": money(value), "reason": None, "missing_persistence": None}


def inventory_metrics(quantity: Any, selling_price: Any, cost_price: Any):
    qty = Decimal(str(quantity or 0))
    selling_known = selling_price is not None
    cost_known = cost_price is not None
    selling = qty * Decimal(str(selling_price)) if selling_known else None
    cost = qty * Decimal(str(cost_price)) if cost_known else None
    selling_metric = known_money(
        selling, selling_known,
        reason="Current selling price is unavailable.", field="products.selling_price",
    )
    cost_metric = known_money(
        cost, cost_known,
        reason="Recorded unit cost is unavailable.", field="products.cost_price",
    )
    both_known = selling_known and cost_known
    profit = selling - cost if both_known else None
    profit_metric = known_money(
        profit, both_known,
        reason="Projected gross profit requires both current selling price and recorded unit cost.",
        field="products.selling_price,products.cost_price",
    )
    if not both_known or selling == 0:
        margin = unavailable_metric(
            reason=("Margin requires available prices and a non-zero selling value."),
            missing_persistence="products.selling_price,products.cost_price",
        )
    else:
        margin = {
            "available": True,
            "value": ((profit / selling) * Decimal("100")).quantize(MONEY_QUANTUM),
            "reason": None, "missing_persistence": None,
        }
    return selling_metric, cost_metric, profit_metric, margin


__all__ = ["REPORTING_TIMEZONE_NAME", "inventory_metrics", "known_money", "money", "utc_bounds"]
