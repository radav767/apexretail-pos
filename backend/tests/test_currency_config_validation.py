import unittest
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import httpx

from app.auth.dependencies import AuthActor, get_auth_actor
from app.currencies.repository import CurrencyRepository
from app.currencies.router import get_service
from app.currencies.service import CurrencyService
from app.main import app
from app.models import CompanyCurrency


COMPANY_ID = uuid4()


class SpyDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)


class StubCurrencyRepository(CurrencyRepository):
    def __init__(self, *, settings=True, base=True):
        self.db = SpyDb()
        self._settings = (
            SimpleNamespace(
                base_currency_id=None,
                currency_code="USD",
                currency_symbol="$",
                decimal_places=2,
                currency_config_version=1,
                multi_currency_enabled=False,
            )
            if settings is True
            else settings
        )
        self._base = (
            CompanyCurrency(
                id=uuid4(), company_id=COMPANY_ID, code="USD",
                display_name="US Dollar", symbol="$", decimal_places=2,
                active=True, is_base=True, cash_accepted=True,
                card_accepted=True, mobile_accepted=True, display_order=0,
            )
            if base is True
            else base
        )
        if self._settings is not None and self._base is not None:
            self._settings.base_currency_id = self._base.id

    async def settings(self, _company_id, *, for_update=False):
        return self._settings

    async def base(self, _company_id):
        return self._base

    async def list(self, _company_id, *, active=None, for_update=False):
        if self._base is None:
            return []
        return [self._base] if active is not False else []

    async def recent_effective_rates(self, *_args, **_kwargs):
        return []


class CurrencyConfigValidationApiTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repo = StubCurrencyRepository()
        actor = AuthActor("user", COMPANY_ID, "owner")
        self.actor = actor
        self.service = CurrencyService(self.repo)

        async def override_actor():
            return self.actor

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

    async def test_pos_config_returns_explicit_base_currency(self):
        response = await self.request("GET", f"/api/currencies/{COMPANY_ID}/pos-config")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["base_currency_code"], "USD")
        self.assertEqual(response.json()["currencies"][0]["code"], "USD")
        self.assertEqual(self.repo.db.added, [])

    async def test_pos_config_fails_closed_when_base_currency_is_missing(self):
        self.repo._base = None

        response = await self.request("GET", f"/api/currencies/{COMPANY_ID}/pos-config")

        self.assertEqual(response.status_code, 409)
        self.assertIn("incomplete", response.json()["detail"])
        self.assertEqual(self.repo.db.added, [])

    async def test_pos_config_fails_closed_when_company_settings_are_missing(self):
        self.repo._settings = None

        response = await self.request("GET", f"/api/currencies/{COMPANY_ID}/pos-config")

        self.assertEqual(response.status_code, 409)
        self.assertIn("incomplete", response.json()["detail"])
        self.assertEqual(self.repo.db.added, [])

    async def test_financial_conversion_fails_closed_without_configuration(self):
        self.repo._base = None
        with self.assertRaises(HTTPException) as caught:
            await self.service.resolve_from_base(
                COMPANY_ID, "cash", "USD", Decimal("1.00")
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.repo.db.added, [])

        self.repo._base = CompanyCurrency(
            id=uuid4(), company_id=COMPANY_ID, code="USD",
            display_name="US Dollar", symbol="$", decimal_places=2,
            active=True, is_base=True, cash_accepted=True,
            card_accepted=True, mobile_accepted=True, display_order=0,
        )
        self.repo._settings = None
        with self.assertRaises(HTTPException) as caught:
            await self.service.resolve_snapshot(
                COMPANY_ID, "cash", "USD", Decimal("1.00")
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.repo.db.added, [])

    async def test_pos_config_fails_closed_when_base_link_or_values_are_inconsistent(self):
        for field, value in (
            ("base_currency_id", uuid4()),
            ("currency_code", "EUR"),
            ("currency_symbol", "€"),
            ("decimal_places", 0),
        ):
            with self.subTest(field=field):
                self.repo._settings = SimpleNamespace(
                    base_currency_id=self.repo._base.id,
                    currency_code="USD",
                    currency_symbol="$",
                    decimal_places=2,
                    currency_config_version=1,
                    multi_currency_enabled=False,
                )
                setattr(self.repo._settings, field, value)

                response = await self.request("GET", f"/api/currencies/{COMPANY_ID}/pos-config")

                self.assertEqual(response.status_code, 409)
                self.assertIn("inconsistent", response.json()["detail"])
                self.assertEqual(self.repo.db.added, [])

    async def test_currency_create_api_rejects_malformed_or_blank_fields(self):
        base_payload = {
            "company_id": str(COMPANY_ID),
            "code": "EUR",
            "display_name": "Euro",
            "symbol": "€",
        }
        for field, invalid in (
            ("code", "USD/EUR"),
            ("code", "   "),
            ("display_name", "   "),
            ("symbol", "   "),
        ):
            with self.subTest(field=field, invalid=invalid):
                response = await self.request(
                    "POST", "/api/currencies", json={**base_payload, field: invalid}
                )
                self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
