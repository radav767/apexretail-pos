"""Synthetic PostgreSQL integration tests; never connect to production."""
from datetime import datetime, timezone, date, timedelta
from uuid import uuid4
from decimal import Decimal
import unittest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from sqlalchemy import select, func, text
from app.models import Sale, InventoryMovement, KitchenTicket
from app.models.business_operations import OrderSyncReceipt
from app.business_operations.offline import OfflineOrderService
from app.business_operations.schema import OfflineDraftInput, OfflineEditInput, SplitInput
from app.business_operations.schema import BatchStockInput, ProfileInput
from app.business_operations.batch_stock import BatchStockService
from app.models import ProductBatch, BatchAllocation
import test_phase7d_operations as fixtures


class Phase7EIntegrationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.Phase7DOperationsTests.asyncSetUp
    cleanup = fixtures.Phase7DOperationsTests.cleanup
    open = fixtures.Phase7DOperationsTests.open
    add = fixtures.Phase7DOperationsTests.add
    ready = fixtures.Phase7DOperationsTests.ready
    payment = fixtures.Phase7DOperationsTests.payment
    def draft(self, **changes):
        payload = dict(request_id=uuid4(), employee_id=self.employee.id,
            captured_at=datetime.now(timezone.utc), order=dict(branch_id=self.branch.id,
                device_id=self.device.id, request_id=uuid4()),
            items=[dict(version=1, product_id=self.product.id, quantity="2")])
        payload.update(changes)
        return OfflineDraftInput(**payload)

    async def test_offline_draft_retry_is_atomic_and_does_not_print_or_charge(self):
        sync = OfflineOrderService(self.db, self.waiter)
        command = self.draft()
        before = (await self.db.execute(select(func.count(Sale.id)))).scalar_one()
        first = await sync.synchronize(command)
        replay = await sync.synchronize(command)
        self.assertEqual(first["order"], replay["order"])
        self.assertTrue(replay["already_synchronized"])
        self.assertEqual(self.balance.quantity, 100)
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)))).scalar_one(), before)
        self.assertEqual((await self.db.execute(select(func.count(KitchenTicket.id)).where(KitchenTicket.order_id == first["order"]["id"]))).scalar_one(), 0)
        self.assertEqual((await self.db.execute(select(func.count(OrderSyncReceipt.id)).where(OrderSyncReceipt.request_id == command.request_id))).scalar_one(), 1)

    async def test_offline_rejects_cashier_switch_payload_reuse_and_naive_timestamp(self):
        sync = OfflineOrderService(self.db, self.waiter)
        command = self.draft()
        with self.assertRaises(HTTPException) as error:
            await sync.synchronize(command.model_copy(update={"employee_id": uuid4()}))
        self.assertEqual(error.exception.status_code, 403)
        with self.assertRaises(HTTPException) as error:
            await sync.synchronize(command.model_copy(update={"captured_at": datetime.now()}))
        self.assertEqual(error.exception.status_code, 422)
        await sync.synchronize(command)
        changed = command.model_copy(update={"captured_at": datetime.now(timezone.utc)})
        with self.assertRaises(HTTPException) as error: await sync.synchronize(changed)
        self.assertEqual(error.exception.status_code, 409)

    async def test_offline_edit_conflict_preserves_server_order(self):
        order = await self.add(await self.open())
        command = OfflineEditInput(request_id=uuid4(), employee_id=self.employee.id,
            device_id=self.device.id, captured_at=datetime.now(timezone.utc),
            order_id=order["id"], item_id=order["items"][0]["id"],
            change={"version": order["version"] - 1, "quantity": "9", "notes": ""})
        with self.assertRaises(HTTPException) as error:
            await OfflineOrderService(self.db, self.waiter).synchronize(command, edit=True)
        self.assertEqual(error.exception.status_code, 409)
        current = await self.svc.order_out(await self.svc.order(order["id"]))
        self.assertEqual(Decimal(current["items"][0]["quantity"]), 2)

    async def test_quantity_split_conserves_sent_food_and_settles_exactly_once(self):
        order = await self.add(await self.open(), quantity="3")
        order = (await self.svc.send_kitchen(order["id"], order["version"]))["order"]
        result = await self.svc.split(order["id"], SplitInput(version=order["version"], request_id=uuid4(),
            quantities=[{"item_id": order["items"][0]["id"], "quantity": "1"}]))
        self.assertEqual(sum(Decimal(o["items"][0]["quantity"]) for o in result.values()), 3)
        self.assertEqual(sum(Decimal(o["items"][0]["sent_quantity"]) for o in result.values()), 3)
        sale_ids = set()
        for bill in result.values():
            self.assertEqual((await self.svc.send_kitchen(bill["id"], bill["version"]))["jobs"], [])
            paid = await self.svc.settle(bill["id"], self.payment(bill))
            again = await self.svc.settle(bill["id"], self.payment(bill))
            self.assertEqual(paid["sale_id"], again["sale_id"])
            sale_ids.add(paid["sale_id"])
        self.assertEqual(len(sale_ids), 2)
        self.assertEqual(self.balance.quantity, 97)

    async def test_split_invalid_quantities_leave_bill_unchanged(self):
        order = await self.add(await self.open(), quantity="3")
        for quantity in ("3", "4"):
            with self.assertRaises(HTTPException):
                await self.svc.split(order["id"], SplitInput(version=order["version"], request_id=uuid4(),
                    quantities=[{"item_id": order["items"][0]["id"], "quantity": quantity}]))
        self.assertEqual(self.balance.quantity, 100)

    async def test_lot_receiving_case_breaking_returns_and_expired_disposal_are_idempotent(self):
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        self.product.purchase_unit = "carton"; self.product.units_per_purchase = 24
        await self.db.commit()
        service = BatchStockService(self.db, self.owner)
        common = dict(branch_id=self.branch.id, product_id=self.product.id, code="LOT-7E",
            expires_on=date.today() - timedelta(days=1), reason="Synthetic inspected lot")
        receive = BatchStockInput(**common, request_id=uuid4(), operation="receive", quantity=1, received_unit="carton")
        first = await service.execute(receive); again = await service.execute(receive)
        self.assertEqual(first["movement_id"], again["movement_id"])
        self.assertEqual(self.balance.quantity, 124)
        batch = await self.db.get(ProductBatch, first["batch_id"])
        self.assertEqual(batch.quantity, 24)
        for operation in ("supplier_return", "dispose"):
            command = BatchStockInput(**common, request_id=uuid4(), operation=operation, quantity=2)
            initial = await service.execute(command); retry = await service.execute(command)
            self.assertEqual(initial["movement_id"], retry["movement_id"])
        self.assertEqual(self.balance.quantity, 120)
        self.assertEqual(batch.quantity, 20)
        rows = (await self.db.execute(select(BatchAllocation).where(BatchAllocation.batch_id == batch.id))).scalars().all()
        self.assertEqual(sorted(a.quantity for a in rows), [Decimal(-2), Decimal(-2), Decimal(24)])

    async def test_batch_operation_cannot_remove_other_lots_or_change_expiry(self):
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        service = BatchStockService(self.db, self.owner)
        common = dict(branch_id=self.branch.id, product_id=self.product.id, code="LOT-LIMIT",
            expires_on=date.today() + timedelta(days=30), reason="Synthetic inspected lot")
        receipt = await service.execute(BatchStockInput(**common, request_id=uuid4(), operation="receive", quantity=1))
        with self.assertRaises(HTTPException) as error:
            await service.execute(BatchStockInput(**common, request_id=uuid4(), operation="dispose", quantity=2))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual((await self.db.get(ProductBatch, receipt["batch_id"])).quantity, 1)
        await self.db.refresh(self.balance)
        self.assertEqual(self.balance.quantity, 101)

    async def test_profile_switch_does_not_hide_existing_orders(self):
        order = await self.open()
        await self.svc.save_profile(ProfileInput(profile="retail"))
        profile = await self.svc.profile()
        self.assertIn("restaurant", profile["features"])
        self.assertEqual((await self.svc.order(order["id"])).id, order["id"])

    async def test_runtime_role_cannot_rewrite_or_delete_sync_or_batch_receipts(self):
        for table in ("order_sync_receipts", "batch_stock_operations"):
            row = (await self.db.execute(text(f"SELECT has_table_privilege('apex_user','{table}','SELECT') r, has_table_privilege('apex_user','{table}','INSERT') i, has_table_privilege('apex_user','{table}','UPDATE') u, has_table_privilege('apex_user','{table}','DELETE') d"))).mappings().one()
            self.assertEqual(dict(row), {"r": True, "i": True, "u": False, "d": False})

    async def test_offline_draft_invalid_line_rolls_back_order_and_acknowledgement(self):
        from app.models import CommerceOrder
        command = self.draft()
        command.items.append(command.items[0].model_copy(update={"product_id": uuid4()}))
        with self.assertRaises(HTTPException): await OfflineOrderService(self.db, self.waiter).synchronize(command)
        self.assertIsNone((await self.db.execute(select(CommerceOrder.id).where(CommerceOrder.request_id == command.order.request_id))).scalar_one_or_none())
        self.assertIsNone((await self.db.execute(select(OrderSyncReceipt.id).where(OrderSyncReceipt.request_id == command.request_id))).scalar_one_or_none())

    async def test_z_parallel_offline_retries_create_one_order_and_receipt(self):
        from app.models import Employee, PosSession, CommerceOrder
        from app.auth.dependencies import AuthActor
        from app.employees.permissions import normalize_permissions
        command = self.draft()
        company_id, employee_id, session_id = self.company.id, self.employee.id, self.session.id
        await self.db.commit(); await self.transaction.commit()
        async def send():
            async with AsyncSession(self.engine, expire_on_commit=False) as db:
                actor = AuthActor(actor_type="employee", company_id=company_id, role="waiter",
                    employee=await db.get(Employee, employee_id), pos_session=await db.get(PosSession, session_id),
                    permissions=normalize_permissions("waiter", {}))
                return await OfflineOrderService(db, actor).synchronize(command)
        first, second = await asyncio.gather(send(), send())
        self.assertEqual(first["order"]["id"], second["order"]["id"])
        self.assertCountEqual([first["already_synchronized"], second["already_synchronized"]], [False, True])
        async with AsyncSession(self.engine) as db:
            self.assertEqual((await db.execute(select(func.count(CommerceOrder.id)).where(CommerceOrder.request_id == command.order.request_id))).scalar_one(), 1)
            self.assertEqual((await db.execute(select(func.count(OrderSyncReceipt.id)).where(OrderSyncReceipt.request_id == command.request_id))).scalar_one(), 1)

    async def test_legacy_client_cannot_deduct_parent_stock_instead_of_selected_variant(self):
        from app.models import ProductVariant
        from app.sales.service import SalesService
        from app.sales.repository import SalesRepository
        from app.sales.schema import SaleCreate, SaleItemCreate
        self.db.add(ProductVariant(company_id=self.company.id, product_id=self.product.id, name="Large", selling_price=12))
        await self.db.flush()
        before = (await self.db.execute(select(func.count(Sale.id)))).scalar_one()
        with self.assertRaises(HTTPException) as error:
            await SalesService(SalesRepository(self.db)).create_sale(SaleCreate(company_id=self.company.id,
                branch_id=self.branch.id, device_id=self.device.id, client_sale_id=uuid4(), amount_received=100,
                items=[SaleItemCreate(product_id=self.product.id, quantity=1)]), actor=self.owner)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.balance.quantity, 100)
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)))).scalar_one(), before)
