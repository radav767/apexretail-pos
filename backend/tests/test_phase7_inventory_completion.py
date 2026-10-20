"""Variant inventory completion using existing rollback-only PostgreSQL fixtures."""
import unittest
from datetime import date,timedelta
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select,func
from app.models import Branch,ProductBatch,BatchAllocation,InventoryMovement,VariantInventoryBalance
from app.products.service import ProductService
from app.products.repository import ProductRepository
from app.products.schema import ProductVariantCreate, ProductVariantUpdate
from app.inventory.transfer_service import TransferService
from app.inventory.transfer_repository import TransferRepository
from app.inventory.transfer_schema import TransferCreate
from app.inventory.service import InventoryService
from app.inventory.repository import InventoryRepository
from app.inventory.schema import StockTakeCreate
from app.inventory.count_catalog import count_catalog
from app.business_operations.schema import ProfileInput,BatchStockInput
from app.business_operations.batch_stock import BatchStockService
import test_phase7d_operations as fixtures


class InventoryCompletionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.Phase7DOperationsTests.asyncSetUp
    cleanup=fixtures.Phase7DOperationsTests.cleanup

    async def test_variant_metadata_edit_returns_real_unchanged_branch_stock(self):
        await self.prepare()
        result=await ProductService(ProductRepository(self.db)).update_variant(self.company.id,self.a['id'],
            ProductVariantUpdate(branch_id=self.branch.id,name='Small renamed',selling_price=9))
        self.assertEqual(result['stock_qty'],10)
        self.assertEqual(result['name'],'Small renamed')

    async def prepare(self,*,batch=False):
        self.destination=Branch(company_id=self.company.id,shop_id=self.shop.id,name="Destination",active=True,deleted=False)
        self.db.add(self.destination);await self.db.commit()
        product=ProductService(ProductRepository(self.db))
        self.a=await product.create_variant(self.company.id,self.product.id,ProductVariantCreate(name="Small",cost_price=4,
            selling_price=8,branch_id=self.branch.id,stock_qty=10))
        self.b=await product.create_variant(self.company.id,self.product.id,ProductVariantCreate(name="Large",cost_price=6,
            selling_price=10,branch_id=self.branch.id,stock_qty=20))
        if batch:
            self.db.add_all([ProductBatch(company_id=self.company.id,branch_id=self.branch.id,product_id=self.product.id,
                variant_id=self.a["id"],code="SAME",expires_on=date.today()+timedelta(days=30),quantity=10),
                ProductBatch(company_id=self.company.id,branch_id=self.branch.id,product_id=self.product.id,
                variant_id=self.b["id"],code="SAME",expires_on=date.today()+timedelta(days=60),quantity=20)])
            await self.db.commit()

    def transfer(self,**changes):
        values=dict(company_id=self.company.id,request_id=uuid4(),source_branch_id=self.branch.id,
            destination_branch_id=self.destination.id,items=[{"product_id":self.product.id,"variant_id":self.a["id"],"quantity":3}])
        values.update(changes);return TransferCreate(**values)

    async def test_variant_transfer_moves_only_selected_balance_and_preserves_lot_expiry(self):
        await self.prepare(batch=True)
        svc=TransferService(TransferRepository(self.db));command=self.transfer()
        rows=await svc.transfer(command,actor=self.owner)
        replay=await svc.transfer(command,actor=self.owner)
        self.assertEqual([r.id for r in rows],[r.id for r in replay])
        self.assertTrue(all(r.variant_id==self.a["id"] and r.unit_cost==4 for r in rows))
        quantities={(r.branch_id,r.variant_id):r.quantity for r in (await self.db.execute(select(VariantInventoryBalance).where(
            VariantInventoryBalance.company_id==self.company.id))).scalars()}
        self.assertEqual(quantities[(self.branch.id,self.a["id"])],7)
        self.assertEqual(quantities[(self.destination.id,self.a["id"])],3)
        self.assertEqual(quantities[(self.branch.id,self.b["id"])],20)
        self.assertEqual(self.balance.quantity,100);self.assertEqual(self.product.stock_qty,100)
        lots=(await self.db.execute(select(ProductBatch).where(ProductBatch.variant_id==self.a["id"]))).scalars().all()
        self.assertEqual(sum(r.quantity for r in lots),10)
        self.assertEqual(len({r.expires_on for r in lots}),1)

    async def test_multiple_variants_of_one_product_transfer_atomically(self):
        await self.prepare()
        rows=await TransferService(TransferRepository(self.db)).transfer(self.transfer(items=[
            {"product_id":self.product.id,"variant_id":v["id"],"quantity":2} for v in (self.a,self.b)]),actor=self.owner)
        self.assertEqual(len(rows),4)
        self.assertEqual({r.variant_id for r in rows},{self.a["id"],self.b["id"]})
        self.assertEqual(self.balance.quantity,100)

    async def test_variant_identity_changes_cannot_reuse_transfer_receipt(self):
        await self.prepare()
        svc=TransferService(TransferRepository(self.db));command=self.transfer()
        await svc.transfer(command,actor=self.owner)
        changed=command.model_copy(update={"items":self.transfer(items=[{"product_id":self.product.id,"variant_id":self.b["id"],"quantity":3}]).items})
        with self.assertRaises(HTTPException) as caught:await svc.transfer(changed,actor=self.owner)
        self.assertEqual(caught.exception.status_code,409)

    async def test_unknown_variant_does_not_fall_back_to_parent_stock(self):
        await self.prepare()
        with self.assertRaises(HTTPException):await TransferService(TransferRepository(self.db)).transfer(
            self.transfer(items=[{"product_id":self.product.id,"variant_id":uuid4(),"quantity":1}]),actor=self.owner)
        self.assertEqual(self.balance.quantity,100)

    async def test_protected_variant_count_preserves_other_dimensions_and_retries_after_stock_changes(self):
        await self.prepare();svc=InventoryService(InventoryRepository(self.db))
        command=StockTakeCreate(company_id=self.company.id,branch_id=self.branch.id,request_id=uuid4(),items=[
            {"product_id":self.product.id,"variant_id":self.a["id"],"physical_qty":8,"expected_qty":10}])
        first=await svc.stock_take(command,actor=self.owner)
        balance=(await self.db.execute(select(VariantInventoryBalance).where(VariantInventoryBalance.variant_id==self.a["id"]))).scalar_one()
        balance.quantity=6;await self.db.commit()  # Simulated later operation, not a production sale.
        repeat=await svc.stock_take(command,actor=self.owner)
        self.assertEqual(first[0].id,repeat[0].id);self.assertEqual(balance.quantity,6)
        self.assertEqual(self.balance.quantity,100)

    async def test_stale_count_snapshot_rejects_without_overwriting_stock(self):
        await self.prepare();svc=InventoryService(InventoryRepository(self.db))
        with self.assertRaises(HTTPException) as caught:await svc.stock_take(StockTakeCreate(
            company_id=self.company.id,branch_id=self.branch.id,request_id=uuid4(),items=[
                {"product_id":self.product.id,"variant_id":self.a["id"],"physical_qty":8,"expected_qty":11}]),actor=self.owner)
        self.assertEqual(caught.exception.status_code,409)
        self.assertEqual((await self.db.execute(select(VariantInventoryBalance.quantity).where(
            VariantInventoryBalance.variant_id==self.a["id"]))).scalar_one(),10)

    async def test_generic_count_cannot_destroy_batch_attribution(self):
        await self.prepare(batch=True)
        with self.assertRaises(HTTPException) as caught:await InventoryService(InventoryRepository(self.db)).stock_take(
            StockTakeCreate(company_id=self.company.id,branch_id=self.branch.id,items=[
                {"product_id":self.product.id,"variant_id":self.a["id"],"physical_qty":0}]))
        self.assertEqual(caught.exception.status_code,409)
        catalog=await count_catalog(self.db,self.company.id,self.branch.id)
        row=next(r for r in catalog if r["variant_id"]==self.a["id"])
        self.assertEqual(row["batches"][0]["code"],"SAME");self.assertEqual(row["stock_qty"],10)
        self.assertNotIn("cost_price",row)

    async def test_count_catalog_and_destinations_enforce_current_actor_scope(self):
        from app.inventory.router import physical_count_catalog
        from app.inventory.transfer_router import transfer_destinations
        await self.prepare()
        with self.assertRaises(HTTPException):await physical_count_catalog(uuid4(),self.branch.id,self.owner,self.db)
        with self.assertRaises(HTTPException):await physical_count_catalog(self.company.id,self.destination.id,self.waiter,self.db)
        with self.assertRaises(HTTPException):await transfer_destinations(self.company.id,self.waiter,self.db)
        branches=await transfer_destinations(self.company.id,self.owner,self.db)
        self.assertEqual({r["id"] for r in branches},{self.branch.id,self.destination.id})
