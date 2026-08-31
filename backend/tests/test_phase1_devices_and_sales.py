import unittest
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.devices.schema import (
    DeviceActivationClaim,
    DeviceActivationRequest,
    DeviceHeartbeat,
    DeviceRegister,
    DeviceUpdate,
)
from app.devices.service import (
    ACTIVATION_LOCKOUT,
    DeviceService,
    hash_activation_code,
)
from app.business_settings.service import BusinessSettingsService
from app.business_settings.schema import ShopSettingsUpdate
from app.models.company import Company
from app.sales.service import SalesService
from app.sales.schema import SaleCreate, SaleItemCreate


UTC = timezone.utc


class FakeDeviceRepo:
    def __init__(self):
        self.db = FakeAsyncSession(self)
        self.devices = {}
        self.views = {}
        self.pending_by_hash = {}
        self.by_key = {}
        self.activation_attempts = {}
        self.default_shop_id = None
        self.default_branch_id = None
        self.pending_locks = {}
        self.pending_lock_owners = {}

    async def get_by_key(self, company_id, device_key):
        device = self.by_key.get(device_key)
        if device and device.company_id == company_id:
            return device
        return None

    async def get_by_global_key(self, device_key, for_update=False):
        return self.by_key.get(device_key)

    async def get_by_id(self, company_id, device_id):
        device = self.devices.get(device_id)
        if device and device.company_id == company_id:
            return device
        return None

    async def get_pending_activation(
        self,
        company_id,
        activation_code_hash,
        now,
        for_update=False,
    ):
        if for_update:
            lock = self.pending_locks.setdefault(
                activation_code_hash,
                asyncio.Lock(),
            )
            await lock.acquire()
            self.pending_lock_owners[asyncio.current_task()] = lock
        device = self.pending_by_hash.get(activation_code_hash)
        if (
            device
            and device.company_id == company_id
            and device.activation_code_expires_at
            and device.activation_code_expires_at >= now
        ):
            return device
        if for_update:
            self._release_pending_lock()
        return None

    async def get_activation_attempt(
        self,
        company_id,
        device_fingerprint,
        for_update=False,
    ):
        return self.activation_attempts.get(
            (company_id, device_fingerprint)
        )

    async def ensure_activation_attempt(
        self,
        company_id,
        device_fingerprint,
    ):
        self.activation_attempts.setdefault(
            (company_id, device_fingerprint),
            SimpleNamespace(
                company_id=company_id,
                device_fingerprint=device_fingerprint,
                failed_attempts=0,
                locked_until=None,
                last_failed_at=None,
            ),
        )

    async def delete_activation_attempt(
        self,
        company_id,
        device_fingerprint,
    ):
        self.activation_attempts.pop(
            (company_id, device_fingerprint),
            None,
        )

    async def find_branch_pos_number_device(
        self,
        company_id,
        branch_id,
        pos_number,
        exclude_device_id=None,
    ):
        for device in self.devices.values():
            if device.company_id != company_id:
                continue
            if device.branch_id != branch_id:
                continue
            if device.pos_number != pos_number:
                continue
            if device.removed_at is not None:
                continue
            if exclude_device_id is not None and device.id == exclude_device_id:
                continue
            return device
        return None

    async def get_view(self, company_id, device_id):
        return self._serialize_view(self.devices[device_id])

    async def list_devices(self, company_id):
        return [
            self._serialize_view(device)
            for device in self.devices.values()
            if device.company_id == company_id
        ]

    async def get_shop(self, company_id, shop_id):
        if str(shop_id).startswith("00000000"):
            return None
        return SimpleNamespace(id=shop_id, company_id=company_id)

    async def get_branch(self, company_id, branch_id):
        shop_id = (
            self.default_shop_id
            or next(
                (
                    device.shop_id
                    for device in self.devices.values()
                    if device.branch_id == branch_id
                ),
                None,
            )
            or uuid4()
        )
        return SimpleNamespace(
            id=branch_id,
            company_id=company_id,
            shop_id=shop_id,
            name="Front Branch",
        )

    async def create_device(self, **kwargs):
        device_id = uuid4()
        payload = {
            "id": device_id,
            "deleted": False,
            "removed_at": None,
            "deactivated_at": None,
            "deactivation_reason": None,
            "activation_code_hash": None,
            "activation_code_expires_at": None,
            "device_fingerprint": None,
            "pending_shop_id": kwargs.get("shop_id"),
            "pending_branch_id": kwargs.get("branch_id"),
            "last_seen_platform": kwargs.get("platform"),
            "last_seen_app_version": kwargs.get("app_version"),
            **kwargs,
        }
        device = SimpleNamespace(**payload)
        self.devices[device_id] = device
        self.by_key[device.device_key] = device
        self.views[(device.company_id, device_id)] = self._serialize_view(device)
        if device.activation_code_hash:
            self.pending_by_hash[device.activation_code_hash] = device
        return device

    async def update_registration(
        self,
        device,
        *,
        name,
        device_fingerprint,
        platform,
        app_version,
        last_seen_at,
    ):
        device.name = name
        device.device_fingerprint = device_fingerprint
        device.platform = platform
        device.app_version = app_version
        device.last_seen_at = last_seen_at
        device.last_seen_platform = platform
        device.last_seen_app_version = app_version
        self.views[(device.company_id, device.id)] = self._serialize_view(device)
        return device

    async def save(self, device):
        old_hash = next(
            (
                code_hash
                for code_hash, pending_device in self.pending_by_hash.items()
                if pending_device.id == device.id
                and code_hash != device.activation_code_hash
            ),
            None,
        )
        if old_hash is not None:
            self.pending_by_hash.pop(old_hash, None)
        self.devices[device.id] = device
        self.by_key[device.device_key] = device
        self.views[(device.company_id, device.id)] = self._serialize_view(device)
        if device.activation_code_hash:
            self.pending_by_hash[device.activation_code_hash] = device
        self._release_pending_lock()
        return device

    async def flush(self, device=None):
        if device is not None:
            await self.save(device)

    def _release_pending_lock(self):
        lock = self.pending_lock_owners.pop(
            asyncio.current_task(),
            None,
        )
        if lock is not None and lock.locked():
            lock.release()

    def _serialize_view(self, device):
        return {
            "id": device.id,
            "company_id": device.company_id,
            "shop_id": device.shop_id,
            "branch_id": device.branch_id,
            "shop_name": "Main Shop",
            "branch_name": "Front Branch",
            "shop_address_line_1": "12 Main Street",
            "shop_address_line_2": None,
            "shop_city": "Harare",
            "shop_state_province": None,
            "shop_country": "Zimbabwe",
            "shop_phone": "555-1000",
            "shop_tax_vat_number": "VAT-1",
            "name": device.name,
            "friendly_name": getattr(device, "friendly_name", None),
            "pos_number": getattr(device, "pos_number", None),
            "device_key": device.device_key,
            "platform": getattr(device, "platform", None),
            "app_version": getattr(device, "app_version", None),
            "last_seen_at": getattr(device, "last_seen_at", None),
            "last_seen_platform": getattr(device, "last_seen_platform", None),
            "last_seen_app_version": getattr(
                device,
                "last_seen_app_version",
                None,
            ),
            "status": getattr(device, "status", "active"),
            "claimed_at": getattr(device, "claimed_at", None),
            "deactivated_at": getattr(device, "deactivated_at", None),
            "deactivation_reason": getattr(
                device,
                "deactivation_reason",
                None,
            ),
            "removed_at": getattr(device, "removed_at", None),
            "pending_shop_id": getattr(
                device,
                "pending_shop_id",
                None,
            ),
            "pending_branch_id": getattr(
                device,
                "pending_branch_id",
                None,
            ),
            "active": getattr(device, "active", True),
        }


class FakeTransaction:
    def __init__(self, repo):
        self.repo = repo

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.repo._release_pending_lock()
        return False


class FakeAsyncSession:
    def __init__(self, repo):
        self.repo = repo

    def begin(self):
        return FakeTransaction(self.repo)


class DeviceServicePhase1Test(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.company_id = uuid4()
        self.shop_id = uuid4()
        self.branch_id = uuid4()
        self.repo = FakeDeviceRepo()
        self.repo.default_shop_id = self.shop_id
        self.repo.default_branch_id = self.branch_id
        self.service = DeviceService(self.repo)

        async def resolve_branch(_company_id, _branch_id):
            return SimpleNamespace(
                id=self.branch_id,
                shop_id=self.shop_id,
            )

        self.service.stock = SimpleNamespace(
            resolve_branch=resolve_branch
        )

    async def test_existing_device_remains_active(self):
        existing = await self.repo.create_device(
            company_id=self.company_id,
            shop_id=self.shop_id,
            branch_id=self.branch_id,
            device_key="device-a",
            name="Front POS",
            friendly_name="Front POS",
            pos_number=1,
            platform="android",
            app_version="1.0.0",
            status="active",
            active=True,
            claimed_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )

        result = await self.service.register(
            DeviceRegister(
                company_id=self.company_id,
                device_key="device-a",
                name="Front POS",
                platform="android",
                app_version="1.2.0",
            )
        )

        self.assertEqual(result["id"], existing.id)
        self.assertTrue(result["active"])

    async def test_activation_request_claim_and_retry(self):
        request_result = await self.service.request_activation(
            DeviceActivationRequest(
                company_id=self.company_id,
                friendly_name="Counter 1",
                pos_number=2,
                shop_id=self.shop_id,
                branch_id=self.branch_id,
            )
        )

        self.assertTrue(request_result["activation_code"])

        claim_result = await self.service.claim_activation(
            DeviceActivationClaim(
                company_id=self.company_id,
                activation_code=request_result["activation_code"],
                device_key="claimed-device",
                device_fingerprint="fingerprint-a",
                name="Android POS",
                platform="android",
                app_version="2.0.0",
            )
        )

        retry_result = await self.service.claim_activation(
            DeviceActivationClaim(
                company_id=self.company_id,
                activation_code="IGNORED",
                device_key="claimed-device",
                device_fingerprint="fingerprint-a",
                name="Android POS",
                platform="android",
                app_version="2.0.0",
            )
        )

        self.assertEqual(claim_result["id"], retry_result["id"])
        self.assertEqual(claim_result["device_key"], "claimed-device")

    async def test_activation_code_cannot_be_reused_or_expired(self):
        request_result = await self.service.request_activation(
            DeviceActivationRequest(
                company_id=self.company_id,
                friendly_name="Counter 2",
                pos_number=3,
                shop_id=self.shop_id,
                branch_id=self.branch_id,
            )
        )
        code = request_result["activation_code"]

        await self.service.claim_activation(
            DeviceActivationClaim(
                company_id=self.company_id,
                activation_code=code,
                device_key="claimed-once",
                device_fingerprint="fingerprint-b",
                name="Android POS",
                platform="android",
                app_version="2.0.0",
            )
        )

        with self.assertRaises(HTTPException) as reused_error:
            await self.service.claim_activation(
                DeviceActivationClaim(
                    company_id=self.company_id,
                    activation_code=code,
                    device_key="claimed-twice",
                    device_fingerprint="fingerprint-c",
                    name="Android POS",
                    platform="android",
                    app_version="2.0.0",
                )
            )
        self.assertEqual(reused_error.exception.status_code, 400)

        expired_device = await self.repo.create_device(
            company_id=self.company_id,
            shop_id=self.shop_id,
            branch_id=self.branch_id,
            device_key="pending-expired",
            name="Pending",
            friendly_name="Pending",
            pos_number=4,
            platform="pending",
            app_version="pending",
            status="pending",
            active=False,
            claimed_at=None,
            activation_code_hash=hash_activation_code("EXPIRED1"),
            activation_code_expires_at=datetime.now(UTC) - timedelta(minutes=1),
            device_fingerprint=None,
            pending_shop_id=self.shop_id,
            pending_branch_id=self.branch_id,
            last_seen_at=None,
        )
        self.assertIsNotNone(expired_device)

        with self.assertRaises(HTTPException) as expired_error:
            await self.service.claim_activation(
                DeviceActivationClaim(
                    company_id=self.company_id,
                    activation_code="EXPIRED1",
                    device_key="claim-expired",
                    device_fingerprint="fingerprint-d",
                    name="Android POS",
                    platform="android",
                    app_version="2.0.0",
                )
            )
        self.assertEqual(expired_error.exception.status_code, 400)

    async def test_activation_failed_attempts_lock_out_after_five_failures(self):
        fingerprint = "fingerprint-lockout"

        for _ in range(5):
            with self.assertRaises(HTTPException) as invalid_code_error:
                await self.service.claim_activation(
                    DeviceActivationClaim(
                        company_id=self.company_id,
                        activation_code="WRONGCODE",
                        device_key=f"device-{uuid4()}",
                        device_fingerprint=fingerprint,
                        name="Android POS",
                        platform="android",
                        app_version="2.0.0",
                    )
                )
            self.assertEqual(invalid_code_error.exception.status_code, 400)

        with self.assertRaises(HTTPException) as lockout_error:
            await self.service.claim_activation(
                DeviceActivationClaim(
                    company_id=self.company_id,
                    activation_code="WRONGCODE",
                    device_key="device-locked",
                    device_fingerprint=fingerprint,
                    name="Android POS",
                    platform="android",
                    app_version="2.0.0",
                )
            )
        self.assertEqual(lockout_error.exception.status_code, 429)

    async def test_activation_lockout_expires_and_restarts_counting(self):
        fingerprint = "fingerprint-expiring-lockout"
        base_time = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
        current_time = {"value": base_time}

        def fake_utcnow():
            return current_time["value"]

        with patch("app.devices.service.utcnow", fake_utcnow):
            for _ in range(5):
                with self.assertRaises(HTTPException):
                    await self.service.claim_activation(
                        DeviceActivationClaim(
                            company_id=self.company_id,
                            activation_code="WRONGCODE",
                            device_key=f"device-{uuid4()}",
                            device_fingerprint=fingerprint,
                            name="Android POS",
                            platform="android",
                            app_version="2.0.0",
                        )
                    )

            with self.assertRaises(HTTPException) as lockout_error:
                await self.service.claim_activation(
                    DeviceActivationClaim(
                        company_id=self.company_id,
                        activation_code="WRONGCODE",
                        device_key="device-locked",
                        device_fingerprint=fingerprint,
                        name="Android POS",
                        platform="android",
                        app_version="2.0.0",
                    )
                )
            self.assertEqual(lockout_error.exception.status_code, 429)

            current_time["value"] = base_time + ACTIVATION_LOCKOUT + timedelta(
                seconds=1
            )

            with self.assertRaises(HTTPException) as after_expiry_error:
                await self.service.claim_activation(
                    DeviceActivationClaim(
                        company_id=self.company_id,
                        activation_code="WRONGCODE",
                        device_key="device-after-expiry",
                        device_fingerprint=fingerprint,
                        name="Android POS",
                        platform="android",
                        app_version="2.0.0",
                    )
                )
            self.assertEqual(after_expiry_error.exception.status_code, 400)

            attempt = self.repo.activation_attempts[
                (self.company_id, fingerprint)
            ]
            self.assertEqual(attempt.failed_attempts, 1)
            self.assertIsNone(attempt.locked_until)

    async def test_cross_company_claim_is_rejected(self):
        other_company_id = uuid4()
        await self.repo.create_device(
            company_id=other_company_id,
            shop_id=self.shop_id,
            branch_id=self.branch_id,
            device_key="device-cross",
            name="Other",
            friendly_name="Other",
            pos_number=5,
            platform="android",
            app_version="1.0.0",
            status="active",
            active=True,
            claimed_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )

        with self.assertRaises(HTTPException):
            await self.service.claim_activation(
                DeviceActivationClaim(
                    company_id=self.company_id,
                    activation_code="UNUSED",
                    device_key="device-cross",
                    device_fingerprint="fingerprint-e",
                    name="Android POS",
                    platform="android",
                    app_version="2.0.0",
                )
            )

    async def test_concurrent_claims_only_activate_once(self):
        request_result = await self.service.request_activation(
            DeviceActivationRequest(
                company_id=self.company_id,
                friendly_name="Counter 7",
                pos_number=7,
                shop_id=self.shop_id,
                branch_id=self.branch_id,
            )
        )

        async def claim(device_key):
            return await self.service.claim_activation(
                DeviceActivationClaim(
                    company_id=self.company_id,
                    activation_code=request_result["activation_code"],
                    device_key=device_key,
                    device_fingerprint=f"fingerprint-{device_key}",
                    name="Android POS",
                    platform="android",
                    app_version="2.0.0",
                )
            )

        results = await asyncio.gather(
            claim("claimed-concurrency-a"),
            claim("claimed-concurrency-b"),
            return_exceptions=True,
        )

        successes = [
            result for result in results if isinstance(result, dict)
        ]
        failures = [
            result
            for result in results
            if isinstance(result, HTTPException)
        ]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].status_code, 400)

    async def test_pos_number_must_be_unique_within_branch(self):
        await self.repo.create_device(
            company_id=self.company_id,
            shop_id=self.shop_id,
            branch_id=self.branch_id,
            device_key="device-branch-1a",
            name="Front POS",
            friendly_name="Front POS",
            pos_number=11,
            platform="android",
            app_version="1.0.0",
            status="active",
            active=True,
            claimed_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )

        with self.assertRaises(HTTPException) as duplicate_error:
            await self.service.request_activation(
                DeviceActivationRequest(
                    company_id=self.company_id,
                    friendly_name="Back POS",
                    pos_number=11,
                    shop_id=self.shop_id,
                    branch_id=self.branch_id,
                )
            )

        self.assertEqual(duplicate_error.exception.status_code, 409)

    async def test_pos_number_can_be_reused_in_different_branch(self):
        other_branch_id = uuid4()
        other_shop_id = uuid4()

        async def get_branch(company_id, branch_id):
            shop_id = (
                other_shop_id
                if branch_id == other_branch_id
                else self.shop_id
            )
            return SimpleNamespace(
                id=branch_id,
                company_id=company_id,
                shop_id=shop_id,
                name="Branch",
            )

        self.repo.get_branch = get_branch

        await self.repo.create_device(
            company_id=self.company_id,
            shop_id=self.shop_id,
            branch_id=self.branch_id,
            device_key="device-branch-origin",
            name="Front POS",
            friendly_name="Front POS",
            pos_number=12,
            platform="android",
            app_version="1.0.0",
            status="active",
            active=True,
            claimed_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )

        result = await self.service.request_activation(
            DeviceActivationRequest(
                company_id=self.company_id,
                friendly_name="Side POS",
                pos_number=12,
                shop_id=other_shop_id,
                branch_id=other_branch_id,
            )
        )

        self.assertEqual(result["device"]["branch_id"], other_branch_id)

    async def test_heartbeat_and_access_state_transitions(self):
        device = await self.repo.create_device(
            company_id=self.company_id,
            shop_id=self.shop_id,
            branch_id=self.branch_id,
            device_key="device-heartbeat",
            name="Counter 3",
            friendly_name="Counter 3",
            pos_number=6,
            platform="android",
            app_version="1.0.0",
            status="active",
            active=True,
            claimed_at=datetime.now(UTC),
            last_seen_at=None,
        )

        heartbeat = await self.service.heartbeat(
            DeviceHeartbeat(
                company_id=self.company_id,
                device_id=device.id,
                platform="android",
                app_version="2.1.0",
            )
        )
        self.assertIsNotNone(heartbeat["last_seen_at"])

        deactivated = await self.service.update(
            self.company_id,
            device.id,
            DeviceUpdate(
                status="deactivated",
                deactivation_reason="Lost tablet",
            ),
        )
        self.assertEqual(deactivated["status"], "deactivated")

        reactivated = await self.service.update(
            self.company_id,
            device.id,
            DeviceUpdate(status="active"),
        )
        self.assertEqual(reactivated["status"], "active")

        removed = await self.service.update(
            self.company_id,
            device.id,
            DeviceUpdate(status="removed"),
        )
        self.assertEqual(removed["status"], "removed")


class FakeSalesRepo:
    def __init__(self, blocked_at=None):
        self.db = None
        self.blocked_at = blocked_at
        self.saved_sale = None
        self.saved_sales = []
        self.shop = SimpleNamespace(
            id=uuid4(),
            company_id=uuid4(),
            name="Main Shop",
            address_line_1="12 Main Street",
            address_line_2="Suite 2",
            city="Harare",
            state_province=None,
            country="Zimbabwe",
            phone="555-0000",
            tax_vat_number="VAT-88",
        )

    async def get_by_client_sale_id(self, *_args, **_kwargs):
        return None

    async def resolve_branch(self, company_id, branch_id):
        return SimpleNamespace(
            id=branch_id or uuid4(),
            shop_id=uuid4(),
            name="Front Branch",
        )

    async def get_device(self, _company_id, *, device_id=None, device_key=None):
        if device_id is None and device_key is None:
            return None
        return SimpleNamespace(
            id=device_id or uuid4(),
            friendly_name="Counter A",
            name="Counter A",
            pos_number=8,
            removed_at=self.blocked_at,
            deactivated_at=self.blocked_at,
        )

    async def get_shop(self, company_id, shop_id):
        self.shop.id = shop_id
        self.shop.company_id = company_id
        return self.shop

    async def get_product(self, company_id, product_id):
        return SimpleNamespace(
            id=product_id,
            company_id=company_id,
            name="Rice",
            selling_price=Decimal("5.00"),
            cost_price=Decimal("2.00"),
        )

    async def get_balance(self, *_args, **_kwargs):
        return SimpleNamespace(quantity=Decimal("10"))

    async def sync_product_total(self, _product):
        return Decimal("8")

    async def get_employee(self, **_kwargs):
        return SimpleNamespace(
            id=uuid4(),
            branch_id=_kwargs["company_id"],
            role="owner",
            permissions={"sales": True},
            name="Cashier Jane",
        )

    async def save_sale(self, sale, *_args):
        self.saved_sale = sale
        self.saved_sales.append(sale)
        return sale


class FakeSettingsService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def get(self, _company_id):
        return {
            "name": "ApexRetail",
            "tax_name": "VAT",
            "tax_rate": Decimal("15"),
            "tax_inclusive": False,
            "receipt_footer": "Thank you",
        }


class MutableSettingsService:
    receipt_footer = "Thank you"

    def __init__(self, *_args, **_kwargs):
        pass

    async def get(self, _company_id):
        return {
            "name": "ApexRetail",
            "tax_name": "VAT",
            "tax_rate": Decimal("15"),
            "tax_inclusive": False,
            "receipt_footer": self.receipt_footer,
        }


class SalesServicePhase1Test(unittest.IsolatedAsyncioTestCase):
    async def test_server_derives_snapshots_and_allows_pre_deactivation_queue(self):
        company_id = uuid4()
        branch_id = uuid4()
        device_id = uuid4()
        blocked_at = datetime.now(UTC)
        repo = FakeSalesRepo(blocked_at=blocked_at)
        service = SalesService(repo)

        payload = SaleCreate(
            company_id=company_id,
            branch_id=branch_id,
            device_id=device_id,
            payment_method="cash",
            amount_received=Decimal("10"),
            client_created_at=blocked_at - timedelta(minutes=1),
            items=[
                SaleItemCreate(
                    product_id=uuid4(),
                    quantity=Decimal("1"),
                )
            ],
        )

        with patch(
            "app.sales.service.BusinessSettingsService",
            FakeSettingsService,
        ):
            sale = await service.create_sale(payload, actor=None)

        self.assertEqual(sale.shop_name_snapshot, "Main Shop")
        self.assertEqual(sale.branch_name_snapshot, "Front Branch")
        self.assertEqual(sale.pos_name_snapshot, "Counter A")
        self.assertEqual(sale.pos_number_snapshot, "8")
        self.assertEqual(
            sale.shop_address_snapshot["address_line_1"],
            "12 Main Street",
        )
        self.assertEqual(sale.receipt_footer_snapshot, "Thank you")

    async def test_client_cannot_override_trusted_receipt_snapshots(self):
        company_id = uuid4()
        branch_id = uuid4()
        device_id = uuid4()
        repo = FakeSalesRepo()
        service = SalesService(repo)

        payload = SaleCreate.model_validate(
            {
                "company_id": str(company_id),
                "branch_id": str(branch_id),
                "device_id": str(device_id),
                "payment_method": "cash",
                "amount_received": "10.00",
                "items": [
                    {
                        "product_id": str(uuid4()),
                        "quantity": "1",
                    }
                ],
                "shop_name_snapshot": "FORGED SHOP",
                "shop_address_snapshot": {
                    "address_line_1": "FORGED ADDRESS"
                },
                "receipt_footer_snapshot": "FORGED FOOTER",
            }
        )

        with patch(
            "app.sales.service.BusinessSettingsService",
            FakeSettingsService,
        ):
            sale = await service.create_sale(payload, actor=None)

        self.assertEqual(sale.shop_name_snapshot, "Main Shop")
        self.assertEqual(
            sale.shop_address_snapshot["address_line_1"],
            "12 Main Street",
        )
        self.assertEqual(sale.receipt_footer_snapshot, "Thank you")

    async def test_historical_receipt_snapshots_do_not_change_after_settings_edits(self):
        company_id = uuid4()
        branch_id = uuid4()
        device_id = uuid4()
        repo = FakeSalesRepo()
        service = SalesService(repo)

        first_payload = SaleCreate(
            company_id=company_id,
            branch_id=branch_id,
            device_id=device_id,
            payment_method="cash",
            amount_received=Decimal("10"),
            items=[
                SaleItemCreate(
                    product_id=uuid4(),
                    quantity=Decimal("1"),
                )
            ],
        )

        second_payload = SaleCreate(
            company_id=company_id,
            branch_id=branch_id,
            device_id=device_id,
            payment_method="cash",
            amount_received=Decimal("10"),
            items=[
                SaleItemCreate(
                    product_id=uuid4(),
                    quantity=Decimal("1"),
                )
            ],
        )

        with patch(
            "app.sales.service.BusinessSettingsService",
            MutableSettingsService,
        ):
            first_sale = await service.create_sale(
                first_payload,
                actor=None,
            )
            MutableSettingsService.receipt_footer = "Updated Footer"
            second_sale = await service.create_sale(
                second_payload,
                actor=None,
            )

        self.assertEqual(first_sale.receipt_footer_snapshot, "Thank you")
        self.assertEqual(second_sale.receipt_footer_snapshot, "Updated Footer")
        self.assertEqual(
            repo.saved_sales[0].receipt_footer_snapshot,
            "Thank you",
        )

    async def test_new_activity_after_deactivation_is_blocked(self):
        company_id = uuid4()
        branch_id = uuid4()
        device_id = uuid4()
        blocked_at = datetime.now(UTC)
        repo = FakeSalesRepo(blocked_at=blocked_at)
        service = SalesService(repo)

        payload = SaleCreate(
            company_id=company_id,
            branch_id=branch_id,
            device_id=device_id,
            payment_method="cash",
            amount_received=Decimal("10"),
            client_created_at=blocked_at + timedelta(minutes=1),
            items=[
                SaleItemCreate(
                    product_id=uuid4(),
                    quantity=Decimal("1"),
                )
            ],
        )

        with patch(
            "app.sales.service.BusinessSettingsService",
            FakeSettingsService,
        ):
            with self.assertRaises(HTTPException):
                await service.create_sale(payload, actor=None)


class FakeSettingsDbResult:
    def __init__(self, *, one=None, many=None):
        self._one = one
        self._many = many or []

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return self

    def all(self):
        return self._many


class FakeSettingsDb:
    def __init__(self, company, shop):
        self.company = company
        self.shop = shop

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is Company:
            return FakeSettingsDbResult(one=self.company)
        return FakeSettingsDbResult(one=self.shop, many=[self.shop])

    def add(self, _value):
        return None

    async def commit(self):
        return None

    async def refresh(self, _value):
        return None

    async def rollback(self):
        return None


class BusinessSettingsPhase1Test(unittest.IsolatedAsyncioTestCase):
    async def test_shop_address_updates_persist(self):
        company_id = uuid4()
        shop_id = uuid4()
        company = Company(
            id=company_id,
            name="ApexRetail",
            owner_name="Owner",
            owner_email="owner@example.com",
            business_type="Retail",
            country="Zimbabwe",
            phone="555-1000",
            active=True,
            deleted=False,
        )
        shop = SimpleNamespace(
            id=shop_id,
            company_id=company_id,
            name="Main Shop",
            address_line_1=None,
            address_line_2=None,
            city=None,
            state_province=None,
            country=None,
            phone=None,
            tax_vat_number=None,
            active=True,
            deleted=False,
        )
        service = BusinessSettingsService(
            FakeSettingsDb(company, shop)
        )

        result = await service.update_shop(
            company_id,
            shop_id,
            ShopSettingsUpdate(
                address_line_1="12 Main Street",
                address_line_2="Suite 3",
                city="Harare",
                country="Zimbabwe",
                phone="555-2222",
                tax_vat_number="VAT-55",
            ),
        )

        self.assertEqual(shop.address_line_1, "12 Main Street")
        self.assertEqual(shop.city, "Harare")
        self.assertEqual(shop.tax_vat_number, "VAT-55")
        self.assertEqual(result["address_line_1"], "12 Main Street")
        self.assertEqual(result["phone"], "555-2222")
