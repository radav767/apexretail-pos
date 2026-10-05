import asyncio
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

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
from app.customers.schema import CustomerCreate, CustomerUpdate
from app.customers.service import CustomerService
from app.employees.service import EmployeeService
from app.expenses.repository import ExpenseRepository
from app.expenses.schema import ExpenseCategoryCreate, ExpenseCategoryUpdate, ExpenseCreate
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
    def test_financial_pagination_parameters_reject_invalid_values(self):
        from app.main import app
        schema = app.openapi()
        for path in (
            "/api/customers/{company_id}",
            "/api/customers/{company_id}/{customer_id}/transactions",
            "/api/credit/{company_id}/receivables",
            "/api/credit/{company_id}/settlements",
            "/api/expenses/{company_id}",
        ):
            parameters = {item["name"]: item["schema"] for item in schema["paths"][path]["get"]["parameters"]}
            page_schema = next(item for item in parameters["page"]["anyOf"] if item.get("type") == "integer")
            size_schema = next(item for item in parameters["page_size"]["anyOf"] if item.get("type") == "integer")
            self.assertEqual(page_schema["minimum"], 1)
            self.assertEqual(size_schema["minimum"], 1)
            self.assertEqual(size_schema["maximum"], 100)

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

    def test_cashier_customer_edits_are_contact_only(self):
        cashier = AuthActor("employee", COMPANY, "cashier", employee=SimpleNamespace(id=EMPLOYEE), permissions={"customers_view": True})
        CustomerService.enforce_cashier_update_policy(
            CustomerUpdate(name="New name", phone="123", email="a@example.test", address="Address").model_dump(exclude_unset=True),
            cashier,
        )
        for protected in (
            CustomerUpdate(active=False), CustomerUpdate(credit_enabled=True),
            CustomerUpdate(credit_limit="10"), CustomerUpdate(unlimited_credit=True),
            CustomerUpdate(credit_terms_days=30), CustomerUpdate(customer_code="NEW"),
        ):
            with self.subTest(fields=protected.model_fields_set), self.assertRaisesRegex(HTTPException, "Manager permission"):
                CustomerService.enforce_cashier_update_policy(protected.model_dump(exclude_unset=True), cashier)

    def test_cashier_creates_credit_disabled_and_manager_can_configure_credit(self):
        cashier = AuthActor("employee", COMPANY, "cashier", employee=SimpleNamespace(id=EMPLOYEE), permissions={"customers_view": True})
        manager = AuthActor("employee", COMPANY, "manager", employee=SimpleNamespace(id=EMPLOYEE), permissions={"customers_manage": True})
        safe = CustomerCreate(company_id=COMPANY, customer_code="CASH", name="Cashier Customer")
        CustomerService.enforce_cashier_create_policy(safe, cashier)
        configured = CustomerCreate(company_id=COMPANY, customer_code="MGR", name="Manager Customer", credit_enabled=True, credit_limit="100", credit_terms_days=30)
        with self.assertRaisesRegex(HTTPException, "Manager permission"):
            CustomerService.enforce_cashier_create_policy(configured, cashier)
        CustomerService.enforce_cashier_create_policy(configured, manager)

    def test_cashier_can_post_expenses_but_not_manage_categories(self):
        permissions = EmployeeService.build_permissions("cashier", None)
        self.assertTrue(permissions["expenses_create"])
        self.assertFalse(permissions["expenses_manage"])


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

    async def create_customer(self, *, code="CUST", enabled=True, limit="100.00", unlimited=False, active=True):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            return await CustomerService(CustomerRepository(session)).create(CustomerCreate(
                company_id=COMPANY, customer_code=code, name=f"Customer {code}",
                credit_enabled=enabled, unlimited_credit=unlimited,
                credit_limit=None if unlimited else limit, credit_terms_days=30, active=active,
            ), self.owner)

    async def credit_sale(self, customer_id, amount="60.00", client_sale_id=None):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            return await SalesService(SalesRepository(session)).create_sale(SaleCreate(
                company_id=COMPANY, branch_id=BRANCH, customer_id=customer_id,
                payment_method="credit", client_sale_id=client_sale_id,
                items=[SaleItemCreate(product_id=PRODUCT, quantity="1", unit_price=amount, line_total=amount)],
            ), actor=self.owner)

    async def test_pos_credit_customer_status_unlimited_and_customer_required(self):
        async with AsyncSession(self.engine) as session:
            with self.assertRaisesRegex(HTTPException, "customer is required"):
                await SalesService(SalesRepository(session)).create_sale(SaleCreate(
                    company_id=COMPANY, branch_id=BRANCH, payment_method="credit",
                    items=[SaleItemCreate(product_id=PRODUCT, quantity="1", unit_price="60.00", line_total="60.00")],
                ), actor=self.owner)

        inactive = await self.create_customer(code="INACTIVE", active=False)
        with self.assertRaisesRegex(HTTPException, "not found or inactive"):
            await self.credit_sale(inactive["id"])

        unlimited = await self.create_customer(code="UNLIMITED", unlimited=True, limit=None)
        sale = await self.credit_sale(unlimited["id"], "1000.00")
        self.assertEqual(sale.customer_id, unlimited["id"])
        async with AsyncSession(self.engine) as session:
            receivable = (await session.execute(
                select(CreditReceivable).where(CreditReceivable.sale_id == sale.id)
            )).scalar_one()
            self.assertEqual(receivable.original_amount, Decimal("1000.00"))
            self.assertEqual(receivable.outstanding_balance, Decimal("1000.00"))
            self.assertEqual(receivable.due_date, datetime.now(ZoneInfo("Africa/Harare")).date() + timedelta(days=30))

    async def test_pos_credit_duplicate_retry_deducts_inventory_once(self):
        customer = await self.create_customer(code="IDEMPOTENT", unlimited=True, limit=None)
        client_sale_id = uuid4()
        first = await self.credit_sale(customer["id"], "60.00", client_sale_id)
        second = await self.credit_sale(customer["id"], "60.00", client_sale_id)
        self.assertEqual(first.id, second.id)

        async with AsyncSession(self.engine) as session:
            receivable_count = (await session.execute(text(
                "SELECT count(*) FROM credit_receivables WHERE sale_id=:sale_id"
            ), {"sale_id": first.id})).scalar_one()
            movement_count = (await session.execute(text(
                "SELECT count(*) FROM inventory_movements WHERE reference=:reference"
            ), {"reference": first.receipt_number})).scalar_one()
            branch_quantity = (await session.execute(text(
                "SELECT quantity FROM inventory_balances WHERE company_id=:company AND branch_id=:branch AND product_id=:product"
            ), {"company": COMPANY, "branch": BRANCH, "product": PRODUCT})).scalar_one()
            self.assertEqual(receivable_count, 1)
            self.assertEqual(movement_count, 1)
            self.assertEqual(branch_quantity, Decimal("19.000"))

    async def test_cash_card_mobile_sales_remain_non_credit(self):
        sale_ids = []
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = SalesService(SalesRepository(session))
            for method in ("cash", "card", "mobile"):
                sale = await service.create_sale(SaleCreate(
                    company_id=COMPANY,
                    branch_id=BRANCH,
                    payment_method=method,
                    amount_received="60.00" if method == "cash" else None,
                    client_sale_id=uuid4(),
                    items=[SaleItemCreate(product_id=PRODUCT, quantity="1", unit_price="60.00", line_total="60.00")],
                ), actor=self.owner)
                self.assertEqual(sale.payment_method, method)
                self.assertIsNone(sale.customer_id)
                sale_ids.append(sale.id)

        async with AsyncSession(self.engine) as session:
            receivable_count = (await session.execute(text(
                "SELECT count(*) FROM credit_receivables WHERE sale_id = ANY(:sale_ids)"
            ), {"sale_ids": sale_ids})).scalar_one()
            self.assertEqual(receivable_count, 0)

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
            self.assertEqual([row["transaction_type"] for row in history], ["settlement", "settlement", "credit_sale"])

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

    async def test_dashboard_financial_summary_keeps_sales_settlements_and_expenses_separate(self):
        async with self.engine.begin() as connection:
            await connection.execute(
                text("UPDATE products SET cost_price=1, selling_price=2 WHERE id=:id"),
                {"id": PRODUCT},
            )
        customer = await self.create_customer(code="DASH", limit="10.00")
        sale = await self.credit_sale(customer["id"], "2.00")
        async with AsyncSession(self.engine) as session:
            receivable_id = (await session.execute(
                select(CreditReceivable.id).where(CreditReceivable.sale_id == sale.id)
            )).scalar_one()
            credit = CreditService(CreditRepository(session))
            for suffix in ("one", "two"):
                await credit.create_settlement(SettlementCreate(
                    company_id=COMPANY, receivable_id=receivable_id,
                    branch_id=BRANCH, amount="1.00", payment_method="cash",
                    idempotency_key=f"dashboard-settlement-{suffix}",
                ), self.owner)
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            expenses = ExpenseService(ExpenseRepository(session))
            category = await expenses.create_category(
                ExpenseCategoryCreate(company_id=COMPANY, name="Dashboard expense"),
                self.owner,
            )
        async with AsyncSession(self.engine) as session:
            await ExpenseService(ExpenseRepository(session)).create_expense(
                ExpenseCreate(
                    company_id=COMPANY, category_id=category.id, branch_id=BRANCH,
                    amount="0.50", occurred_at=datetime.now(timezone.utc),
                    payment_method="cash", description="Dashboard test",
                    idempotency_key="dashboard-expense-001",
                ),
                self.owner,
            )
        async with AsyncSession(self.engine) as session:
            today = datetime.now(timezone.utc).date()
            summary = await ReportsService(ReportsRepository(session)).financial_summary(
                COMPANY, date_from=today, date_to=today, shop_id=SHOP,
            )
            expected = {
                "gross_sales": "2.00", "net_sales": "2.00",
                "cost_of_sales": "1.00", "gross_profit": "1.00",
                "operating_expenses": "0.50", "net_profit": "0.50",
                "credit_sales": "2.00", "credit_settlements": "2.00",
                "cash_settlements": "2.00", "outstanding_receivables": "0.00",
                "expected_cash_movement": "1.50",
            }
            for key, value in expected.items():
                with self.subTest(metric=key):
                    self.assertEqual(summary[key], Decimal(value))
            self.assertEqual(summary["cash_sales"], Decimal("0.00"))
            self.assertEqual(summary["card_sales"], Decimal("0.00"))
            self.assertEqual(summary["mobile_sales"], Decimal("0.00"))

    async def test_financial_history_resolves_actor_names_with_scoped_fallbacks(self):
        customer = await self.create_customer(code="ACTOR", limit="100.00")
        sale = await self.credit_sale(customer["id"], "20.00")
        async with AsyncSession(self.engine) as session:
            receivable_id = (await session.execute(
                select(CreditReceivable.id).where(CreditReceivable.sale_id == sale.id)
            )).scalar_one()
            settlement = await CreditService(CreditRepository(session)).create_settlement(
                SettlementCreate(
                    company_id=COMPANY, receivable_id=receivable_id,
                    branch_id=BRANCH, amount="5.00", payment_method="cash",
                    idempotency_key="actor-settlement-001",
                ),
                self.employee,
            )
            self.assertEqual(settlement["actor_id"], EMPLOYEE)
            self.assertEqual(settlement["actor_name"], "Cashier")
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            expenses = ExpenseService(ExpenseRepository(session))
            category = await expenses.create_category(
                ExpenseCategoryCreate(company_id=COMPANY, name="Actor history"), self.owner
            )
        async with AsyncSession(self.engine) as session:
            expenses = ExpenseService(ExpenseRepository(session))
            employee_expense = await expenses.create_expense(ExpenseCreate(
                company_id=COMPANY, category_id=category.id, branch_id=BRANCH,
                amount="1.00", occurred_at=datetime.now(timezone.utc),
                payment_method="cash", description="Employee expense",
                idempotency_key="actor-expense-employee-001",
            ), self.employee)
            owner_expense = await expenses.create_expense(ExpenseCreate(
                company_id=COMPANY, category_id=category.id, branch_id=BRANCH,
                amount="1.00", occurred_at=datetime.now(timezone.utc),
                payment_method="card", description="Owner expense",
                idempotency_key="actor-expense-owner-001",
            ), self.owner)
            self.assertEqual(employee_expense.actor_name, "Cashier")
            self.assertEqual(owner_expense.actor_name, "owner@example.test")
        async with AsyncSession(self.engine) as session:
            settlement_rows = await CreditService(CreditRepository(session)).list_settlements(
                COMPANY, self.owner, customer_id=customer["id"], limit=100, offset=0,
            )
            expense_rows = await ExpenseService(ExpenseRepository(session)).list_expenses(
                COMPANY, self.owner, branch_id=BRANCH, limit=100, offset=0,
            )
            history = await CustomerService(CustomerRepository(session)).history(COMPANY, customer["id"])
            self.assertEqual(settlement_rows[0]["actor_name"], "Cashier")
            self.assertEqual(
                {row["description"]: row["actor_name"] for row in expense_rows},
                {"Employee expense": "Cashier", "Owner expense": "owner@example.test"},
            )
            settlement_history = next(row for row in history if row["transaction_type"] == "settlement")
            self.assertEqual(settlement_history["actor_name"], "Cashier")

        async with self.engine.begin() as connection:
            await connection.execute(text(
                "UPDATE employees SET active=false WHERE id=:employee"
            ), {"employee": EMPLOYEE})
        async with AsyncSession(self.engine) as session:
            settlement_rows = await CreditService(CreditRepository(session)).list_settlements(
                COMPANY, self.owner, customer_id=customer["id"], limit=100, offset=0,
            )
            expense_rows = await ExpenseService(ExpenseRepository(session)).list_expenses(
                COMPANY, self.owner, employee_id=EMPLOYEE, limit=100, offset=0,
            )
            self.assertEqual(settlement_rows[0]["actor_name"], str(EMPLOYEE))
            self.assertEqual(expense_rows[0]["actor_name"], str(EMPLOYEE))

        async with self.engine.begin() as connection:
            await connection.execute(text(
                "UPDATE employees SET active=true, company_id=:other WHERE id=:employee"
            ), {"employee": EMPLOYEE, "other": OTHER_COMPANY})
        async with AsyncSession(self.engine) as session:
            settlement_rows = await CreditService(CreditRepository(session)).list_settlements(
                COMPANY, self.owner, customer_id=customer["id"], limit=100, offset=0,
            )
            self.assertEqual(settlement_rows[0]["actor_name"], str(EMPLOYEE))

    async def test_expense_category_lifecycle_and_history_filters(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            expenses = ExpenseService(ExpenseRepository(session))
            used = await expenses.create_category(
                ExpenseCategoryCreate(company_id=COMPANY, name="Operations"), self.owner
            )
            unused = await expenses.create_category(
                ExpenseCategoryCreate(company_id=COMPANY, name="Temporary"), self.owner
            )
            updated = await expenses.update_category(
                COMPANY,
                used.id,
                ExpenseCategoryUpdate(name="Operating costs", description="Daily operations", active=False),
                self.owner,
            )
            self.assertFalse(updated.active)
            updated = await expenses.update_category(
                COMPANY, used.id, ExpenseCategoryUpdate(active=True), self.owner
            )
            self.assertTrue(updated.active)

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            expenses = ExpenseService(ExpenseRepository(session))
            posted = await expenses.create_expense(
                ExpenseCreate(
                    company_id=COMPANY,
                    category_id=used.id,
                    branch_id=BRANCH,
                    amount="12.50",
                    occurred_at=datetime.now(timezone.utc),
                    payment_method="card",
                    reference="POWER-REF-001",
                    description="Power account",
                    idempotency_key="expense-category-filter-001",
                ),
                self.owner,
            )
            rows = await expenses.list_expenses(
                COMPANY,
                self.owner,
                actor_user_id=USER,
                search="power-ref",
                limit=100,
                offset=0,
            )
            self.assertEqual([row["id"] for row in rows], [posted.id])
            with self.assertRaisesRegex(HTTPException, "cannot be deleted"):
                await expenses.delete_category(COMPANY, used.id, self.owner)
            await expenses.delete_category(COMPANY, unused.id, self.owner)
            categories = await expenses.list_categories(COMPANY, self.owner)
            self.assertEqual([category.id for category in categories], [used.id])
            with self.assertRaises(HTTPException) as isolated:
                await expenses.update_category(
                    OTHER_COMPANY, used.id, ExpenseCategoryUpdate(active=False), self.owner
                )
            self.assertEqual(isolated.exception.status_code, 403)

    async def test_financial_lists_are_filtered_paginated_and_company_scoped(self):
        created = []
        for index in range(5):
            enabled_customer = index % 2 == 0
            created.append(await self.create_customer(code=f"PAGE-{index}", enabled=enabled_customer, limit="100.00" if enabled_customer else None))
        async with AsyncSession(self.engine) as session:
            customers = CustomerService(CustomerRepository(session))
            first, first_total = await customers.list(COMPANY, limit=2, offset=0, with_total=True)
            middle, middle_total = await customers.list(COMPANY, limit=2, offset=2, with_total=True)
            last, last_total = await customers.list(COMPANY, limit=2, offset=4, with_total=True)
            matched, matched_total = await customers.list(COMPANY, search="PAGE-3", limit=25, offset=0, with_total=True)
            enabled, enabled_total = await customers.list(COMPANY, credit_enabled=True, limit=25, offset=0, with_total=True)
            empty, empty_total = await customers.list(COMPANY, search="DOES-NOT-EXIST", limit=25, offset=0, with_total=True)
            self.assertEqual((len(first), len(middle), len(last)), (2, 2, 1))
            self.assertEqual((first_total, middle_total, last_total), (5, 5, 5))
            self.assertEqual(([row["customer_code"] for row in matched], matched_total), (["PAGE-3"], 1))
            self.assertEqual(enabled_total, 3)
            self.assertTrue(all(row["credit_enabled"] for row in enabled))
            self.assertEqual((empty, empty_total), ([], 0))

        sale = await self.credit_sale(created[0]["id"], "20.00")
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            receivable = (await session.execute(select(CreditReceivable).where(CreditReceivable.sale_id == sale.id))).scalar_one()
            settlement = await CreditService(CreditRepository(session)).create_settlement(
                SettlementCreate(company_id=COMPANY, receivable_id=receivable.id, branch_id=BRANCH, amount="5.00", payment_method="card", reference="PAGE-SETTLE", idempotency_key="pagination-settlement"),
                self.owner,
            )
        async with AsyncSession(self.engine) as session:
            credit = CreditService(CreditRepository(session))
            partial, partial_total = await credit.list_receivables(COMPANY, self.owner, customer_id=created[0]["id"], status="partially_paid", search=sale.receipt_number, limit=25, offset=0, with_total=True)
            payments, payment_total = await credit.list_settlements(COMPANY, self.owner, customer_id=created[0]["id"], payment_method="card", search="PAGE-SETTLE", limit=25, offset=0, with_total=True)
            self.assertEqual(([row["id"] for row in partial], partial_total), ([receivable.id], 1))
            self.assertEqual(([row["id"] for row in payments], payment_total), ([settlement["id"]], 1))
            history, history_total = await CustomerService(CustomerRepository(session)).history(COMPANY, created[0]["id"], transaction_type="settlement", start_at=datetime.now(timezone.utc) - timedelta(days=1), end_at=datetime.now(timezone.utc) + timedelta(days=1), limit=25, offset=0, with_total=True)
            self.assertEqual((len(history), history_total), (1, 1))

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            expenses = ExpenseService(ExpenseRepository(session))
            category = await expenses.create_category(ExpenseCategoryCreate(company_id=COMPANY, name="Pagination"), self.owner)
            for index, method in enumerate(("cash", "card", "mobile", "cash", "card")):
                await ExpenseService(ExpenseRepository(session)).create_expense(ExpenseCreate(
                    company_id=COMPANY, category_id=category.id, branch_id=BRANCH,
                    amount="1.00", occurred_at=datetime.now(timezone.utc), payment_method=method,
                    reference=f"PAGE-EXP-{index}", description=f"Paged expense {index}",
                    idempotency_key=f"pagination-expense-{index}",
                ), self.owner)
        async with AsyncSession(self.engine) as session:
            expenses = ExpenseService(ExpenseRepository(session))
            expense_first, expense_total, expense_summary = await expenses.list_expenses(COMPANY, self.owner, category_id=category.id, branch_id=BRANCH, limit=2, offset=0, with_total=True)
            expense_last, last_expense_total, _ = await expenses.list_expenses(COMPANY, self.owner, category_id=category.id, limit=2, offset=4, with_total=True)
            filtered, filtered_total, filtered_summary = await expenses.list_expenses(COMPANY, self.owner, category_id=category.id, payment_method="mobile", actor_id=USER, search="PAGE-EXP-2", start_at=datetime.now(timezone.utc)-timedelta(days=1), end_at=datetime.now(timezone.utc)+timedelta(days=1), limit=25, offset=0, with_total=True)
            self.assertEqual((len(expense_first), len(expense_last), expense_total, last_expense_total), (2, 1, 5, 5))
            self.assertEqual(([row["reference"] for row in filtered], filtered_total), (["PAGE-EXP-2"], 1))
            self.assertEqual(expense_summary["total"], Decimal("5.00"))
            self.assertEqual(filtered_summary["mobile"], Decimal("1.00"))


if __name__ == "__main__":
    unittest.main()
