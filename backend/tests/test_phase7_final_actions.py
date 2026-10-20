"""Synthetic PostgreSQL fixtures only; reuse the existing rollback-only harness."""
import unittest
import hashlib
from pydantic import ValidationError
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, func, text

from app.models import Branch, InventoryBalance, InventoryMovement, ProductBatch, BatchAllocation, AuditEvent
from app.inventory.transfer_service import TransferService
from app.inventory.transfer_repository import TransferRepository
from app.inventory.transfer_schema import TransferCreate
from app.business_operations.batches import allocate_batch_movements
from app.products.repository import ProductRepository
from app.products.service import ProductService
from app.products.schema import ProductVariantCreate, ProductVariantUpdate, ProductPriceLevelCreate, ProductPriceLevelUpdate
from app.products.schema import ProductUpdate, ProductCreate, CategoryCreate, CategoryUpdate
from app.products.router import protect_restricted_cost
from app.business_operations.schema import BatchStockInput, ProfileInput
from app.business_operations.batch_stock import BatchStockService
from app.auth.dependencies import AuthActor
from app.models import VariantInventoryBalance
import test_phase7d_operations as fixtures


class FinalActionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.Phase7DOperationsTests.asyncSetUp
    cleanup = fixtures.Phase7DOperationsTests.cleanup

    async def transfer_setup(self, *, tracked=True):
        self.destination = Branch(company_id=self.company.id, shop_id=self.shop.id, name="Destination", active=True, deleted=False)
        self.db.add(self.destination)
        if tracked:
            self.db.add_all([ProductBatch(company_id=self.company.id, branch_id=self.branch.id,
                product_id=self.product.id, code=code, expires_on=date.today()+timedelta(days=days), quantity=qty)
                for code, days, qty in [("FIRST", 30, 2), ("SECOND", 60, 98)]])
        await self.db.commit()
        self.command = TransferCreate(company_id=self.company.id, source_branch_id=self.branch.id,
            destination_branch_id=self.destination.id, reference="TEST-"+str(uuid4()),
            items=[{"product_id": self.product.id, "quantity": "3"}])
        self.transfers = TransferService(TransferRepository(self.db))

    async def test_transfer_preserves_fefo_lots_expiry_stock_and_single_ledger(self):
        await self.transfer_setup()
        before_sale_total = self.sale.total_amount
        movements = await self.transfers.transfer(self.command)
        batches = (await self.db.execute(select(ProductBatch).where(ProductBatch.company_id==self.company.id))).scalars().all()
        positions = {(b.branch_id, b.code): b for b in batches}
        self.assertEqual(positions[(self.branch.id,"FIRST")].quantity, 0)
        self.assertEqual(positions[(self.branch.id,"SECOND")].quantity, 97)
        self.assertEqual(positions[(self.destination.id,"FIRST")].quantity, 2)
        self.assertEqual(positions[(self.destination.id,"SECOND")].quantity, 1)
        self.assertEqual(sum(b.quantity for b in batches), 100)
        for code in ("FIRST","SECOND"):
            self.assertEqual(positions[(self.branch.id,code)].expires_on,positions[(self.destination.id,code)].expires_on)
        self.assertEqual(len(movements),2)
        allocations=(await self.db.execute(select(BatchAllocation).where(BatchAllocation.movement_id.in_([m.id for m in movements])))).scalars().all()
        self.assertEqual(len(allocations),4)
        self.assertEqual(sum(a.quantity for a in allocations),0)
        self.assertEqual(self.product.stock_qty,100)
        self.assertEqual(self.sale.total_amount,before_sale_total)
        # A repeated hook invocation must not move another lot or create stock.
        await allocate_batch_movements(self.db,movements)
        self.assertEqual(sum(b.quantity for b in batches),100)
        self.assertEqual((await self.db.execute(select(func.count(BatchAllocation.id)).where(
            BatchAllocation.movement_id.in_([m.id for m in movements])))).scalar_one(),4)

    async def test_conflicting_destination_expiry_rolls_back_entire_transfer(self):
        await self.transfer_setup()
        self.db.add(ProductBatch(company_id=self.company.id,branch_id=self.destination.id,
            product_id=self.product.id,code="FIRST",expires_on=date.today()+timedelta(days=90),quantity=0))
        await self.db.commit()
        company, branch, product, reference = self.company.id,self.branch.id,self.product.id,self.command.reference
        with self.assertRaises(HTTPException) as rejected:
            await self.transfers.transfer(self.command)
        self.assertEqual(rejected.exception.status_code,409)
        qty=(await self.db.execute(select(InventoryBalance.quantity).where(InventoryBalance.branch_id==branch,
            InventoryBalance.product_id==product))).scalar_one()
        self.assertEqual(qty,100)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(
            InventoryMovement.company_id==company,InventoryMovement.reference==reference))).scalar_one(),0)
        self.assertEqual((await self.db.execute(select(func.sum(ProductBatch.quantity)).where(
            ProductBatch.company_id==company))).scalar_one(),100)

    async def test_unassigned_source_cannot_create_untraceable_tracked_destination_stock(self):
        await self.transfer_setup(tracked=False)
        self.db.add(ProductBatch(company_id=self.company.id,branch_id=self.destination.id,
            product_id=self.product.id,code="EXISTING",expires_on=date.today()+timedelta(days=90),quantity=0))
        await self.db.commit()
        branch, product = self.branch.id,self.product.id
        with self.assertRaises(HTTPException) as rejected:
            await self.transfers.transfer(self.command)
        self.assertEqual(rejected.exception.status_code,409)
        self.assertEqual((await self.db.execute(select(InventoryBalance.quantity).where(
            InventoryBalance.branch_id==branch,InventoryBalance.product_id==product))).scalar_one(),100)

    async def test_non_batch_transfer_keeps_existing_behavior(self):
        await self.transfer_setup(tracked=False)
        movements=await self.transfers.transfer(self.command)
        self.assertEqual(len(movements),2)
        self.assertEqual(self.balance.quantity,97)
        self.assertEqual((await self.db.execute(select(func.count(ProductBatch.id)).where(
            ProductBatch.company_id==self.company.id))).scalar_one(),0)

    async def test_protected_transfer_retry_reuses_movements_and_rejects_changed_payload(self):
        await self.transfer_setup()
        self.command.request_id=uuid4()
        first=await self.transfers.transfer(self.command,actor=self.owner)
        repeat=await self.transfers.transfer(self.command,actor=self.owner)
        self.assertEqual([m.id for m in first],[m.id for m in repeat])
        self.assertEqual(self.balance.quantity,97)
        self.assertEqual((await self.db.execute(select(func.count(AuditEvent.id)).where(
            AuditEvent.company_id==self.company.id,AuditEvent.action=="inventory_transfer_committed_v1"))).scalar_one(),1)
        with self.assertRaises(HTTPException) as conflict:
            await self.transfers.transfer(self.command.model_copy(update={"notes":"Different request"}),actor=self.owner)
        self.assertEqual(conflict.exception.status_code,409)
        self.assertEqual(self.balance.quantity,97)
        self.assertEqual((await self.db.execute(select(func.sum(ProductBatch.quantity)).where(
            ProductBatch.company_id==self.company.id))).scalar_one(),100)
        identity=f"transfer:{self.company.id}:{self.command.request_id}"
        key=int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8],"big",signed=True)
        async with self.engine.connect() as connection:
            self.assertFalse((await connection.execute(text("SELECT pg_try_advisory_xact_lock(:key)"),{"key":key})).scalar_one())

    async def test_transfer_route_redacts_cost_and_rejects_wrong_source_branch(self):
        from app.inventory.transfer_router import create_stock_transfer
        await self.transfer_setup(tracked=False)
        self.product.cost_price=Decimal("2.50");await self.db.commit()
        actor=AuthActor(actor_type="employee",company_id=self.company.id,role="custom",employee=self.employee,
            permissions={"inventory_transfer":True,"product_costs_view":False},pos_session=self.session)
        rows=await create_stock_transfer(self.command,service=self.transfers,_actor=actor,_entitlement=None)
        self.assertTrue(all(row.unit_cost is None for row in rows))
        stored=await self.db.get(InventoryMovement,rows[0].id)
        self.assertEqual(stored.unit_cost,Decimal("2.50"))
        with self.assertRaises(HTTPException) as denied:
            await create_stock_transfer(self.command.model_copy(update={"source_branch_id":self.destination.id}),
                service=self.transfers,_actor=actor,_entitlement=None)
        self.assertEqual(denied.exception.status_code,403)

    async def test_transfer_retry_capability_requires_current_permission(self):
        from app.inventory.transfer_router import transfer_capabilities
        result=await transfer_capabilities(self.owner)
        self.assertEqual(result,{"idempotency":"audit-v1"})
        actor=AuthActor(actor_type="employee",company_id=self.company.id,role="custom",employee=self.employee,
            permissions={"inventory_transfer":False},pos_session=self.session)
        with self.assertRaises(HTTPException): await transfer_capabilities(actor)

    async def test_variant_metadata_edit_archive_restore_preserves_stock_and_attributes(self):
        service=ProductService(ProductRepository(self.db))
        variant=await service.create_variant(self.company.id,self.product.id,ProductVariantCreate(
            name="Small",attributes={"size":"S"},cost_price="2",selling_price="5",
            branch_id=self.branch.id,stock_qty="8"))
        changed=await service.update_variant(self.company.id,variant["id"],ProductVariantUpdate(
            name="Small green",selling_price="6",branch_id=self.branch.id,reorder_level="3"))
        self.assertEqual(changed["stock_qty"],8)
        self.assertEqual(changed["attributes"],{"size":"S"})
        self.assertEqual(changed["cost_price"],2)
        for active in (False,True):
            await service.update_variant(self.company.id,variant["id"],ProductVariantUpdate(active=active))
        rows=await service.list_variants(self.company.id,self.product.id,self.branch.id)
        self.assertEqual(rows[0]["stock_qty"],8)
        with self.assertRaises(HTTPException):
            await service.update_variant(uuid4(),variant["id"],ProductVariantUpdate(name="Foreign"))

    async def test_price_level_create_edit_delete_and_company_boundary(self):
        service=ProductService(ProductRepository(self.db))
        row=await service.create_price_level(self.company.id,self.product.id,ProductPriceLevelCreate(name="Wholesale",price="8",minimum_quantity="12"))
        row=await service.update_price_level(self.company.id,row.id,ProductPriceLevelUpdate(price="7",minimum_quantity="24"))
        self.assertEqual(row.price,7)
        self.assertEqual(row.minimum_quantity,24)
        with self.assertRaises(HTTPException):
            await service.delete_price_level(uuid4(),row.id)
        await service.delete_price_level(self.company.id,row.id)
        self.assertEqual(await service.list_price_levels(self.company.id,self.product.id),[])

    async def test_batch_count_uses_existing_stock_ledger_and_retry_identity(self):
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        lot=ProductBatch(company_id=self.company.id,branch_id=self.branch.id,product_id=self.product.id,
            code="COUNT",expires_on=date.today()+timedelta(days=30),quantity=100)
        self.db.add(lot);await self.db.commit()
        service=BatchStockService(self.db,self.owner)
        command=BatchStockInput(request_id=uuid4(),operation="count",branch_id=self.branch.id,
            product_id=self.product.id,code="COUNT",expires_on=lot.expires_on,quantity="97",reason="Physical count")
        result=await service.execute(command)
        self.assertEqual(lot.quantity,97);self.assertEqual(self.balance.quantity,97)
        self.assertEqual(self.product.stock_qty,97)
        movement=await self.db.get(InventoryMovement,result["movement_id"])
        self.assertEqual(movement.movement_type,"stock_take")
        self.assertEqual(movement.before_qty,100);self.assertEqual(movement.after_qty,97)
        replay=await service.execute(command)
        self.assertTrue(replay["already_processed"]);self.assertEqual(replay["movement_id"],result["movement_id"])
        self.assertEqual(lot.quantity,97)
        # Count an increase, then zero, without receiving or selling a second time.
        for quantity in (102,0):
            await service.execute(command.model_copy(update={"request_id":uuid4(),"quantity":Decimal(quantity)}))
            self.assertEqual(lot.quantity,quantity);self.assertEqual(self.balance.quantity,quantity)

    async def test_variant_batch_count_does_not_change_parent_or_other_variants(self):
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        variant=await ProductService(ProductRepository(self.db)).create_variant(self.company.id,self.product.id,
            ProductVariantCreate(name="Dose",cost_price="4",selling_price="8",branch_id=self.branch.id))
        service=BatchStockService(self.db,self.owner)
        command=BatchStockInput(request_id=uuid4(),operation="receive",branch_id=self.branch.id,
            product_id=self.product.id,variant_id=variant["id"],code="DOSE",expires_on=date.today()+timedelta(days=30),quantity=10,reason="Receiving")
        await service.execute(command)
        command=command.model_copy(update={"request_id":uuid4(),"operation":"count","quantity":Decimal("7")})
        result=await service.execute(command)
        balance=(await self.db.execute(select(VariantInventoryBalance).where(
            VariantInventoryBalance.variant_id==variant["id"]))).scalar_one()
        self.assertEqual(balance.quantity,7);self.assertEqual(self.balance.quantity,100)
        movement=await self.db.get(InventoryMovement,result["movement_id"])
        self.assertEqual(movement.variant_id,variant["id"]);self.assertEqual(movement.unit_cost,4)

    async def test_batch_count_requires_its_own_permission_and_does_not_accept_foreign_branch(self):
        actor=AuthActor(actor_type="employee",company_id=self.company.id,role="cashier",employee=self.employee,
            permissions={"batches_manage":True,"inventory_adjust":True,"inventory_count":False},pos_session=self.session)
        command=BatchStockInput(request_id=uuid4(),operation="count",branch_id=self.branch.id,
            product_id=self.product.id,code="COUNT",expires_on=date.today(),quantity=0,reason="Physical count")
        with self.assertRaises(HTTPException) as denied:
            await BatchStockService(self.db,actor).execute(command)
        self.assertEqual(denied.exception.status_code,403)
        actor.permissions["inventory_count"]=True
        with self.assertRaises(HTTPException):
            await BatchStockService(self.db,actor).execute(command.model_copy(update={"branch_id":uuid4()}))

    async def test_redacted_cost_from_old_client_does_not_erase_existing_product_cost(self):
        actor=AuthActor(actor_type="employee",company_id=self.company.id,role="custom",employee=self.employee,
            permissions={"products_edit":True,"product_costs_view":False},pos_session=self.session)
        self.product.cost_price=Decimal("2.50");await self.db.commit()
        data=ProductUpdate(name="Edited without cost access",cost_price=None)
        protected=protect_restricted_cost(data,actor)
        self.assertNotIn("cost_price",protected.model_dump(exclude_unset=True))
        self.assertIn("cost_price",data.model_fields_set)
        changed=await ProductService(ProductRepository(self.db)).update_product(self.company.id,self.product.id,protected,actor=actor)
        self.assertEqual(changed.cost_price,Decimal("2.50"))
        with self.assertRaises(HTTPException) as denied:
            protect_restricted_cost(ProductUpdate(cost_price="9"),actor)
        self.assertEqual(denied.exception.status_code,403)

    def test_authorized_cost_clear_remains_supported(self):
        data=ProductUpdate(cost_price=None)
        self.assertIn("cost_price",protect_restricted_cost(data,self.owner).model_fields_set)

    def test_required_catalog_update_fields_reject_null_before_database_write(self):
        for schema, fields in ((CategoryUpdate,("name","active")),
                (ProductUpdate,("name","product_type","unit","units_per_purchase","track_inventory","tax_exempt","stock_qty","reorder_level","active")),
                (ProductVariantUpdate,("name","attributes","active","stock_qty","reorder_level")),
                (ProductPriceLevelUpdate,("name","price","minimum_quantity","active"))):
            self.assertEqual(schema().model_dump(exclude_unset=True),{})
            for field in fields:
                with self.subTest(schema=schema.__name__,field=field):
                    with self.assertRaises(ValidationError): schema(**{field:None})

    async def test_category_crud_hierarchy_dependencies_and_company_boundary(self):
        service=ProductService(ProductRepository(self.db))
        parent=await service.create_category(CategoryCreate(company_id=self.company.id,name="Parent"))
        child=await service.create_category(CategoryCreate(company_id=self.company.id,name="Child",parent_id=parent.id))
        changed=await service.update_category(self.company.id,child.id,CategoryUpdate(name="Renamed child"))
        self.assertEqual(changed.name,"Renamed child")
        with self.assertRaises(HTTPException):
            await service.update_category(self.company.id,parent.id,CategoryUpdate(parent_id=child.id))
        with self.assertRaises(HTTPException):
            await service.delete_category(self.company.id,parent.id)
        with self.assertRaises(HTTPException):
            await service.update_category(uuid4(),child.id,CategoryUpdate(name="Foreign"))
        with self.assertRaises(HTTPException):
            await service.delete_category(self.company.id,self.category.id)
        await service.delete_category(self.company.id,child.id)
        await service.delete_category(self.company.id,parent.id)
        names=[row.name for row in await service.list_categories(self.company.id)]
        self.assertNotIn("Parent",names);self.assertNotIn("Renamed child",names)

    async def test_product_crud_retry_and_archive_preserve_existing_financial_records(self):
        service=ProductService(ProductRepository(self.db))
        command=ProductCreate(company_id=self.company.id,branch_id=self.branch.id,create_request_key=str(uuid4()),
            name="New synthetic product",unit="each",cost_price="2",selling_price="5",stock_qty="4")
        created=await service.create_product(command,actor=self.owner)
        repeated=await service.create_product(command,actor=self.owner)
        self.assertEqual(created.id,repeated.id)
        balance=(await self.db.execute(select(InventoryBalance).where(InventoryBalance.product_id==created.id))).scalar_one()
        self.assertEqual(balance.quantity,4)
        changed=await service.update_product(self.company.id,created.id,ProductUpdate(name="Edited product",selling_price="6"),actor=self.owner)
        self.assertEqual(changed.selling_price,6)
        with self.assertRaises(HTTPException):
            await service.update_product(uuid4(),created.id,ProductUpdate(name="Foreign"),actor=self.owner)
        total=self.sale.total_amount
        await service.archive_product(self.company.id,created.id,actor=self.owner)
        self.assertFalse(created.active);self.assertIsNotNone(created.archived_at)
        self.assertEqual(balance.quantity,4);self.assertEqual(self.sale.total_amount,total)
