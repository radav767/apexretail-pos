"""Real PostgreSQL stock/lot integration; synthetic rollback-only fixtures."""
import unittest
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select, func
from fastapi import HTTPException
from app.models import ProductVariant, ProductBatch, InventoryMovement, SaleItem, BatchReturnHold, BatchAllocation
from app.business_operations.schema import BatchStockInput, BatchInput, ProfileInput
from app.business_operations.batch_stock import BatchStockService
from app.business_operations.returns import ReturnService, InspectionInput
from app.sales.repository import SalesRepository
from app.sales.service import SalesService
from app.sales.schema import SaleCreate, SaleItemCreate, RefundCreate, RefundItemCreate
import test_phase7d_operations as fixtures


class VariantBatchTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.Phase7DOperationsTests.asyncSetUp
    cleanup = fixtures.Phase7DOperationsTests.cleanup

    async def prepare(self):
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        self.a = ProductVariant(company_id=self.company.id, product_id=self.product.id, name="250mg", selling_price=12, cost_price=4)
        self.b = ProductVariant(company_id=self.company.id, product_id=self.product.id, name="500mg", selling_price=15, cost_price=6)
        self.db.add_all([self.a, self.b]); await self.db.flush()
        self.stock = BatchStockService(self.db, self.owner)
        self.sales_repo = SalesRepository(self.db); self.sales = SalesService(self.sales_repo)

    def command(self, variant, **overrides):
        data = dict(request_id=uuid4(), branch_id=self.branch.id, product_id=self.product.id,
            variant_id=variant.id, operation="receive", code="SAME-PHYSICAL-CODE", expires_on=date.today()+timedelta(days=60),
            quantity=10, reason="Synthetic verified variant lot")
        data.update(overrides); return BatchStockInput(**data)

    async def balance_for(self, variant):
        # A rejected sale rolls back and expires ORM objects; explicit async
        # refresh avoids implicit IO while asserting the rollback invariant.
        for row in (self.company, self.branch, self.product, variant): await self.db.refresh(row)
        return await self.sales_repo.get_variant_balance(self.company.id, self.branch, self.product.id, variant.id)

    async def make_sale(self, variant, quantity=2, client=None):
        return await self.sales.create_sale(SaleCreate(company_id=self.company.id, branch_id=self.branch.id,
            device_id=self.device.id, client_sale_id=client or uuid4(), amount_received=1000,
            items=[SaleItemCreate(product_id=self.product.id, variant_id=variant.id, quantity=quantity)]), actor=self.owner)

    async def returned(self):
        await self.prepare(); await self.stock.execute(self.command(self.a))
        sale = await self.make_sale(self.a)
        item = (await self.db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))).scalar_one()
        await self.sales.create_refund(RefundCreate(company_id=self.company.id, original_sale_id=sale.id,
            branch_id=self.branch.id, device_id=self.device.id, reason="Synthetic variant return",
            items=[RefundItemCreate(sale_item_id=item.id, quantity=1)]), actor=self.owner)
        return (await self.db.execute(select(BatchReturnHold).where(BatchReturnHold.company_id == self.company.id))).scalar_one()

    def inspection(self, hold, **changes):
        values = dict(request_id=uuid4(), hold_id=hold.id, code="RETURNED-250MG", expires_on=date.today()+timedelta(days=30),
            disposition="restock", reason="Inspected synthetic returned variant", confirmed=True)
        values.update(changes); return InspectionInput(**values)

    async def test_receive_separate_variants_same_code_replay_and_parent_unchanged(self):
        await self.prepare(); command = self.command(self.a)
        first = await self.stock.execute(command); replay = await self.stock.execute(command)
        second = await self.stock.execute(self.command(self.b))
        self.assertEqual(first["movement_id"], replay["movement_id"])
        self.assertNotEqual(first["batch_id"], second["batch_id"])
        self.assertEqual((await self.balance_for(self.a)).quantity, 10)
        self.assertEqual((await self.balance_for(self.b)).quantity, 10)
        self.assertEqual(self.balance.quantity, 100)
        movement = await self.db.get(InventoryMovement, first["movement_id"])
        self.assertEqual(movement.variant_id, self.a.id); self.assertEqual(movement.unit_cost, 4)

    async def test_variant_sale_retry_deducts_original_variant_and_lot_once(self):
        await self.prepare(); first = await self.stock.execute(self.command(self.a)); await self.stock.execute(self.command(self.b))
        client = uuid4(); sale = await self.make_sale(self.a, client=client); replay = await self.make_sale(self.a, client=client)
        self.assertEqual(sale.id, replay.id)
        self.assertEqual((await self.balance_for(self.a)).quantity, 8)
        self.assertEqual((await self.balance_for(self.b)).quantity, 10)
        self.assertEqual((await self.db.get(ProductBatch, first["batch_id"])).quantity, 8)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(
            InventoryMovement.company_id == self.company.id, InventoryMovement.movement_type == "variant_sale"))).scalar_one(), 1)

    async def test_variant_return_inspection_never_restores_stock_twice(self):
        hold = await self.returned(); service = ReturnService(self.db, self.owner)
        pending = await service.pending(); self.assertEqual(pending[0]["variant_id"], self.a.id)
        self.assertEqual(pending[0]["variant_name"], "250mg")
        command = self.inspection(hold); first = await service.inspect(command); replay = await service.inspect(command)
        self.assertEqual(first["id"], replay["id"])
        self.assertEqual((await self.balance_for(self.a)).quantity, 9)
        batch = (await self.db.execute(select(ProductBatch).where(ProductBatch.code == "RETURNED-250MG", ProductBatch.company_id == self.company.id))).scalar_one()
        self.assertEqual(batch.variant_id, self.a.id); self.assertEqual(batch.quantity, 1)
        self.assertEqual(self.balance.quantity, 100)

    async def test_expired_variant_return_disposal_exactly_once(self):
        hold = await self.returned(); service = ReturnService(self.db, self.owner)
        command = self.inspection(hold, disposition="dispose", expires_on=date.today()-timedelta(days=1))
        await service.inspect(command); await service.inspect(command)
        self.assertEqual((await self.balance_for(self.a)).quantity, 8)
        self.assertEqual(self.balance.quantity, 100)
        self.assertEqual(await service.pending(), [])

    async def test_variant_case_breaking_and_selected_lot_adjustment(self):
        await self.prepare(); self.product.purchase_unit = "carton"; self.product.units_per_purchase = 24
        first = await self.stock.execute(self.command(self.a, quantity=1, received_unit="carton"))
        remove = self.command(self.a, operation="supplier_return", quantity=3)
        await self.stock.execute(remove); await self.stock.execute(remove)
        self.assertEqual((await self.balance_for(self.a)).quantity, 21)
        self.assertEqual((await self.db.get(ProductBatch, first["batch_id"])).quantity, 21)

    async def test_variant_hold_cannot_be_bypassed_by_assignment_or_overselling(self):
        await self.returned()
        with self.assertRaises(HTTPException):
            await self.svc.assign_batch(BatchInput(branch_id=self.branch.id, product_id=self.product.id, variant_id=self.a.id,
                code="BYPASS", expires_on=date.today()+timedelta(days=2), quantity=1))
        with self.assertRaises(HTTPException): await self.make_sale(self.a, quantity=9)
        self.assertEqual((await self.balance_for(self.a)).quantity, 9)

    async def test_missing_or_foreign_variant_and_unauthorized_employee_rejected(self):
        await self.prepare()
        for variant_id in (None, uuid4()):
            with self.assertRaises(HTTPException): await self.stock.execute(self.command(self.a, variant_id=variant_id))
        with self.assertRaises(HTTPException): await BatchStockService(self.db, self.waiter).execute(self.command(self.a))
        self.assertEqual((await self.balance_for(self.a)).quantity, 0)

    async def test_parent_lots_are_not_silently_consumed_by_variant_sales(self):
        # Assign before introducing variants: represents a preserved legacy lot.
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        await self.svc.assign_batch(BatchInput(branch_id=self.branch.id, product_id=self.product.id,
            code="LEGACY", expires_on=date.today()+timedelta(days=30), quantity=100))
        await self.prepare()
        balance = await self.balance_for(self.a); balance.quantity = 10; await self.db.commit()
        with self.assertRaises(HTTPException): await self.make_sale(self.a)
        balance = await self.balance_for(self.a); self.assertEqual(balance.quantity, 10)
        legacy = (await self.db.execute(select(ProductBatch).where(ProductBatch.company_id == self.company.id))).scalar_one()
        self.assertIsNone(legacy.variant_id); self.assertEqual(legacy.quantity, 100)

    async def test_populated_variant_batch_downgrade_is_guarded(self):
        import importlib.util
        from pathlib import Path
        from unittest.mock import patch
        await self.prepare(); await self.stock.execute(self.command(self.a))
        spec = importlib.util.spec_from_file_location("variant_migration", Path(__file__).resolve().parents[1] / "migrations/versions/p7j_variant_batches.py")
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        def attempt(connection):
            with patch.object(migration.op, "get_bind", return_value=connection):
                with self.assertRaisesRegex(RuntimeError, "Variant batches exist"): migration.downgrade()
        await self.connection.run_sync(attempt)

    async def test_expired_variant_lot_cannot_be_sold(self):
        await self.prepare(); await self.stock.execute(self.command(self.a, expires_on=date.today()-timedelta(days=1)))
        with self.assertRaises(HTTPException): await self.make_sale(self.a)
        self.assertEqual((await self.balance_for(self.a)).quantity, 10)

    async def test_generic_variant_editor_cannot_bypass_lot_accounting(self):
        from app.products.service import ProductService
        from app.products.repository import ProductRepository
        from app.products.schema import ProductVariantUpdate
        await self.prepare(); result = await self.stock.execute(self.command(self.a))
        service = ProductService(ProductRepository(self.db))
        with self.assertRaises(HTTPException) as error:
            await service.update_variant(self.company.id, self.a.id, ProductVariantUpdate(branch_id=self.branch.id, stock_qty=0, name="Must not mutate"))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.a.name, "250mg")
        self.assertEqual((await self.balance_for(self.a)).quantity, 10)
        self.assertEqual((await self.db.get(ProductBatch, result["batch_id"])).quantity, 10)

    async def test_lot_disposal_cannot_make_stock_negative(self):
        await self.prepare(); result = await self.stock.execute(self.command(self.a))
        batch_id = result["batch_id"]
        with self.assertRaises(HTTPException): await self.stock.execute(self.command(self.a, operation="dispose", quantity=11))
        self.assertEqual((await self.balance_for(self.a)).quantity, 10)
        self.assertEqual((await self.db.get(ProductBatch, batch_id)).quantity, 10)

    async def test_same_request_cannot_change_variant_identity(self):
        await self.prepare(); command = self.command(self.a); await self.stock.execute(command)
        with self.assertRaises(HTTPException): await self.stock.execute(command.model_copy(update={"variant_id": self.b.id}))
        self.assertEqual((await self.balance_for(self.a)).quantity, 10)
        self.assertEqual((await self.balance_for(self.b)).quantity, 0)

    async def test_variant_batch_history_and_audit_reference_original_stock_movement(self):
        from app.models import AuditEvent
        await self.prepare(); result = await self.stock.execute(self.command(self.a))
        listed = await self.svc.batches()
        row = next(row for row in listed if row["id"] == result["batch_id"])
        self.assertEqual(row["variant_id"], self.a.id); self.assertEqual(row["variant_name"], "250mg")
        audit = (await self.db.execute(select(AuditEvent).where(AuditEvent.company_id == self.company.id,
            AuditEvent.action == "batch_stock_receive"))).scalar_one()
        self.assertEqual(str(audit.details["movement_id"]), str(result["movement_id"]))
        self.assertEqual((await self.db.execute(select(func.count(BatchAllocation.id)).where(
            BatchAllocation.movement_id == result["movement_id"]))).scalar_one(), 1)
