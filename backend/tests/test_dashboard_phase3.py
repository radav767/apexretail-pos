import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.auth.dependencies import AuthActor, get_auth_actor
from app.dashboard.accounting import (
    percentage_change,
    preceding_period,
    transaction_filters,
    transaction_population_cte,
    utc_bounds,
)
from app.dashboard.router import get_service as get_dashboard_service
from app.dashboard.service import DashboardService
from app.main import app


class DashboardPhase3AccountingTest(unittest.TestCase):
    def test_preceding_period_has_equal_inclusive_length(self):
        self.assertEqual(
            preceding_period(date(2026, 8, 10), date(2026, 8, 16)),
            (date(2026, 8, 3), date(2026, 8, 9)),
        )

    def test_percentage_change_uses_absolute_previous_and_handles_zero(self):
        self.assertEqual(
            percentage_change(Decimal("120"), Decimal("100")),
            {"available": True, "amount": Decimal("20.00"), "percentage": Decimal("20.00")},
        )
        self.assertIsNone(percentage_change(Decimal("5"), Decimal("0"))["percentage"])

    def test_harare_bounds_are_half_open_utc(self):
        start_at, end_at = utc_bounds(date(2026, 8, 10), date(2026, 8, 10))
        self.assertEqual(start_at.isoformat(), "2026-08-09T22:00:00+00:00")
        self.assertEqual(end_at.isoformat(), "2026-08-10T22:00:00+00:00")

    def test_canonical_population_prevents_item_fanout(self):
        sql = transaction_population_cte(transaction_filters())
        self.assertIn("GROUP BY si.sale_id", sql)
        self.assertIn("LEFT JOIN item_costs", sql)
        self.assertIn("partially_refunded", sql)
        self.assertIn("s.original_sale_id IS NOT NULL", sql)


class DashboardPhase3ExportTest(unittest.IsolatedAsyncioTestCase):
    async def test_csv_uses_returned_screen_result_and_escapes_formulas(self):
        summary = {
            "top_products": [{
                "id": uuid4(), "name": "=unsafe", "revenue": Decimal("10"),
                "quantity": Decimal("2"), "gross_profit": Decimal("4"),
            }]
        }
        repository = SimpleNamespace(get_phase3_summary=AsyncMock(return_value=summary))
        content = await DashboardService(repository).export_phase3(
            uuid4(), section="top_products", range_key="today", granularity="day"
        )
        self.assertIn("id,name,revenue,quantity,gross_profit", content)
        self.assertIn("'=unsafe", content)
        repository.get_phase3_summary.assert_awaited_once()

    async def test_drilldown_export_refuses_to_silently_truncate(self):
        repository = SimpleNamespace(get_drilldown=AsyncMock(return_value={
            "total": DashboardService.DRILLDOWN_EXPORT_LIMIT + 1,
            "limit": DashboardService.DRILLDOWN_EXPORT_LIMIT,
            "offset": 0,
            "metrics": {},
            "rows": [],
        }))
        with self.assertRaises(HTTPException) as caught:
            await DashboardService(repository).export_drilldown(
                uuid4(), range_key="custom", date_from=date(2026, 8, 1),
                date_to=date(2026, 8, 31), metric="net_sales",
            )
        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("10,001 rows", caught.exception.detail)
        self.assertIn("Narrow", caught.exception.detail)

    async def test_drilldown_export_uses_centralized_totals(self):
        metrics = {key: metric(value) for key, value in {
            "gross_sales": "10.00", "refunds": "2.00",
            "net_sales": "8.00", "cost_of_sales": "3.00",
            "gross_profit": "5.00", "discounts": "1.00",
        }.items()}
        row = {
            "id": uuid4(), "receipt_number": "=unsafe", "created_at": "2026-08-01",
            "shop_name": "Shop", "cashier_name": "Cashier",
            "payment_method": "cash", "status": "completed",
            "gross_sales": "10.00", "refunds": "2.00", "net_sales": "8.00",
            "cost_of_sales": "3.00", "gross_profit": "5.00",
            "discounts": metric("1.00"),
        }
        repository = SimpleNamespace(get_drilldown=AsyncMock(return_value={
            "total": 1, "limit": 10_000, "offset": 0,
            "metrics": metrics, "rows": [row],
        }))
        content = await DashboardService(repository).export_drilldown(
            uuid4(), range_key="today", metric="net_sales",
        )
        self.assertIn("'=unsafe", content)
        self.assertIn("TOTAL,,,,,,,10.00,2.00,8.00,3.00,5.00,1.00,True", content)


def metric(value="0.00", available=True):
    return {
        "available": available, "value": value if available else None,
        "reason": None if available else "Unknown", "missing_persistence": None,
    }


def phase3_response(company_id):
    metrics = {key: metric() for key in (
        "gross_sales", "net_sales", "cost_of_sales", "gross_profit", "discounts", "refunds"
    )}
    return {
        "range_key": "today", "date_from": "2026-08-10", "date_to": "2026-08-10",
        "reporting_timezone": "Africa/Harare", "shop_id": None,
        "currency_symbol": "$", "decimal_places": 2, "shops": [], "metrics": metrics,
        "granularity": "day",
        "comparison": {"date_from": "2026-08-09", "date_to": "2026-08-09", "metrics": {
            key: {"available": True, "amount": "0.00", "percentage": None, "reason": None}
            for key in metrics
        }},
        "trends": [], "top_products": [], "top_categories": [],
        "payment_methods": [], "shop_breakdown": [], "cashier_breakdown": [],
        "discount_breakdown": [], "refund_breakdown": [],
    }


class DashboardPhase3ApiSecurityTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.company_id = uuid4()
        self.service = SimpleNamespace(
            get_summary=AsyncMock(return_value={
                "today_sales": "0", "today_transactions": 0, "total_products": 0,
                "low_stock_products": 0, "stock_value": "0",
            }),
            get_phase3_summary=AsyncMock(return_value=phase3_response(self.company_id)),
            get_drilldown=AsyncMock(return_value={
                "total": 0, "limit": 50, "offset": 0,
                "metrics": phase3_response(self.company_id)["metrics"], "rows": [],
            }),
            export_phase3=AsyncMock(return_value="period_start,period_end\n"),
            export_drilldown=AsyncMock(return_value="id,receipt_number\n"),
        )
        async def override_service():
            return self.service

        app.dependency_overrides[get_dashboard_service] = override_service

    def tearDown(self):
        app.dependency_overrides.clear()

    def set_actor(self, company_id=None, reports=True, role=None):
        self.branch_id = uuid4()
        async def override_actor():
            return AuthActor(
                actor_type="employee", company_id=company_id or self.company_id,
                role=role or ("administrator" if reports else "cashier"), permissions={"reports": reports},
                employee=SimpleNamespace(id=uuid4(), branch_id=self.branch_id),
            )

        app.dependency_overrides[get_auth_actor] = override_actor

    async def request(self, path, **kwargs):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.get(path, **kwargs)

    async def test_analytics_drilldown_and_export_are_authorized(self):
        self.set_actor()
        for suffix in ("", "/sales", "/sales.csv", "/export.csv"):
            response = await self.request(f"/api/dashboard/analytics-v3/{self.company_id}{suffix}")
            self.assertEqual(response.status_code, 200, response.text)

    async def test_drilldown_forwards_paginated_dimension_filters(self):
        self.set_actor()
        response = await self.request(
            f"/api/dashboard/analytics-v3/{self.company_id}/sales",
            params={
                "range_key": "custom", "date_from": "2026-08-01",
                "date_to": "2026-08-31", "metric": "gross_profit",
                "dimension": "payment", "dimension_key": "cash",
                "limit": 25, "offset": 50,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        kwargs = self.service.get_drilldown.await_args.kwargs
        self.assertEqual(kwargs["dimension"], "payment")
        self.assertEqual(kwargs["dimension_key"], "cash")
        self.assertEqual(kwargs["limit"], 25)
        self.assertEqual(kwargs["offset"], 50)

    async def test_all_dashboard_generations_reject_cross_company(self):
        self.set_actor(company_id=uuid4())
        for path in (
            f"/api/dashboard/summary/{self.company_id}",
            f"/api/dashboard/summary-v2/{self.company_id}",
            f"/api/dashboard/analytics-v3/{self.company_id}",
            f"/api/dashboard/analytics-v3/{self.company_id}/sales",
            f"/api/dashboard/analytics-v3/{self.company_id}/sales.csv",
            f"/api/dashboard/analytics-v3/{self.company_id}/export.csv",
        ):
            response = await self.request(path)
            self.assertEqual(response.status_code, 403, path)

    async def test_legacy_route_is_now_secured_without_shape_change(self):
        response = await self.request(f"/api/dashboard/summary/{self.company_id}")
        self.assertEqual(response.status_code, 401)
        self.set_actor()
        response = await self.request(f"/api/dashboard/summary/{self.company_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {
            "today_sales", "today_transactions", "total_products",
            "low_stock_products", "stock_value",
        })

    async def test_reports_permission_is_required(self):
        self.set_actor(reports=False)
        response = await self.request(f"/api/dashboard/analytics-v3/{self.company_id}")
        self.assertEqual(response.status_code, 403)

    async def test_branch_employee_is_scoped_and_cannot_view_company_analytics(self):
        self.set_actor(role="manager")
        response = await self.request(f"/api/dashboard/summary/{self.company_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["stock_value"])
        self.service.get_summary.assert_awaited_once_with(self.company_id, branch_id=self.branch_id)
        response = await self.request(f"/api/dashboard/analytics-v3/{self.company_id}")
        self.assertEqual(response.status_code, 403)
        self.service.get_phase3_summary.assert_not_awaited()
