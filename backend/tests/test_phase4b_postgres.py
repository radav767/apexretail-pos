import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.auth.dependencies import resolve_auth_actor
from app.auth.security import create_access_token, hash_password, hash_session_token
from app.db.session import get_db
from app.devices.authority import TERMINAL_IDENTITY_REVOKED
from app.devices.repository import DeviceRepository
from app.devices.schema import (
    DeviceActivationClaim,
    DeviceActivationRequest,
    DeviceAssignmentRequest,
    DeviceDecommissionRequest,
    DeviceDeleteRequest,
)
from app.devices.service import DeviceService
from app.employees.repository import EmployeeRepository
from app.employees.schema import PinLoginRequest
from app.employees.service import EmployeeService
from app.inventory.branch_repository import BranchInventoryRepository
from app.inventory.branch_schema import BranchCreate
from app.inventory.branch_service import BranchInventoryService
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate, SaleItemCreate
from app.sales.service import SalesService
from app.main import app


TEST_DATABASE_ENV = "APEX_PHASE4B_TEST_DATABASE_URL"


class FailingDeleteRepository(DeviceRepository):
    async def delete_device_row(self, device_id):
        raise RuntimeError("synthetic deletion failure")


class FailingClaimRepository(DeviceRepository):
    async def flush(self, device=None):
        await super().flush(device)
        raise RuntimeError("synthetic activation failure")


class Phase4BPostgresTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database_url = os.getenv(TEST_DATABASE_ENV)
        if not database_url:
            self.skipTest(f"{TEST_DATABASE_ENV} is not configured")
        parsed = make_url(database_url)
        if not (parsed.database or "").startswith("apexretail_phase4b_test_"):
            self.fail("refusing Phase 4B integration database without test prefix")

        self.engine = create_async_engine(database_url)
        self.company_id = uuid4()
        self.other_company_id = uuid4()
        self.shop_id = uuid4()
        self.other_shop_id = uuid4()
        self.branch_id = uuid4()
        self.branch_2_id = uuid4()
        self.other_branch_id = uuid4()
        self.user_id = uuid4()
        self.employee_id = uuid4()
        self.device_id = uuid4()
        self.device_key = f"phase4b-device-{uuid4()}"
        self.fingerprint = f"phase4b-fingerprint-{uuid4()}"
        self.public_device_key = f"phase4b-public-device-{uuid4()}"
        self.public_fingerprint = f"phase4b-public-fingerprint-{uuid4()}"
        self.public_test_token = str(uuid4())
        self.password = "phase4b-password"
        self.pin = "4826"
        self.actor = SimpleNamespace(
            actor_type="user",
            company_id=self.company_id,
            user=SimpleNamespace(id=self.user_id, password_hash=hash_password(self.password)),
            employee=None,
        )
        await self.seed()
        self.addAsyncCleanup(self.engine.dispose)

    async def seed(self):
        async with self.engine.begin() as connection:
            await connection.execute(text("""
                INSERT INTO companies (id,name,owner_email,business_type,active,deleted)
                VALUES (:company,'Phase 4B',:email,'Retail',true,false),
                       (:other,'Other Phase 4B',:other_email,'Retail',true,false)
            """), {
                "company": self.company_id, "other": self.other_company_id,
                "email": f"{self.company_id}@example.test",
                "other_email": f"{self.other_company_id}@example.test",
            })
            await connection.execute(text("""
                INSERT INTO users (id,company_id,email,password_hash,role,active,deleted)
                VALUES (:id,:company,:email,:password,'owner',true,false)
            """), {
                "id": self.user_id, "company": self.company_id,
                "email": f"owner-{self.company_id}@example.test",
                "password": self.actor.user.password_hash,
            })
            await connection.execute(text("""
                INSERT INTO company_subscriptions
                    (id,company_id,status,trial_started_at,trial_ends_at,
                     grace_ends_at,billing_currency,status_reason)
                VALUES (:id,:company,'trial',now(),now() + interval '30 days',
                        now() + interval '33 days','USD','Phase 4B activation test')
            """), {"id": uuid4(), "company": self.company_id})
            await connection.execute(text("""
                INSERT INTO shops (id,company_id,name,active,deleted)
                VALUES (:shop,:company,'Main Shop',true,false),
                       (:other_shop,:other,'Other Shop',true,false)
            """), {
                "shop": self.shop_id, "company": self.company_id,
                "other_shop": self.other_shop_id, "other": self.other_company_id,
            })
            await connection.execute(text("""
                INSERT INTO branches (id,company_id,shop_id,name,active,deleted)
                VALUES (:branch,:company,:shop,'Main',true,false),
                       (:branch2,:company,:shop,'Warehouse',true,false),
                       (:other_branch,:other,:other_shop,'Foreign',true,false)
            """), {
                "branch": self.branch_id, "branch2": self.branch_2_id,
                "company": self.company_id, "shop": self.shop_id,
                "other_branch": self.other_branch_id,
                "other": self.other_company_id, "other_shop": self.other_shop_id,
            })
            await connection.execute(text("""
                INSERT INTO employees
                    (id,company_id,shop_id,branch_id,name,pin,role,permissions,active,deleted)
                VALUES (:id,:company,:shop,:branch,'Owner',:pin,'owner',
                        '{"sales": true, "manage_devices": true}'::jsonb,true,false)
            """), {
                "id": self.employee_id, "company": self.company_id,
                "shop": self.shop_id, "branch": self.branch_id,
                "pin": hash_password(self.pin),
            })
            await connection.execute(text("""
                INSERT INTO devices
                    (id,company_id,shop_id,branch_id,name,friendly_name,pos_number,
                     device_key,device_fingerprint,platform,app_version,status,
                     assignment_revision,active,deleted)
                VALUES (:id,:company,:shop,:branch,'POS 1','Front Counter',1,
                        :key,:fingerprint,'android','test','active',1,true,false)
            """), {
                "id": self.device_id, "company": self.company_id,
                "shop": self.shop_id, "branch": self.branch_id,
                "key": self.device_key, "fingerprint": self.fingerprint,
            })

    def owner_token(self):
        return create_access_token(
            str(self.user_id),
            f"owner-{self.company_id}@example.test",
        )

    async def public_client(self):
        engine = self.engine

        async def override_get_db():
            async with AsyncSession(engine, expire_on_commit=False) as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        self.addCleanup(app.dependency_overrides.pop, get_db, None)
        return AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://phase4b.test",
        )

    async def request_public_activation(self, client, *, name, pos_number):
        response = await client.post(
            "/api/devices/activate/request",
            headers={"Authorization": f"Bearer {self.owner_token()}"},
            json={
                "company_id": str(self.company_id),
                "friendly_name": name,
                "pos_number": pos_number,
                "shop_id": str(self.shop_id),
                "branch_id": str(self.branch_id),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_public_activation_is_atomic_and_attaches_company_branch(self):
        async with await self.public_client() as client:
            activation = await self.request_public_activation(
                client,
                name="Public Activation Success",
                pos_number=20,
            )
            response = await client.post(
                "/api/devices/activate/claim",
                json={
                    "company_id": str(self.company_id),
                    "activation_code": activation["activation_code"],
                    "device_key": self.public_device_key,
                    "device_fingerprint": self.public_fingerprint,
                    "name": "Public Android",
                    "platform": "android",
                    "app_version": "phase4b-test",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            claimed = response.json()
            self.assertEqual(claimed["company_id"], str(self.company_id))
            self.assertEqual(claimed["shop_id"], str(self.shop_id))
            self.assertEqual(claimed["branch_id"], str(self.branch_id))
            self.assertEqual(claimed["status"], "active")
            self.assertTrue(claimed["active"])

        async with AsyncSession(self.engine) as session:
            row = (await session.execute(text("""
                SELECT company_id,shop_id,branch_id,device_key,status,active,
                       claimed_at,activation_code_hash,activation_code_expires_at
                FROM devices WHERE id=:id
            """), {"id": claimed["id"]})).one()
            self.assertEqual(row.company_id, self.company_id)
            self.assertEqual(row.shop_id, self.shop_id)
            self.assertEqual(row.branch_id, self.branch_id)
            self.assertEqual(row.device_key, self.public_device_key)
            self.assertEqual(row.status, "active")
            self.assertTrue(row.active)
            self.assertIsNotNone(row.claimed_at)
            self.assertIsNone(row.activation_code_hash)
            self.assertIsNone(row.activation_code_expires_at)

    async def test_public_activation_rejects_invalid_and_expired_credentials(self):
        async with await self.public_client() as client:
            invalid = await client.post(
                "/api/devices/activate/claim",
                json={
                    "company_id": str(self.company_id),
                    "activation_code": "NOT-A-VALID-CODE",
                    "device_key": "invalid-public-key",
                    "device_fingerprint": "invalid-public-fingerprint",
                    "name": "Invalid Android",
                    "platform": "android",
                    "app_version": "phase4b-test",
                },
            )
            self.assertEqual(invalid.status_code, 400, invalid.text)
            activation = await self.request_public_activation(
                client,
                name="Expired Public Activation",
                pos_number=21,
            )

        async with self.engine.begin() as connection:
            await connection.execute(text("""
                UPDATE devices SET activation_code_expires_at=now() - interval '1 minute'
                WHERE id=:id
            """), {"id": activation["device"]["id"]})

        async with await self.public_client() as client:
            expired = await client.post(
                "/api/devices/activate/claim",
                json={
                    "company_id": str(self.company_id),
                    "activation_code": activation["activation_code"],
                    "device_key": "expired-public-key",
                    "device_fingerprint": "expired-public-fingerprint",
                    "name": "Expired Android",
                    "platform": "android",
                    "app_version": "phase4b-test",
                },
            )
            self.assertEqual(expired.status_code, 400, expired.text)

        async with AsyncSession(self.engine) as session:
            pending = (await session.execute(text("""
                SELECT status,active,claimed_at,device_key
                FROM devices WHERE id=:id
            """), {"id": activation["device"]["id"]})).one()
            self.assertEqual(pending.status, "pending")
            self.assertFalse(pending.active)
            self.assertIsNone(pending.claimed_at)
            self.assertTrue(pending.device_key.startswith("pending-"))
            self.assertEqual(await session.scalar(text("""
                SELECT failed_attempts FROM device_activation_attempts
                WHERE company_id=:company AND device_fingerprint=:fingerprint
            """), {
                "company": self.company_id,
                "fingerprint": "invalid-public-fingerprint",
            }), 1)

    async def test_public_activation_is_idempotent_and_code_cannot_be_reclaimed(self):
        async with await self.public_client() as client:
            activation = await self.request_public_activation(
                client,
                name="Already Claimed Public Activation",
                pos_number=22,
            )
            payload = {
                "company_id": str(self.company_id),
                "activation_code": activation["activation_code"],
                "device_key": f"already-claimed-public-key-{self.public_test_token}",
                "device_fingerprint": f"already-claimed-public-fingerprint-{self.public_test_token}",
                "name": "Claimed Android",
                "platform": "android",
                "app_version": "phase4b-test",
            }
            first = await client.post("/api/devices/activate/claim", json=payload)
            retry = await client.post(
                "/api/devices/activate/claim",
                json={**payload, "activation_code": "IDEMPOTENT-RETRY"},
            )
            reused = await client.post(
                "/api/devices/activate/claim",
                json={
                    **payload,
                    "device_key": f"second-public-key-{self.public_test_token}",
                    "device_fingerprint": f"second-public-fingerprint-{self.public_test_token}",
                },
            )
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertEqual(first.json()["id"], retry.json()["id"])
            self.assertEqual(reused.status_code, 400, reused.text)

    async def test_public_concurrent_claims_only_one_can_activate(self):
        async with await self.public_client() as client:
            activation = await self.request_public_activation(
                client,
                name="Concurrent Public Activation",
                pos_number=23,
            )

            async def claim(suffix):
                return await client.post(
                    "/api/devices/activate/claim",
                    json={
                        "company_id": str(self.company_id),
                        "activation_code": activation["activation_code"],
                        "device_key": f"concurrent-public-key-{self.public_test_token}-{suffix}",
                        "device_fingerprint": f"concurrent-public-fingerprint-{self.public_test_token}-{suffix}",
                        "name": "Concurrent Android",
                        "platform": "android",
                        "app_version": "phase4b-test",
                    },
                )

            first, second = await asyncio.gather(claim("a"), claim("b"))
            self.assertEqual(sorted([first.status_code, second.status_code]), [200, 400])

        async with AsyncSession(self.engine) as session:
            row = (await session.execute(text("""
                SELECT status,active,claimed_at,device_key
                FROM devices WHERE id=:id
            """), {"id": activation["device"]["id"]})).one()
            self.assertEqual(row.status, "active")
            self.assertTrue(row.active)
            self.assertIsNotNone(row.claimed_at)
            self.assertIn(row.device_key, {
                f"concurrent-public-key-{self.public_test_token}-a",
                f"concurrent-public-key-{self.public_test_token}-b",
            })

    async def test_activation_failure_rolls_back_without_partial_claim(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as request_session:
            activation = await DeviceService(
                DeviceRepository(request_session)
            ).request_activation(DeviceActivationRequest(
                company_id=self.company_id,
                friendly_name="Rollback Activation",
                pos_number=24,
                shop_id=self.shop_id,
                branch_id=self.branch_id,
            ))

        async with AsyncSession(self.engine, expire_on_commit=False) as claim_session:
            await claim_session.execute(text(
                "SELECT status FROM company_subscriptions WHERE company_id=:company"
            ), {"company": self.company_id})
            self.assertTrue(claim_session.in_transaction())
            with self.assertRaisesRegex(RuntimeError, "synthetic activation failure"):
                await DeviceService(FailingClaimRepository(claim_session)).claim_activation(
                    DeviceActivationClaim(
                        company_id=self.company_id,
                        activation_code=activation["activation_code"],
                        device_key="rollback-public-key",
                        device_fingerprint="rollback-public-fingerprint",
                        name="Rollback Android",
                        platform="android",
                        app_version="phase4b-test",
                    )
                )

        async with AsyncSession(self.engine) as session:
            row = (await session.execute(text("""
                SELECT status,active,claimed_at,device_key,device_fingerprint,
                       activation_code_hash,activation_code_expires_at
                FROM devices WHERE id=:id
            """), {"id": activation["device"]["id"]})).one()
            self.assertEqual(row.status, "pending")
            self.assertFalse(row.active)
            self.assertIsNone(row.claimed_at)
            self.assertIsNone(row.device_fingerprint)
            self.assertTrue(row.device_key.startswith("pending-"))
            self.assertIsNotNone(row.activation_code_hash)
            self.assertIsNotNone(row.activation_code_expires_at)
            self.assertEqual(await session.scalar(text("""
                SELECT count(*) FROM devices WHERE device_key='rollback-public-key'
            """)), 0)

    def delete_request(self, **overrides):
        values = {
            "confirmation_name": "Front Counter",
            "reauthentication_secret": self.password,
            "reason": "Phase 4B integration test",
            "offline_queue_resolved": True,
            "active_checkout_closed": True,
        }
        values.update(overrides)
        return DeviceDeleteRequest(**values)

    async def test_company_scoped_branch_creation_and_cross_company_rejection(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = BranchInventoryService(BranchInventoryRepository(session))
            created = await service.create_branch(
                BranchCreate(company_id=self.company_id, shop_id=self.shop_id, name="Kiosk"),
                actor=self.actor,
            )
            self.assertEqual(created["shop_id"], self.shop_id)
            audit_count = await session.scalar(text("""
                SELECT count(*) FROM audit_events
                WHERE company_id=:company AND action='terminal_branch_create'
            """), {"company": self.company_id})
            self.assertEqual(audit_count, 1)
            with self.assertRaises(HTTPException) as denied:
                await service.create_branch(
                    BranchCreate(
                        company_id=self.company_id,
                        shop_id=self.other_shop_id,
                        name="Tenant Escape",
                    ),
                    actor=self.actor,
                )
            self.assertEqual(denied.exception.status_code, 404)

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = DeviceService(DeviceRepository(session))
            with self.assertRaises(HTTPException) as denied:
                await service.reassign(
                    self.company_id,
                    self.device_id,
                    DeviceAssignmentRequest(
                        shop_id=self.other_shop_id,
                        branch_id=self.other_branch_id,
                        pos_number=4,
                        reason="Invalid cross-company move",
                        expected_assignment_revision=1,
                        offline_queue_resolved=True,
                        active_checkout_closed=True,
                    ),
                    self.actor,
                )
            self.assertEqual(denied.exception.status_code, 404)

    async def test_decommission_blocks_delete_then_revokes_session(self):
        token = f"phase4b-session-{uuid4()}"
        async with self.engine.begin() as connection:
            await connection.execute(text("""
                INSERT INTO pos_sessions
                    (id,company_id,employee_id,device_id,shop_id,branch_id,token_hash,expires_at)
                VALUES (:id,:company,:employee,:device,:shop,:branch,:token,:expires)
            """), {
                "id": uuid4(), "company": self.company_id,
                "employee": self.employee_id, "device": self.device_id,
                "shop": self.shop_id, "branch": self.branch_id,
                "token": hash_session_token(token),
                "expires": datetime.now(timezone.utc) + timedelta(hours=12),
            })

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = DeviceService(DeviceRepository(session))
            with self.assertRaises(HTTPException) as blocked:
                await service.delete_permanently(
                    self.company_id, self.device_id, self.delete_request(), self.actor,
                )
            self.assertEqual(blocked.exception.status_code, 409)
            await service.decommission(
                self.company_id,
                self.device_id,
                DeviceDecommissionRequest(
                    reason="Dependency-blocked decommission",
                    offline_queue_resolved=True,
                    active_checkout_closed=True,
                ),
                self.actor,
            )

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            revoked = await session.execute(text("""
                SELECT revoked_at, revoke_reason FROM pos_sessions WHERE token_hash=:token
            """), {"token": hash_session_token(token)})
            row = revoked.one()
            self.assertIsNotNone(row.revoked_at)
            self.assertEqual(row.revoke_reason, "terminal_decommissioned")

    async def test_reassignment_revokes_session_increments_revision_and_audits(self):
        token = f"phase4b-reassign-session-{uuid4()}"
        async with self.engine.begin() as connection:
            await connection.execute(text("""
                INSERT INTO pos_sessions
                    (id,company_id,employee_id,device_id,shop_id,branch_id,token_hash,expires_at)
                VALUES (:id,:company,:employee,:device,:shop,:branch,:token,:expires)
            """), {
                "id": uuid4(), "company": self.company_id,
                "employee": self.employee_id, "device": self.device_id,
                "shop": self.shop_id, "branch": self.branch_id,
                "token": hash_session_token(token),
                "expires": datetime.now(timezone.utc) + timedelta(hours=12),
            })

        request = DeviceAssignmentRequest(
            shop_id=self.shop_id,
            branch_id=self.branch_2_id,
            pos_number=2,
            reason="Move to warehouse",
            expected_assignment_revision=1,
            offline_queue_resolved=True,
            active_checkout_closed=True,
        )
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = DeviceService(DeviceRepository(session))
            moved = await service.reassign(
                self.company_id, self.device_id, request, self.actor,
            )
            self.assertEqual(moved["branch_id"], self.branch_2_id)
            self.assertEqual(moved["assignment_revision"], 2)
            with self.assertRaises(HTTPException) as stale:
                await service.reassign(
                    self.company_id, self.device_id, request, self.actor,
                )
            self.assertEqual(stale.exception.status_code, 409)

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            row = (await session.execute(text("""
                SELECT revoked_at, revoke_reason FROM pos_sessions WHERE token_hash=:token
            """), {"token": hash_session_token(token)})).one()
            self.assertIsNotNone(row.revoked_at)
            self.assertEqual(row.revoke_reason, "terminal_reassigned")
            details = await session.scalar(text("""
                SELECT details FROM audit_events
                WHERE company_id=:company AND action='terminal_reassign'
            """), {"company": self.company_id})
            self.assertEqual(details["previous_branch_id"], str(self.branch_id))
            self.assertEqual(details["new_branch_id"], str(self.branch_2_id))
            self.assertEqual(details["assignment_revision"], 2)

    async def test_permanent_delete_is_idempotent_rejects_login_refresh_and_sync(self):
        token = f"phase4b-delete-session-{uuid4()}"
        sale_id = uuid4()
        async with self.engine.begin() as connection:
            await connection.execute(text("""
                INSERT INTO sales
                    (id,company_id,shop_id,branch_id,device_id,employee_id,receipt_number,
                     subtotal_amount,tax_rate,tax_amount,tax_inclusive,total_amount,
                     amount_received,change_due,payment_method,status,reprint_count)
                VALUES (:id,:company,:shop,:branch,:device,:employee,:receipt,
                        10,0,0,false,10,10,0,'cash','completed',0)
            """), {
                "id": sale_id, "company": self.company_id, "shop": self.shop_id,
                "branch": self.branch_id, "device": self.device_id,
                "employee": self.employee_id, "receipt": f"P4B-{sale_id}",
            })
            await connection.execute(text("""
                INSERT INTO pos_sessions
                    (id,company_id,employee_id,device_id,shop_id,branch_id,token_hash,
                     expires_at,revoked_at,revoke_reason)
                VALUES (:id,:company,:employee,:device,:shop,:branch,:token,:expires,
                        now(),'terminal_decommissioned')
            """), {
                "id": uuid4(), "company": self.company_id,
                "employee": self.employee_id, "device": self.device_id,
                "shop": self.shop_id, "branch": self.branch_id,
                "token": hash_session_token(token),
                "expires": datetime.now(timezone.utc) + timedelta(hours=12),
            })

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = DeviceService(DeviceRepository(session))
            with self.assertRaises(HTTPException) as wrong_name:
                await service.delete_permanently(
                    self.company_id,
                    self.device_id,
                    self.delete_request(confirmation_name="front counter"),
                    self.actor,
                )
            self.assertEqual(wrong_name.exception.status_code, 400)
            with self.assertRaises(HTTPException) as wrong_password:
                await service.delete_permanently(
                    self.company_id,
                    self.device_id,
                    self.delete_request(reauthentication_secret="wrong-password"),
                    self.actor,
                )
            self.assertEqual(wrong_password.exception.status_code, 401)
            first = await service.delete_permanently(
                self.company_id, self.device_id, self.delete_request(), self.actor,
            )
            second = await service.delete_permanently(
                self.company_id, self.device_id, self.delete_request(), self.actor,
            )
            self.assertFalse(first["already_deleted"])
            self.assertTrue(second["already_deleted"])

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            preserved = await session.execute(
                text("SELECT device_id FROM sales WHERE id=:id"), {"id": sale_id},
            )
            self.assertIsNone(preserved.scalar_one())
            self.assertEqual(await session.scalar(text(
                "SELECT count(*) FROM device_tombstones WHERE id=:id"
            ), {"id": self.device_id}), 1)
            self.assertEqual(await session.scalar(text("""
                SELECT count(*) FROM audit_events
                WHERE company_id=:company AND action='terminal_delete'
                  AND details->>'terminal_id'=:device
            """), {"company": self.company_id, "device": str(self.device_id)}), 1)
            with self.assertRaises(Exception):
                await session.execute(text(
                    "UPDATE device_tombstones SET reason='tampered' WHERE id=:id"
                ), {"id": self.device_id})
            await session.rollback()

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            self.assertIsNone(await resolve_auth_actor(token, session))
            with self.assertRaises(HTTPException) as login_rejected:
                await EmployeeService(EmployeeRepository(session)).pin_login(PinLoginRequest(
                    company_id=self.company_id,
                    branch_id=self.branch_id,
                    shop_id=self.shop_id,
                    device_id=self.device_id,
                    device_key=self.device_key,
                    pin=self.pin,
                ))
            self.assertEqual(login_rejected.exception.detail["code"], TERMINAL_IDENTITY_REVOKED)

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            with self.assertRaises(HTTPException) as sync_rejected:
                await SalesService(SalesRepository(session)).create_sale(
                    SaleCreate(
                        company_id=self.company_id,
                        branch_id=self.branch_id,
                        device_id=self.device_id,
                        device_key=self.device_key,
                        assignment_revision=1,
                        client_sale_id=uuid4(),
                        items=[SaleItemCreate(product_id=uuid4(), quantity=1)],
                    ),
                    actor=None,
                )
            self.assertEqual(sync_rejected.exception.detail["code"], TERMINAL_IDENTITY_REVOKED)

    async def test_concurrent_reassignment_and_deletion_are_serialized(self):
        async def reassign():
            async with AsyncSession(self.engine, expire_on_commit=False) as session:
                return await DeviceService(DeviceRepository(session)).reassign(
                    self.company_id,
                    self.device_id,
                    DeviceAssignmentRequest(
                        shop_id=self.shop_id,
                        branch_id=self.branch_2_id,
                        pos_number=2,
                        reason="Concurrent move",
                        expected_assignment_revision=1,
                        offline_queue_resolved=True,
                        active_checkout_closed=True,
                    ),
                    self.actor,
                )

        async def delete():
            async with AsyncSession(self.engine, expire_on_commit=False) as session:
                return await DeviceService(DeviceRepository(session)).delete_permanently(
                    self.company_id, self.device_id, self.delete_request(), self.actor,
                )

        results = await asyncio.gather(reassign(), delete(), return_exceptions=True)
        self.assertTrue(any(isinstance(result, dict) and result.get("deleted") for result in results))
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            self.assertEqual(await session.scalar(text(
                "SELECT count(*) FROM devices WHERE id=:id"
            ), {"id": self.device_id}), 0)
            tombstone = (await session.execute(text("""
                SELECT previous_branch_id, assignment_revision
                FROM device_tombstones WHERE id=:id
            """), {"id": self.device_id})).one()
            self.assertIn(tombstone.previous_branch_id, {self.branch_id, self.branch_2_id})
            self.assertIn(tombstone.assignment_revision, {1, 2})

    async def test_delete_transaction_rolls_back_identity_session_and_audit(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = DeviceService(FailingDeleteRepository(session))
            with self.assertRaisesRegex(RuntimeError, "synthetic deletion failure"):
                await service.delete_permanently(
                    self.company_id, self.device_id, self.delete_request(), self.actor,
                )

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            self.assertEqual(await session.scalar(text(
                "SELECT count(*) FROM devices WHERE id=:id"
            ), {"id": self.device_id}), 1)
            self.assertEqual(await session.scalar(text(
                "SELECT count(*) FROM device_tombstones WHERE id=:id"
            ), {"id": self.device_id}), 0)
            self.assertEqual(await session.scalar(text("""
                SELECT count(*) FROM audit_events
                WHERE company_id=:company AND action='terminal_delete'
            """), {"company": self.company_id}), 0)


if __name__ == "__main__":
    unittest.main()
