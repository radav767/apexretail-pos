import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.reports.repository import ReportsRepository
from app.reports.schema import SalesHistoryQuery
from app.reports.service import ReportsService


TEST_DATABASE_ENV = "APEX_PHASE4A_TEST_DATABASE_URL"
COMPANY = UUID("41000000-0000-0000-0000-000000000001")
OTHER_COMPANY = UUID("41000000-0000-0000-0000-000000000002")
SHOP = UUID("42000000-0000-0000-0000-000000000001")
OTHER_SHOP = UUID("42000000-0000-0000-0000-000000000002")
BRANCH = UUID("43000000-0000-0000-0000-000000000001")
OTHER_BRANCH = UUID("43000000-0000-0000-0000-000000000002")
CASHIER = UUID("44000000-0000-0000-0000-000000000001")
OTHER_CASHIER = UUID("44000000-0000-0000-0000-000000000002")
CATEGORY = UUID("45000000-0000-0000-0000-000000000001")
OTHER_CATEGORY = UUID("45000000-0000-0000-0000-000000000002")
PRODUCT = UUID("46000000-0000-0000-0000-000000000001")
UNKNOWN_COST_PRODUCT = UUID("46000000-0000-0000-0000-000000000002")
OTHER_PRODUCT = UUID("46000000-0000-0000-0000-000000000003")


class Phase4APostgresTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database_url = os.getenv(TEST_DATABASE_ENV)
        if not database_url:
            self.skipTest(f"{TEST_DATABASE_ENV} is not configured")
        parsed = make_url(database_url)
        if not (parsed.database or "").startswith("apexretail_phase4a_test_"):
            self.fail("refusing Phase 4A integration database without test prefix")
        self.engine = create_async_engine(database_url)
        self.connection = await self.engine.connect()
        self.transaction = await self.connection.begin()
        self.session = AsyncSession(bind=self.connection)
        self.addAsyncCleanup(self._close_database)
        await self.seed()
        self.repo = ReportsRepository(self.session)
        self.service = ReportsService(self.repo)

    async def asyncTearDown(self):
        pass

    async def _close_database(self):
        if not hasattr(self, "engine"):
            return
        await self.session.close()
        await self.transaction.rollback()
        await self.connection.close()
        await self.engine.dispose()

    async def seed(self):
        await self.connection.execute(text("""
            INSERT INTO companies (id,name,owner_email,business_type,active,deleted)
            VALUES (:company,'Phase 4A','phase4a@example.test','Retail',true,false),
                   (:other,'Other','phase4a-other@example.test','Retail',true,false)
        """), {"company": COMPANY, "other": OTHER_COMPANY})
        await self.connection.execute(text("""
            INSERT INTO shops (id,company_id,name,active,deleted)
            VALUES (:shop,:company,'Harare',true,false),(:other_shop,:other,'Other',true,false)
        """), {"shop": SHOP, "company": COMPANY, "other_shop": OTHER_SHOP, "other": OTHER_COMPANY})
        await self.connection.execute(text("""
            INSERT INTO branches (id,company_id,shop_id,name,active,deleted)
            VALUES (:branch,:company,:shop,'Main',true,false),(:other_branch,:other,:other_shop,'Other',true,false)
        """), {"branch": BRANCH, "company": COMPANY, "shop": SHOP, "other_branch": OTHER_BRANCH, "other": OTHER_COMPANY, "other_shop": OTHER_SHOP})
        await self.connection.execute(text("""
            INSERT INTO employees (id,company_id,shop_id,branch_id,name,pin,role,permissions,active,deleted)
            VALUES (:cashier,:company,:shop,:branch,'Alice','0000','cashier','{}'::jsonb,true,false),
                   (:other_cashier,:other,:other_shop,:other_branch,'Mallory','0000','cashier','{}'::jsonb,true,false)
        """), {"cashier": CASHIER, "company": COMPANY, "shop": SHOP, "branch": BRANCH, "other_cashier": OTHER_CASHIER, "other": OTHER_COMPANY, "other_shop": OTHER_SHOP, "other_branch": OTHER_BRANCH})
        await self.connection.execute(text("""
            INSERT INTO categories (id,company_id,name,active,deleted)
            VALUES (:category,:company,'Drinks',true,false),(:other_category,:other,'Other',true,false)
        """), {"category": CATEGORY, "company": COMPANY, "other_category": OTHER_CATEGORY, "other": OTHER_COMPANY})
        await self.connection.execute(text("""
            INSERT INTO products (id,company_id,category_id,name,sku,unit,cost_price,selling_price,stock_qty,reorder_level,active,deleted)
            VALUES (:product,:company,:category,'Coffee','COF','each',2,5,10,1,true,false),
                   (:unknown,:company,:category,'Mystery','MYS','each',NULL,8,4,1,true,false),
                   (:other_product,:other,:other_category,'Other','OTH','each',1,2,1,0,true,false)
        """), {"product": PRODUCT, "unknown": UNKNOWN_COST_PRODUCT, "company": COMPANY, "category": CATEGORY, "other_product": OTHER_PRODUCT, "other": OTHER_COMPANY, "other_category": OTHER_CATEGORY})
        await self.connection.execute(text("""
            INSERT INTO inventory_balances (id,company_id,shop_id,branch_id,product_id,quantity,reorder_level,active,deleted)
            VALUES (:i1,:company,:shop,:branch,:product,10,1,true,false),
                   (:i2,:company,:shop,:branch,:unknown,4,1,true,false),
                   (:i3,:other,:other_shop,:other_branch,:other_product,99,1,true,false)
        """), {"i1": uuid4(), "i2": uuid4(), "i3": uuid4(), "company": COMPANY, "shop": SHOP, "branch": BRANCH, "product": PRODUCT, "unknown": UNKNOWN_COST_PRODUCT, "other": OTHER_COMPANY, "other_shop": OTHER_SHOP, "other_branch": OTHER_BRANCH, "other_product": OTHER_PRODUCT})
        await self.connection.execute(text("""
            INSERT INTO company_settings (id,company_id,currency_code,currency_symbol,decimal_places,tax_name,tax_rate,tax_inclusive,paper_size,auto_print,payment_methods,active,deleted)
            VALUES (:id,:company,'USD','Z$',2,'VAT',0,false,'80mm',false,'["cash","credit"]'::jsonb,true,false)
        """), {"id": uuid4(), "company": COMPANY})
        original = UUID("47000000-0000-0000-0000-000000000001")
        refund = UUID("47000000-0000-0000-0000-000000000002")
        unknown = UUID("47000000-0000-0000-0000-000000000003")
        cancelled = UUID("47000000-0000-0000-0000-000000000004")
        other_sale = UUID("47000000-0000-0000-0000-000000000005")
        rows = [
            (original, COMPANY, SHOP, BRANCH, CASHIER, None, "R-1", "Alice", "Main", "cash", "partially_refunded", Decimal("100"), Decimal("5"), datetime(2026,9,1,10,tzinfo=timezone.utc)),
            (refund, COMPANY, SHOP, BRANCH, CASHIER, original, "RF-1", "Alice", "Main", "cash", "refunded", Decimal("-20"), None, datetime(2026,9,2,10,tzinfo=timezone.utc)),
            (unknown, COMPANY, SHOP, BRANCH, CASHIER, None, "R-2", "Alice", "Main", "credit", "completed", Decimal("50"), None, datetime(2026,9,3,10,tzinfo=timezone.utc)),
            (cancelled, COMPANY, SHOP, BRANCH, CASHIER, None, "R-C", "Alice", "Main", "cash", "cancelled", Decimal("75"), None, datetime(2026,9,4,10,tzinfo=timezone.utc)),
            (other_sale, OTHER_COMPANY, OTHER_SHOP, OTHER_BRANCH, OTHER_CASHIER, None, "OTHER", "Mallory", "Other", "cash", "completed", Decimal("900"), Decimal("0"), datetime(2026,9,1,10,tzinfo=timezone.utc)),
        ]
        for row in rows:
            await self.connection.execute(text("""
                INSERT INTO sales (id,company_id,shop_id,branch_id,employee_id,original_sale_id,receipt_number,cashier_name,shop_name_snapshot,branch_name_snapshot,subtotal_amount,tax_rate,tax_amount,tax_inclusive,total_amount,discount_amount,amount_received,change_due,payment_method,status,reprint_count,created_at)
                VALUES (:id,:company,:shop,:branch,:employee,:original,:receipt,:cashier,'Harare',:branch_name,:total,0,0,false,:total,:discount,:received,0,:payment,:status,0,:created)
            """), {"id":row[0],"company":row[1],"shop":row[2],"branch":row[3],"employee":row[4],"original":row[5],"receipt":row[6],"cashier":row[7],"branch_name":row[8],"payment":row[9],"status":row[10],"total":row[11],"discount":row[12],"received":max(row[11], Decimal("0")),"created":row[13]})
        items = [
            (original, PRODUCT, "Coffee", Decimal("2"), Decimal("100"), Decimal("40"), True, CATEGORY, "Drinks"),
            (refund, PRODUCT, "Coffee", Decimal("0.4"), Decimal("-20"), Decimal("-8"), True, CATEGORY, "Drinks"),
            (unknown, UNKNOWN_COST_PRODUCT, "Mystery", Decimal("1"), Decimal("50"), Decimal("0"), None, None, None),
            (cancelled, PRODUCT, "Coffee", Decimal("1"), Decimal("75"), Decimal("30"), True, CATEGORY, "Drinks"),
            (other_sale, OTHER_PRODUCT, "Other", Decimal("1"), Decimal("900"), Decimal("1"), True, OTHER_CATEGORY, "Other"),
        ]
        for sale_id, product_id, name, quantity, line_total, line_cost, known, category_id, category_name in items:
            await self.connection.execute(text("""
                INSERT INTO sale_items (id,sale_id,product_id,product_name,category_id_snapshot,category_name_snapshot,quantity,selling_unit,unit_price,line_total,line_discount_amount,unit_cost,line_cost,cost_snapshot_available)
                VALUES (:id,:sale,:product,:name,:category,:category_name,:quantity,'each',50,:line_total,NULL,20,:line_cost,:known)
            """), {"id":uuid4(),"sale":sale_id,"product":product_id,"name":name,"category":category_id,"category_name":category_name,"quantity":quantity,"line_total":line_total,"line_cost":line_cost,"known":known})

    def query(self, view="individual", **kwargs):
        return SalesHistoryQuery(view=view, date_from=date(2026,9,1), date_to=date(2026,9,30), **kwargs)

    async def test_all_views_reconcile_without_tenant_or_item_fanout(self):
        individual = await self.service.sales_history(COMPANY, self.query())
        self.assertEqual(individual["summary"]["gross_sales"], Decimal("150.00"))
        self.assertEqual(individual["summary"]["refunds"], Decimal("20.00"))
        self.assertEqual(individual["summary"]["net_sales"], Decimal("130.00"))
        self.assertEqual(individual["summary"]["transactions"], 4)
        self.assertFalse(individual["summary"]["cost_of_sales"]["available"])
        self.assertFalse(individual["summary"]["discounts"]["available"])
        expected = {"cashier": 1, "product": 2, "category": 2, "payment_type": 2, "shop_branch": 1, "credit_sales": 1, "refunds_cancellations": 2}
        for view, row_count in expected.items():
            report = await self.service.sales_history(COMPANY, self.query(view))
            self.assertEqual(report["total"], row_count, view)
        exceptions = await self.service.sales_history(COMPANY, self.query("refunds_cancellations"))
        self.assertTrue(exceptions["summary"]["discounts"]["available"])
        self.assertEqual(exceptions["summary"]["discounts"]["value"], Decimal("0.00"))
        product = await self.service.sales_history(COMPANY, self.query("product", product_id=PRODUCT))
        self.assertEqual(product["rows"][0]["amount"], Decimal("80.00"))
        self.assertEqual(Decimal(product["rows"][0]["quantity"]), Decimal("1.600"))

    async def test_filters_pagination_validation_and_inventory_availability(self):
        first = await self.service.sales_history(COMPANY, self.query(limit=1, offset=0, sort_by="date"))
        second = await self.service.sales_history(COMPANY, self.query(limit=1, offset=1, sort_by="date"))
        self.assertEqual(first["total"], 4)
        self.assertNotEqual(first["rows"][0]["dimension_id"], second["rows"][0]["dimension_id"])
        self.assertEqual((await self.service.sales_history(COMPANY, self.query(branch_id=BRANCH)))["total"], 4)
        with self.assertRaisesRegex(Exception, "not found for this company"):
            await self.service.sales_history(COMPANY, self.query(branch_id=OTHER_BRANCH))
        valuation = await self.service.inventory_valuation(COMPANY, branch_id=BRANCH)
        self.assertEqual(valuation["summary"]["quantity"], Decimal("14.000"))
        self.assertEqual(valuation["summary"]["selling_value"]["value"], Decimal("82.00"))
        self.assertFalse(valuation["summary"]["cost_value"]["available"])
        known = await self.service.inventory_valuation(COMPANY, branch_id=BRANCH, product_id=PRODUCT)
        self.assertEqual(known["summary"]["cost_value"]["value"], Decimal("20.00"))
        self.assertEqual(known["summary"]["projected_gross_profit"]["value"], Decimal("30.00"))
        self.assertEqual(known["summary"]["margin_percentage"]["value"], Decimal("60.00"))

    async def test_product_groups_allocate_tax_inclusive_sale_total(self):
        sale_id = uuid4()
        await self.connection.execute(text("""
            INSERT INTO sales (id,company_id,shop_id,branch_id,employee_id,receipt_number,cashier_name,
              shop_name_snapshot,branch_name_snapshot,subtotal_amount,tax_rate,tax_amount,tax_inclusive,
              total_amount,discount_amount,amount_received,change_due,payment_method,status,reprint_count,created_at)
            VALUES (:id,:company,:shop,:branch,:employee,'TAX-1','Alice','Harare','Main',10,10,1,false,
              11,0,11,0,'cash','completed',0,:created)
        """), {"id": sale_id, "company": COMPANY, "shop": SHOP, "branch": BRANCH,
                "employee": CASHIER, "created": datetime(2026, 9, 10, 10, tzinfo=timezone.utc)})
        for product_id, name, line_total in ((PRODUCT, "Coffee", Decimal("4")),
                                              (UNKNOWN_COST_PRODUCT, "Mystery", Decimal("6"))):
            await self.connection.execute(text("""
                INSERT INTO sale_items (id,sale_id,product_id,product_name,quantity,selling_unit,
                  unit_price,line_total,line_discount_amount,unit_cost,line_cost,cost_snapshot_available)
                VALUES (:id,:sale,:product,:name,1,'each',:line_total,:line_total,0,1,1,true)
            """), {"id": uuid4(), "sale": sale_id, "product": product_id,
                    "name": name, "line_total": line_total})
        report = await self.service.sales_history(
            COMPANY,
            SalesHistoryQuery(view="product", date_from=date(2026, 9, 10), date_to=date(2026, 9, 10)),
        )
        self.assertEqual(sum((row["amount"] for row in report["rows"]), Decimal("0")), Decimal("11.00"))
        self.assertEqual(report["summary"]["net_sales"], Decimal("11.00"))


if __name__ == "__main__":
    unittest.main()
