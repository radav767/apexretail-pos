import asyncio
import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DBAPIError
from app.models import Employee, PosSession, TipEntry, TipEntitlement, Sale, CashierShiftCashMovement, CashierShift
from app.business_operations.tips import TipService, allocate
from app.business_operations.tip_schema import TipConfigInput, TipInput
from app.shifts.service import ShiftService
from app.shifts.repository import ShiftRepository
from app.shifts.schema import ShiftOpen, ShiftClose
from app.auth.dependencies import AuthActor
import test_phase7d_operations as fixtures


class AllocationTests(unittest.TestCase):
    def test_allocations_conserve_minor_units_and_are_deterministic(self):
        for precision in range(5):
            unit = Decimal(1).scaleb(-precision)
            for ticks in range(1, 40):
                amount = unit * ticks
                result = allocate(amount, {"a": Decimal(1), "b": Decimal(2), "c": Decimal(3)}, precision)
                self.assertEqual(sum(result.values()), amount)
                self.assertTrue(all(v >= 0 for v in result.values()))
                self.assertEqual(result, allocate(amount, {"c": Decimal(3), "b": Decimal(2), "a": Decimal(1)}, precision))


class TipIntegrationTests(unittest.IsolatedAsyncioTestCase):
    cleanup = fixtures.Phase7DOperationsTests.cleanup

    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.manager = TipService(self.db, self.owner)
        self.pos = TipService(self.db, self.cashier)
        self.cashier.permissions = {**self.cashier.permissions, "tips_manage": True, "tips_payout": True}
        await self.manager.configure(TipConfigInput(enabled=True, policy="staff"))
        self.shifts = ShiftService(ShiftRepository(self.db))
        self.shift = await self.shifts.open(ShiftOpen(idempotency_key=str(uuid4())), self.cashier)

    def command(self, **changes):
        values = dict(request_id=uuid4(), shift_id=self.shift["id"], kind="collect", sale_id=self.sale.id,
            payment_method="cash", currency_code="USD", amount=10, reason="Confirmed synthetic tip", confirmed=True)
        values.update(changes)
        return TipInput(**values)

    async def report(self): return await self.manager.report(date.today(), date.today())

    async def test_staff_tip_cash_and_retries_do_not_change_sale_revenue_or_stock(self):
        sale_total, stock = self.sale.total_amount, self.balance.quantity
        command = self.command()
        first = await self.pos.record(command); second = await self.pos.record(command)
        self.assertEqual(first["id"], second["id"]); self.assertTrue(second["already_recorded"])
        self.assertEqual(self.sale.total_amount, sale_total); self.assertEqual(self.balance.quantity, stock)
        self.assertEqual((await self.db.execute(select(func.count(CashierShiftCashMovement.id)).where(CashierShiftCashMovement.shift_id == self.shift["id"]))).scalar_one(), 1)
        self.assertEqual(Decimal((await self.report())["balances"][0]["outstanding"]), 10)
        view = await self.shifts.view(await self.db.get(CashierShift, self.shift["id"]))
        self.assertEqual(view["currencies"][0]["expected_cash"], 10)
        self.assertEqual(view["summary"]["net_sales_base"], 0)

    async def test_shared_distribution_policy_changes_and_partial_refunds_preserve_original_shares(self):
        other = Employee(company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id,
            name="Synthetic colleague", role="waiter", pin=self.employee.pin, permissions={})
        self.db.add(other); await self.db.flush()
        await self.manager.configure(TipConfigInput(enabled=True, policy="shared", weights={self.employee.id: 1, other.id: 2}))
        first = await self.pos.record(self.command(amount="0.05", payment_method="card"))
        amounts = sorted((await self.db.execute(select(TipEntitlement.amount).where(TipEntitlement.entry_id == first["id"]))).scalars())
        self.assertEqual(amounts, [Decimal("0.02"), Decimal("0.03")])
        await self.manager.configure(TipConfigInput(enabled=True, policy="business", business_retention_confirmed=True))
        for amount in ("0.02", "0.03"):
            await self.pos.record(self.command(kind="reverse", sale_id=None, original_id=first["id"], payment_method="card", amount=amount))
        self.assertTrue(all(Decimal(row["outstanding"]) == 0 for row in (await self.report())["balances"]))
        with self.assertRaises(HTTPException):
            await self.pos.record(self.command(kind="reverse", sale_id=None, original_id=first["id"], payment_method="card", amount="0.01"))

    async def test_business_tips_have_no_employee_allocation_and_no_drawer_increase_for_mobile(self):
        await self.manager.configure(TipConfigInput(enabled=True, policy="business", business_retention_confirmed=True))
        receipt = await self.pos.record(self.command(payment_method="mobile"))
        self.assertEqual((await self.db.execute(select(func.count(TipEntitlement.id)).where(TipEntitlement.entry_id == receipt["id"]))).scalar_one(), 0)
        view = await self.shifts.view(await self.db.get(CashierShift, self.shift["id"]))
        self.assertEqual(view["currencies"][0]["expected_cash"], 0)
        self.assertEqual(view["tips"]["totals"][0]["policy"], "business")

    async def test_cash_payout_refund_and_immutable_closing_tip_snapshot(self):
        tip = await self.pos.record(self.command())
        payout = self.command(kind="payout", sale_id=None, employee_id=self.employee.id, amount=3)
        await self.pos.record(payout); await self.pos.record(payout)
        await self.pos.record(self.command(kind="reverse", sale_id=None, original_id=tip["id"], amount=2))
        closed = await self.shifts.close(self.shift["id"], ShiftClose(counted_balances=[{"currency_code": "USD", "amount": 5}],
            idempotency_key=str(uuid4()), confirmed=True), self.cashier)
        self.assertEqual(closed["currencies"][0]["expected_cash"], 5)
        self.assertEqual(len(closed["tips"]["totals"]), 3)
        from app.shifts.report import thermal_html, simple_pdf
        for width in ("58mm", "80mm"):
            html = thermal_html(closed, width)
            self.assertIn("TIPS (separate from sales)", html)
            self.assertIn("collect / cash / staff", html)
        self.assertIn(b"TIPS", simple_pdf(closed))
        with self.assertRaises(HTTPException): await self.pos.record(self.command())
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():
                await self.db.execute(text("UPDATE cashier_shifts SET tips_snapshot='{}'::jsonb WHERE id=:id"), {"id": self.shift["id"]})

    async def test_paid_tip_reversal_records_negative_entitlement_without_fabricated_payroll(self):
        tip = await self.pos.record(self.command(payment_method="card"))
        await self.pos.record(self.command(kind="payout", sale_id=None, employee_id=self.employee.id, amount=10, payment_method="mobile"))
        await self.pos.record(self.command(kind="reverse", sale_id=None, original_id=tip["id"], amount=10, payment_method="card"))
        balance = (await self.report())["balances"][0]
        self.assertEqual(Decimal(balance["outstanding"]), -10); self.assertTrue(balance["overpaid_after_reversal"])
        with self.assertRaises(HTTPException): await self.pos.record(self.command(kind="payout", sale_id=None, employee_id=self.employee.id, amount=1, payment_method="mobile"))

    async def test_permissions_precision_confirmation_original_method_and_payload_identity(self):
        tip = await self.pos.record(self.command(payment_method="card"))
        with self.assertRaises(HTTPException): await self.pos.record(self.command(kind="reverse", sale_id=None, original_id=tip["id"], payment_method="mobile"))
        with self.assertRaises(HTTPException): await self.pos.record(self.command(amount="0.001"))
        with self.assertRaises(HTTPException): await self.pos.record(self.command(confirmed=False))
        command = self.command(); await self.pos.record(command)
        with self.assertRaises(HTTPException): await self.pos.record(command.model_copy(update={"amount": Decimal(11)}))
        self.cashier.permissions["tips_collect"] = False
        with self.assertRaises(HTTPException) as error: await self.pos.record(self.command())
        self.assertEqual(error.exception.status_code, 403)

    async def test_ledger_and_entitlements_reject_direct_update_and_delete(self):
        receipt = await self.pos.record(self.command())
        for table in ("tip_entries", "tip_entitlements"):
            grants = (await self.db.execute(text(f"SELECT has_table_privilege('apex_user','{table}','UPDATE'),has_table_privilege('apex_user','{table}','DELETE')"))).one()
            self.assertEqual(tuple(grants), (False, False))
            with self.assertRaises(DBAPIError):
                async with self.db.begin_nested(): await self.db.execute(text(f"DELETE FROM {table}"))

    async def test_disabled_policy_does_not_erase_existing_liability(self):
        await self.pos.record(self.command())
        await self.manager.configure(TipConfigInput(enabled=False))
        with self.assertRaises(HTTPException): await self.pos.record(self.command())
        await self.pos.record(self.command(kind="payout", sale_id=None, employee_id=self.employee.id, amount=1))
        self.assertEqual(Decimal((await self.report())["balances"][0]["outstanding"]), 9)

    async def test_product_tip_guard_preserves_authorized_historical_service_refunds(self):
        from app.business_operations.schema import ProfileInput
        from app.sales.service import SalesService
        from app.sales.repository import SalesRepository
        from app.sales.schema import SaleCreate, SaleItemCreate, RefundCreate, RefundItemCreate
        self.product.product_type = "service"; self.product.track_inventory = False
        await self.svc.save_profile(ProfileInput(profile="restaurant", tip_product_id=self.product.id))
        await self.manager.configure(TipConfigInput(enabled=False))
        sales = SalesService(SalesRepository(self.db))
        with self.assertRaises(HTTPException) as error:
            await sales.create_sale(SaleCreate(company_id=self.company.id, branch_id=self.branch.id, device_id=self.device.id,
                client_sale_id=uuid4(), amount_received=100, items=[SaleItemCreate(product_id=self.product.id, quantity=1)]), actor=self.owner)
        self.assertEqual(error.exception.status_code, 409)
        from app.models import SaleItem
        item = (await self.db.execute(select(SaleItem).where(SaleItem.sale_id == self.sale.id))).scalar_one()
        refund = await sales.create_refund(RefundCreate(company_id=self.company.id, original_sale_id=self.sale.id,
            branch_id=self.branch.id, device_id=self.device.id, reason="Authorized historical service refund",
            items=[RefundItemCreate(sale_item_id=item.id, quantity=1)]), actor=self.owner)
        self.assertEqual(refund.total_amount, -12)

    async def test_tip_reports_and_settings_reject_cross_company_and_branch_access(self):
        from app.models import Company, User
        other = Company(name="Other synthetic tenant", owner_email=f"{uuid4()}@example.test")
        self.db.add(other); await self.db.flush()
        user = User(company_id=other.id, email=f"{uuid4()}@example.test", password_hash="fixture-only", role="owner")
        self.db.add(user); await self.db.flush()
        actor = AuthActor(actor_type="user", company_id=other.id, role="owner", user=user)
        other_service = TipService(self.db, actor)
        self.assertEqual((await other_service.report(date.today(), date.today()))["balances"], [])
        with self.assertRaises(HTTPException): await other_service.record(self.command(kind="payout", sale_id=None, employee_id=self.employee.id, payment_method="mobile"))
        with self.assertRaises(HTTPException): await other_service.configure(TipConfigInput(enabled=True, policy="shared", weights={self.employee.id: 1}))
        self.cashier.permissions["tips_reports_view"] = True
        with self.assertRaises(HTTPException): await self.pos.report(date.today(), date.today(), uuid4())

    async def test_tip_collection_rejects_mismatched_session_branch_and_disabled_employee(self):
        from types import SimpleNamespace
        session = self.cashier.pos_session
        self.cashier.pos_session = SimpleNamespace(employee_id=self.employee.id, company_id=self.company.id,
            device_id=self.device.id, branch_id=uuid4(), shop_id=self.shop.id)
        with self.assertRaises(HTTPException) as error: await self.pos.record(self.command())
        self.assertEqual(error.exception.status_code, 403)
        self.cashier.pos_session = session
        self.employee.active = False
        with self.assertRaises(HTTPException) as error: await self.pos.record(self.command())
        self.assertEqual(error.exception.status_code, 403)

    async def test_z_parallel_collection_has_one_allocation_and_cash_movement(self):
        command = self.command()
        company_id, employee_id, session_id = self.company.id, self.employee.id, self.session.id
        permissions = self.cashier.permissions
        await self.db.commit(); await self.transaction.commit()
        async def record():
            async with AsyncSession(self.engine, expire_on_commit=False) as db:
                actor = AuthActor(actor_type="employee", company_id=company_id, role="cashier", permissions=permissions,
                    employee=await db.get(Employee, employee_id), pos_session=await db.get(PosSession, session_id))
                return await TipService(db, actor).record(command)
        first, second = await asyncio.gather(record(), record())
        self.assertEqual(first["id"], second["id"])
        async with AsyncSession(self.engine) as db:
            self.assertEqual((await db.execute(select(func.count(TipEntitlement.id)).where(TipEntitlement.entry_id == first["id"]))).scalar_one(), 1)
