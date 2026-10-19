import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.auth.dependencies import resolve_auth_actor
from app.auth.security import hash_session_token
from app.employees.repository import EmployeeRepository
from app.employees.schema import PinLoginRequest
from app.employees.service import EmployeeService


TEST_DATABASE_ENV = "APEX_DASHBOARD_TEST_DATABASE_URL"


class FailingCommitSession:
    def __init__(self, session):
        self.session = session

    async def execute(self, *args, **kwargs):
        return await self.session.execute(*args, **kwargs)

    async def flush(self):
        await self.session.flush()

    def add(self, value):
        self.session.add(value)

    async def commit(self):
        raise RuntimeError("synthetic commit failure")

    async def rollback(self):
        await self.session.rollback()


class DeviceTakeoverPostgresTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database_url = os.getenv(TEST_DATABASE_ENV)
        if not database_url:
            self.skipTest(f"{TEST_DATABASE_ENV} is not configured")
        parsed = make_url(database_url)
        if not (parsed.database or "").startswith("apexretail_phase2_test_"):
            self.fail("refusing device integration database without test prefix")

        self.engine = create_async_engine(database_url)
        self.company_id = uuid4()
        self.shop_id = uuid4()
        self.branch_id = uuid4()
        self.employee_id = uuid4()
        self.target_id = uuid4()
        self.source_id = uuid4()
        self.old_key = f"old-device-{uuid4()}"
        self.new_key = f"new-device-{uuid4()}"
        self.initial_token = f"initial-{uuid4()}"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=12)

        async with self.engine.begin() as connection:
            await connection.execute(text("""
                INSERT INTO companies
                    (id, name, owner_email, business_type, active, deleted)
                VALUES (:id, 'Takeover Test', :email, 'Retail', true, false)
            """), {"id": self.company_id, "email": f"{self.company_id}@example.test"})
            await connection.execute(text("""
                INSERT INTO shops (id, company_id, name, active, deleted)
                VALUES (:id, :company_id, 'Test Shop', true, false)
            """), {"id": self.shop_id, "company_id": self.company_id})
            await connection.execute(text("""
                INSERT INTO branches
                    (id, company_id, shop_id, name, active, deleted)
                VALUES (:id, :company_id, :shop_id, 'Main', true, false)
            """), {
                "id": self.branch_id, "company_id": self.company_id,
                "shop_id": self.shop_id,
            })
            await connection.execute(text("""
                INSERT INTO employees
                    (id, company_id, shop_id, branch_id, name, pin, role,
                     permissions, active, deleted)
                VALUES
                    (:id, :company_id, :shop_id, :branch_id, 'Cashier',
                     '1234', 'cashier', '{"sales": true}'::jsonb, true, false)
            """), {
                "id": self.employee_id, "company_id": self.company_id,
                "shop_id": self.shop_id, "branch_id": self.branch_id,
            })
            await connection.execute(text("""
                INSERT INTO employee_shop_access (id, employee_id, shop_id)
                VALUES (:id, :employee_id, :shop_id)
            """), {
                "id": uuid4(), "employee_id": self.employee_id,
                "shop_id": self.shop_id,
            })
            for device_id, key, number, name in (
                (self.target_id, self.old_key, 1, "Target"),
                (self.source_id, self.new_key, 2, "Source"),
            ):
                await connection.execute(text("""
                    INSERT INTO devices
                        (id, company_id, shop_id, branch_id, name, pos_number,
                         device_key, platform, app_version, status,
                         active, deleted)
                    VALUES
                        (:id, :company_id, :shop_id, :branch_id, :name,
                         :number, :key, 'Web', 'test', 'active', true, false)
                """), {
                    "id": device_id, "company_id": self.company_id,
                    "shop_id": self.shop_id, "branch_id": self.branch_id,
                    "name": name, "number": number, "key": key,
                })
            await connection.execute(text("""
                INSERT INTO pos_sessions
                    (id, company_id, employee_id, device_id, shop_id,
                     branch_id, token_hash, expires_at)
                VALUES
                    (:id, :company_id, :employee_id, :device_id, :shop_id,
                     :branch_id, :token_hash, :expires_at)
            """), {
                "id": uuid4(), "company_id": self.company_id,
                "employee_id": self.employee_id, "device_id": self.source_id,
                "shop_id": self.shop_id, "branch_id": self.branch_id,
                "token_hash": hash_session_token(self.initial_token),
                "expires_at": expires_at,
            })

    async def asyncTearDown(self):
        if not hasattr(self, "engine"):
            return
        async with self.engine.connect() as connection:
            protected = (await connection.execute(text("SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='audit_events_append_only')"))).scalar_one()
        if protected:
            # These tests commit across concurrent connections. Retain their
            # audit evidence in the prefix-guarded disposable database rather
            # than disabling the Phase 7B protection for fixture cleanup.
            await self.engine.dispose()
            return
        async with self.engine.begin() as connection:
            for table in ("audit_events", "pos_sessions"):
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE company_id = :company_id"),
                    {"company_id": self.company_id},
                )
            await connection.execute(
                text("DELETE FROM employee_shop_access WHERE employee_id = :employee_id"),
                {"employee_id": self.employee_id},
            )
            for table in ("employees", "devices", "branches", "shops"):
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE company_id = :company_id"),
                    {"company_id": self.company_id},
                )
            await connection.execute(
                text("DELETE FROM companies WHERE id = :company_id"),
                {"company_id": self.company_id},
            )
        await self.engine.dispose()

    def request(self, device_key, *, takeover, session_token=None):
        return PinLoginRequest(
            company_id=self.company_id,
            shop_id=self.shop_id,
            branch_id=self.branch_id,
            device_id=self.target_id,
            device_key=device_key,
            session_token=session_token,
            pin="1234",
            takeover=takeover,
        )

    async def login(self, request):
        async with AsyncSession(self.engine) as session:
            return await EmployeeService(EmployeeRepository(session)).pin_login(request)

    async def device_keys(self):
        async with AsyncSession(self.engine) as session:
            result = await session.execute(text("""
                SELECT id, device_key FROM devices
                WHERE company_id = :company_id ORDER BY pos_number
            """), {"company_id": self.company_id})
            return dict(result.all())

    async def active_sessions(self):
        async with AsyncSession(self.engine) as session:
            result = await session.execute(text("""
                SELECT device_id, token_hash FROM pos_sessions
                WHERE company_id = :company_id AND revoked_at IS NULL
                  AND expires_at > now()
            """), {"company_id": self.company_id})
            return result.all()

    async def test_takeover_persists_retry_rejects_former_and_transfers_back(self):
        approved = await self.login(self.request(self.new_key, takeover=True))
        self.assertEqual(approved["device_id"], self.target_id)
        self.assertEqual(approved["device_key"], self.new_key)
        keys = await self.device_keys()
        self.assertEqual(keys[self.target_id], self.new_key)
        self.assertTrue(keys[self.source_id].startswith("released-"))

        retried = await self.login(self.request(
            self.new_key, takeover=False,
            session_token=approved["access_token"],
        ))
        self.assertEqual(retried["access_token"], approved["access_token"])
        async with AsyncSession(self.engine) as session:
            actor = await resolve_auth_actor(approved["access_token"], session)
            self.assertIsNotNone(actor)
            self.assertEqual(actor.company_id, self.company_id)

        with self.assertRaises(HTTPException) as former:
            await self.login(self.request(self.old_key, takeover=False))
        self.assertEqual(former.exception.status_code, 409)

        transferred_back = await self.login(self.request(self.old_key, takeover=True))
        self.assertEqual(transferred_back["device_key"], self.old_key)
        with self.assertRaises(HTTPException) as displaced:
            await self.login(self.request(self.new_key, takeover=False))
        self.assertEqual(displaced.exception.status_code, 409)
        sessions = await self.active_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].device_id, self.target_id)

    async def test_concurrent_takeover_and_replay_leave_one_identity_and_session(self):
        first, replay = await asyncio.gather(
            self.login(self.request(self.new_key, takeover=True)),
            self.login(self.request(self.new_key, takeover=True)),
        )
        self.assertEqual(first["device_key"], self.new_key)
        self.assertEqual(replay["device_key"], self.new_key)
        keys = await self.device_keys()
        self.assertEqual(keys[self.target_id], self.new_key)
        self.assertEqual(sum(key == self.new_key for key in keys.values()), 1)
        self.assertEqual(len(await self.active_sessions()), 1)

    async def test_takeover_transaction_rolls_back_all_identity_and_session_changes(self):
        async with AsyncSession(self.engine) as session:
            failing = FailingCommitSession(session)
            service = EmployeeService(EmployeeRepository(failing))
            with self.assertRaisesRegex(RuntimeError, "synthetic commit failure"):
                await service.pin_login(self.request(self.new_key, takeover=True))

        keys = await self.device_keys()
        self.assertEqual(keys[self.target_id], self.old_key)
        self.assertEqual(keys[self.source_id], self.new_key)
        sessions = await self.active_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].device_id, self.source_id)


if __name__ == "__main__":
    unittest.main()
