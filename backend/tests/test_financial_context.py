import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.financial_context import resolve_shift_for_write


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Database:
    def __init__(self, settings, shift):
        self.settings = settings
        self.shift = shift
        self.calls = []

    async def execute(self, statement):
        self.calls.append(statement)
        return _Result(self.settings if len(self.calls) == 1 else self.shift)


class FinancialContextTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.company_id = uuid4()
        self.branch_id = uuid4()
        self.device_id = uuid4()
        self.employee_id = uuid4()
        self.shift_id = uuid4()
        self.settings = SimpleNamespace(shift_enforcement_enabled=False, shift_required_from=None)
        self.shift = SimpleNamespace(
            id=self.shift_id, company_id=self.company_id, branch_id=self.branch_id,
            shop_id=uuid4(), device_id=self.device_id, employee_id=self.employee_id,
            status="open",
        )
        self.session = SimpleNamespace(
            company_id=self.company_id, branch_id=self.branch_id, employee_id=self.employee_id,
            shop_id=self.shift.shop_id, device_id=self.device_id,
        )
        self.actor = SimpleNamespace(
            actor_type="employee", employee=SimpleNamespace(id=self.employee_id),
            pos_session=self.session,
        )

    async def test_online_sale_auto_attaches_only_the_open_shift_for_session_identity(self):
        db = _Database(self.settings, self.shift)
        result = await resolve_shift_for_write(
            db, self.actor, self.company_id, self.branch_id, attach_active=True,
        )
        self.assertIs(result, self.shift)
        self.assertEqual(len(db.calls), 2)

    async def test_no_open_shift_is_allowed_while_enforcement_is_disabled(self):
        db = _Database(self.settings, None)
        result = await resolve_shift_for_write(
            db, self.actor, self.company_id, self.branch_id, attach_active=True,
        )
        self.assertIsNone(result)

    async def test_employee_jwt_without_pos_session_keeps_legacy_unshifted_sales_available(self):
        db = _Database(self.settings, self.shift)
        actor = SimpleNamespace(actor_type="employee", employee=SimpleNamespace(id=self.employee_id), pos_session=None)
        result = await resolve_shift_for_write(
            db, actor, self.company_id, self.branch_id, attach_active=True,
        )
        self.assertIsNone(result)
        self.assertEqual(len(db.calls), 1)

    async def test_offline_sync_never_attaches_a_current_shift(self):
        db = _Database(self.settings, self.shift)
        result = await resolve_shift_for_write(
            db, self.actor, self.company_id, self.branch_id,
            occurred_at=datetime.now(timezone.utc), attach_active=True,
        )
        self.assertIsNone(result)
        self.assertEqual(len(db.calls), 1)

    async def test_company_or_branch_mismatch_is_rejected(self):
        db = _Database(self.settings, self.shift)
        with self.assertRaisesRegex(HTTPException, "company or branch mismatch"):
            await resolve_shift_for_write(
                db, self.actor, self.company_id, uuid4(), attach_active=True,
            )

    async def test_pos_session_cashier_mismatch_is_rejected(self):
        db = _Database(self.settings, self.shift)
        self.session.employee_id = uuid4()
        with self.assertRaisesRegex(HTTPException, "cashier mismatch"):
            await resolve_shift_for_write(
                db, self.actor, self.company_id, self.branch_id, attach_active=True,
            )

    async def test_explicit_shift_requires_opaque_pos_session(self):
        db = _Database(self.settings, self.shift)
        actor = SimpleNamespace(actor_type="employee", employee=self.actor.employee, pos_session=None)
        with self.assertRaisesRegex(HTTPException, "opaque POS session"):
            await resolve_shift_for_write(db, actor, self.company_id, self.branch_id, self.shift_id)

    async def test_offline_payload_cannot_assert_an_unverified_shift(self):
        db = _Database(self.settings, self.shift)
        with self.assertRaisesRegex(HTTPException, "Offline sales cannot attach"):
            await resolve_shift_for_write(
                db, self.actor, self.company_id, self.branch_id, self.shift_id,
                occurred_at=datetime.now(timezone.utc), attach_active=True,
            )

    async def test_signed_identity_is_checked_without_expiry_then_closed_shift_is_quarantined(self):
        occurred_at = datetime.now(timezone.utc)
        self.shift.opened_at = occurred_at - timedelta(hours=1)
        self.shift.status = "closed"
        claims = {
            "shift_id": str(self.shift_id),
            "company_id": str(self.company_id),
            "branch_id": str(self.branch_id),
            "device_id": str(self.device_id),
            "employee_id": str(self.employee_id),
        }
        db = _Database(self.settings, self.shift)
        with patch("app.financial_context.decode_offline_shift_token", return_value=claims) as decode:
            with self.assertRaises(HTTPException) as raised:
                await resolve_shift_for_write(
                    db, self.actor, self.company_id, self.branch_id, self.shift_id,
                    occurred_at=occurred_at, attach_active=True,
                    offline_shift_token="signed-expired-token",
                )
        decode.assert_called_once_with("signed-expired-token", verify_expiration=False)
        self.assertEqual(raised.exception.detail["code"], "offline_shift_closed")
