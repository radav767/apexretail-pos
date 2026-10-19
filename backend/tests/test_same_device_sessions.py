import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import HTTPException

from app.auth.security import hash_session_token
from app.employees.schema import PinLoginRequest
from app.employees.service import EmployeeService
from app.models import AuditEvent


class Result:
    def __init__(self, rows):
        self.rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class SameDeviceSessionTest(unittest.IsolatedAsyncioTestCase):
    def fixture(
        self, *, existing_kind=None, historical_kind=None,
        requested_key_owner=None, source_terminal_existing=None,
    ):
        company_id = uuid4()
        shop_id = uuid4()
        branch_id = uuid4()
        employee = SimpleNamespace(
            id=uuid4(), company_id=company_id, shop_id=shop_id,
            branch_id=branch_id, name="Fixture Cashier", role="cashier",
            permissions={"sales": True}, pin="1234",
        )
        device = SimpleNamespace(
            id=uuid4(), company_id=company_id, shop_id=shop_id,
            branch_id=branch_id, name="Fixture POS", friendly_name="Fixture POS",
            pos_number=1, device_key="stable-device-key",
        )
        existing = None
        terminal_existing = None
        historical = None
        if existing_kind == "same":
            existing = self.session(employee, device)
            terminal_existing = existing
        elif existing_kind == "other":
            existing = self.session(employee, SimpleNamespace(id=uuid4()))
        if historical_kind == "expired":
            historical = self.session(
                employee, device, token="expired-token", expired=True,
            )
        shop = SimpleNamespace(id=shop_id, name="Fixture Shop")
        responses = [
            Result([shop_id]), Result([shop]), Result([device]), Result([device]),
            Result([existing] if existing else []),
            Result([terminal_existing] if terminal_existing else []),
        ]
        if existing is None:
            responses.append(Result([historical] if historical else []))
        responses.extend([
            Result([requested_key_owner] if requested_key_owner else []),
        ])
        if requested_key_owner and requested_key_owner.id != device.id:
            responses.append(
                Result([source_terminal_existing] if source_terminal_existing else [])
            )
        response_iter = iter(responses)

        async def execute(statement, _params=None):
            if "pg_advisory_xact_lock" in str(statement):
                return Result([])
            return next(response_iter)

        db = SimpleNamespace(
            execute=AsyncMock(side_effect=execute), commit=AsyncMock(),
            rollback=AsyncMock(), flush=AsyncMock(), add=Mock(),
        )
        repo = SimpleNamespace(
            db=db,
            active_pin_candidates=AsyncMock(return_value=[employee]),
        )
        return EmployeeService(repo), db, employee, device, existing or historical

    @staticmethod
    def session(employee, device, token="session-token", *, expired=False):
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=uuid4(), employee_id=employee.id, device_id=device.id,
            token_hash=hash_session_token(token), revoked_at=None,
            expires_at=now - timedelta(minutes=1) if expired else now + timedelta(hours=1),
            last_authenticated_at=now - timedelta(minutes=5), created_at=now - timedelta(hours=1),
        )

    async def test_reload_back_repeated_login_and_second_tab_resume_same_session(self):
        service, db, employee, device, active = self.fixture(existing_kind="same")
        result = await service.pin_login(PinLoginRequest(
            company_id=employee.company_id, branch_id=device.branch_id,
            shop_id=device.shop_id, device_id=device.id, pin="1234",
            device_key=device.device_key, session_token="session-token",
        ))
        self.assertEqual(result["access_token"], "session-token")
        self.assertEqual(result["device_id"], device.id)
        self.assertGreater(active.expires_at, datetime.now(timezone.utc))
        self.assertEqual(db.add.call_count, 1)
        self.assertIsInstance(db.add.call_args.args[0], AuditEvent)
        db.commit.assert_awaited_once()

    async def test_expired_same_device_authentication_is_rotated_without_migration(self):
        service, db, employee, device, expired = self.fixture(historical_kind="expired")
        result = await service.pin_login(PinLoginRequest(
            company_id=employee.company_id, branch_id=device.branch_id,
            shop_id=device.shop_id, device_id=device.id, pin="1234",
            device_key=device.device_key,
        ))
        self.assertNotEqual(result["access_token"], "expired-token")
        self.assertEqual(expired.token_hash, hash_session_token(result["access_token"]))
        self.assertGreater(expired.expires_at, datetime.now(timezone.utc))
        self.assertEqual(db.add.call_count, 1)
        self.assertIsInstance(db.add.call_args.args[0], AuditEvent)

    async def test_different_browser_identity_requires_existing_takeover_workflow(self):
        service, db, employee, selected_device, _active = self.fixture(existing_kind="other")
        with self.assertRaises(HTTPException) as caught:
            await service.pin_login(PinLoginRequest(
                company_id=employee.company_id, branch_id=selected_device.branch_id,
                shop_id=selected_device.shop_id, device_id=selected_device.id,
                pin="1234", device_key=selected_device.device_key,
            ))
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("another device", caught.exception.detail)
        db.commit.assert_not_awaited()

    async def test_same_terminal_id_without_its_device_key_is_not_same_device(self):
        service, db, employee, device, _active = self.fixture(existing_kind="same")
        with self.assertRaises(HTTPException) as caught:
            await service.pin_login(PinLoginRequest(
                company_id=employee.company_id, branch_id=device.branch_id,
                shop_id=device.shop_id, device_id=device.id, pin="1234",
                device_key="different-browser-key", session_token="session-token",
            ))
        self.assertEqual(caught.exception.status_code, 409)
        db.commit.assert_not_awaited()

    async def test_explicit_takeover_still_moves_a_genuinely_different_device(self):
        source = SimpleNamespace(
            id=uuid4(), company_id=uuid4(), device_key="new-browser-key",
        )
        # Rebuild with the same-tenant device that currently owns the browser
        # identity so both sides of the transfer are exercised.
        service, db, employee, device, active = self.fixture(
            existing_kind="other", requested_key_owner=source,
        )
        source.company_id = employee.company_id
        requested_key = source.device_key
        result = await service.pin_login(PinLoginRequest(
            company_id=employee.company_id, branch_id=device.branch_id,
            shop_id=device.shop_id, device_id=device.id, pin="1234",
            device_key=requested_key, takeover=True,
        ))
        self.assertEqual(result["device_id"], device.id)
        self.assertEqual(result["device_key"], requested_key)
        self.assertEqual(device.device_key, requested_key)
        self.assertTrue(str(source.device_key).startswith("released-"))
        self.assertIsNotNone(active.revoked_at)
        self.assertEqual(active.revoke_reason, "takeover")
        self.assertEqual(db.add.call_count, 4)
        self.assertIsInstance(db.add.call_args_list[-1].args[0], AuditEvent)
        db.flush.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_cross_company_device_key_cannot_be_taken_over(self):
        foreign_owner = SimpleNamespace(
            id=uuid4(), company_id=uuid4(), device_key="foreign-key",
        )
        service, db, employee, device, _active = self.fixture(
            existing_kind="other", requested_key_owner=foreign_owner,
        )
        with self.assertRaises(HTTPException) as caught:
            await service.pin_login(PinLoginRequest(
                company_id=employee.company_id, branch_id=device.branch_id,
                shop_id=device.shop_id, device_id=device.id, pin="1234",
                device_key=foreign_owner.device_key, takeover=True,
            ))
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("another company", caught.exception.detail)
        db.commit.assert_not_awaited()

    async def test_takeover_commit_failure_rolls_back_transaction(self):
        service, db, employee, device, active = self.fixture(existing_kind="other")
        db.commit.side_effect = RuntimeError("synthetic commit failure")
        with self.assertRaisesRegex(RuntimeError, "synthetic commit failure"):
            await service.pin_login(PinLoginRequest(
                company_id=employee.company_id, branch_id=device.branch_id,
                shop_id=device.shop_id, device_id=device.id, pin="1234",
                device_key="new-browser-key", takeover=True,
            ))
        self.assertIsNotNone(active.revoked_at)
        db.rollback.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
