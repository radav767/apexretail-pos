import unittest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from app.employees.manager_approval import (
    consume_manager_authorization,
    context_hash,
    token_hash,
)
from app.employees.permissions import PERMISSION_KEYS, has_permission, normalize_permissions
from app.auth.dependencies import AuthActor, require_permission


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class RecordingDB:
    def __init__(self, authorization, approver=None):
        self.authorization = authorization
        self.approver = approver
        self.added = []

    async def execute(self, _query):
        if "FROM employees" in str(_query):
            return ScalarResult(self.approver)
        return ScalarResult(self.authorization)

    def add(self, value):
        self.added.append(value)


class Phase7BPermissionTests(unittest.IsolatedAsyncioTestCase):
    def test_product_edit_permission_does_not_reveal_restricted_cost(self):
        from app.products.router import product_response
        from app.products.schema import ProductOut
        actor = AuthActor(actor_type="employee", company_id=uuid4(), role="custom", permissions=normalize_permissions("kitchen_staff", {"products_edit": True, "product_costs_view": False}))
        product = ProductOut(id=uuid4(), company_id=actor.company_id, name="Restricted cost fixture", category_id=None, sku=None, barcode=None, unit="each", cost_price=Decimal("5.50"), selling_price=Decimal("10.00"), stock_qty=Decimal("2"), reorder_level=Decimal("0"), active=True)
        response = product_response(product, actor)
        self.assertIsNone(response.cost_price)
        self.assertEqual(product.cost_price, Decimal("5.50"))
        self.assertEqual(response.selling_price, Decimal("10.00"))

    async def test_every_granular_permission_rejects_explicit_denial(self):
        for key in PERMISSION_KEYS:
            with self.subTest(permission=key):
                actor = AuthActor(actor_type="employee", company_id=uuid4(), role="custom", permissions=normalize_permissions("kitchen_staff", {key: False}))
                with self.assertRaises(HTTPException) as caught:
                    await require_permission(key)(actor)
                self.assertEqual(caught.exception.status_code, 403)
                actor.permissions = normalize_permissions("kitchen_staff", {key: True})
                self.assertIs(await require_permission(key)(actor), actor)

    def test_explicit_granular_denial_overrides_legacy_permission(self):
        permissions = normalize_permissions(
            "cashier",
            {"sales": True, "sales_history_view": False},
        )
        self.assertTrue(has_permission(permissions, "sales_process"))
        self.assertFalse(has_permission(permissions, "sales_history_view"))

    def test_cashier_and_manager_presets_remain_backwards_compatible(self):
        cashier = normalize_permissions("cashier", {})
        manager = normalize_permissions("manager", {})
        self.assertTrue(has_permission(cashier, "sales"))
        self.assertTrue(has_permission(cashier, "cash_movements_manage"))
        self.assertFalse(has_permission(cashier, "sales_refund"))
        self.assertTrue(has_permission(manager, "approve_restricted_actions"))
        self.assertTrue(has_permission(manager, "employees_manage"))

    def test_existing_expense_recording_permission_is_preserved(self):
        permissions = normalize_permissions("cashier", {"expenses_create": True, "expenses_manage": False})
        self.assertTrue(permissions["expenses_create"])
        self.assertFalse(permissions["expenses_manage"])

    async def test_manager_authorization_is_context_bound_and_single_use(self):
        raw_token = "one-time-manager-token"
        company_id = uuid4()
        requester_id = uuid4()
        device_id = uuid4()
        context = {
            "product_id": str(uuid4()),
            "adjustment_type": "remove",
            "quantity": "2.000",
        }
        authorization = SimpleNamespace(
            requester_employee_id=requester_id,
            approver_employee_id=uuid4(),
            company_id=company_id,
            device_id=device_id,
            action="stock_adjustment",
            context_hash=context_hash(context),
            token_hash=token_hash(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            used_at=None,
        )
        actor = SimpleNamespace(
            company_id=company_id,
            actor_type="employee",
            employee=SimpleNamespace(id=requester_id),
            pos_session=SimpleNamespace(device_id=device_id, branch_id=uuid4()),
        )
        approver = SimpleNamespace(
            id=authorization.approver_employee_id, role="supervisor", role_id=None,
            branch_id=actor.pos_session.branch_id, permissions={},
        )
        db = RecordingDB(authorization, approver)

        consumed = await consume_manager_authorization(
            db, actor, raw_token, "stock_adjustment", context,
        )
        self.assertIs(consumed, authorization)
        self.assertIsNotNone(authorization.used_at)
        self.assertEqual(len(db.added), 1)

        with self.assertRaisesRegex(HTTPException, "invalid, expired, used"):
            await consume_manager_authorization(
                db, actor, raw_token, "stock_adjustment", context,
            )

    async def test_manager_authorization_rejects_different_context(self):
        raw_token = "context-manager-token"
        company_id = uuid4()
        requester_id = uuid4()
        device_id = uuid4()
        authorization = SimpleNamespace(
            requester_employee_id=requester_id,
            approver_employee_id=uuid4(),
            company_id=company_id,
            device_id=device_id,
            action="refund",
            context_hash=context_hash({"original_sale_id": "sale-a"}),
            token_hash=token_hash(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            used_at=None,
        )
        actor = SimpleNamespace(
            company_id=company_id,
            actor_type="employee",
            employee=SimpleNamespace(id=requester_id),
            pos_session=SimpleNamespace(device_id=device_id),
        )

        with self.assertRaisesRegex(HTTPException, "invalid, expired, used"):
            await consume_manager_authorization(
                RecordingDB(authorization), actor, raw_token, "refund",
                {"original_sale_id": "sale-b"},
            )
        self.assertIsNone(authorization.used_at)


if __name__ == "__main__":
    unittest.main()
