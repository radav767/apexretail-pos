import asyncio
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.auth.dependencies import AuthActor
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
from app.credit.service import CreditService
from app.customers.repository import CustomerRepository
from app.customers.schema import CustomerCreate
from app.customers.service import CustomerService
from app.expenses.repository import ExpenseRepository
from app.expenses.schema import ExpenseCategoryCreate, ExpenseCreate
from app.expenses.service import ExpenseService
from app.models import CreditReceivable, Customer
from app.reports.repository import ReportsRepository
from app.reports.schema import SalesHistoryQuery
from app.reports.service import ReportsService
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate, SaleItemCreate
from app.sales.service import SalesService


TEST_DATABASE_ENV = "APEX_PHASE4C_TEST_DATABASE_URL"
COMPANY = UUID("71000000-0000-0000-0000-000000000001")
OTHER_COMPANY = UUID("71000000-0000-0000-0000-000000000002")
SHOP = UUID("72000000-0000-0000-0000-000000000001")
OTHER_SHOP = UUID("72000000-0000-0000-0000-000000000002")
BRANCH = UUID("73000000-0000-0000-0000-000000000001")
SECOND_BRANCH = UUID("73000000-0000-0000-0000-000000000002")
OTHER_BRANCH = UUID("73000000-0000-0000-0000-000000000003")
USER = UUID("74000000-0000-0000-0000-000000000001")
EMPLOYEE = UUID("75000000-0000-0000-0000-000000000001")
CATEGORY = UUID("76000000-0000-0000-0000-000000000001")
PRODUCT = UUID("77000000-0000-0000-0000-000000000001")


class CreditPolicyValidationTest(unittest.TestCase):
    def test_credit_requires_explicit_policy(self):
        base = {"company_id": uuid4(), "customer_code": "C1", "name": "Customer"}
        with self.assertRaises(ValidationError):
            CustomerCreate(**base, credit_enabled=True)
        with self.assertRaises(ValidationError):
            CustomerCreate(**base, unlimited_credit=True)
        limited = CustomerCreate(**base, credit_enabled=True, credit_limit="25.00")
        self.assertEqual(limited.credit_limit, Decimal("25.00"))
        unlimited = CustomerCreate(**base, credit_enabled=True, unlimited_credit=True)
        self.assertIsNone(unlimited.credit_limit)

    def test_legacy_credit_report_has_explicit_label(self):
        query = SalesHistoryQuery(view="credit_sales", date_from=date(2026, 1, 1), date_to=date(2026, 1, 1))
        sql, _, _ = ReportsRepository.sales_history_rows_sql(query)
        self.assertIn("Legacy / Unassigned", sql)

    def test_zero_and_negative_financial_amounts_are_rejected(self):
        for amount in ("0", "-1"):
            with self.subTest(kind="settlement", amount=amount), self.assertRaises(ValidationError):
                SettlementCreate(company_id=uuid4(), receivable_id=uuid4(), branch_id=uuid4(), amount=amount, payment_method="cash", idempotency_key="valid-key")
            with self.subTest(kind="expense", amount=amount), self.assertRaises(ValidationError):
                ExpenseCreate(company_id=uuid4(), category_id=uuid4(), branch_id=uuid4(), amount=amount, occurred_at=datetime.now(timezone.utc), payment_method="cash", description="Test", idempotency_key="valid-key")


class FinancialFoundationPostgresTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database_url = os.getenv(TEST_DATABASE_ENV)
        if not database_url:
            self.skipTest(f"{TEST_DATABASE_ENV} is not configured")
        parsed = make_url(database_url)
        if not (parsed.database or "").startswith("apexretail_phase4c_test_"):
            self.fail("refusing financial integration database without test prefix")
        self.database_url = database_url
        self.engine = create_async_engine(database_url)
        async with self.engine.begin() as connection:
            await self.seed(connection)
        self.addAsyncCleanup(self._cleanup)
        self.owner = AuthActor("user", COMPANY, "owner", user=SimpleNamespace(id=USER))
        self.employee = AuthActor(
            "employee", COMPANY, "cashier",
            employee=SimpleNamespace(id=EMPLOYEE, branch_id=BRANCH),
            permissions={"credit_sales": True, "credit_settlements": True, "expenses_manage": True},
        )

    async def _cleanup(self):
        async with self.engine.begin() as connection:
            # The database name guard in asyncSetUp makes this test-only
            # cleanup safe, and TRUNCATE intentionally does not mutate posted
            # financial rows through ordinary UPDATE/DELETE operations.
            await connection.execute(text("""
                TRUNCATE audit_events, expenses, expense_categories,
                credit_settlements, credit_receivables, inventory_movements,
                sale_items, sales, inventory_balances, products, categories,
                pos_sessions, employees, users, company_settings, branches,
                shops, customers, companies CASCADE
            """))
        await self.engine.dispose()

    async def seed(self, connection):
        await connection.execute(text("""
            INSERT INTO companies (id,name,owner_email,business_type,active,deleted)
            VALUES (:company,'Finance Test','finance@example.test','Retail',true,false),
                   (:other,'Other','other-finance@example.test','Retail',true,false)
        """), {"company": COMPANY, "other": OTHER_COMPANY})
        await connection.execute(text("""
            INSERT INTO shops (id,company_id,name,active,deleted) VALUES
            (:shop,:company,'Main Shop',true,false),(:other_shop,:other,'Other Shop',true,false)
        """), {"shop": SHOP, "company": COMPANY, "other_shop": OTHER_SHOP, "other": OTHER_COMPANY})
        await connection.execute(text("""
            INSERT INTO branches (id,company_id,shop_id,name,active,deleted) VALUES
            (:branch,:company,:shop,'Main',true,false),
            (:second,:company,:shop,'Second',true,false),
            (:other_branch,:other,:other_shop,'Other',true,false)
        """), {"branch": BRANCH, "second": SECOND_BRANCH, "company": COMPANY, "shop": SHOP, "other_branch": OTHER_BRANCH, "other": OTHER_COMPANY, "other_shop": OTHER_SHOP})
        await connection.execute(text("INSERT INTO users (id,company_id,email,password_hash,role,active,deleted) VALUES (:id,:company,'owner@example.test','x','owner',true,false)"), {"id": USER, "company": COMPANY})
        await connection.execute(text("INSERT INTO employees (id,company_id,shop_id,branch_id,name,pin,role,permissions,active,deleted) VALUES (:id,:company,:shop,:branch,'Cashier','x','cashier','{}'::jsonb,true,false)"), {"id": EMPLOYEE, "company": COMPANY, "shop": SHOP, "branch": BRANCH})
        await connection.execute(text("INSERT INTO categories (id,company_id,name,active,deleted) VALUES (:id,:company,'Goods',true,false)"), {"id": CATEGORY, "company": COMPANY})
        await connection.execute(text("""
            INSERT INTO products (id,company_id,category_id,name,sku,unit,cost_price,selling_price,stock_qty,reorder_level,active,deleted)
            VALUES (:id,:company,:category,'Item','ITEM','each',20,60,20,1,true,false)
        """), {"id": PRODUCT, "company": COMPANY, "category": CATEGORY})
        await connection.execute(text("""
            INSERT INTO inventory_balances (id,company_id,shop_id,branch_id,product_id,quantity,reorder_level,active,deleted)
            VALUES (:id,:company,:shop,:branch,:product,20,1,true,false)
        """), {"id": uuid4(), "company": COMPANY, "shop": SHOP, "branch": BRANCH, "product": PRODUCT})
        await connection.execute(text("""
            INSERT INTO company_settings (id,company_id,currency_code,currency_symbol,decimal_places,tax_name,tax_rate,tax_inclusive,paper_size,auto_print,payment_methods,active,deleted)
            VALUES (:id,:company,'USD','$',2,'Tax',0,false,'80mm',false,'["cash","card","mobile","credit"]'::jsonb,true,false)
        """), {"id": uuid4(), "company": COMPANY})

    async def create_customer(self, *, code="CUST", enabled=True, limit="100.00", unlimited=False):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            return await CustomerService(CustomerRepository(session)).create(CustomerCreate(
                company_id=COMPANY, customer_code=code, name=f"Customer {code}",
                credit_enabled=enabled, unlimited_credit=unlimited,
                credit_limit=None if unlimited else limit, credit_terms_days=30,
            ), self.owner)

    async def credit_sale(self, customer_id, amount="60.00"):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            return await SalesService(SalesRepository(session)).create_sale(SaleCreate(
                company_id=COMPANY, branch_id=BRANCH, customer_id=customer_id,
                payment_method="credit", items=[SaleItemCreate(product_id=PRODUCT, quantity="1", unit_price=amount, line_total=amount)],
            ), actor=self.owner)

    async def test_company_isolation_credit_policy_and_limit(self):
        disabled = await self.create_customer(code="OFF", enabled=False, limit=None)
        with self.assertRaisesRegex(HTTPException, "not enabled"):
            await self.credit_sale(disabled["id"])
        limited = await self.create_customer(code="LIMIT", limit="100.00")
        sale = await self.credit_sale(limited["id"], "60.00")
        self.assertEqual(sale.amount_received, Decimal("0.00"))
        with self.assertRaisesRegex(HTTPException, "limit exceeded"):
            await self.credit_sale(limited["id"], "60.00")
        async with AsyncSession(self.engine) as session:
            with self.assertRaisesRegex(HTTPException, "Customer not found"):
                await CustomerService(CustomerRepository(session)).get(OTHER_COMPANY, limited["id"])

    async def test_partial_full_overpayment_balance_history_and_cash_reporting(self):
        customer = await self.create_customer(code="PAY", limit="200.00")
        sale = await self.credit_sale(customer["id"], "60.00")
        async with AsyncSession(self.engine) as session:
            receivable = (await session.execute(select(CreditReceivable).where(CreditReceivable.sale_id == sale.id))).scalar_one()
            receivable_id = receivable.id
            credit = CreditService(CreditRepository(session))
            first = await credit.create_settlement(SettlementCreate(company_id=COMPANY, receivable_id=receivable_id, branch_id=BRANCH, amount="20.00", payment_method="cash", idempotency_key="settle-partial-001"), self.owner)
            self.assertEqual(first["outstanding_balance"], Decimal("40.00"))
        async with AsyncSession(self.engine) as session:
            credit = CreditService(CreditRepository(session))
            with self.assertRaisesRegex(HTTPException, "exceeds"):
                await credit.create_settlement(SettlementCreate(company_id=COMPANY, receivable_id=receivable_id, branch_id=BRANCH, amount="41.00", payment_method="cash", idempotency_key="settle-overpay-001"), self.owner)
            final = await credit.create_settlement(SettlementCreate(company_id=COMPANY, receivable_id=receivable_id, branch_id=BRANCH, amount="40.00", payment_method="cash", idempotency_key="settle-final-001"), self.owner)
            self.assertEqual(final["outstanding_balance"], Decimal("0.00"))
        async with AsyncSession(self.engine) as session:
            customers = CustomerService(CustomerRepository(session))
            view = await customers.get(COMPANY, customer["id"])
            history = await customers.history(COMPANY, customer["id"])
            self.assertEqual(view["outstanding_balance"], Decimal("0.00"))
            self.assertEqual([row["transaction_type"] for row in history], ["credit_sale", "settlement", "settlement"])

            expenses = ExpenseService(ExpenseRepository(session))
            category = await expenses.create_category(ExpenseCategoryCreate(company_id=COMPANY, name="Utilities"), self.owner)
        async with AsyncSession(self.engine) as session:
            expenses = ExpenseService(ExpenseRepository(session))
            expense = await expenses.create_expense(ExpenseCreate(company_id=COMPANY, category_id=category.id, branch_id=BRANCH, amount="10.00", occurred_at=datetime.now(timezone.utc), payment_method="cash", description="Power", idempotency_key="expense-cash-001"), self.owner)
            expense_id = expense.id
            rows = await expenses.list_expenses(COMPANY, self.owner, branch_id=BRANCH, payment_method="cash", limit=100, offset=0)
            self.assertEqual(len(rows), 1)
            with self.assertRaisesRegex(HTTPException, "Branch access denied"):
                await expenses.create_expense(ExpenseCreate(company_id=COMPANY, category_id=category.id, branch_id=SECOND_BRANCH, amount="1.00", occurred_at=datetime.now(timezone.utc), payment_method="cash", description="Denied", idempotency_key="expense-denied-001"), self.employee)
        async with AsyncSession(self.engine) as session:
            with self.assertRaises(Exception):
                await session.execute(text("UPDATE expenses SET amount=1 WHERE id=:id"), {"id": expense_id})
            await session.rollback()
            with self.assertRaises(Exception):
                await session.execute(text("DELETE FROM credit_settlements WHERE receivable_id=:id"), {"id": receivable_id})
            await session.rollback()
        async with AsyncSession(self.engine) as session:
            today = datetime.now(timezone.utc).date()
            summary = await ReportsService(ReportsRepository(session)).financial_summary(COMPANY, date_from=today, date_to=today)
            self.assertEqual(summary["net_sales"], Decimal("60.00"))
            self.assertEqual(summary["operating_expenses"], Decimal("10.00"))
            self.assertEqual(summary["net_profit"], Decimal("30.00"))
            self.assertEqual(summary["cash_settlements"], Decimal("60.00"))
            self.assertEqual(summary["cash_expenses"], Decimal("10.00"))
            self.assertEqual(summary["expected_cash_movement"], Decimal("50.00"))

    async def test_concurrent_settlements_cannot_overpay(self):
        customer = await self.create_customer(code="RACE", limit="200.00")
        sale = await self.credit_sale(customer["id"], "100.00")
        async with AsyncSession(self.engine) as session:
            receivable_id = (await session.execute(select(CreditReceivable.id).where(CreditReceivable.sale_id == sale.id))).scalar_one()

        async def settle(key):
            async with AsyncSession(self.engine, expire_on_commit=False) as session:
                try:
                    result = await CreditService(CreditRepository(session)).create_settlement(SettlementCreate(company_id=COMPANY, receivable_id=receivable_id, branch_id=BRANCH, amount="60.00", payment_method="card", idempotency_key=key), self.owner)
                    return result["amount"]
                except HTTPException as exc:
                    return exc.status_code

        results = await asyncio.gather(settle("concurrent-settle-001"), settle("concurrent-settle-002"))
        self.assertCountEqual(results, [Decimal("60.00"), 409])
        async with AsyncSession(self.engine) as session:
            receivable = await CreditRepository(session).get_receivable(COMPANY, receivable_id)
            self.assertEqual(receivable.outstanding_balance, Decimal("40.00"))


if __name__ == "__main__":
    unittest.main()
