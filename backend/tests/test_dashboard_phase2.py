import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import HTTPException
import httpx

from app.auth.dependencies import AuthActor, get_auth_actor
from app.dashboard.router import get_service as get_dashboard_service
from app.dashboard.repository import (
    DashboardRepository,
    build_phase2_metrics,
    resolve_phase2_date_range,
)
from app.main import app


class DashboardPhase2RangeTest(unittest.TestCase):
    def test_today_uses_reporting_timezone_day(self):
        start_date, end_date = resolve_phase2_date_range(
            "today",
            date_from=None,
            date_to=None,
            today=date(2026, 8, 19),
        )

        self.assertEqual(start_date, date(2026, 8, 19))
        self.assertEqual(end_date, date(2026, 8, 19))

    def test_last_seven_days_is_inclusive(self):
        start_date, end_date = resolve_phase2_date_range(
            "last_7_days",
            date_from=None,
            date_to=None,
            today=date(2026, 8, 19),
        )

        self.assertEqual(start_date, date(2026, 8, 13))
        self.assertEqual(end_date, date(2026, 8, 19))

    def test_yesterday_returns_previous_reporting_day(self):
        start_date, end_date = resolve_phase2_date_range(
            "yesterday",
            date_from=None,
            date_to=None,
            today=date(2026, 8, 19),
        )

        self.assertEqual(start_date, date(2026, 8, 18))
        self.assertEqual(end_date, date(2026, 8, 18))

    def test_last_month_returns_full_previous_calendar_month(self):
        start_date, end_date = resolve_phase2_date_range(
            "last_month",
            date_from=None,
            date_to=None,
            today=date(2026, 8, 19),
        )

        self.assertEqual(start_date, date(2026, 7, 1))
        self.assertEqual(end_date, date(2026, 7, 31))

    def test_custom_range_requires_dates(self):
        with self.assertRaises(HTTPException) as context:
            resolve_phase2_date_range(
                "custom",
                date_from=None,
                date_to=date(2026, 8, 19),
                today=date(2026, 8, 19),
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("date_from", context.exception.detail)

    def test_custom_range_rejects_reversed_and_more_than_366_inclusive_days(self):
        for start, end in ((date(2026, 8, 2), date(2026, 8, 1)),
                           (date(2024, 1, 1), date(2025, 1, 1))):
            with self.assertRaises(HTTPException):
                resolve_phase2_date_range("custom", date_from=start, date_to=end)
        self.assertEqual(
            resolve_phase2_date_range("custom", date_from=date(2024, 1, 1), date_to=date(2024, 12, 31)),
            (date(2024, 1, 1), date(2024, 12, 31)),
        )


class DashboardPhase2MetricsTest(unittest.TestCase):
    def test_metrics_include_refunds_and_flag_missing_discounts(self):
        metrics = build_phase2_metrics(
            gross_sales=Decimal("150.00"),
            refunds=Decimal("30.00"),
            cost_of_sales=Decimal("72.00"),
            discounts=Decimal("5.00"),
            discounts_known=False,
        )

        self.assertEqual(
            metrics["gross_sales"]["value"],
            Decimal("150.00"),
        )
        self.assertEqual(
            metrics["cost_of_sales"]["value"],
            Decimal("72.00"),
        )
        self.assertEqual(
            metrics["gross_profit"]["value"],
            Decimal("48.00"),
        )
        self.assertFalse(metrics["discounts"]["available"])
        self.assertIsNone(metrics["discounts"]["value"])
        self.assertEqual(
            metrics["discounts"]["missing_persistence"],
            "sales.discount_amount",
        )
        self.assertTrue(metrics["refunds"]["available"])
        self.assertEqual(
            metrics["refunds"]["value"],
            Decimal("30.00"),
        )
        self.assertTrue(metrics["net_sales"]["available"])
        self.assertEqual(
            metrics["net_sales"]["value"],
            Decimal("120.00"),
        )


class FakeResult:
    def __init__(
        self,
        *,
        row=None,
        rows=None,
        scalar=None,
    ):
        self.row = row
        self.rows = rows or []
        self.scalar = scalar

    def mappings(self):
        return self

    def first(self):
        return self.row

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.scalar


class DashboardPhase2RepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_summary_separates_sales_from_items_and_uses_refunds(self):
        company_id = uuid4()
        shop_id = uuid4()
        shop = SimpleNamespace(id=shop_id, name="Main Shop")
        setting = SimpleNamespace(currency_symbol="Z$", decimal_places=2)
        db = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    FakeResult(rows=[shop]),
                    FakeResult(scalar=setting),
                    FakeResult(
                        row={
                            "gross_sales": Decimal("150.00"),
                            "refunds": Decimal("30.00"),
                            "discounts": Decimal("5.00"),
                            "original_sale_count": 2,
                            "known_discount_count": 1,
                            "net_sales": Decimal("120.00"),
                            "cost_of_sales": Decimal("72.00"),
                            "gross_profit": Decimal("48.00"),
                        }
                    ),
                ]
            )
        )

        summary = await DashboardRepository(db).get_phase2_summary(
            company_id,
            range_key="today",
            shop_id=shop_id,
        )

        sales_sql = str(db.execute.await_args_list[2].args[0])
        self.assertIn("GROUP BY si.sale_id", sales_sql)
        self.assertIn("LEFT JOIN item_costs", sales_sql)
        self.assertIn("s.original_sale_id IS NULL", sales_sql)
        self.assertIn("partially_refunded", sales_sql)
        self.assertIn("s.original_sale_id IS NOT NULL", sales_sql)
        self.assertEqual(
            summary["metrics"]["net_sales"]["value"],
            Decimal("120.00"),
        )
        self.assertEqual(
            summary["metrics"]["gross_profit"]["value"],
            Decimal("48.00"),
        )

    async def test_shop_filter_must_belong_to_company(self):
        db = SimpleNamespace(
            execute=AsyncMock(
                return_value=FakeResult(rows=[])
            )
        )

        with self.assertRaises(HTTPException) as context:
            await DashboardRepository(db).get_phase2_summary(
                uuid4(),
                range_key="today",
                shop_id=uuid4(),
            )

        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(db.execute.await_count, 1)


def dashboard_response(company_id, shop_id):
    def metric(value):
        return {
            "available": True,
            "value": value,
            "reason": None,
            "missing_persistence": None,
        }

    return {
        "range_key": "custom",
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
        "reporting_timezone": "Africa/Harare",
        "shop_id": str(shop_id),
        "currency_symbol": "$",
        "decimal_places": 2,
        "shops": [{"id": str(shop_id), "name": "Main Shop"}],
        "metrics": {
            "gross_sales": metric("150.00"),
            "net_sales": metric("120.00"),
            "cost_of_sales": metric("72.00"),
            "gross_profit": metric("48.00"),
            "discounts": metric("5.00"),
            "refunds": metric("30.00"),
        },
    }


class DashboardPhase2ApiTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.company_id = uuid4()
        self.shop_id = uuid4()
        self.service = SimpleNamespace(
            get_phase2_summary=AsyncMock(
                return_value=dashboard_response(
                    self.company_id,
                    self.shop_id,
                )
            )
        )
        async def dashboard_service_override():
            return self.service

        app.dependency_overrides[get_dashboard_service] = (
            dashboard_service_override
        )

    def tearDown(self):
        app.dependency_overrides.clear()

    def set_actor(self, *, company_id=None, reports=True):
        actor = AuthActor(
            actor_type="employee",
            company_id=company_id or self.company_id,
            role="manager",
            permissions={"reports": reports},
        )
        async def auth_actor_override():
            return actor

        app.dependency_overrides[get_auth_actor] = auth_actor_override

    async def request(self, path, **kwargs):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path, **kwargs)

    async def test_authenticated_request_forwards_dates_and_shop(self):
        self.set_actor()
        response = await self.request(
            f"/api/dashboard/summary-v2/{self.company_id}",
            params={
                "range_key": "custom",
                "date_from": "2026-08-01",
                "date_to": "2026-08-31",
                "shop_id": str(self.shop_id),
            },
            headers={"Authorization": "Bearer dashboard-test"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["metrics"]["gross_profit"]["value"],
            "48.00",
        )
        self.service.get_phase2_summary.assert_awaited_once_with(
            self.company_id,
            range_key="custom",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
            shop_id=self.shop_id,
        )

    async def test_reports_permission_is_required(self):
        self.set_actor(reports=False)
        response = await self.request(
            f"/api/dashboard/summary-v2/{self.company_id}",
            headers={"Authorization": "Bearer dashboard-test"},
        )

        self.assertEqual(response.status_code, 403)
        self.service.get_phase2_summary.assert_not_awaited()

    async def test_cross_company_access_is_rejected(self):
        self.set_actor(company_id=uuid4())
        response = await self.request(
            f"/api/dashboard/summary-v2/{self.company_id}",
            headers={"Authorization": "Bearer dashboard-test"},
        )

        self.assertEqual(response.status_code, 403)
        self.service.get_phase2_summary.assert_not_awaited()

    async def test_unauthenticated_request_is_rejected(self):
        response = await self.request(f"/api/dashboard/summary-v2/{self.company_id}")
        self.assertEqual(response.status_code, 401)
        self.service.get_phase2_summary.assert_not_awaited()

    async def test_invalid_range_and_dates_are_rejected(self):
        self.set_actor()
        for params in ({"range_key": "invalid"}, {"date_from": "not-a-date"}, {"shop_id": "invalid"}):
            response = await self.request(f"/api/dashboard/summary-v2/{self.company_id}", params=params)
            self.assertEqual(response.status_code, 422)
        self.service.get_phase2_summary.assert_not_awaited()


class DashboardDiscountSnapshotTest(unittest.IsolatedAsyncioTestCase):
    async def create_sale(self, discount, line_total="0.80"):
        from unittest.mock import patch
        from app.sales.schema import SaleCreate, SaleItemCreate
        from app.sales.service import SalesService
        # Reuse the established weighted checkout fixture.
        from tests.test_weighted_sales_and_subscriptions import FakeSalesRepo

        repo = FakeSalesRepo()
        payload = SaleCreate(
            company_id=uuid4(),
            amount_received=Decimal("1"),
            discount_amount=discount,
            items=[SaleItemCreate(
                product_id=repo.product.id, quantity=Decimal("0.250"),
                unit_price=Decimal("4"), line_total=Decimal(line_total),
            )],
        )
        with patch("app.sales.service.BusinessSettingsService.get", return_value={
            "tax_name": "Tax", "tax_rate": Decimal("0"),
            "tax_inclusive": False, "receipt_footer": "Thank you",
        }):
            return await SalesService(repo).create_sale(payload, actor=None)

    async def test_explicit_discount_snapshot_is_saved_without_discounting_twice(self):
        sale = await self.create_sale(Decimal("0.20"))
        self.assertEqual(sale.discount_amount, Decimal("0.20"))
        self.assertEqual(sale.total_amount, Decimal("0.80"))

    async def test_legacy_discount_remains_unknown(self):
        sale = await self.create_sale(None)
        self.assertIsNone(sale.discount_amount)

    async def test_explicit_zero_is_preserved(self):
        sale = await self.create_sale(Decimal("0"), "1.00")
        self.assertEqual(sale.discount_amount, Decimal("0"))

    async def test_inconsistent_discount_is_rejected(self):
        with self.assertRaises(HTTPException) as context:
            await self.create_sale(Decimal("0.10"))
        self.assertEqual(context.exception.status_code, 400)

    async def test_employee_without_discount_permission_cannot_submit_snapshot(self):
        from app.sales.schema import SaleCreate
        from app.sales.service import SalesService
        actor = AuthActor(
            actor_type="employee", company_id=uuid4(), role="cashier",
            permissions={"sales": True, "discounts": False},
        )
        with self.assertRaises(HTTPException) as context:
            await SalesService(SimpleNamespace()).create_sale(
                SaleCreate(company_id=actor.company_id, discount_amount=Decimal("1"), items=[]),
                actor=actor,
            )
        self.assertEqual(context.exception.status_code, 403)
