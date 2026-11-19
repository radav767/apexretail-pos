"""Decimal-only snapshot allocation; never read current catalog tax or prices."""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from fastapi import HTTPException

CENT = Decimal('0.01')


def allocate(total, weights):
    """Largest remainder, stable input order; exact sum in base minor units."""
    cents = int((Decimal(total) / CENT).to_integral_value(rounding=ROUND_HALF_UP))
    denominator = sum(weights, Decimal(0))
    if cents == 0: return [Decimal(0) for _ in weights]
    if denominator <= 0: raise HTTPException(409, 'Tax allocation requires review')
    exact = [Decimal(cents) * value / denominator for value in weights]
    units = [int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in exact]
    for index in sorted(range(len(weights)), key=lambda i: (-(exact[i]-units[i]), i))[:cents-sum(units)]:
        units[index] += 1
    return [Decimal(value)*CENT for value in units]


def reconcile_sale_tax(items, tax_total, inclusive):
    weights = []
    for item in items:
        rate = Decimal(item.tax_rate_snapshot or 0) / 100
        amount = Decimal(item.line_total)
        weights.append(amount - amount/(1+rate) if inclusive and rate else amount*rate)
    for item, tax in zip(items, allocate(tax_total, weights)):
        item.tax_amount = tax


def reverse_component(original, previous, cumulative, quantity):
    target = (Decimal(original or 0)*cumulative/quantity).quantize(CENT, rounding=ROUND_HALF_UP)
    result = target - previous
    if result < 0 or target > Decimal(original or 0):
        raise HTTPException(409, 'Historical refund allocation requires review')
    return result


def refund_plan(sale, items, previous, requested):
    if Decimal(sale.tax_amount or 0) and any(item.tax_amount is None for item in items.values()):
        raise HTTPException(409, 'Historical item tax snapshots require review')
    plan = {}
    for request in requested:
        item = items.get(request.sale_item_id)
        if item is None: raise HTTPException(400, 'Refund item not found in original sale')
        old = previous[request.sale_item_id]
        returned = sum((Decimal(row.quantity) for row in old), Decimal(0))
        quantity = Decimal(item.quantity)
        if returned + request.quantity > quantity:
            raise HTTPException(400, 'Refund quantity exceeds remaining quantity')
        amounts = []
        for field in ('line_total', 'tax_amount', 'line_cost'):
            if field == 'tax_amount' and any(row.tax_amount is None for row in old) and Decimal(item.tax_amount or 0):
                raise HTTPException(409, 'Historical refund tax allocation requires review')
            amounts.append(reverse_component(getattr(item, field), sum((abs(Decimal(getattr(row, field) or 0)) for row in old), Decimal(0)), returned+request.quantity, quantity))
        plan[item.id] = tuple(amounts)  # original line basis, tax disclosure, cost
    return plan
