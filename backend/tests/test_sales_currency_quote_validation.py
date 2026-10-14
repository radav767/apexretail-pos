from unittest import TestCase
from uuid import uuid4
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException

from app.sales.schema import SaleCreate
from app.sales.service import SalesService
from app.currencies.service import CurrencyService


class CurrencyQuoteValidationTests(TestCase):
    def _sale(self, *, version=3, rate_id=None):
        return SaleCreate(
            company_id=uuid4(),
            payment_method="cash",
            payment_currency_code="ZAR",
            currency_config_version=version,
            exchange_rate_id=rate_id,
            items=[],
        )

    def test_current_quote_is_accepted(self):
        rate_id = uuid4()
        SalesService.validate_currency_quote(
            self._sale(rate_id=rate_id), {"exchange_rate_id": rate_id}, 3
        )

    def test_changed_currency_configuration_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            SalesService.validate_currency_quote(
                self._sale(), {"exchange_rate_id": None}, 4
            )
        self.assertEqual(raised.exception.status_code, 409)

    def test_changed_exchange_rate_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            SalesService.validate_currency_quote(
                self._sale(rate_id=uuid4()), {"exchange_rate_id": uuid4()}, 3
            )
        self.assertEqual(raised.exception.status_code, 409)

    def test_legacy_callers_without_quote_fields_remain_compatible(self):
        data = self._sale(version=None)
        data.exchange_rate_id = None
        SalesService.validate_currency_quote(data, {"exchange_rate_id": uuid4()}, None)


class FakeCurrencyRepository:
    def __init__(self, *, card_allowed=True, rate=Decimal("1.5000000000"), company_id=None):
        self.company_id = company_id or uuid4()
        self.base_currency = SimpleNamespace(
            id=uuid4(), company_id=self.company_id, code="USD", symbol="$",
            decimal_places=2, active=True, is_base=True,
        )
        self.foreign_currency = SimpleNamespace(
            id=uuid4(), company_id=self.company_id, code="ZAR", symbol="R",
            decimal_places=2, active=True, is_base=False, cash_accepted=True,
            card_accepted=card_allowed, mobile_accepted=True,
        )
        self.settings_row = SimpleNamespace(
            currency_code="USD", currency_symbol="$", decimal_places=2,
            base_currency_id=self.base_currency.id, multi_currency_enabled=True,
        )
        self.rate = SimpleNamespace(id=uuid4(), foreign_units_per_base=rate) if rate is not None else None

    async def settings(self, company_id, **kwargs):
        return self.settings_row if company_id == self.company_id else None

    async def base(self, company_id):
        return self.base_currency if company_id == self.company_id else None

    async def by_code(self, company_id, code, active=True):
        if company_id != self.company_id:
            return None
        return {"USD": self.base_currency, "ZAR": self.foreign_currency}.get(code)

    async def current_rate(self, company_id, currency_id, at):
        return self.rate if company_id == self.company_id and currency_id == self.foreign_currency.id else None


class CurrencyResolutionTests(TestCase):
    def test_foreign_conversion_and_rate_snapshot_are_decimal_exact(self):
        repo = FakeCurrencyRepository(rate=Decimal("18.5000000000"))
        snapshot = __import__("asyncio").run(
            CurrencyService(repo).resolve_from_base(
                repo.company_id, "cash", "ZAR", Decimal("10.00"),
                at=datetime.now(timezone.utc),
            )
        )
        self.assertEqual(snapshot["original_amount"], Decimal("185.00"))
        self.assertEqual(snapshot["base_amount"], Decimal("10.00"))
        self.assertEqual(snapshot["exchange_rate_snapshot"], Decimal("18.5000000000"))

    def test_payment_method_restriction_is_enforced(self):
        repo = FakeCurrencyRepository(card_allowed=False)
        with self.assertRaises(HTTPException) as raised:
            __import__("asyncio").run(
                CurrencyService(repo).resolve_from_base(
                    repo.company_id, "card", "ZAR", Decimal("1.00"),
                )
            )
        self.assertEqual(raised.exception.status_code, 409)

    def test_missing_exchange_rate_is_rejected(self):
        repo = FakeCurrencyRepository(rate=None)
        with self.assertRaises(HTTPException) as raised:
            __import__("asyncio").run(
                CurrencyService(repo).resolve_from_base(
                    repo.company_id, "cash", "ZAR", Decimal("1.00"),
                )
            )
        self.assertEqual(raised.exception.status_code, 409)

    def test_other_company_currency_is_not_resolvable(self):
        repo = FakeCurrencyRepository()
        with self.assertRaises(HTTPException) as raised:
            __import__("asyncio").run(
                CurrencyService(repo).resolve_from_base(
                    uuid4(), "cash", "ZAR", Decimal("1.00"),
                )
            )
        self.assertEqual(raised.exception.status_code, 409)
