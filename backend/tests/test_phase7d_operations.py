import os
import asyncio
import unittest
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession
import test_phase7c_printing as fixtures
from app.models import (Company, CompanySetting, CompanyCurrency, User, Customer, Product, InventoryBalance, InventoryMovement, ProductBatch, BatchAllocation,
    CommerceOrder, CommerceOrderItem, KitchenTicket, Sale, SaleItem, AuditEvent, PrintJob, PrinterStation, PrinterRoute, Employee)
from app.auth.dependencies import AuthActor
from app.employees.permissions import normalize_permissions
from app.employees.admin_service import EmployeeAdminService
from app.business_operations.service import BusinessService
from app.business_operations.profiles import infer_profile
from app.business_operations.schema import (OrderInput, OrderItemInput, ItemUpdate, TableInput, MoveInput, SplitInput, MergeInput, SettlementInput,
    ProfileInput, BatchInput, RoomInput, GuestInput)
from app.sales.schema import SaleCreate, SaleItemCreate, RefundCreate, RefundItemCreate
from app.sales.service import SalesService
from app.sales.repository import SalesRepository
from app.inventory.service import InventoryService
from app.inventory.repository import InventoryRepository
from app.inventory.schema import GRNCreate, StockAdjustmentCreate
from app.printing.schema import JobInput, ClaimInput


class ProfileUnitTests(unittest.TestCase):
    def test_legacy_business_labels_are_preserved_and_recognized(self):
        for label, key in (("Retail", "retail"), ("Restaurant", "restaurant"), ("Hotel / Hospitality", "hospitality"), ("Hardware / Wholesale", "wholesale"), ("Other", "general")):
            self.assertEqual(infer_profile(label), key)

    def test_custom_and_unknown_roles_do_not_inherit_kitchen_powers(self):
        self.assertFalse(normalize_permissions("denied", {})["kitchen_update"])
        self.assertFalse(normalize_permissions("missing-role", {})["kitchen_view"])
        self.assertTrue(normalize_permissions("kitchen_staff", {})["kitchen_view"])


class Phase7DOperationsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = os.getenv("APEX_PHASE7D_TEST_DATABASE_URL")
        if not url: self.skipTest("APEX_PHASE7D_TEST_DATABASE_URL is not configured")
        if make_url(url).database not in {"apexretail_phase7c_test_phase7d", "apexretail_phase7c_test_phase7e"}: self.fail("Refusing a non-disposable Phase 7D/7E database")
        with patch.dict(os.environ, {"APEX_PHASE7C_TEST_DATABASE_URL": url}):
            await fixtures.PrintingPostgresTests.asyncSetUp(self)
        self.company.business_type = "Restaurant"
        self.user = User(company_id=self.company.id, email=f"{uuid4()}@example.test", password_hash="fixture-only", role="owner")
        self.db.add(self.user)
        self.balance = InventoryBalance(company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id, product_id=self.product.id, quantity=100, reorder_level=0)
        self.db.add(self.balance)
        currency = CompanyCurrency(company_id=self.company.id, code="USD", display_name="Test dollar", symbol="$", decimal_places=2, active=True, is_base=True)
        self.db.add(currency); await self.db.flush()
        self.db.add(CompanySetting(company_id=self.company.id, base_currency_id=currency.id, currency_code="USD", currency_symbol="$", tax_rate=0, shift_enforcement_enabled=False, reporting_timezone="UTC"))
        await self.db.flush()
        from app.subscriptions.service import SubscriptionService
        await SubscriptionService(self.db).get_or_create_trial(self.company.id, commit=False)
        await self.db.commit()
        self.owner.user = self.user
        self.svc = BusinessService(self.db, self.owner)
        self.waiter = AuthActor(actor_type="employee", company_id=self.company.id, role="waiter", employee=self.employee, permissions=normalize_permissions("waiter", {}), pos_session=self.session)
        self.waiter_svc = BusinessService(self.db, self.waiter)
        self.kitchen_station = PrinterStation(company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id, device_id=self.device.id, name="Kitchen", purpose="kitchen", transport="system", address="", paper_width="80mm", auto_print=False, active=True)
        self.db.add(self.kitchen_station); await self.db.flush()
        self.db.add(PrinterRoute(station_id=self.kitchen_station.id, target_type="category", target_id=self.category.id))
        await self.db.commit()

    async def cleanup(self): await fixtures.PrintingPostgresTests.cleanup(self)

    async def open(self, **changes):
        data = dict(branch_id=self.branch.id, device_id=self.device.id, request_id=uuid4(), waiter_id=self.employee.id)
        data.update(changes)
        return await self.svc.create_order(OrderInput(**data))

    async def add(self, order, quantity="2", **changes):
        return await self.svc.add_item(order["id"], OrderItemInput(version=order["version"], product_id=self.product.id, quantity=quantity, **changes))

    def payment(self, order, **changes):
        payment = dict(company_id=self.company.id, items=[], payment_method="cash", amount_received="100")
        payment.update(changes)
        return SettlementInput(version=order["version"], payment=SaleCreate(**payment))

    async def ready(self, **changes):
        order = await self.add(await self.open(**changes))
        return (await self.svc.send_kitchen(order["id"], order["version"]))["order"]

    async def test_unpaid_kitchen_dispatch_has_no_financial_or_stock_effect(self):
        order = await self.add(await self.open())
        self.assertEqual(self.balance.quantity, 100)
        result = await self.svc.send_kitchen(order["id"], order["version"])
        self.assertEqual(len(result["jobs"]), 1)
        self.assertIsNone(result["jobs"][0]["sale_id"])
        self.assertEqual(self.balance.quantity, 100)
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id == self.company.id))).scalar_one(), 1)
        repeated = await self.svc.send_kitchen(order["id"], result["order"]["version"])
        self.assertEqual(repeated["jobs"], [])

    async def test_order_create_request_is_idempotent(self):
        request = uuid4(); a = await self.open(request_id=request); b = await self.open(request_id=request)
        self.assertEqual(a["id"], b["id"])

    async def test_item_edits_are_versioned_and_sent_notes_are_protected(self):
        order = await self.add(await self.open(), notes="No nuts")
        with self.assertRaises(HTTPException): await self.add({**order, "version": 1})
        dispatched = (await self.svc.send_kitchen(order["id"], order["version"]))["order"]
        with self.assertRaises(HTTPException): await self.svc.edit_item(order["id"], order["items"][0]["id"], ItemUpdate(version=dispatched["version"], quantity=2, notes="Add nuts"))

    async def test_cancellations_dispatch_negative_ticket_and_no_stock(self):
        order = await self.ready()
        item = order["items"][0]
        order = await self.svc.edit_item(order["id"], item["id"], ItemUpdate(version=order["version"], quantity=0))
        result = await self.svc.send_kitchen(order["id"], order["version"])
        self.assertEqual(result["jobs"][0]["payload"]["items"][0]["quantity"], "-2.000")
        cancelled = await self.svc.cancel(order["id"], result["order"]["version"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.balance.quantity, 100)
        ticket = (await self.db.execute(select(KitchenTicket).where(KitchenTicket.print_job_id == result["jobs"][0]["id"]))).scalar_one()
        self.assertEqual((await self.svc.kitchen_state(ticket.id, "acknowledged"))["status"], "acknowledged")
        older = (await self.db.execute(select(KitchenTicket).where(KitchenTicket.order_id == order["id"], KitchenTicket.id != ticket.id))).scalar_one()
        self.assertEqual(older.status, "needs_review")
        with self.assertRaises(HTTPException): await self.svc.kitchen_state(older.id, "preparing")

    async def test_kds_roles_status_and_bar_isolation(self):
        await self.ready()
        kitchen_actor = AuthActor(actor_type="employee", company_id=self.company.id, role="kitchen_staff", employee=self.employee, permissions=normalize_permissions("kitchen_staff", {}), pos_session=self.session)
        kitchen = BusinessService(self.db, kitchen_actor)
        tickets = await kitchen.kitchen(); self.assertEqual(len(tickets), 1)
        with self.assertRaises(HTTPException): await kitchen.kitchen_state(tickets[0]["id"], "served")
        for state in ("preparing", "ready", "served"): self.assertEqual((await kitchen.kitchen_state(tickets[0]["id"], state))["status"], state)
        with self.assertRaises(HTTPException): await kitchen.list_orders()
        bartender = BusinessService(self.db, AuthActor(actor_type="employee", company_id=self.company.id, role="bartender", employee=self.employee, permissions=normalize_permissions("bartender", {}), pos_session=self.session))
        self.assertEqual(await bartender.kitchen(), [])

    async def test_settlement_reuses_sale_engine_and_retries_never_deduct_twice(self):
        order = await self.ready()
        result = await self.svc.settle(order["id"], self.payment(order))
        self.assertEqual(result["order"]["status"], "settled")
        self.assertEqual(self.balance.quantity, 98)
        repeated = await self.svc.settle(order["id"], self.payment(order))
        self.assertEqual(result["sale_id"], repeated["sale_id"])
        self.assertTrue(repeated["already_settled"])
        self.assertEqual(self.balance.quantity, 98)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id == self.company.id, InventoryMovement.movement_type == "sale"))).scalar_one(), 1)

    async def test_duplicate_product_lines_are_grouped_for_existing_checkout(self):
        order = await self.add(await self.open(), "1", notes="One hot")
        order = await self.add(order, "2", notes="Two mild")
        order = (await self.svc.send_kitchen(order["id"], order["version"]))["order"]
        result = await self.svc.settle(order["id"], self.payment(order))
        lines = (await self.db.execute(select(SaleItem).where(SaleItem.sale_id == result["sale_id"]))).scalars().all()
        self.assertEqual(len(lines), 1); self.assertEqual(lines[0].quantity, 3); self.assertEqual(self.balance.quantity, 97)

    async def test_settlement_failure_rolls_back_order_stock_and_sale(self):
        order = await self.ready()
        with self.assertRaises(HTTPException): await self.svc.settle(order["id"], self.payment(order, amount_received="0"))
        row = await self.db.get(CommerceOrder, order["id"])
        self.assertEqual(row.status, "open"); self.assertIsNone(row.sale_id)
        await self.db.refresh(self.balance); self.assertEqual(self.balance.quantity, 100)

    async def test_online_only_operations_do_not_consume_offline_sale_payload(self):
        order = await self.ready()
        with self.assertRaises(HTTPException): await self.svc.settle(order["id"], self.payment(order, client_created_at=datetime.now(timezone.utc)))
        self.assertEqual(self.balance.quantity, 100)

    async def test_settlement_cannot_reprint_kitchen_preparation(self):
        order = await self.ready(); result = await self.svc.settle(order["id"], self.payment(order))
        with self.assertRaises(HTTPException): await self.svc.enqueue(self.kitchen_station.id, JobInput(sale_id=result["sale_id"], kind="kot", request_key="duplicate-preparation"))

    async def test_split_merge_and_table_transfer_preserve_quantities(self):
        order = await self.add(await self.open(), "1")
        order = await self.add(order, "2")
        split = await self.svc.split(order["id"], SplitInput(version=order["version"], item_ids=[order["items"][0]["id"]], request_id=uuid4()))
        self.assertEqual(len(split["source"]["items"]), 1); self.assertEqual(len(split["target"]["items"]), 1)
        merged = await self.svc.merge(order["id"], MergeInput(version=split["source"]["version"], source_id=split["target"]["id"], source_version=split["target"]["version"]))
        self.assertEqual(sum(i["quantity"] for i in merged["items"]), 3)
        table = await self.svc.save_table(TableInput(branch_id=self.branch.id, name="Table 12", x=2, y=1))
        moved = await self.svc.move(order["id"], MoveInput(version=merged["version"], table_id=table["id"], waiter_id=self.employee.id))
        self.assertEqual(moved["table_name"], "Table 12"); self.assertEqual(self.balance.quantity, 100)

    async def test_waiter_cannot_manage_another_waiter_or_settle(self):
        order = await self.open()
        self.waiter.employee = SimpleNamespace(id=uuid4(), branch_id=self.branch.id)
        with self.assertRaises(HTTPException): await self.waiter_svc.order(order["id"])
        with self.assertRaises(HTTPException): await self.waiter_svc.settle(order["id"], self.payment(order))

    async def test_prepared_table_transfer_queues_only_informational_updates(self):
        order = await self.ready()
        table = await self.svc.save_table(TableInput(branch_id=self.branch.id, name="Table 20"))
        moved = await self.svc.move(order["id"], MoveInput(version=order["version"], table_id=table["id"], waiter_id=self.employee.id))
        self.assertEqual(len(moved["print_jobs"]), 1)
        self.assertEqual(moved["print_jobs"][0]["payload"]["table"], "Table 20")
        self.assertTrue(all(Decimal(i["quantity"]) == 0 for i in moved["print_jobs"][0]["payload"]["items"]))
        self.assertEqual(self.balance.quantity, 100)

    async def test_tenant_and_branch_isolation(self):
        order = await self.open()
        foreign = BusinessService(self.db, AuthActor(actor_type="user", company_id=uuid4(), role="owner"))
        with self.assertRaises(HTTPException): await foreign.order(order["id"])
        self.waiter.employee = SimpleNamespace(id=self.employee.id, branch_id=uuid4())
        with self.assertRaises(HTTPException): await self.waiter_svc.order(order["id"])

    async def test_tips_service_products_use_existing_tax_and_sale_lines(self):
        tip = Product(company_id=self.company.id, name="Voluntary tip", product_type="service", track_inventory=False, selling_price=2, cost_price=0, tax_exempt=True)
        self.db.add(tip); await self.db.flush()
        await self.svc.save_profile(ProfileInput(profile="restaurant", tip_product_id=tip.id))
        order = await self.ready()
        order = await self.svc.add_item(order["id"], OrderItemInput(version=order["version"], product_id=tip.id, quantity=1))
        charge = next(i for i in order["items"] if i["product_id"] == tip.id)
        self.assertEqual(charge["sent_quantity"], charge["quantity"])
        result = await self.svc.settle(order["id"], self.payment(order))
        sale = await self.db.get(Sale, result["sale_id"])
        self.assertEqual(sale.total_amount, 26)

    async def test_guest_room_charge_uses_existing_credit_receivable(self):
        await self.svc.save_profile(ProfileInput(profile="hospitality"))
        room = await self.svc.save_room(RoomInput(branch_id=self.branch.id, name="204"))
        customer = Customer(company_id=self.company.id, customer_code=f"G-{uuid4().hex[:10]}", name="Synthetic guest", credit_enabled=True, unlimited_credit=True, credit_terms_days=7)
        self.db.add(customer); await self.db.flush()
        guest = await self.svc.open_guest(GuestInput(room_id=room["id"], customer_id=customer.id))
        order = await self.ready(kind="room_service", guest_id=guest["id"])
        data = self.payment(order, payment_method="credit"); data.charge_to_room = True
        result = await self.svc.settle(order["id"], data)
        folio = await self.svc.folio(guest["id"])
        self.assertEqual(folio["charges"][0]["sale_id"], result["sale_id"])
        self.assertEqual(Decimal(folio["charges"][0]["outstanding"]), 24)
        with self.assertRaises(HTTPException): await self.svc.close_guest(guest["id"])

    async def test_quotation_customer_price_level_applies_at_sale_conversion(self):
        from app.models import ProductPriceLevel
        await self.svc.save_profile(ProfileInput(profile="wholesale"))
        customer = Customer(company_id=self.company.id, customer_code=f"W-{uuid4().hex[:10]}", name="Wholesale buyer", price_level_name="Wholesale")
        self.db.add(customer); await self.db.flush()
        self.db.add(ProductPriceLevel(company_id=self.company.id, product_id=self.product.id, name="Wholesale", minimum_quantity=1, price=9))
        await self.db.flush()
        order = await self.add(await self.open(kind="quotation", customer_id=customer.id))
        self.assertEqual(Decimal(order["estimated_subtotal"]), 18)
        from app.business_operations.quotations import transition
        from app.business_operations.schema import QuotationTransition
        for action in ('sent','accepted'):
            order=await transition(self.svc,order['id'],QuotationTransition(version=order['version'],request_id=uuid4(),action=action,
                valid_until=datetime.now(timezone.utc)+timedelta(days=1) if action=='sent' else None))
        result = await self.svc.settle(order["id"], self.payment(order))
        self.assertEqual((await self.db.get(Sale, result["sale_id"])).total_amount, 18)

    async def test_batch_assignment_never_adds_physical_stock(self):
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        await self.svc.assign_batch(BatchInput(branch_id=self.branch.id, product_id=self.product.id, code="LOT-A", expires_on=date.today()+timedelta(days=10), quantity=100))
        self.assertEqual(self.balance.quantity, 100); self.assertEqual(self.product.stock_qty, 100)
        with self.assertRaises(HTTPException): await self.svc.assign_batch(BatchInput(branch_id=self.branch.id, product_id=self.product.id, code="LOT-B", expires_on=date.today()+timedelta(days=30), quantity=1))

    async def test_batch_fefo_allocates_existing_sale_movement_once(self):
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        early = await self.svc.assign_batch(BatchInput(branch_id=self.branch.id, product_id=self.product.id, code="EARLY", expires_on=date.today()+timedelta(days=5), quantity=1))
        late = await self.svc.assign_batch(BatchInput(branch_id=self.branch.id, product_id=self.product.id, code="LATE", expires_on=date.today()+timedelta(days=30), quantity=99))
        payload = SaleCreate(company_id=self.company.id, branch_id=self.branch.id, device_id=self.device.id, client_sale_id=uuid4(), amount_received=100, items=[SaleItemCreate(product_id=self.product.id, quantity=2)])
        sale = await SalesService(SalesRepository(self.db)).create_sale(payload, actor=self.owner)
        repeated = await SalesService(SalesRepository(self.db)).create_sale(payload, actor=self.owner)
        self.assertEqual(sale.id, repeated.id); self.assertEqual(self.balance.quantity, 98)
        self.assertEqual((await self.db.get(ProductBatch, early["id"])).quantity, 0)
        self.assertEqual((await self.db.get(ProductBatch, late["id"])).quantity, 98)
        allocations = (await self.db.execute(select(BatchAllocation).join(ProductBatch).where(ProductBatch.company_id == self.company.id))).scalars().all()
        self.assertEqual(len(allocations), 2)

    async def test_expired_batches_block_sale_without_stock_or_financial_commit(self):
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        await self.svc.assign_batch(BatchInput(branch_id=self.branch.id, product_id=self.product.id, code="EXPIRED", expires_on=date.today()-timedelta(days=1), quantity=100))
        with self.assertRaises(HTTPException):
            await SalesService(SalesRepository(self.db)).create_sale(SaleCreate(company_id=self.company.id, branch_id=self.branch.id, device_id=self.device.id, amount_received=100, items=[SaleItemCreate(product_id=self.product.id, quantity=1)]), actor=self.owner)
        await self.db.refresh(self.balance); self.assertEqual(self.balance.quantity, 100)

    async def test_unconfigured_retail_profile_does_not_gain_restaurant_mutations(self):
        self.company.business_type = "Retail"; await self.db.flush()
        with self.assertRaises(HTTPException): await self.open()
        self.assertEqual(self.company.business_type, "Retail")

    async def test_restaurant_report_uses_persisted_sale_values(self):
        order = await self.ready(); await self.svc.settle(order["id"], self.payment(order))
        report = await self.svc.reports(date.today(), date.today())
        self.assertEqual(Decimal(report["currency_totals"][0]["sales"]), 24)

    async def test_failure_after_sale_flush_rolls_back_entire_settlement(self):
        order = await self.ready()
        with patch.object(self.svc, "audit", side_effect=RuntimeError("Synthetic post-sale failure")):
            with self.assertRaises(RuntimeError): await self.svc.settle(order["id"], self.payment(order))
        await self.db.refresh(self.balance)
        self.assertEqual(self.balance.quantity, 100)
        row = await self.db.get(CommerceOrder, order["id"])
        self.assertIsNone(row.sale_id); self.assertEqual(row.status, "open")
        self.assertIsNone((await self.db.execute(select(Sale.id).where(Sale.client_sale_id == row.id))).scalar_one_or_none())

    async def test_linked_refunds_are_included_in_restaurant_report(self):
        order = await self.ready(); result = await self.svc.settle(order["id"], self.payment(order))
        item = (await self.db.execute(select(SaleItem).where(SaleItem.sale_id == result["sale_id"]))).scalar_one()
        await SalesService(SalesRepository(self.db)).create_refund(RefundCreate(company_id=self.company.id, original_sale_id=result["sale_id"], branch_id=self.branch.id, device_id=self.device.id,
            reason="Synthetic authorized return", items=[RefundItemCreate(sale_item_id=item.id, quantity=1)]), actor=self.owner)
        report = await self.svc.reports(date.today(), date.today())
        self.assertEqual(Decimal(report["currency_totals"][0]["sales"]), 12)
        self.assertEqual(Decimal(report["currency_totals"][0]["refunds"]), 12)

    async def test_guest_account_closure_and_room_deactivation_preserve_records(self):
        await self.svc.save_profile(ProfileInput(profile="hospitality"))
        room = await self.svc.save_room(RoomInput(branch_id=self.branch.id, name="205"))
        customer = Customer(company_id=self.company.id, customer_code=f"G-{uuid4().hex[:10]}", name="Synthetic guest")
        self.db.add(customer); await self.db.flush()
        guest = await self.svc.open_guest(GuestInput(room_id=room["id"], customer_id=customer.id))
        with self.assertRaises(HTTPException): await self.svc.save_room(RoomInput(branch_id=self.branch.id, name="205", active=False), room["id"])
        self.assertTrue((await self.svc.close_guest(guest["id"]))["closed"])
        await self.svc.save_room(RoomInput(branch_id=self.branch.id, name="205", active=False), room["id"])
        self.assertFalse((await self.svc.rooms())[0]["active"])

    async def test_composite_components_use_the_same_batch_allocation_hook(self):
        from app.models import ProductComponent
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        lot = await self.svc.assign_batch(BatchInput(branch_id=self.branch.id, product_id=self.product.id, code="COMPONENT", expires_on=date.today()+timedelta(days=30), quantity=100))
        parent = Product(company_id=self.company.id, name="Synthetic bundle", product_type="composite", track_inventory=False, selling_price=30)
        self.db.add(parent); await self.db.flush()
        self.db.add(ProductComponent(company_id=self.company.id, composite_product_id=parent.id, component_product_id=self.product.id, quantity=2, unit="each")); await self.db.flush()
        await SalesService(SalesRepository(self.db)).create_sale(SaleCreate(company_id=self.company.id, branch_id=self.branch.id, device_id=self.device.id, amount_received=100, items=[SaleItemCreate(product_id=parent.id, quantity=1)]), actor=self.owner)
        self.assertEqual(self.balance.quantity, 98)
        self.assertEqual((await self.db.get(ProductBatch, lot["id"])).quantity, 98)

    async def test_settlement_route_preserves_subscription_write_gate(self):
        from unittest.mock import AsyncMock
        import httpx
        from app.main import app
        from app.auth.dependencies import get_auth_actor
        from app.db.session import get_db
        order = await self.ready()
        async def db_override(): yield self.db
        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_auth_actor] = lambda: self.owner
        try:
            from app.models import CompanySubscription
            subscription = (await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one()
            subscription.status='expired'; await self.db.commit()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                result = await client.post(f"/api/operations/orders/{order['id']}/settle", json=self.payment(order).model_dump(mode="json"))
                self.assertEqual(result.status_code, 402)
                self.assertEqual(self.balance.quantity, 100)
        finally:
            app.dependency_overrides.pop(get_db, None); app.dependency_overrides.pop(get_auth_actor, None)

    async def test_runtime_role_cannot_mutate_kitchen_ticket_identity(self):
        values = (await self.db.execute(text("SELECT has_column_privilege('apex_user','kitchen_tickets','status','UPDATE'), has_column_privilege('apex_user','kitchen_tickets','order_id','UPDATE'), has_table_privilege('apex_user','batch_allocations','DELETE')"))).one()
        self.assertEqual(tuple(values), (True, False, False))

    async def test_z_parallel_settlements_have_one_sale_and_stock_deduction(self):
        order = await self.ready(); payment = self.payment(order)
        company_id, user_id, balance_id = self.company.id, self.user.id, self.balance.id
        await self.db.commit(); await self.transaction.commit()
        async def settle():
            async with AsyncSession(self.engine, expire_on_commit=False) as db:
                actor = AuthActor(actor_type="user", company_id=company_id, role="owner", user=await db.get(User, user_id))
                return await BusinessService(db, actor).settle(order["id"], payment)
        a, b = await asyncio.gather(settle(), settle())
        self.assertEqual(a["sale_id"], b["sale_id"])
        self.assertCountEqual([a["already_settled"], b["already_settled"]], [False, True])
        async with AsyncSession(self.engine) as db:
            self.assertEqual((await db.get(InventoryBalance, balance_id)).quantity, 98)
            self.assertEqual((await db.execute(select(func.count(Sale.id)).where(Sale.client_sale_id == order["id"]))).scalar_one(), 1)
