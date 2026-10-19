"""Phase 7B integration checks; refuse every non-disposable database."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.auth.dependencies import AuthActor, resolve_auth_actor
from app.auth.security import hash_password, hash_session_token
from app.employees.admin_service import EmployeeAdminService
from app.employees.manager_approval import consume_manager_authorization, issue_manager_authorization
from app.employees.permissions import normalize_permissions
from app.employees.repository import EmployeeRepository
from app.employees.schema import EmployeeCreate, EmployeeUpdate, ManagerAuthorizationCreate, RoleCreate, RoleUpdate
from app.employees.service import EmployeeService
from app.models import AuditEvent, Branch, Company, Device, Employee, ManagerAuthorization, PosSession, Shop, User


class Phase7BPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = os.getenv("APEX_PHASE7B_TEST_DATABASE_URL")
        if not url:
            self.skipTest("APEX_PHASE7B_TEST_DATABASE_URL is not configured")
        if not (make_url(url).database or "").startswith("apexretail_phase7b_test"):
            self.fail("Refusing a database without the Phase 7B disposable prefix")
        self.engine = create_async_engine(url)
        self.connection = await self.engine.connect()
        self.transaction = await self.connection.begin()
        self.db = AsyncSession(bind=self.connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
        self.addAsyncCleanup(self.cleanup)
        self.company = Company(name="Synthetic Phase 7B", owner_email=f"{uuid4()}@example.test")
        self.db.add(self.company)
        await self.db.flush()
        self.shop = Shop(company_id=self.company.id, name="Synthetic Shop")
        self.db.add(self.shop)
        await self.db.flush()
        self.branch = Branch(company_id=self.company.id, shop_id=self.shop.id, name="Main")
        self.other_branch = Branch(company_id=self.company.id, shop_id=self.shop.id, name="Other")
        self.user = User(company_id=self.company.id, email=f"{uuid4()}@example.test", password_hash="fixture", role="owner")
        self.db.add_all([self.branch, self.other_branch, self.user])
        await self.db.flush()
        self.device = Device(company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id, name="Fixture Register", device_key=str(uuid4()))
        self.cashier = self.employee("Cashier", "cashier", "1234")
        self.manager = self.employee("Supervisor", "supervisor", "9876")
        self.db.add_all([self.device, self.cashier, self.manager])
        await self.db.flush()
        self.session_token = str(uuid4())
        self.pos_session = PosSession(
            company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id,
            device_id=self.device.id, employee_id=self.cashier.id,
            token_hash=hash_session_token(self.session_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        self.db.add(self.pos_session)
        await self.db.commit()
        self.actor = AuthActor(actor_type="employee", company_id=self.company.id, role="cashier", employee=self.cashier, permissions=self.cashier.permissions, pos_session=self.pos_session)
        self.owner = AuthActor(actor_type="user", company_id=self.company.id, role="owner", user=self.user)
        self.service = EmployeeService(EmployeeRepository(self.db))
        self.admin = EmployeeAdminService(self.db)

    def employee(self, name, role, pin):
        return Employee(company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id, name=name, role=role, permissions=normalize_permissions(role, {}), pin=hash_password(pin))

    async def cleanup(self):
        await self.db.close()
        await self.transaction.rollback()
        await self.connection.close()
        await self.engine.dispose()

    def request(self, **changes):
        values = dict(company_id=self.company.id, manager_pin="9876", action="stock_adjustment", reason="Synthetic adjustment approval", context={"product_id": str(uuid4()), "quantity": "2.000"})
        values.update(changes)
        return ManagerAuthorizationCreate(**values)

    async def test_employee_crud_pin_hash_device_restriction_and_audit(self):
        created = await self.service.create(EmployeeCreate(
            company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id,
            name="New Clerk", pin="2468", role="inventory_clerk",
            device_restricted=True, device_ids=[self.device.id],
        ), self.owner)
        stored = await self.db.get(Employee, created["id"])
        self.assertTrue(stored.pin.startswith("$2"))
        self.assertEqual(created["device_ids"], [self.device.id])
        updated = await self.service.update(self.company.id, stored.id, EmployeeUpdate(name="Updated Clerk", active=False), self.owner)
        self.assertEqual(updated["name"], "Updated Clerk")
        self.assertFalse(updated["active"])
        actions = (await self.db.execute(select(AuditEvent.action).where(AuditEvent.company_id == self.company.id))).scalars().all()
        self.assertIn("employee_created", actions)
        self.assertIn("employee_deactivated", actions)

    async def test_custom_role_changes_propagate_and_cannot_escalate(self):
        role = await self.admin.create_role(RoleCreate(company_id=self.company.id, name="Receiving specialist", permissions={"inventory_receive": True}), self.owner)
        await self.service.update(self.company.id, self.cashier.id, EmployeeUpdate(role_id=role["id"]), self.owner)
        permissions = await self.service.effective_permissions(self.cashier, self.db)
        self.assertTrue(permissions["inventory_receive"])
        self.assertFalse(permissions["sales_process"])
        await self.admin.update_role(self.company.id, role["id"], RoleUpdate(permissions={"inventory_receive": False}), self.owner)
        self.assertFalse((await self.service.effective_permissions(self.cashier, self.db))["inventory_receive"])
        with self.assertRaises(HTTPException) as caught:
            await self.admin.create_role(RoleCreate(company_id=self.company.id, name="Escalation", permissions={"roles_manage": True}), self.actor)
        self.assertEqual(caught.exception.status_code, 403)
        with self.assertRaises(HTTPException):
            await self.admin.update_role(self.company.id, role["id"], RoleUpdate(name="owner"), self.owner)

    async def test_device_restriction_revokes_existing_session(self):
        await self.service.update(self.company.id, self.cashier.id, EmployeeUpdate(device_restricted=True, device_ids=[]), self.owner)
        self.assertIsNone(await resolve_auth_actor(self.session_token, self.db))
        self.assertEqual(self.pos_session.revoke_reason, "device_access_revoked")

    async def test_deactivated_employee_cannot_restore_session(self):
        await self.service.update(self.company.id, self.cashier.id, EmployeeUpdate(active=False), self.owner)
        self.assertIsNotNone(self.pos_session.revoked_at)
        self.assertIsNone(await resolve_auth_actor(self.session_token, self.db))

    async def test_manager_approval_is_single_use_and_numerically_canonical(self):
        request = self.request()
        result = await issue_manager_authorization(self.db, self.actor, request)
        context = {**request.context, "quantity": "2"}
        await consume_manager_authorization(self.db, self.actor, result["authorization_token"], request.action, context)
        await self.db.commit()
        with self.assertRaises(HTTPException):
            await consume_manager_authorization(self.db, self.actor, result["authorization_token"], request.action, context)

    async def test_manager_approval_rejects_wrong_action_device_and_revocation(self):
        request = self.request()
        result = await issue_manager_authorization(self.db, self.actor, request)
        with self.assertRaises(HTTPException):
            await consume_manager_authorization(self.db, self.actor, result["authorization_token"], "refund", request.context)
        self.manager.active = False
        await self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            await consume_manager_authorization(self.db, self.actor, result["authorization_token"], request.action, request.context)
        self.assertIn("revoked", caught.exception.detail)

    async def test_expired_approval_and_different_device_are_rejected(self):
        from types import SimpleNamespace
        request = self.request()
        issued = await issue_manager_authorization(self.db, self.actor, request)
        authorization = (await self.db.execute(select(ManagerAuthorization).where(
            ManagerAuthorization.company_id == self.company.id,
        ))).scalar_one()
        authorization.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await self.db.commit()
        with self.assertRaises(HTTPException):
            await consume_manager_authorization(self.db, self.actor, issued["authorization_token"], request.action, request.context)
        authorization.expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        await self.db.commit()
        self.actor.pos_session = SimpleNamespace(device_id=uuid4(), branch_id=self.branch.id)
        with self.assertRaises(HTTPException):
            await consume_manager_authorization(self.db, self.actor, issued["authorization_token"], request.action, request.context)

    async def test_employee_history_includes_profile_changes(self):
        await self.service.update(self.company.id, self.cashier.id, EmployeeUpdate(name="Renamed cashier"), self.owner)
        events = await self.admin.audit_log(self.company.id, employee_id=self.cashier.id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "employee_updated")

    async def test_dashboard_summary_uses_only_the_selected_branch(self):
        from app.dashboard.repository import DashboardRepository
        for branch, amount in ((self.branch, 9), (self.other_branch, 99)):
            await self.db.execute(text("""
                INSERT INTO sales (id,company_id,shop_id,branch_id,receipt_number,
                  subtotal_amount,tax_rate,tax_amount,tax_inclusive,total_amount,
                  amount_received,change_due,payment_method,status,reprint_count,created_at)
                VALUES (:id,:company,:shop,:branch,:receipt,:amount,0,0,false,
                  :amount,:amount,0,'cash','completed',0,now())
            """), {"id": uuid4(), "company": self.company.id, "shop": self.shop.id,
                    "branch": branch.id, "receipt": str(uuid4()), "amount": amount})
        main = await DashboardRepository(self.db).get_summary(self.company.id, self.branch.id)
        other = await DashboardRepository(self.db).get_summary(self.company.id, self.other_branch.id)
        self.assertEqual(main["today_sales"], 9)
        self.assertEqual(main["today_transactions"], 1)
        self.assertEqual(other["today_sales"], 99)

    async def test_manager_approval_rejects_other_branch_and_missing_action_permission(self):
        self.manager.branch_id = self.other_branch.id
        await self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            await issue_manager_authorization(self.db, self.actor, self.request())
        self.assertEqual(caught.exception.status_code, 403)
        self.manager.branch_id = self.branch.id
        self.manager.permissions = normalize_permissions("supervisor", {"inventory_adjust": False})
        await self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            await issue_manager_authorization(self.db, self.actor, self.request())
        self.assertEqual(caught.exception.status_code, 401)

    async def test_manager_pin_attempts_are_rate_limited_and_not_logged(self):
        for _ in range(5):
            with self.assertRaises(HTTPException) as caught:
                await issue_manager_authorization(self.db, self.actor, self.request(manager_pin="0000"))
            self.assertEqual(caught.exception.status_code, 401)
        with self.assertRaises(HTTPException) as caught:
            await issue_manager_authorization(self.db, self.actor, self.request())
        self.assertEqual(caught.exception.status_code, 429)
        events = (await self.db.execute(select(AuditEvent).where(AuditEvent.company_id == self.company.id))).scalars().all()
        self.assertNotIn("0000", str([event.details for event in events]))

    async def test_branch_and_foreign_company_role_assignment_are_rejected(self):
        role = await self.admin.create_role(RoleCreate(company_id=self.company.id, name="Local role"), self.owner)
        with self.assertRaises(HTTPException):
            await self.service.update(self.company.id, self.cashier.id, EmployeeUpdate(role_id=uuid4()), self.owner)
        self.assertIsNone(await self.service.repo.get_role(uuid4(), role["id"]))
        manager_actor = AuthActor(actor_type="employee", company_id=self.company.id, role="supervisor", employee=self.manager, permissions=self.manager.permissions)
        with self.assertRaises(HTTPException):
            await self.service.update(self.company.id, self.cashier.id, EmployeeUpdate(branch_id=self.other_branch.id), manager_actor)

    async def test_audit_history_cannot_be_updated_or_deleted(self):
        event = AuditEvent(company_id=self.company.id, action="synthetic_audit_test")
        self.db.add(event)
        await self.db.commit()
        for verb in ("UPDATE audit_events SET action='tampered'", "DELETE FROM audit_events"):
            with self.assertRaises(Exception) as caught:
                async with self.db.begin_nested():
                    await self.db.execute(text(f"{verb} WHERE id=:id"), {"id": event.id})
            self.assertIn("append-only", str(caught.exception))

    async def test_audit_protection_preserves_authorized_terminal_deletion(self):
        event = AuditEvent(company_id=self.company.id, device_id=self.device.id,
                           action="terminal_delete", details={"terminal_id": str(self.device.id)})
        self.db.add(event)
        await self.db.commit()
        await self.db.execute(text("DELETE FROM devices WHERE id=:id"), {"id": self.device.id})
        await self.db.commit()
        await self.db.refresh(event)
        self.assertIsNone(event.device_id)
        self.assertEqual(event.details["terminal_id"], str(self.device.id))
        self.assertEqual(event.action, "terminal_delete")
