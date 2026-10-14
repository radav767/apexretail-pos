import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import httpx

from app.auth.dependencies import AuthActor, get_auth_actor
from app.main import app
from app.shifts.router import get_service
from app.shifts.service import ShiftService


COMPANY_ID = uuid4()
OTHER_COMPANY_ID = uuid4()
SHIFT_ID = uuid4()
EMPLOYEE_ID = uuid4()
BRANCH_ID = uuid4()
DEVICE_ID = uuid4()


def shift_row():
    return {
        "id": SHIFT_ID,
        "shift_number": "SHF-TEST-001",
        "company_id": COMPANY_ID,
        "shop_id": uuid4(),
        "branch_id": BRANCH_ID,
        "device_id": DEVICE_ID,
        "employee_id": EMPLOYEE_ID,
        "cashier_name": "Test Cashier",
        "cashier_role": "cashier",
        "shop_name": "Test Shop",
        "branch_name": "Main",
        "register_name": "Register 1",
        "status": "closed",
        "opened_at": datetime(2026, 10, 14, 8, tzinfo=timezone.utc),
        "closed_at": datetime(2026, 10, 14, 17, tzinfo=timezone.utc),
        "opening_note": None,
        "closing_note": None,
        "currencies": [{
            "currency_code": "USD", "currency_name": "US Dollar", "symbol": "$",
            "decimal_places": 2, "cash_accepted": True, "opening_float": Decimal("20.00"),
            "cash_sales": Decimal("50.00"), "cash_refunds": Decimal("2.00"),
            "cash_settlements": Decimal("5.00"), "cash_expenses": Decimal("3.00"),
            "cash_in": Decimal("0.00"), "cash_out": Decimal("0.00"),
            "cash_paid_out": Decimal("5.00"), "expected_cash": Decimal("70.00"),
            "counted_cash": Decimal("69.00"), "variance": Decimal("-1.00"),
        }],
        "summary": {
            "gross_sales_base": Decimal("50.00"), "net_sales_base": Decimal("48.00"),
            "total_sales_base": Decimal("48.00"), "cost_of_sales_base": Decimal("20.00"),
            "gross_profit_base": Decimal("28.00"), "discounts_base": Decimal("0.00"),
            "cash_sales_base": Decimal("48.00"), "card_sales_base": Decimal("0.00"),
            "mobile_sales_base": Decimal("0.00"), "credit_sales_base": Decimal("0.00"),
            "cash_settlements_base": Decimal("5.00"), "card_settlements_base": Decimal("0.00"),
            "mobile_settlements_base": Decimal("0.00"), "cash_expenses_base": Decimal("3.00"),
            "noncash_expenses_base": Decimal("0.00"), "cash_received_base": Decimal("55.00"),
            "cash_paid_out_base": Decimal("5.00"), "refunds_base": Decimal("2.00"),
            "base_currency_code": "USD",
        },
    }


class FakeShiftService:
    def __init__(self):
        self.history_call = None
        self.summary_call = None
        self.export_call = None

    async def history(self, company_id, actor, **filters):
        self.history_call = (company_id, filters)
        return [shift_row()], 1

    async def report_summary(self, company_id, actor, **filters):
        self.summary_call = (company_id, filters)
        return {
            "total_shifts": 1, "open_shifts": 0, "closed_shifts": 1,
            "total_sales_base": Decimal("48.00"), "cash_received_base": Decimal("55.00"),
            "base_currency_code": "USD",
            "variance_by_currency": [{"currency_code": "USD", "amount": Decimal("-1.00")}],
        }

    async def filter_options(self, company_id, actor):
        return {
            "cashiers": [{"id": EMPLOYEE_ID, "name": "Test Cashier", "role": "cashier"}],
            "branches": [{"id": BRANCH_ID, "name": "Main", "shop_name": "Test Shop"}],
            "devices": [{"id": DEVICE_ID, "name": "Register 1"}],
        }

    async def detail(self, company_id, shift_id, actor):
        if company_id != COMPANY_ID or shift_id != SHIFT_ID:
            from fastapi import HTTPException
            raise HTTPException(404, "Shift not found")
        return shift_row()

    async def export_history(self, company_id, actor, **filters):
        self.export_call = (company_id, filters)
        return [shift_row()], 1

    async def my_history(self, actor, *, page, page_size):
        return [shift_row()], 1

    async def my_detail(self, shift_id, actor):
        return shift_row()

    async def create_cash_movement(self, shift_id, data, actor):
        return {
            "id": uuid4(), "company_id": COMPANY_ID, "shift_id": shift_id,
            "branch_id": BRANCH_ID, "device_id": DEVICE_ID, "employee_id": EMPLOYEE_ID,
            "actor_name": "Test Cashier", "movement_type": data.movement_type,
            "currency_code": data.currency_code, "amount": data.amount,
            "reason": data.reason, "idempotency_key": data.idempotency_key,
            "created_at": datetime.now(timezone.utc),
        }


class ShiftReportsApiTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = FakeShiftService()
        actor = AuthActor("user", COMPANY_ID, "owner")

        async def override_actor():
            return actor

        async def override_service():
            return self.service

        self.original_overrides = dict(app.dependency_overrides)
        app.dependency_overrides[get_auth_actor] = override_actor
        app.dependency_overrides[get_service] = override_service

    def tearDown(self):
        app.dependency_overrides = self.original_overrides

    async def request(self, method, path, **kwargs):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    async def test_list_supports_filters_summary_names_and_pagination(self):
        start_at = "2026-10-14T00:00:00Z"
        end_at = "2026-10-15T00:00:00Z"
        response = await self.request(
            "GET", f"/api/shifts/company/{COMPANY_ID}",
            params={
                "branch_id": str(BRANCH_ID), "employee_id": str(EMPLOYEE_ID),
                "device_id": str(DEVICE_ID), "status": "closed",
                "start_at": start_at, "end_at": end_at, "page": 2, "page_size": 10,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["items"][0]["cashier_name"], "Test Cashier")
        self.assertEqual(body["items"][0]["branch_name"], "Main")
        self.assertEqual(body["items"][0]["register_name"], "Register 1")
        self.assertEqual(body["summary"]["base_currency_code"], "USD")
        self.assertEqual(self.service.history_call[1]["status"], "closed")
        self.assertEqual(self.service.summary_call[1]["employee_id"], EMPLOYEE_ID)

    async def test_filter_options_and_shift_details_are_available(self):
        options = await self.request("GET", f"/api/shifts/company/{COMPANY_ID}/filters")
        detail = await self.request("GET", f"/api/shifts/company/{COMPANY_ID}/{SHIFT_ID}")
        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.json()["devices"][0]["name"], "Register 1")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["currencies"][0]["expected_cash"], "70.00")

    async def test_company_isolation_denies_other_tenant_report(self):
        response = await self.request("GET", f"/api/shifts/company/{OTHER_COMPANY_ID}")
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.service.history_call)

    async def test_export_csv_contains_names_and_physical_currency_breakdown(self):
        response = await self.request("GET", f"/api/shifts/company/{COMPANY_ID}/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn("Test Cashier", response.text)
        self.assertIn("currency_cash_breakdown", response.text)
        self.assertIn("USD", response.text)

    async def test_export_csv_neutralizes_spreadsheet_formulas_in_names(self):
        row = shift_row()
        row["cashier_name"] = "=HYPERLINK(\"https://example.invalid\")"
        self.service.export_history = AsyncMock(return_value=([row], 1))
        response = await self.request("GET", f"/api/shifts/company/{COMPANY_ID}/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=HYPERLINK", response.text)

    async def test_cashier_history_and_cash_movement_routes_are_registered(self):
        history = await self.request("GET", "/api/shifts/my-history", params={"page": 1, "page_size": 10})
        detail = await self.request("GET", f"/api/shifts/mine/{SHIFT_ID}")
        movement = await self.request("POST", f"/api/shifts/{SHIFT_ID}/cash-movements", json={
            "movement_type": "cash_in", "currency_code": "usd", "amount": "2.00",
            "reason": "Float top-up", "idempotency_key": "api-cash-in-0001",
        })
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["total"], 1)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(movement.status_code, 200)
        self.assertEqual(movement.json()["currency_code"], "USD")
        self.assertEqual(movement.json()["actor_name"], "Test Cashier")


class CashMovementSchemaTest(unittest.TestCase):
    def test_cash_movement_requires_positive_amount_reason_and_currency(self):
        from pydantic import ValidationError
        from app.shifts.schema import CashMovementCreate

        parsed = CashMovementCreate(
            movement_type="cash_out", currency_code=" zar ", amount="5.25",
            reason="Petty cash", idempotency_key="cash-out-schema-1",
        )
        self.assertEqual(parsed.currency_code, "ZAR")
        self.assertEqual(parsed.reason, "Petty cash")
        for values in (
            {"movement_type": "cash_in", "currency_code": "USD", "amount": "0", "reason": "x", "idempotency_key": "schema-key-000"},
            {"movement_type": "cash_in", "currency_code": "USD", "amount": "-1", "reason": "x", "idempotency_key": "schema-key-001"},
            {"movement_type": "cash_in", "currency_code": "USD", "amount": "1", "reason": "  ", "idempotency_key": "schema-key-002"},
        ):
            with self.assertRaises(ValidationError):
                CashMovementCreate(**values)


class ShiftReportCashCalculationTest(unittest.IsolatedAsyncioTestCase):
    async def test_open_shift_expected_cash_stays_separate_by_physical_currency(self):
        usd = SimpleNamespace(
            currency_code="USD", currency_name_snapshot="US Dollar", currency_symbol_snapshot="$",
            decimal_places_snapshot=2, cash_accepted_snapshot=True, opening_float=Decimal("20.00"), cash_sales=None,
            cash_refunds=None, cash_settlements=None, cash_expenses=None,
            expected_cash=None, counted_cash=None, variance=None,
        )
        zar = SimpleNamespace(
            currency_code="ZAR", currency_name_snapshot="South African Rand", currency_symbol_snapshot="R",
            decimal_places_snapshot=2, cash_accepted_snapshot=True, opening_float=Decimal("500.00"), cash_sales=None,
            cash_refunds=None, cash_settlements=None, cash_expenses=None,
            expected_cash=None, counted_cash=None, variance=None,
        )

        class ReportRepo:
            async def snapshots(self, _shift_id):
                return [usd, zar]

            async def identity(self, _shift):
                return {"cashier_name": "Cashier", "branch_name": "Main", "register_name": "Register 1"}

        service = ShiftService(ReportRepo())
        service._currency_activity = AsyncMock(side_effect=[
            (Decimal("40"), Decimal("5"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("1")),
            (Decimal("100"), Decimal("0"), Decimal("20"), Decimal("15"), Decimal("0"), Decimal("0")),
        ])
        service._base_summary = AsyncMock(return_value={
            "gross_sales_base": Decimal("140"), "net_sales_base": Decimal("140"),
            "cost_of_sales_base": Decimal("0"), "gross_profit_base": Decimal("140"),
            "discounts_base": Decimal("0"), "cash_sales_base": Decimal("140"),
            "card_sales_base": Decimal("0"), "mobile_sales_base": Decimal("0"),
            "credit_sales_base": Decimal("0"), "cash_settlements_base": Decimal("22"),
            "card_settlements_base": Decimal("0"), "mobile_settlements_base": Decimal("0"),
            "cash_expenses_base": Decimal("18"), "noncash_expenses_base": Decimal("0"),
        })
        shift = SimpleNamespace(
            id=uuid4(), company_id=COMPANY_ID, shift_number="SHIFT-OPEN", shop_id=uuid4(),
            branch_id=BRANCH_ID, device_id=DEVICE_ID, employee_id=EMPLOYEE_ID,
            status="open", opened_at=datetime.now(timezone.utc), closed_at=None,
            opening_note=None, closing_note=None,
            **{name: None for name in (
                "gross_sales_base", "net_sales_base", "cost_of_sales_base", "gross_profit_base",
                "discounts_base", "cash_sales_base", "card_sales_base", "mobile_sales_base",
                "credit_sales_base", "cash_settlements_base", "card_settlements_base",
                "mobile_settlements_base", "cash_expenses_base", "noncash_expenses_base",
            )},
        )

        view = await service.view(shift)

        expected = {row["currency_code"]: row["expected_cash"] for row in view["currencies"]}
        self.assertEqual(expected, {"USD": Decimal("57.00"), "ZAR": Decimal("605.00")})
        self.assertEqual(
            {row["currency_code"]: row["cash_paid_out"] for row in view["currencies"]},
            {"USD": Decimal("9.00"), "ZAR": Decimal("15.00")},
        )
        self.assertEqual(view["summary"]["total_sales_base"], Decimal("140"))


if __name__ == "__main__":
    unittest.main()
