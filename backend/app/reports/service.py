import csv
import io
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from app.reports.accounting import (
    REPORTING_TIMEZONE_NAME, inventory_metrics, known_money, money, utc_bounds,
)


def csv_cell(value):
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


class ReportsService:
    EXPORT_LIMIT = 10_000

    def __init__(self, repo):
        self.repo = repo

    async def sales_history(self, company_id, query, *, export=False):
        if query.date_to < query.date_from:
            raise HTTPException(400, "End date cannot be before start date")
        if (query.date_to - query.date_from).days >= 366:
            raise HTTPException(400, "Report range cannot exceed 366 days")
        invalid = await self.repo.validate_dimensions(company_id, query.model_dump())
        if invalid:
            raise HTTPException(404, f"Selected {invalid.removesuffix('_id')} was not found for this company")
        start_at, end_at = utc_bounds(query.date_from, query.date_to)
        total, raw_rows, summary_row = await self.repo.sales_history(
            company_id, query, start_at, end_at, export=export
        )
        if export and total > self.EXPORT_LIMIT:
            raise HTTPException(422, f"Export contains {total:,} rows. Narrow the filters below {self.EXPORT_LIMIT + 1:,} rows.")
        currency_symbol, decimal_places = await self.repo.currency(company_id)
        rows = []
        for raw in raw_rows:
            cost = known_money(raw.get("cost"), bool(raw.get("cost_known")), reason="Recorded historical cost is unavailable for one or more sales.", field="sale_items.cost_snapshot_available")
            amount = money(raw.get("amount"))
            profit = known_money(amount - money(raw.get("cost")), bool(raw.get("cost_known")), reason="Gross profit is unavailable because historical cost is incomplete.", field="sale_items.cost_snapshot_available")
            discount = known_money(raw.get("discount"), bool(raw.get("discount_known")), reason="Historical discount components are unavailable for one or more sales.", field="sales.discount_amount")
            row = {**raw, "amount": amount, "cost": cost, "gross_profit": profit, "discount": discount}
            rows.append(row)
        cost_known = bool(summary_row.get("cost_known")) if summary_row.get("transactions") else True
        discount_known = bool(summary_row.get("discount_known")) if summary_row.get("transactions") else True
        net_sales = money(summary_row.get("net_sales"))
        summary = {
            "gross_sales": money(summary_row.get("gross_sales")),
            "refunds": money(summary_row.get("refunds")),
            "net_sales": net_sales,
            "transactions": int(summary_row.get("transactions") or 0),
            "cost_of_sales": known_money(summary_row.get("cost"), cost_known, reason="Recorded historical cost is incomplete for this population.", field="sale_items.cost_snapshot_available"),
            "gross_profit": known_money(net_sales - money(summary_row.get("cost")), cost_known, reason="Gross profit is unavailable because historical cost is incomplete.", field="sale_items.cost_snapshot_available"),
            "discounts": known_money(summary_row.get("discount"), discount_known, reason="Historical discount components are incomplete for this population.", field="sales.discount_amount"),
        }
        options = await self.repo.options(company_id)
        return {
            "view": query.view, "date_from": query.date_from, "date_to": query.date_to,
            "reporting_timezone": REPORTING_TIMEZONE_NAME,
            "currency_symbol": currency_symbol, "decimal_places": decimal_places,
            "total": total, "limit": query.limit, "offset": query.offset,
            "summary": summary, "rows": rows, "filters": query.model_dump(), "options": options,
        }

    async def sales_history_csv(self, company_id, query):
        report = await self.sales_history(company_id, query, export=True)
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["label", "transactions", "quantity", "amount", "cost", "cost_available", "gross_profit", "discount", "discount_available", "status", "payment_method", "created_at"])
        for row in report["rows"]:
            writer.writerow([csv_cell(row.get("label")), row.get("transactions"), row.get("quantity"), row.get("amount"), row["cost"].get("value"), row["cost"].get("available"), row["gross_profit"].get("value"), row["discount"].get("value"), row["discount"].get("available"), csv_cell(row.get("status")), csv_cell(row.get("payment_method")), row.get("created_at")])
        return output.getvalue()

    async def financial_summary(self, company_id, *, date_from, date_to, branch_id=None, shop_id=None):
        if date_to < date_from:
            raise HTTPException(400, "End date cannot be before start date")
        if (date_to - date_from).days >= 366:
            raise HTTPException(400, "Report range cannot exceed 366 days")
        invalid = await self.repo.validate_dimensions(company_id, {"branch_id": branch_id, "shop_id": shop_id})
        if invalid:
            raise HTTPException(404, f"Selected {invalid.removesuffix('_id')} was not found for this company")
        start_at, end_at = utc_bounds(date_from, date_to)
        row = await self.repo.financial_summary(company_id, start_at, end_at, branch_id, shop_id)
        return {key: money(value) for key, value in row.items()}

    async def inventory_valuation(self, company_id, *, branch_id=None, category_id=None, product_id=None, limit=50, offset=0, export=False):
        invalid = await self.repo.validate_dimensions(company_id, {"branch_id": branch_id, "category_id": category_id, "product_id": product_id})
        if invalid:
            raise HTTPException(404, f"Selected {invalid.removesuffix('_id')} was not found for this company")
        total, raw_rows, aggregate = await self.repo.valuation(company_id, branch_id=branch_id, category_id=category_id, product_id=product_id, limit=limit, offset=offset, export=export)
        if export and total > self.EXPORT_LIMIT:
            raise HTTPException(422, f"Export contains {total:,} rows. Narrow the filters.")
        rows = []
        for raw in raw_rows:
            metrics = inventory_metrics(raw["quantity"], raw["selling_price"], raw["cost_price"])
            rows.append({**{k: raw[k] for k in ("product_id","product_name","sku","branch_id","branch_name","shop_id","shop_name","quantity")}, "variant_id": raw.get("variant_id"), "selling_value": metrics[0], "cost_value": metrics[1], "projected_gross_profit": metrics[2], "margin_percentage": metrics[3]})
        total_qty = Decimal(str(aggregate.get("quantity") or 0))
        summary_metrics = inventory_metrics(
            Decimal("1"),
            aggregate.get("selling_value") if aggregate.get("selling_known") else None,
            aggregate.get("cost_value") if aggregate.get("cost_known") else None,
        )
        currency_symbol, decimal_places = await self.repo.currency(company_id)
        return {"as_of": datetime.now(timezone.utc), "basis": "Projected valuation using current selling prices and recorded current unit costs; it is not historical realized profit.", "currency_symbol": currency_symbol, "decimal_places": decimal_places, "total": total, "limit": limit, "offset": offset, "summary": {"quantity": total_qty.quantize(Decimal("0.001")), "selling_value": summary_metrics[0], "cost_value": summary_metrics[1], "projected_gross_profit": summary_metrics[2], "margin_percentage": summary_metrics[3]}, "rows": rows}

    async def inventory_csv(self, company_id, **kwargs):
        report = await self.inventory_valuation(company_id, export=True, **kwargs)
        output = io.StringIO(); writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["shop","branch","product","sku","quantity","selling_value","cost_value","projected_gross_profit","margin_percentage"])
        for row in report["rows"]:
            writer.writerow([csv_cell(row["shop_name"]),csv_cell(row["branch_name"]),csv_cell(row["product_name"]),csv_cell(row["sku"]),row["quantity"],row["selling_value"]["value"],row["cost_value"]["value"],row["projected_gross_profit"]["value"],row["margin_percentage"]["value"]])
        return output.getvalue()
