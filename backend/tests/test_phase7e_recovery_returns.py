import unittest
from datetime import date, timedelta, datetime, timezone
from uuid import uuid4
from sqlalchemy import select, func
from fastapi import HTTPException
from app.models import BatchReturnHold, BatchReturnInspection, BatchInspectionDisposal, SaleItem, Sale, ProductBatch, InventoryMovement, CommerceOrder
from app.business_operations.schema import ProfileInput, BatchInput, OfflineDraftInput
from app.business_operations.returns import ReturnService, InspectionInput
from app.business_operations.offline import OfflineOrderService
from app.sales.service import SalesService
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate, SaleItemCreate, RefundCreate, RefundItemCreate
import test_phase7d_operations as fixtures


class RecoveryReturnTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.Phase7DOperationsTests.asyncSetUp
    cleanup = fixtures.Phase7DOperationsTests.cleanup

    async def returned(self):
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        await self.svc.assign_batch(BatchInput(branch_id=self.branch.id, product_id=self.product.id, code="ORIGINAL",
            expires_on=date.today()+timedelta(days=30), quantity=100))
        sales = SalesService(SalesRepository(self.db))
        sale = await sales.create_sale(SaleCreate(company_id=self.company.id, branch_id=self.branch.id,
            device_id=self.device.id, client_sale_id=uuid4(), amount_received=100,
            items=[SaleItemCreate(product_id=self.product.id, quantity=2)]), actor=self.owner)
        item = (await self.db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))).scalar_one()
        refund = await sales.create_refund(RefundCreate(company_id=self.company.id, original_sale_id=sale.id,
            branch_id=self.branch.id, device_id=self.device.id, reason="Synthetic customer return inspection",
            items=[RefundItemCreate(sale_item_id=item.id, quantity=1)]), actor=self.owner)
        hold = (await self.db.execute(select(BatchReturnHold).where(BatchReturnHold.company_id == self.company.id))).scalar_one()
        return hold, refund

    def inspect(self, hold, **changes):
        data = dict(request_id=uuid4(), hold_id=hold.id, code="INSPECTED-RETURN", expires_on=date.today()+timedelta(days=20),
            disposition="restock", reason="Synthetic physical inspection confirmed", confirmed=True)
        data.update(changes); return InspectionInput(**data)

    async def test_customer_refund_creates_hold_without_duplicate_stock_restoration(self):
        hold, refund = await self.returned()
        self.assertEqual(self.balance.quantity, 99)
        self.assertEqual(hold.quantity, 1)
        before_refund = refund.total_amount
        service = ReturnService(self.db, self.owner)
        command = self.inspect(hold)
        first = await service.inspect(command); again = await service.inspect(command)
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(self.balance.quantity, 99)
        self.assertEqual(refund.total_amount, before_refund)
        self.assertEqual(len(await service.pending()), 0)
        self.assertEqual((await self.db.execute(select(func.sum(ProductBatch.quantity)).where(ProductBatch.company_id == self.company.id))).scalar_one(), 99)

    async def test_expired_return_disposal_deducts_stock_once_without_another_refund(self):
        hold, _ = await self.returned()
        service = ReturnService(self.db, self.owner)
        with self.assertRaises(HTTPException): await service.inspect(self.inspect(hold, expires_on=date.today()-timedelta(days=1)))
        command = self.inspect(hold, disposition="dispose", expires_on=date.today()-timedelta(days=1))
        first = await service.inspect(command); await service.inspect(command)
        self.assertEqual(self.balance.quantity, 98)
        self.assertEqual((await self.db.execute(select(func.count(BatchInspectionDisposal.inspection_id)).where(BatchInspectionDisposal.inspection_id == first["id"]))).scalar_one(), 1)
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id == self.company.id, Sale.original_sale_id.is_not(None)))).scalar_one(), 1)

    async def test_pending_return_cannot_be_released_by_generic_assignment(self):
        hold, _ = await self.returned()
        with self.assertRaises(HTTPException): await self.svc.assign_batch(BatchInput(branch_id=self.branch.id,
            product_id=self.product.id, code="BYPASS", expires_on=date.today()+timedelta(days=10), quantity=1))
        self.assertEqual(self.balance.quantity, 99)
        self.assertEqual(len(await ReturnService(self.db, self.owner).pending()), 1)
        with self.assertRaises(HTTPException): await ReturnService(self.db, self.waiter).inspect(self.inspect(hold))

    async def test_pending_return_cannot_be_sold_from_the_parent_stock_balance(self):
        await self.returned()
        with self.assertRaises(HTTPException) as error:
            await SalesService(SalesRepository(self.db)).create_sale(SaleCreate(company_id=self.company.id,
                branch_id=self.branch.id, device_id=self.device.id, client_sale_id=uuid4(), amount_received=2000,
                items=[SaleItemCreate(product_id=self.product.id, quantity=99)]), actor=self.owner)
        self.assertEqual(error.exception.status_code, 409)
        await self.db.refresh(self.balance)
        self.assertEqual(self.balance.quantity, 99)

    async def test_populated_return_migration_refuses_to_remove_real_refund_holds(self):
        import importlib.util
        from pathlib import Path
        from unittest.mock import patch
        hold, _ = await self.returned()
        spec = importlib.util.spec_from_file_location("return_migration", Path(__file__).resolve().parents[1] / "migrations/versions/p7i_pharmacy_return_holds.py")
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        def attempt(connection):
            with patch.object(migration.op, "get_bind", return_value=connection):
                with self.assertRaisesRegex(RuntimeError, "return holds exist"): migration.downgrade()
        await self.connection.run_sync(attempt)
        self.assertIsNotNone(await self.db.get(BatchReturnHold, hold.id))
        self.assertEqual(self.balance.quantity, 99)

    async def test_offline_recovery_never_creates_unknown_commands_and_matches_original_payload(self):
        command = OfflineDraftInput(request_id=uuid4(), employee_id=self.employee.id, captured_at=datetime.now(timezone.utc),
            order={"branch_id": self.branch.id, "device_id": self.device.id, "request_id": uuid4()},
            items=[{"version": 1, "product_id": self.product.id, "quantity": 2}])
        service = OfflineOrderService(self.db, self.waiter)
        before = (await self.db.execute(select(func.count(CommerceOrder.id)))).scalar_one()
        with self.assertRaises(HTTPException) as error: await service.recover(command)
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual((await self.db.execute(select(func.count(CommerceOrder.id)))).scalar_one(), before)
        saved = await service.synchronize(command)
        recovered = await service.recover(command)
        self.assertEqual(saved["order"], recovered["order"])
        with self.assertRaises(HTTPException): await service.recover(command.model_copy(update={"captured_at": datetime.now(timezone.utc)}))
        with self.assertRaises(HTTPException): await service.recover(command.model_copy(update={"employee_id": uuid4()}))
