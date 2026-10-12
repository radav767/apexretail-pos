import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.auth.repository import AuthRepository
from app.auth.schema import RegisterRequest
from app.auth.service import AuthService
from app.models import (
    AuditEvent,
    Branch,
    Company,
    CompanyCurrency,
    CompanySetting,
    CompanySubscription,
    CompanySubscriptionHistory,
    Device,
    Employee,
    Shop,
    User,
)
from app.subscriptions.service import SubscriptionService


TEST_DATABASE_ENV = "APEX_REGISTRATION_TEST_DATABASE_URL"


def registration_request(
    *,
    email: str = "owner-one@example.com",
    business_name: str = "Atomic Shop One",
    currency_code: str = "USD",
    currency_symbol: str = "$",
    decimal_places: int = 2,
) -> RegisterRequest:
    return RegisterRequest(
        owner_name="Registration Owner",
        owner_pin="2468",
        business_name=business_name,
        business_type="Retail",
        country="Test Country",
        phone="+1 555 0100",
        email=email,
        password="registration-test-password",
        confirm_password="registration-test-password",
        device_key=f"registration-device-{email}",
        base_currency_code=currency_code,
        base_currency_symbol=currency_symbol,
        base_currency_decimal_places=decimal_places,
    )


class RegistrationCurrencyValidationTest(unittest.TestCase):
    def test_currency_is_required(self):
        payload = registration_request().model_dump()
        payload.pop("base_currency_code")
        with self.assertRaises(ValidationError):
            RegisterRequest(**payload)

    def test_unknown_currency_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "supported base currency"):
            registration_request(currency_code="XYZ", currency_symbol="X")

    def test_known_currency_symbol_and_precision_must_match(self):
        with self.assertRaisesRegex(ValidationError, "symbol for EUR"):
            registration_request(currency_code="EUR", currency_symbol="$")
        with self.assertRaisesRegex(ValidationError, "decimal precision for JPY"):
            registration_request(
                currency_code="JPY",
                currency_symbol="¥",
                decimal_places=2,
            )

    def test_currency_code_is_normalized_without_a_default(self):
        request = registration_request(currency_code=" eur ", currency_symbol="€")
        self.assertEqual(request.base_currency_code, "EUR")
        self.assertEqual(request.base_currency_decimal_places, 2)


class RegistrationAtomicityPostgresTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database_url = os.getenv(TEST_DATABASE_ENV)
        if not database_url:
            self.skipTest(f"{TEST_DATABASE_ENV} is not configured")
        parsed = make_url(database_url)
        if not (parsed.database or "").startswith("apexretail_registration_test_"):
            self.fail("refusing non-registration test database")
        self.engine = create_async_engine(database_url)
        async with self.engine.begin() as connection:
            await connection.execute(text("""
                TRUNCATE audit_events, company_subscription_history,
                company_subscriptions, company_settings,
                currency_exchange_rates, company_currencies, pos_sessions,
                employees, devices, users, branches, shops, companies CASCADE
            """))
        self.addAsyncCleanup(self.engine.dispose)

    @staticmethod
    def service(session: AsyncSession) -> AuthService:
        return AuthService(AuthRepository(session))

    async def register(self, data: RegisterRequest):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            with patch(
                "app.auth.service.get_settings",
                return_value=SimpleNamespace(
                    subscription_offline_grace_hours=72,
                    subscription_provider_name=None,
                ),
            ):
                return await self.service(session).register(data)

    async def scalar_count(self, model) -> int:
        async with AsyncSession(self.engine) as session:
            return int(
                (await session.execute(select(func.count()).select_from(model))).scalar_one()
            )

    async def test_success_creates_complete_atomic_registration(self):
        result = await self.register(registration_request())
        company_id = result["company"]["id"]

        async with AsyncSession(self.engine) as session:
            setting = (
                await session.execute(
                    select(CompanySetting).where(
                        CompanySetting.company_id == company_id
                    )
                )
            ).scalar_one()
            currency = (
                await session.execute(
                    select(CompanyCurrency).where(
                        CompanyCurrency.company_id == company_id,
                        CompanyCurrency.is_base.is_(True),
                    )
                )
            ).scalar_one()
            audit = (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.company_id == company_id,
                        AuditEvent.action == "company_registered",
                    )
                )
            ).scalar_one()

            self.assertEqual(setting.base_currency_id, currency.id)
            self.assertEqual(setting.currency_code, "USD")
            self.assertEqual(setting.currency_symbol, "$")
            self.assertEqual(setting.decimal_places, 2)
            self.assertFalse(setting.shift_enforcement_enabled)
            self.assertTrue(currency.active)
            self.assertTrue(currency.is_base)
            self.assertEqual(audit.details["base_currency"], "USD")

        for model in (
            Company,
            Shop,
            Branch,
            User,
            Employee,
            Device,
            CompanySetting,
            CompanyCurrency,
            CompanySubscription,
            CompanySubscriptionHistory,
        ):
            self.assertEqual(await self.scalar_count(model), 1)

    async def test_failure_rolls_back_every_registration_record(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = self.service(session)
            with (
                patch(
                    "app.auth.service.get_settings",
                    return_value=SimpleNamespace(
                        subscription_offline_grace_hours=72,
                        subscription_provider_name=None,
                    ),
                ),
                patch.object(
                    SubscriptionService,
                    "get_or_create_trial",
                    new=AsyncMock(side_effect=RuntimeError("test-only failure")),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "test-only failure"):
                    await service.register(registration_request())

        for model in (
            Company,
            Shop,
            Branch,
            User,
            Employee,
            Device,
            CompanySetting,
            CompanyCurrency,
            AuditEvent,
        ):
            self.assertEqual(await self.scalar_count(model), 0)

    async def test_repeated_registration_is_rejected_without_duplicates(self):
        request = registration_request()
        await self.register(request)
        with self.assertRaises(HTTPException) as error:
            await self.register(request)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(await self.scalar_count(Company), 1)
        self.assertEqual(await self.scalar_count(CompanySetting), 1)
        self.assertEqual(await self.scalar_count(CompanyCurrency), 1)

    async def test_concurrent_registration_retry_creates_one_complete_company(self):
        request = registration_request()
        results = await asyncio.gather(
            self.register(request),
            self.register(request),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        conflicts = [
            result
            for result in results
            if isinstance(result, HTTPException) and result.status_code == 409
        ]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(await self.scalar_count(Company), 1)
        self.assertEqual(await self.scalar_count(CompanySetting), 1)
        self.assertEqual(await self.scalar_count(CompanyCurrency), 1)
        self.assertEqual(await self.scalar_count(CompanySubscription), 1)

    async def test_company_currency_settings_are_isolated(self):
        first = await self.register(registration_request())
        second = await self.register(
            registration_request(
                email="owner-two@example.com",
                business_name="Atomic Shop Two",
                currency_code="EUR",
                currency_symbol="€",
            )
        )
        async with AsyncSession(self.engine) as session:
            rows = list(
                (
                    await session.execute(
                        select(CompanySetting.company_id, CompanySetting.currency_code)
                        .order_by(CompanySetting.currency_code)
                    )
                ).all()
            )
        self.assertEqual(
            {(str(company_id), code) for company_id, code in rows},
            {
                (first["company"]["id"], "USD"),
                (second["company"]["id"], "EUR"),
            },
        )
