import unittest
from datetime import date
from decimal import Decimal
from inspect import getsource
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import HTTPException
from app.auth.dependencies import AuthActor, ensure_company_access, require_permission
from app.reports.accounting import inventory_metrics
from app.reports.repository import ReportsRepository
from app.reports.schema import SalesHistoryQuery
from app.reports.service import ReportsService


class Phase4AAccountingTest(unittest.TestCase):
    def test_inventory_formulas_and_rounding_are_server_side(self):
        selling, cost, profit, margin = inventory_metrics("3", "10.00", "4.00")
        self.assertEqual(selling["value"], Decimal("30.00"))
        self.assertEqual(cost["value"], Decimal("12.00"))
        self.assertEqual(profit["value"], Decimal("18.00"))
        self.assertEqual(margin["value"], Decimal("60.00"))

    def test_missing_cost_and_zero_denominator_are_unavailable(self):
        _selling, cost, profit, margin = inventory_metrics("2", "5", None)
        self.assertFalse(cost["available"])
        self.assertFalse(profit["available"])
        self.assertFalse(margin["available"])
        self.assertIsNone(cost["value"])
        self.assertFalse(inventory_metrics("2", "0", "1")[3]["available"])

    def test_canonical_sales_cte_aggregates_items_before_sale_totals(self):
        query = SalesHistoryQuery(date_from=date(2026, 9, 1), date_to=date(2026, 9, 2))
        sql = ReportsRepository._cte(query)
        self.assertIn("GROUP BY si.sale_id", sql)
        self.assertIn("LEFT JOIN item_totals", sql)
        self.assertIn("cost_snapshot_available IS TRUE", sql)
        self.assertIn("LOWER(s.status) IN ('cancelled','canceled','voided') OR s.original_sale_id IS NOT NULL", sql)

    def test_grouped_revenue_allocates_sale_totals_and_order_has_final_tie_breaker(self):
        query = SalesHistoryQuery(view="product", date_from=date(2026, 9, 1), date_to=date(2026, 9, 2))
        sql, _sort, _direction = ReportsRepository.sales_history_rows_sql(query)
        self.assertIn("tx.amount * si.line_total / tx.line_amount", sql)
        self.assertIn("SUM(si.line_total)", sql)
        self.assertIn("dimension_id ASC NULLS LAST", getsource(ReportsRepository.sales_history))


class Phase4AServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_historical_values_are_never_zero(self):
        repo = SimpleNamespace(
            validate_dimensions=AsyncMock(return_value=None),
            sales_history=AsyncMock(return_value=(1, [{
                "dimension_id": uuid4(), "label": "R-1", "transactions": 1,
                "quantity": None, "amount": Decimal("5"), "cost": Decimal("0"),
                "cost_known": False, "discount": None, "discount_known": False,
            }], {
                "gross_sales": Decimal("5"), "refunds": 0, "net_sales": Decimal("5"),
                "cost": 0, "cost_known": False, "discount": None,
                "discount_known": False, "transactions": 1,
            })),
            currency=AsyncMock(return_value=("Z$", 2)),
            options=AsyncMock(return_value={}),
        )
        report = await ReportsService(repo).sales_history(
            uuid4(), SalesHistoryQuery(date_from=date(2026, 9, 1), date_to=date(2026, 9, 1))
        )
        self.assertFalse(report["rows"][0]["cost"]["available"])
        self.assertIsNone(report["summary"]["discounts"]["value"])

    async def test_selected_cross_company_dimension_is_rejected(self):
        repo = SimpleNamespace(validate_dimensions=AsyncMock(return_value="branch_id"))
        with self.assertRaisesRegex(Exception, "not found for this company"):
            await ReportsService(repo).sales_history(
                uuid4(), SalesHistoryQuery(date_from=date.today(), date_to=date.today(), branch_id=uuid4())
            )

    async def test_csv_escapes_spreadsheet_formulas(self):
        service = ReportsService(SimpleNamespace())
        service.sales_history = AsyncMock(return_value={"rows": [{
            "label": "=cmd", "transactions": 1, "quantity": None, "amount": Decimal("1"),
            "cost": {"value": None, "available": False},
            "gross_profit": {"value": None}, "discount": {"value": None, "available": False},
        }]})
        csv_text = await service.sales_history_csv(uuid4(), SimpleNamespace())
        self.assertIn("'=cmd", csv_text)

    async def test_inventory_csv_escapes_all_user_controlled_labels(self):
        service = ReportsService(SimpleNamespace())
        service.inventory_valuation = AsyncMock(return_value={"rows": [{
            "shop_name": "=shop", "branch_name": "+branch",
            "product_name": "@product", "sku": "-sku", "quantity": Decimal("1"),
            "selling_value": {"value": Decimal("2")},
            "cost_value": {"value": Decimal("1")},
            "projected_gross_profit": {"value": Decimal("1")},
            "margin_percentage": {"value": Decimal("50")},
        }]})
        csv_text = await service.inventory_csv(uuid4())
        for escaped in ("'=shop", "'+branch", "'@product", "'-sku"):
            self.assertIn(escaped, csv_text)


class Phase4AApiPermissionTest(unittest.IsolatedAsyncioTestCase):
    async def test_reports_permission_and_company_isolation(self):
        company_id = uuid4()
        check_reports = require_permission("reports")
        with self.assertRaises(HTTPException) as denied:
            await check_reports(AuthActor("employee", company_id, "cashier", permissions={"reports": False}))
        self.assertEqual(denied.exception.status_code, 403)
        check_valuation = require_permission("inventory_valuation")
        with self.assertRaises(HTTPException) as denied_valuation:
            await check_valuation(AuthActor("employee", company_id, "cashier", permissions={"inventory_valuation": False}))
        self.assertEqual(denied_valuation.exception.status_code, 403)
        with self.assertRaises(HTTPException) as other:
            ensure_company_access(AuthActor("user", uuid4(), "owner"), company_id)
        self.assertEqual(other.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
