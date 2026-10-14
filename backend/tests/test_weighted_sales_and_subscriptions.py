import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.auth.security import (
    create_entitlement_snapshot_token,
    decode_entitlement_token,
)
from app.sales.schema import SaleCreate, SaleItemCreate
from app.sales.service import SalesService
from app.subscriptions.paynow import build_hash, validate_hash
from app.subscriptions.service import SubscriptionService


UTC = timezone.utc


class FakeSalesRepo:
    def __init__(self):
        self.db = object()
        self.base_currency = SimpleNamespace(code="EUR", decimal_places=2, is_base=True)
        self.product = SimpleNamespace(
            id=uuid4(),
            name="Beef",
            unit="kg",
            selling_price=Decimal("4.00"),
            cost_price=Decimal("2.00"),
        )
        self.balance = SimpleNamespace(quantity=Decimal("1.000"))
        self.saved = None

    async def get_by_client_sale_id(self, *_args, **_kwargs):
        return None

    async def resolve_branch(self, *_args, **_kwargs):
        return SimpleNamespace(id=uuid4(), shop_id=uuid4(), name="Front")

    async def get_device(self, *_args, **_kwargs):
        return None

    async def get_shop(self, *_args, **_kwargs):
        return SimpleNamespace(
            id=uuid4(),
            name="Main Shop",
            address_line_1=None,
            address_line_2=None,
            city=None,
            state_province=None,
            country=None,
            phone=None,
            tax_vat_number=None,
        )

    async def get_product(self, *_args, **_kwargs):
        return self.product

    async def get_balance(self, *_args, **_kwargs):
        return self.balance

    async def sync_product_total(self, _product):
        return self.balance.quantity

    async def get_employee(self, *_args, **_kwargs):
        return None

    async def save_sale(self, sale, sale_items, products, balances, inventory_movements):
        self.saved = {
            "sale": sale,
            "items": sale_items,
            "movements": inventory_movements,
        }
        return sale


class WeightedSalesTest(unittest.IsolatedAsyncioTestCase):
    async def test_weighted_sale_uses_decimal_quantity_and_preserves_snapshot(self):
        repo = FakeSalesRepo()
        service = SalesService(repo)
        payload = SaleCreate(
            company_id=uuid4(),
            payment_method="cash",
            amount_received=Decimal("1.00"),
            items=[
                SaleItemCreate(
                    product_id=repo.product.id,
                    quantity=Decimal("0.250"),
                    selling_unit="kg",
                    unit_price=Decimal("4.00"),
                    line_total=Decimal("1.00"),
                )
            ],
        )

        with patch(
            "app.sales.service.BusinessSettingsService.get",
            return_value={
                "tax_name": "Tax",
                "tax_rate": Decimal("0"),
                "tax_inclusive": False,
                "receipt_footer": "Thank you",
            },
        ):
            sale = await service.create_sale(payload, actor=None)

        self.assertEqual(sale.total_amount, Decimal("1.00"))
        self.assertEqual(sale.base_currency_code, "EUR")
        self.assertEqual(sale.payment_currency_code, "EUR")
        self.assertEqual(sale.exchange_rate_snapshot, Decimal("1"))
        self.assertEqual(repo.balance.quantity, Decimal("0.750"))
        saved_item = repo.saved["items"][0]
        self.assertEqual(saved_item.quantity, Decimal("0.250"))
        self.assertEqual(saved_item.selling_unit, "kg")
        self.assertEqual(saved_item.unit_price, Decimal("4.00"))
        self.assertEqual(saved_item.line_total, Decimal("1.00"))
        movement = repo.saved["movements"][0]
        self.assertEqual(movement.quantity, Decimal("0.250"))


class FakeSubscriptionDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def execute(self, *_args, **_kwargs):
        event = next(
            (
                item
                for item in reversed(self.added)
                if item.__class__.__name__ == "SubscriptionWebhookEvent"
            ),
            None,
        )
        return SimpleNamespace(
            scalar_one_or_none=lambda: event,
            scalar_one=lambda: event,
            scalars=lambda: SimpleNamespace(
                all=lambda: [],
                first=lambda: None,
            ),
        )

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, _value):
        return None


class TrialCreationTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_or_create_trial_is_idempotent(self):
        company_id = uuid4()
        db = FakeSubscriptionDb()
        service = SubscriptionService(db)
        existing_subscription = SimpleNamespace(
            status="trial",
            company_id=company_id,
            plan=None,
            trial_started_at=datetime.now(UTC),
            trial_ends_at=datetime.now(UTC) + timedelta(days=30),
            current_period_started_at=None,
            current_period_ends_at=None,
            grace_ends_at=datetime.now(UTC) + timedelta(days=30, hours=72),
        )
        service.get_current = AsyncMock(
            side_effect=[None, existing_subscription]
        )

        trial = await service.get_or_create_trial(company_id)
        existing = await service.get_or_create_trial(company_id)

        self.assertEqual(trial.status, "trial")
        self.assertEqual((trial.trial_ends_at - trial.trial_started_at).days, 30)
        self.assertEqual(existing.status, "trial")


class SubscriptionSecurityTest(unittest.TestCase):
    def test_webhook_signature_verification_rejects_invalid_signature(self):
        service = SubscriptionService(
            db=SimpleNamespace(),
            provider_name="generic",
            checkout_base_url="https://pay.example.test/checkout",
            webhook_secret="webhook-secret",
        )
        body = b'{"provider":"generic"}'
        with self.assertRaises(HTTPException):
            service.verify_webhook_signature(
                body=body,
                provided_signature="sha256=bad",
            )

    def test_entitlement_token_rejects_symmetric_signing(self):
        now = datetime.now(UTC)
        settings = SimpleNamespace(
            jwt_secret="test-secret",
            jwt_algorithm="HS256",
            entitlement_signing_algorithm="HS256",
            entitlement_private_key=None,
            entitlement_public_key=None,
        )
        with patch("app.auth.security.get_settings", return_value=settings):
            with self.assertRaises(RuntimeError):
                create_entitlement_snapshot_token(
                    company_id="company-1",
                    status="active",
                    plan="monthly",
                    offline_grace_expires_at=now + timedelta(hours=4),
                    snapshot_expires_at=now + timedelta(hours=1),
                )


class SubscriptionPresentationTest(unittest.TestCase):
    def test_page_maps_grace_period_to_past_due_and_reports_missing_provider_config(self):
        company_id = uuid4()

        class FakeResult:
            def scalars(self):
                return self

            def all(self):
                return []

            def first(self):
                return None

        class FakeDb:
            async def execute(self, *_args, **_kwargs):
                return FakeResult()

        service = SubscriptionService(
            db=FakeDb(),
            offline_grace_hours=72,
        )
        subscription = SimpleNamespace(
            company_id=company_id,
            plan="monthly",
            status="grace_period",
            trial_started_at=None,
            trial_ends_at=None,
            current_period_started_at=datetime(2026, 8, 1, tzinfo=UTC),
            current_period_ends_at=datetime(2026, 8, 31, tzinfo=UTC),
            grace_ends_at=datetime(2026, 9, 3, tzinfo=UTC),
            provider=None,
            provider_reference=None,
            licensed_terminal_count=None,
            status_reason="Payment overdue",
        )
        service.ensure_current = AsyncMock(return_value=subscription)
        service.snapshot_for = lambda _subscription: {
            "status": "grace_period",
            "display_status": "past_due",
            "display_status_label": "Past due",
            "plan": "monthly",
            "effective_until": subscription.current_period_ends_at,
            "offline_grace_expires_at": subscription.grace_ends_at,
            "snapshot_token": "token",
            "snapshot_expires_at": subscription.grace_ends_at,
            "writes_allowed": True,
            "message": None,
        }

        page = self.async_run(service.page(company_id))

        self.assertEqual(page["current"]["display_status"], "past_due")
        self.assertEqual(page["current"]["display_status_label"], "Past due")
        self.assertEqual(page["current"]["plan_label"], "Monthly")
        self.assertEqual(
            page["current"]["renewal_or_expiry_at"],
            subscription.grace_ends_at,
        )
        self.assertEqual(page["usage"]["billable_terminals"], 0)
        self.assertEqual(page["billing_options"][0]["terminal_count"], 0)
        self.assertFalse(page["activation_available"])
        self.assertFalse(page["checkout_configured"])
        self.assertFalse(page["webhook_configured"])
        self.assertEqual(len(page["payment_configuration_required"]), 5)

    def test_enforce_writes_allowed_returns_clear_message_for_expired_company(self):
        company_id = uuid4()
        service = SubscriptionService(db=SimpleNamespace())
        service.ensure_current = AsyncMock(
            return_value=SimpleNamespace(status="expired")
        )

        with self.assertRaises(HTTPException) as error:
            self.async_run(service.enforce_writes_allowed(company_id))

        self.assertEqual(error.exception.status_code, 402)
        self.assertEqual(
            error.exception.detail,
            "This subscription is no longer active. Renew it to continue creating new sales or changing billable records.",
        )

    def async_run(self, coroutine):
        import asyncio

        return asyncio.run(coroutine)


class PaynowHashTest(unittest.TestCase):
    def test_validate_hash_accepts_valid_payload(self):
        pairs = [
            ("reference", "APR-SUB-1"),
            ("amount", "8.00"),
            ("status", "Paid"),
        ]
        hash_value = build_hash(pairs, "secret-key")
        signed_pairs = [*pairs, ("hash", hash_value)]

        self.assertTrue(
            validate_hash(
                signed_pairs,
                "secret-key",
            )
        )

    def test_validate_hash_rejects_modified_payload(self):
        pairs = [
            ("reference", "APR-SUB-1"),
            ("amount", "8.00"),
            ("status", "Paid"),
            ("hash", build_hash(
                [
                    ("reference", "APR-SUB-1"),
                    ("amount", "8.00"),
                    ("status", "Paid"),
                ],
                "secret-key",
            )),
        ]

        tampered = list(pairs)
        tampered[1] = ("amount", "9.00")

        self.assertFalse(
            validate_hash(
                tampered,
                "secret-key",
            )
        )


class PaynowSubscriptionServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeSubscriptionDb()
        self.service = SubscriptionService(
            self.db,
            provider_name="paynow",
            paynow_integration_id="12345",
            paynow_integration_key="integration-key",
            paynow_return_url="https://backoffice.apexpos.cloud",
            paynow_result_url="https://api.apexpos.cloud/api/subscriptions/paynow/result",
        )
        self.subscription = SimpleNamespace(
            id=uuid4(),
            company_id=uuid4(),
            plan=None,
            status="trial",
            trial_started_at=datetime.now(UTC),
            trial_ends_at=datetime.now(UTC) + timedelta(days=30),
            current_period_started_at=None,
            current_period_ends_at=None,
            grace_ends_at=datetime.now(UTC) + timedelta(days=33),
            provider=None,
            provider_reference=None,
            billing_currency="USD",
            licensed_terminal_count=None,
            unit_price=None,
            total_amount=None,
            status_reason="Initial 30-day free trial",
        )
        self.company = SimpleNamespace(
            id=self.subscription.company_id,
            owner_email="owner@example.com",
        )

    def build_paynow_initiation_response(
        self,
        *,
        reference: str,
        amount: str,
        browser_url: str = "https://paynow.test/go",
        poll_url: str = "https://www.paynow.co.zw/interface/poll/?guid=1",
        paynow_reference: str = "PNW-123",
        status: str = "Ok",
    ) -> bytes:
        pairs = [
            ("status", status),
            ("browserurl", browser_url),
            ("pollurl", poll_url),
            ("reference", reference),
            ("paynowreference", paynow_reference),
            ("amount", amount),
        ]
        pairs.append(
            (
                "hash",
                build_hash(
                    pairs,
                    "integration-key",
                ),
            )
        )
        return urlencode(pairs).encode("utf-8")

    def build_paynow_body(
        self,
        *,
        reference: str,
        amount: str,
        status: str,
        paynow_reference: str = "PNW-123",
        poll_url: str = "https://www.paynow.co.zw/interface/poll/?guid=1",
    ) -> bytes:
        pairs = [
            ("reference", reference),
            ("paynowreference", paynow_reference),
            ("amount", amount),
            ("status", status),
            ("pollurl", poll_url),
        ]
        pairs.append(
            (
                "hash",
                build_hash(
                    pairs,
                    "integration-key",
                ),
            )
        )
        return urlencode(pairs).encode("utf-8")

    async def test_activate_or_renew_with_paynow_uses_one_terminal_monthly_price(self):
        self.service.ensure_current = AsyncMock(
            return_value=self.subscription
        )
        self.service.get_company = AsyncMock(
            return_value=self.company
        )
        self.service.send_paynow_request = AsyncMock(
            return_value=self.build_paynow_initiation_response(
                reference="APR-SUB-TEST",
                amount="8.00",
            )
        )
        self.service.create_session_reference = lambda: "APR-SUB-TEST"
        self.service.get_billable_device_ids = AsyncMock(
            return_value=[uuid4()]
        )

        result = await self.service.activate_or_renew(
            self.subscription.company_id,
            "monthly",
        )

        self.assertEqual(result["provider"], "paynow")
        self.assertEqual(result["checkout_session_reference"], "APR-SUB-TEST")
        checkout = next(
            item
            for item in self.db.added
            if item.__class__.__name__ == "SubscriptionCheckoutSession"
        )
        self.assertEqual(checkout.unit_price, Decimal("8.00"))
        self.assertEqual(checkout.terminal_count, 1)
        self.assertEqual(checkout.total_amount, Decimal("8.00"))

    async def test_send_paynow_request_uses_async_transport(self):
        captured_request = None

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, content=b"status=Ok")

        transport = httpx.MockTransport(handler)
        with patch(
            "app.subscriptions.service.httpx.AsyncHTTPTransport",
            return_value=transport,
        ) as async_transport:
            response = await self.service.send_paynow_request(
                [("reference", "APR-SUB-TEST")]
            )

        async_transport.assert_called_once_with()
        self.assertEqual(response, b"status=Ok")
        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.method, "POST")
        self.assertEqual(
            str(captured_request.url),
            "https://www.paynow.co.zw/interface/initiatetransaction",
        )
        self.assertEqual(
            captured_request.content,
            b"reference=APR-SUB-TEST",
        )

    async def test_send_paynow_request_maps_transport_failure_to_502(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(
                "Payment service connection failed",
                request=request,
            )

        transport = httpx.MockTransport(handler)
        with patch(
            "app.subscriptions.service.httpx.AsyncHTTPTransport",
            return_value=transport,
        ):
            with self.assertRaises(HTTPException) as error:
                await self.service.send_paynow_request(
                    [("reference", "APR-SUB-TEST")]
                )

        self.assertEqual(error.exception.status_code, 502)
        self.assertEqual(
            error.exception.detail,
            "The payment service is temporarily unavailable. Please try again.",
        )

    async def test_activate_or_renew_with_paynow_uses_multiple_terminal_yearly_price(self):
        self.service.ensure_current = AsyncMock(
            return_value=self.subscription
        )
        self.service.get_company = AsyncMock(
            return_value=self.company
        )
        response_pairs = [
            ("status", "Ok"),
            ("browserurl", "https://paynow.test/go"),
            ("pollurl", "https://www.paynow.co.zw/interface/poll/?guid=2"),
            ("reference", "APR-SUB-YEAR"),
            ("paynowreference", "PNW-456"),
            ("amount", "288.00"),
        ]
        response_pairs.append(
            (
                "hash",
                build_hash(
                    response_pairs,
                    "integration-key",
                ),
            )
        )
        self.service.send_paynow_request = AsyncMock(
            return_value=urlencode(response_pairs).encode("utf-8")
        )
        self.service.create_session_reference = lambda: "APR-SUB-YEAR"
        self.service.get_billable_device_ids = AsyncMock(
            return_value=[uuid4(), uuid4(), uuid4()]
        )

        await self.service.activate_or_renew(
            self.subscription.company_id,
            "yearly",
        )

        checkout = next(
            item
            for item in self.db.added
            if item.__class__.__name__ == "SubscriptionCheckoutSession"
        )
        self.assertEqual(checkout.unit_price, Decimal("96.00"))
        self.assertEqual(checkout.terminal_count, 3)
        self.assertEqual(checkout.total_amount, Decimal("288.00"))
        self.assertEqual(checkout.billing_currency, "USD")

    async def test_activate_or_renew_requires_configuration(self):
        service = SubscriptionService(
            self.db,
            provider_name="paynow",
        )
        service.ensure_current = AsyncMock(
            return_value=self.subscription
        )
        result = await service.activate_or_renew(
            self.subscription.company_id,
            "monthly",
        )

        self.assertFalse(result["activation_available"])
        self.assertIn("PAYNOW_INTEGRATION_ID", result["message"])

    async def test_activate_or_renew_surfaces_paynow_timeout(self):
        self.service.ensure_current = AsyncMock(
            return_value=self.subscription
        )
        self.service.get_company = AsyncMock(
            return_value=self.company
        )
        self.service.get_billable_device_ids = AsyncMock(
            return_value=[uuid4()]
        )

        async def timeout_request(_pairs):
            raise HTTPException(
                504,
                "Paynow did not respond in time. Please try again.",
            )

        self.service.send_paynow_request = timeout_request

        with self.assertRaises(HTTPException) as error:
            await self.service.activate_or_renew(
                self.subscription.company_id,
                "monthly",
            )

        self.assertEqual(error.exception.status_code, 504)

    async def test_process_paynow_result_rejects_invalid_hash(self):
        body = urlencode(
            [
              ("reference", "APR-SUB-TEST"),
              ("amount", "8.00"),
              ("status", "Paid"),
              ("hash", "bad"),
            ]
        ).encode("utf-8")

        with self.assertRaises(HTTPException) as error:
            await self.service.process_paynow_result(body)

        self.assertEqual(error.exception.status_code, 403)

    async def test_process_paynow_result_rejects_modified_amount(self):
        session = SimpleNamespace(
            company_id=self.subscription.company_id,
            session_reference="APR-SUB-TEST",
            total_amount=Decimal("8.00"),
            billing_currency="USD",
            terminal_count=1,
            billing_period="monthly",
            plan="monthly",
            unit_price=Decimal("8.00"),
            included_device_ids=[str(uuid4())],
            paynow_reference="PNW-123",
            poll_url="https://poll.example",
            payload={},
            status="pending",
            payment_status="pending",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.service.get_checkout_session_by_reference = AsyncMock(
            return_value=session
        )
        body = self.build_paynow_body(
            reference="APR-SUB-TEST",
            amount="9.00",
            status="Paid",
        )

        with self.assertRaises(HTTPException) as error:
            await self.service.process_paynow_result(body)

        self.assertEqual(error.exception.status_code, 400)

    async def test_process_paynow_result_marks_pending_and_failed_without_activation(self):
        for raw_status, expected_status in [
            ("Sent", "pending"),
            ("Cancelled", "cancelled"),
            ("Failed", "failed"),
        ]:
            db = FakeSubscriptionDb()
            service = SubscriptionService(
                db,
                provider_name="paynow",
                paynow_integration_id="12345",
                paynow_integration_key="integration-key",
                paynow_return_url="https://backoffice.apexpos.cloud",
                paynow_result_url="https://api.apexpos.cloud/api/subscriptions/paynow/result",
            )
            session = SimpleNamespace(
                company_id=self.subscription.company_id,
                session_reference=f"APR-{raw_status}",
                total_amount=Decimal("8.00"),
                billing_currency="USD",
                terminal_count=1,
                billing_period="monthly",
                plan="monthly",
                unit_price=Decimal("8.00"),
                included_device_ids=[str(uuid4())],
                paynow_reference="PNW-123",
                poll_url="https://poll.example",
                payload={},
                status="pending",
                payment_status="pending",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            service.get_checkout_session_by_reference = AsyncMock(
                return_value=session
            )
            service.apply_confirmed_payment = AsyncMock()

            result = await service.process_paynow_result(
                self.build_paynow_body(
                    reference=session.session_reference,
                    amount="8.00",
                    status=raw_status,
                )
            )

            self.assertEqual(result["status"], expected_status)
            service.apply_confirmed_payment.assert_not_called()

    async def test_process_paynow_result_is_idempotent_for_duplicates(self):
        session = SimpleNamespace(
            company_id=self.subscription.company_id,
            session_reference="APR-SUB-DUP",
            total_amount=Decimal("8.00"),
            billing_currency="USD",
            terminal_count=1,
            billing_period="monthly",
            plan="monthly",
            unit_price=Decimal("8.00"),
            included_device_ids=[str(uuid4())],
            paynow_reference="PNW-DUP",
            poll_url="https://poll.example",
            payload={},
            status="pending",
            payment_status="pending",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.service.get_checkout_session_by_reference = AsyncMock(
            return_value=session
        )
        self.service.ensure_current = AsyncMock(
            return_value=self.subscription
        )

        first = await self.service.process_paynow_result(
            self.build_paynow_body(
                reference="APR-SUB-DUP",
                amount="8.00",
                status="Paid",
                paynow_reference="PNW-DUP",
            )
        )
        second = await self.service.process_paynow_result(
            self.build_paynow_body(
                reference="APR-SUB-DUP",
                amount="8.00",
                status="Paid",
                paynow_reference="PNW-DUP",
            )
        )

        self.assertEqual(first["status"], "paid")
        self.assertTrue(second["duplicate"])

    async def test_process_paynow_result_activates_monthly_and_yearly_once(self):
        for plan, amount, delta_days in [
            ("monthly", "16.00", 30),
            ("yearly", "192.00", 365),
        ]:
            db = FakeSubscriptionDb()
            service = SubscriptionService(
                db,
                provider_name="paynow",
                paynow_integration_id="12345",
                paynow_integration_key="integration-key",
                paynow_return_url="https://backoffice.apexpos.cloud",
                paynow_result_url="https://api.apexpos.cloud/api/subscriptions/paynow/result",
            )
            subscription = SimpleNamespace(
                id=uuid4(),
                company_id=self.subscription.company_id,
                plan=None,
                status="expired",
                trial_started_at=None,
                trial_ends_at=None,
                current_period_started_at=None,
                current_period_ends_at=None,
                grace_ends_at=None,
                provider=None,
                provider_reference=None,
                billing_currency="USD",
                licensed_terminal_count=None,
                unit_price=None,
                total_amount=None,
                status_reason=None,
            )
            session = SimpleNamespace(
                company_id=self.subscription.company_id,
                session_reference=f"APR-{plan}",
                total_amount=Decimal(amount),
                billing_currency="USD",
                terminal_count=2,
                billing_period=plan,
                plan=plan,
                unit_price=Decimal("8.00" if plan == "monthly" else "96.00"),
                included_device_ids=[str(uuid4()), str(uuid4())],
                paynow_reference=f"PNW-{plan}",
                poll_url="https://poll.example",
                payload={},
                status="pending",
                payment_status="pending",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            service.get_checkout_session_by_reference = AsyncMock(
                return_value=session
            )
            service.ensure_current = AsyncMock(
                return_value=subscription
            )

            before = datetime.now(UTC)
            result = await service.process_paynow_result(
                self.build_paynow_body(
                    reference=session.session_reference,
                    amount=amount,
                    status="Paid",
                    paynow_reference=session.paynow_reference,
                )
            )

            self.assertEqual(result["status"], "paid")
            self.assertEqual(subscription.status, "active")
            self.assertEqual(subscription.licensed_terminal_count, 2)
            self.assertEqual(
                subscription.total_amount,
                Decimal(amount),
            )
            self.assertGreaterEqual(
                subscription.current_period_ends_at,
                before + timedelta(days=delta_days) - timedelta(minutes=1),
            )
