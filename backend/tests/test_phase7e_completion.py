"""Current variant/lot valuation, real PostgreSQL and route authorization."""
import unittest
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from app.inventory.valuation import stock_summary
from app.inventory.repository import InventoryRepository
from app.reports.repository import ReportsRepository
from app.reports.service import ReportsService
from app.dashboard.repository import DashboardRepository
from app.models import ProductBatch, Sale, VariantInventoryBalance
import test_phase7e_variant_batches as variants
import test_phase7d_operations as fixtures


class CompletionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.Phase7DOperationsTests.asyncSetUp
    cleanup = fixtures.Phase7DOperationsTests.cleanup
    prepare = variants.VariantBatchTests.prepare
    command = variants.VariantBatchTests.command
    make_sale = variants.VariantBatchTests.make_sale

    async def setup_stock(self):
        await self.prepare(); self.product.cost_price=2
        a=await self.stock.execute(self.command(self.a)); b=await self.stock.execute(self.command(self.b))
        return a,b

    async def test_all_stock_summaries_include_variants_without_double_counting_lots(self):
        await self.setup_stock()
        for branch in (None,self.branch.id):
            summary=await stock_summary(self.db,self.company.id,branch)
            self.assertEqual(summary["total_quantity"],120);self.assertEqual(summary["stock_value"],300)
            dashboard=await DashboardRepository(self.db).get_summary(self.company.id,branch)
            self.assertEqual(dashboard["stock_value"],300)
        legacy=await InventoryRepository(self.db).get_valuation(self.company.id)
        self.assertEqual(legacy[1],120);self.assertEqual(legacy[2],300)

    async def test_variant_report_and_csv_keep_distinct_costs_and_names(self):
        await self.setup_stock(); service=ReportsService(ReportsRepository(self.db))
        result=await service.inventory_valuation(self.company.id,branch_id=self.branch.id)
        self.assertEqual(result["total"],3);self.assertEqual(result["summary"]["cost_value"]["value"],300)
        rows={row["variant_id"]:row for row in result["rows"]}
        self.assertEqual(rows[self.a.id]["cost_value"]["value"],40)
        self.assertEqual(rows[self.b.id]["cost_value"]["value"],60)
        csv=await service.inventory_csv(self.company.id,branch_id=self.branch.id)
        self.assertIn("250mg",csv);self.assertIn("500mg",csv)

    async def test_batch_cost_after_sale_is_current_variant_cost_and_read_only(self):
        a,_=await self.setup_stock(); sale=await self.make_sale(self.a)
        total=sale.total_amount
        rows=await ReportsRepository(self.db).batch_valuation(self.company.id,self.branch.id)
        row=next(r for r in rows if r["batch_id"]==a["batch_id"])
        self.assertEqual(row["quantity"],8);self.assertEqual(row["unit_cost"],4);self.assertEqual(row["cost_value"],32)
        self.assertEqual(sale.total_amount,total)
        self.assertEqual((await stock_summary(self.db,self.company.id))["stock_value"],292)

    async def test_cost_fallback_and_missing_cost_are_not_silently_zero(self):
        await self.setup_stock();self.a.cost_price=None;await self.db.flush()
        rows=await ReportsRepository(self.db).batch_valuation(self.company.id)
        self.assertEqual(next(r for r in rows if r["variant_id"]==self.a.id)["cost_value"],20)
        self.product.cost_price=None;await self.db.flush()
        self.assertIsNone((await stock_summary(self.db,self.company.id))["stock_value"])
        rows=await ReportsRepository(self.db).batch_valuation(self.company.id)
        self.assertIsNone(next(r for r in rows if r["variant_id"]==self.a.id)["cost_value"])

    async def test_valuation_filters_company_branch_and_product(self):
        await self.setup_stock();repo=ReportsRepository(self.db)
        self.assertEqual(await repo.batch_valuation(uuid4()),[])
        self.assertEqual(await repo.batch_valuation(self.company.id,uuid4()),[])
        count,rows,total=await repo.valuation(self.company.id,product_id=uuid4())
        self.assertEqual(count,0);self.assertEqual(rows,[]);self.assertEqual(total["quantity"],0)

    async def test_financial_endpoints_deny_restricted_employees_and_cross_company(self):
        from fastapi import FastAPI
        from httpx import AsyncClient,ASGITransport
        from app.reports.router import router
        from app.auth.dependencies import get_auth_actor
        from app.db.session import get_db
        await self.setup_stock();app=FastAPI();app.include_router(router)
        async def database():yield self.db
        app.dependency_overrides[get_db]=database
        app.dependency_overrides[get_auth_actor]=lambda:self.waiter
        async with AsyncClient(transport=ASGITransport(app=app),base_url="http://isolated.test") as client:
            for path in ("batch-valuation","inventory-valuation","sales-history"):
                response=await client.get(f"/reports/{path}/{self.company.id}",params={"date_from":"2026-10-20","date_to":"2026-10-20"})
                self.assertEqual(response.status_code,403,response.text)
            app.dependency_overrides[get_auth_actor]=lambda:self.owner
            response=await client.get(f"/reports/batch-valuation/{self.company.id}")
            self.assertEqual(response.status_code,200,response.text);self.assertEqual(len(response.json()["rows"]),2)
            response=await client.get(f"/reports/batch-valuation/{uuid4()}")
            self.assertIn(response.status_code,(403,404))

    async def test_archived_cashier_cannot_synchronize_retained_restaurant_draft(self):
        from datetime import datetime,timezone
        from fastapi import HTTPException
        from app.business_operations.offline import OfflineOrderService
        from app.business_operations.schema import OfflineDraftInput
        command=OfflineDraftInput(request_id=uuid4(),employee_id=self.employee.id,captured_at=datetime.now(timezone.utc),
            order={"branch_id":self.branch.id,"device_id":self.device.id,"request_id":uuid4()},
            items=[{"product_id":self.product.id,"quantity":1,"version":1}])
        self.employee.deleted=True
        with self.assertRaises(HTTPException) as error:await OfflineOrderService(self.db,self.waiter).synchronize(command)
        self.assertEqual(error.exception.status_code,403)

    async def test_transfer_destination_preserves_total_stock_and_denies_cashier_route(self):
        from app.models import Branch,InventoryBalance
        from app.inventory.transfer_service import TransferService
        from app.inventory.transfer_repository import TransferRepository
        from app.inventory.transfer_schema import TransferCreate
        from app.inventory.transfer_router import router
        from app.inventory.router import router as history_router
        from app.auth.dependencies import get_auth_actor
        from app.db.session import get_db
        from fastapi import FastAPI
        from httpx import AsyncClient,ASGITransport
        destination=Branch(company_id=self.company.id,shop_id=self.shop.id,name="Synthetic destination")
        self.db.add(destination);await self.db.flush()
        command=TransferCreate(company_id=self.company.id,source_branch_id=self.branch.id,destination_branch_id=destination.id,
            reference=f"POS-{uuid4()}",items=[{"product_id":self.product.id,"quantity":3}])
        # A destination with no balance inherits no stock from a parent's total
        # because the source branch already has the authoritative balance.
        result=await TransferService(TransferRepository(self.db)).transfer(command)
        self.assertEqual(len(result),2);self.assertEqual(self.balance.quantity,97)
        self.assertEqual((await stock_summary(self.db,self.company.id))["total_quantity"],100)
        balance=(await self.db.execute(select(InventoryBalance).where(InventoryBalance.branch_id==destination.id,
            InventoryBalance.product_id==self.product.id))).scalar_one()
        self.assertEqual(balance.quantity,3)
        app=FastAPI();app.include_router(router);app.include_router(history_router)
        async def database():yield self.db
        app.dependency_overrides[get_db]=database;app.dependency_overrides[get_auth_actor]=lambda:self.waiter
        async with AsyncClient(transport=ASGITransport(app=app),base_url="http://isolated.test") as client:
            response=await client.post("/inventory/transfers",json=command.model_dump(mode="json"))
            self.assertEqual(response.status_code,403,response.text)
            app.dependency_overrides[get_auth_actor]=lambda:self.owner
            response=await client.get(f"/inventory/history/{self.company.id}",params={"limit":500})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(len([m for m in response.json() if m["reference"]==command.reference]),2)
        self.assertEqual(self.balance.quantity,97)

    async def test_zero_parent_stock_does_not_poison_known_variant_valuation(self):
        await self.setup_stock();self.balance.quantity=0;self.product.cost_price=None;await self.db.flush()
        self.assertEqual((await stock_summary(self.db,self.company.id))["stock_value"],100)
        report=await ReportsService(ReportsRepository(self.db)).inventory_valuation(self.company.id)
        self.assertTrue(report["summary"]["cost_value"]["available"])
        self.assertEqual(report["summary"]["cost_value"]["value"],100)
