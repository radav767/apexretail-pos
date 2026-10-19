import csv
import io

from fastapi import HTTPException

from app.dashboard.repository import DashboardRepository


class DashboardService:
    DRILLDOWN_EXPORT_LIMIT = 10_000
    def __init__(self, repo: DashboardRepository):
        self.repo = repo

    async def get_summary(self, company_id, branch_id=None):
        if branch_id is not None:
            return await self.repo.get_summary(company_id, branch_id=branch_id)
        return await self.repo.get_summary(company_id)

    async def get_phase2_summary(
        self,
        company_id,
        *,
        range_key,
        date_from=None,
        date_to=None,
        shop_id=None,
    ):
        return await self.repo.get_phase2_summary(
            company_id,
            range_key=range_key,
            date_from=date_from,
            date_to=date_to,
            shop_id=shop_id,
        )

    async def get_phase3_summary(self, company_id, **filters):
        return await self.repo.get_phase3_summary(company_id, **filters)

    async def get_drilldown(self, company_id, **filters):
        return await self.repo.get_drilldown(company_id, **filters)

    @staticmethod
    def _safe_csv(value):
        rendered = "" if value is None else str(value)
        if rendered.startswith(("=", "+", "-", "@")):
            return "'" + rendered
        return rendered

    async def export_phase3(self, company_id, *, section, **filters):
        summary = await self.get_phase3_summary(company_id, **filters)
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")

        if section == "trends":
            writer.writerow([
                "period_start", "period_end", "gross_sales", "refunds",
                "net_sales", "cost_of_sales", "gross_profit", "discounts",
                "discounts_available",
            ])
            for point in summary["trends"]:
                metrics = point["metrics"]
                writer.writerow([
                    point["period_start"], point["period_end"],
                    metrics["gross_sales"]["value"], metrics["refunds"]["value"],
                    metrics["net_sales"]["value"], metrics["cost_of_sales"]["value"],
                    metrics["gross_profit"]["value"], metrics["discounts"]["value"],
                    metrics["discounts"]["available"],
                ])
        elif section in {"top_products", "top_categories"}:
            writer.writerow(["id", "name", "revenue", "quantity", "gross_profit"])
            for row in summary[section]:
                writer.writerow([self._safe_csv(row.get(key)) for key in (
                    "id", "name", "revenue", "quantity", "gross_profit"
                )])
        else:
            writer.writerow([
                "key", "name", "transactions", "gross_sales", "refunds",
                "net_sales", "gross_profit", "discounts", "discounts_available",
            ])
            for row in summary[section]:
                writer.writerow([
                    self._safe_csv(row.get("key")), self._safe_csv(row.get("name")),
                    row["transactions"], row["gross_sales"], row["refunds"],
                    row["net_sales"], row["gross_profit"],
                    row["discounts"]["value"], row["discounts"]["available"],
                ])
        return output.getvalue()

    async def export_drilldown(self, company_id, **filters):
        drilldown = await self.get_drilldown(
            company_id,
            **filters,
            limit=self.DRILLDOWN_EXPORT_LIMIT,
            offset=0,
        )
        if drilldown["total"] > self.DRILLDOWN_EXPORT_LIMIT:
            raise HTTPException(
                422,
                (
                    f"This export contains {drilldown['total']:,} rows; the "
                    f"maximum is {self.DRILLDOWN_EXPORT_LIMIT:,}. Narrow the "
                    "date, shop, metric, or detail filter and try again."
                ),
            )
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow([
            "id", "receipt_number", "created_at", "shop", "cashier",
            "payment_method", "status", "gross_sales", "refunds",
            "net_sales", "cost_of_sales", "gross_profit", "discounts",
            "discounts_available",
        ])
        for row in drilldown["rows"]:
            writer.writerow([
                self._safe_csv(row.get("id")), self._safe_csv(row.get("receipt_number")),
                row.get("created_at"), self._safe_csv(row.get("shop_name")),
                self._safe_csv(row.get("cashier_name")),
                self._safe_csv(row.get("payment_method")), self._safe_csv(row.get("status")),
                row.get("gross_sales"), row.get("refunds"), row.get("net_sales"),
                row.get("cost_of_sales"), row.get("gross_profit"),
                row["discounts"]["value"], row["discounts"]["available"],
            ])
        totals = drilldown["metrics"]
        writer.writerow([
            "TOTAL", "", "", "", "", "", "",
            totals["gross_sales"]["value"], totals["refunds"]["value"],
            totals["net_sales"]["value"], totals["cost_of_sales"]["value"],
            totals["gross_profit"]["value"], totals["discounts"]["value"],
            totals["discounts"]["available"],
        ])
        return output.getvalue()
