import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.auth.dependencies import AuthActor
from app.business_settings.schema import CompanySettingsUpdate
from app.business_settings.service import BusinessSettingsService
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
from app.credit.service import CreditService
from app.currencies.repository import CurrencyRepository
from app.currencies.schema import CurrencyCreate, CurrencyUpdate, ExchangeRateCreate
from app.currencies.service import CurrencyService, quantize_currency
from app.expenses.repository import ExpenseRepository
from app.expenses.schema import ExpenseCreate
from app.expenses.service import ExpenseService
from app.financial_context import resolve_shift_for_write
from app.models import CashierShift, CashierShiftCashMovement, CashierShiftCurrencySnapshot, CreditReceivable, CurrencyExchangeRate, Expense, InventoryBalance, Sale
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate, SaleItemCreate
from app.sales.service import SalesService
from app.shifts.repository import ShiftRepository
from app.shifts.schema import CashMovementCreate, ShiftClose, ShiftClosingCount, ShiftOpen, ShiftOpeningBalance
from app.shifts.service import ShiftService


TEST_DATABASE_ENV = "APEX_PHASE5_TEST_DATABASE_URL"
COMPANY = UUID("81000000-0000-0000-0000-000000000001")
OTHER_COMPANY = UUID("81000000-0000-0000-0000-000000000002")
SHOP = UUID("82000000-0000-0000-0000-000000000001")
OTHER_SHOP = UUID("82000000-0000-0000-0000-000000000002")
BRANCH = UUID("83000000-0000-0000-0000-000000000001")
OTHER_BRANCH = UUID("83000000-0000-0000-0000-000000000002")
EMPLOYEE = UUID("84000000-0000-0000-0000-000000000001")
OTHER_EMPLOYEE = UUID("84000000-0000-0000-0000-000000000002")
DEVICE = UUID("85000000-0000-0000-0000-000000000001")
OTHER_DEVICE = UUID("85000000-0000-0000-0000-000000000002")
POS_SESSION = UUID("86000000-0000-0000-0000-000000000001")
OTHER_POS_SESSION = UUID("86000000-0000-0000-0000-000000000002")
USER = UUID("87000000-0000-0000-0000-000000000001")
PRODUCT = UUID("88000000-0000-0000-0000-000000000001")
CATEGORY = UUID("89000000-0000-0000-0000-000000000001")
CUSTOMER = UUID("8a000000-0000-0000-0000-000000000001")
EXPENSE_CATEGORY = UUID("8b000000-0000-0000-0000-000000000001")


class DecimalConversionTest(unittest.TestCase):
    def test_decimal_conversion_is_exact_and_precision_aware(self):
        self.assertEqual(quantize_currency(Decimal("10") * Decimal("18.50"), 2), Decimal("185.00"))
        self.assertEqual(quantize_currency(Decimal("185.00") / Decimal("18.50"), 2), Decimal("10.00"))
        self.assertEqual(quantize_currency(Decimal("1.23456"), 4), Decimal("1.2346"))


class Phase5PostgresTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database_url = os.getenv(TEST_DATABASE_ENV)
        if not database_url:
            self.skipTest(f"{TEST_DATABASE_ENV} is not configured")
        parsed = make_url(database_url)
        if not (parsed.database or "").startswith("apexretail_phase5_test_"):
            self.fail("refusing non-Phase-5 test database")
        self.engine = create_async_engine(database_url)
        async with self.engine.begin() as connection:
            await connection.execute(text("""
                TRUNCATE audit_events, cashier_shift_cash_movements, cashier_shift_currency_snapshots, cashier_shifts,
                expenses, expense_categories, credit_settlements, credit_receivables,
                inventory_movements, sale_items, sales, inventory_balances, products,
                categories, pos_sessions, employees, devices, users, company_settings,
                currency_exchange_rates, company_currencies, branches, shops, customers,
                companies CASCADE
            """))
            await self.seed(connection)
        self.addAsyncCleanup(self.engine.dispose)
        self.actor = self.make_actor(EMPLOYEE, DEVICE, POS_SESSION, COMPANY, SHOP, BRANCH)
        self.other_actor = self.make_actor(OTHER_EMPLOYEE, OTHER_DEVICE, OTHER_POS_SESSION, OTHER_COMPANY, OTHER_SHOP, OTHER_BRANCH)

    @staticmethod
    def make_actor(employee, device, session, company, shop, branch):
        return AuthActor(
            "employee", company, "cashier",
            employee=SimpleNamespace(id=employee, branch_id=branch, name="Cashier"),
            permissions={"sales": True, "credit_sales": True, "credit_settlements": True, "expenses_create": True},
            pos_session=SimpleNamespace(id=session, employee_id=employee, device_id=device, company_id=company, shop_id=shop, branch_id=branch),
        )

    @staticmethod
    async def execute_script(connection, sql, params):
        for statement in sql.split(";"):
            if statement.strip():
                await connection.execute(text(statement), params)

    async def seed(self, connection):
        await self.execute_script(connection, """
            INSERT INTO companies (id,name,owner_email,business_type,active,deleted) VALUES
            (:company,'Shift Test','shift@example.test','Retail',true,false),
            (:other,'Other Shift Test','other-shift@example.test','Retail',true,false);
            INSERT INTO shops (id,company_id,name,active,deleted) VALUES
            (:shop,:company,'Main',true,false),(:other_shop,:other,'Other',true,false);
            INSERT INTO branches (id,company_id,shop_id,name,active,deleted) VALUES
            (:branch,:company,:shop,'Main',true,false),(:other_branch,:other,:other_shop,'Other',true,false);
            INSERT INTO users (id,company_id,email,password_hash,role,active,deleted)
            VALUES (:user,:company,'phase5-owner@example.test','x','owner',true,false);
            INSERT INTO employees (id,company_id,shop_id,branch_id,name,pin,role,permissions,active,deleted) VALUES
            (:employee,:company,:shop,:branch,'Cashier','x','cashier','{}'::jsonb,true,false),
            (:other_employee,:other,:other_shop,:other_branch,'Other Cashier','x','cashier','{}'::jsonb,true,false);
            INSERT INTO devices (id,company_id,shop_id,branch_id,name,device_key,platform,app_version,status,assignment_revision,active,deleted) VALUES
            (:device,:company,:shop,:branch,'POS 1','phase5-device','web','1','active',1,true,false),
            (:other_device,:other,:other_shop,:other_branch,'POS 2','phase5-other-device','web','1','active',1,true,false);
            INSERT INTO pos_sessions (id,company_id,employee_id,device_id,shop_id,branch_id,token_hash,expires_at)
            VALUES (:session,:company,:employee,:device,:shop,:branch,'phase5-token',now()+interval '1 day'),
                   (:other_session,:other,:other_employee,:other_device,:other_shop,:other_branch,'phase5-other-token',now()+interval '1 day');
        """, dict(company=COMPANY, other=OTHER_COMPANY, shop=SHOP, other_shop=OTHER_SHOP, branch=BRANCH, other_branch=OTHER_BRANCH, user=USER, employee=EMPLOYEE, other_employee=OTHER_EMPLOYEE, device=DEVICE, other_device=OTHER_DEVICE, session=POS_SESSION, other_session=OTHER_POS_SESSION))
        await self.execute_script(connection, """
            INSERT INTO company_settings (id,company_id,currency_code,currency_symbol,decimal_places,tax_name,tax_rate,tax_inclusive,paper_size,auto_print,payment_methods,multi_currency_enabled,shift_enforcement_enabled,active,deleted)
            VALUES (:one,:company,'USD','$',2,'Tax',0,false,'80mm',false,'["cash","card","mobile","credit"]'::jsonb,true,true,true,false),
                   (:two,:other,'USD','$',2,'Tax',0,false,'80mm',false,'["cash"]'::jsonb,false,false,true,false);
            INSERT INTO categories (id,company_id,name,active,deleted) VALUES (:category,:company,'Goods',true,false);
            INSERT INTO products (id,company_id,category_id,name,sku,unit,cost_price,selling_price,stock_qty,reorder_level,active,deleted)
            VALUES (:product,:company,:category,'Item','PHASE5','each',5,10,100,1,true,false);
            INSERT INTO inventory_balances (id,company_id,shop_id,branch_id,product_id,quantity,reorder_level,active,deleted)
            VALUES (:balance,:company,:shop,:branch,:product,100,1,true,false);
            INSERT INTO customers (id,company_id,customer_code,name,active,credit_enabled,unlimited_credit,credit_limit,credit_terms_days,deleted)
            VALUES (:customer,:company,'SHIFT-CUST','Shift Customer',true,true,false,100,30,false);
            INSERT INTO expense_categories (id,company_id,name,active,deleted) VALUES (:expense_category,:company,'Operations',true,false);
        """, dict(one=uuid4(), two=uuid4(), company=COMPANY, other=OTHER_COMPANY, category=CATEGORY, product=PRODUCT, balance=uuid4(), shop=SHOP, branch=BRANCH, customer=CUSTOMER, expense_category=EXPENSE_CATEGORY))
        # Same code in different companies is explicitly supported.
        await connection.execute(text("""
            INSERT INTO company_currencies (id,company_id,code,display_name,symbol,decimal_places,active,is_base,cash_accepted,card_accepted,mobile_accepted,display_order)
            VALUES (:base,:company,'USD','US Dollar','$',2,true,true,true,true,true,0),
                   (:other_base,:other,'USD','US Dollar','$',2,true,true,true,true,true,0),
                   (:zar,:company,'ZAR','South African Rand','R',2,true,false,true,true,true,1)
        """), {"base": uuid4(), "other_base": uuid4(), "zar": uuid4(), "company": COMPANY, "other": OTHER_COMPANY})
        await connection.execute(text("""
            UPDATE company_settings cs SET base_currency_id=cc.id
            FROM company_currencies cc WHERE cc.company_id=cs.company_id AND cc.is_base=true
        """))

    async def add_rate(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            repo = CurrencyRepository(session)
            zar = await repo.by_code(COMPANY, "ZAR")
            owner = AuthActor("user", COMPANY, "owner", user=SimpleNamespace(id=USER))
            return await CurrencyService(repo).create_rate(ExchangeRateCreate(
                company_id=COMPANY, currency_id=zar.id,
                foreign_units_per_base="18.5000000000", effective_at=datetime.now(timezone.utc),
            ), owner)

    async def open_shift(self, key="open-shift-0001"):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            return await ShiftService(ShiftRepository(session)).open(ShiftOpen(
                opening_balances=[ShiftOpeningBalance(currency_code="USD", amount="20"), ShiftOpeningBalance(currency_code="ZAR", amount="500")],
                idempotency_key=key,
            ), self.actor)

    async def test_currency_uniqueness_rate_immutability_and_cross_company_code(self):
        rate = await self.add_rate()
        self.assertEqual(rate.foreign_units_per_base, Decimal("18.5000000000"))
        async with AsyncSession(self.engine) as session:
            owner = AuthActor("user", COMPANY, "owner", user=SimpleNamespace(id=USER))
            config = await CurrencyService(CurrencyRepository(session)).pos_config(COMPANY, owner)
            self.assertEqual(config["base_currency_code"], "USD")
            self.assertTrue(config["multi_currency_enabled"])
            self.assertGreaterEqual(config["version"], 2)
            self.assertEqual({row["code"] for row in config["currencies"]}, {"USD", "ZAR"})
        async with AsyncSession(self.engine) as session:
            count = (await session.execute(text("SELECT count(*) FROM company_currencies WHERE code='USD'"))).scalar_one()
            self.assertEqual(count, 2)
            with self.assertRaises(Exception):
                await session.execute(text("UPDATE currency_exchange_rates SET foreign_units_per_base=19 WHERE id=:id"), {"id": rate.id})
        async with AsyncSession(self.engine) as session:
            with self.assertRaises(Exception):
                await session.execute(text("""
                    INSERT INTO company_currencies
                    (id,company_id,code,display_name,symbol,decimal_places,active,is_base,cash_accepted,card_accepted,mobile_accepted,display_order)
                    VALUES (:id,:company,'BASE2','Other Base','B',2,true,true,true,true,true,9)
                """), {"id": uuid4(), "company": COMPANY})

    async def test_currency_admin_permissions_acceptance_and_base_protection(self):
        manager = AuthActor(
            "employee", COMPANY, "manager",
            employee=SimpleNamespace(id=EMPLOYEE, branch_id=BRANCH, name="Currency Manager"),
            permissions={"currencies_manage": True},
            pos_session=self.actor.pos_session,
        )
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = CurrencyService(CurrencyRepository(session))
            with self.assertRaisesRegex(HTTPException, "Currency administration"):
                await service.list(COMPANY, self.actor)
            eur = await service.create(CurrencyCreate(
                company_id=COMPANY, code=" eur ", display_name="Euro", symbol="€",
                cash_accepted=False, card_accepted=True, mobile_accepted=False,
                display_order=3,
            ), manager)
            self.assertEqual(eur["code"], "EUR")
            updated = await service.update(COMPANY, eur["id"], CurrencyUpdate(
                active=True, cash_accepted=True, card_accepted=False,
                mobile_accepted=True, display_order=2,
            ), manager)
            self.assertTrue(updated["cash_accepted"])
            self.assertFalse(updated["card_accepted"])
            self.assertTrue(updated["mobile_accepted"])
            configuration = await service.set_multi_currency(COMPANY, False, manager)
            self.assertFalse(configuration["multi_currency_enabled"])
            configuration = await service.set_multi_currency(COMPANY, True, manager)
            self.assertTrue(configuration["multi_currency_enabled"])
            with self.assertRaisesRegex(HTTPException, "Currency Settings"):
                await BusinessSettingsService(session).update(
                    COMPANY, CompanySettingsUpdate(currency_code="EUR")
                )
            zar = await service.repo.by_code(COMPANY, "ZAR")
            new_base = await service.set_base(COMPANY, zar.id, manager)
            self.assertTrue(new_base["is_base"])
            self.assertEqual(new_base["current_rate"], Decimal("1"))
            bases = [row for row in await service.repo.list(COMPANY) if row.is_base]
            self.assertEqual([row.code for row in bases], ["ZAR"])
            self.assertEqual((await service.repo.base(OTHER_COMPANY)).code, "USD")
            await service.update(COMPANY, zar.id, CurrencyUpdate(symbol="R$", decimal_places=2), manager)
            settings = await service.repo.settings(COMPANY)
            self.assertEqual(settings.currency_symbol, "R$")
            self.assertEqual(settings.currency_code, "ZAR")
            with self.assertRaisesRegex(HTTPException, "cannot be deactivated"):
                await service.update(COMPANY, zar.id, CurrencyUpdate(active=False), manager)
            legacy = Sale(
                id=uuid4(), company_id=COMPANY, receipt_number=f"BASE-{uuid4().hex[:8]}",
                subtotal_amount=Decimal("1"), tax_rate=Decimal("0"), tax_amount=Decimal("0"),
                tax_inclusive=False, total_amount=Decimal("1"), amount_received=Decimal("1"),
                change_due=Decimal("0"), payment_method="cash", status="completed",
            )
            session.add(legacy)
            await session.commit()
            usd = await service.repo.by_code(COMPANY, "USD", active=False)
            with self.assertRaisesRegex(HTTPException, "cannot be changed after financial activity"):
                await service.set_base(COMPANY, usd.id, manager)

    async def test_rate_validation_attribution_ordering_and_company_isolation(self):
        owner = AuthActor("user", COMPANY, "owner", user=SimpleNamespace(id=USER))
        manager = AuthActor(
            "employee", COMPANY, "manager",
            employee=SimpleNamespace(id=EMPLOYEE, branch_id=BRANCH, name="Currency Manager"),
            permissions={"currencies_manage": True},
            pos_session=self.actor.pos_session,
        )
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = CurrencyService(CurrencyRepository(session))
            zar = await service.repo.by_code(COMPANY, "ZAR")
            other_usd = await service.repo.by_code(OTHER_COMPANY, "USD")
            with self.assertRaises(Exception):
                ExchangeRateCreate(
                    company_id=COMPANY, currency_id=zar.id,
                    foreign_units_per_base="0", effective_at=datetime.now(timezone.utc),
                )
            with self.assertRaises(Exception):
                ExchangeRateCreate(
                    company_id=COMPANY, currency_id=zar.id,
                    foreign_units_per_base="-1", effective_at=datetime.now(timezone.utc),
                )
            with self.assertRaises(Exception):
                ExchangeRateCreate(
                    company_id=COMPANY, currency_id=zar.id,
                    foreign_units_per_base="1.12345678901", effective_at=datetime.now(timezone.utc),
                )
            with self.assertRaisesRegex(HTTPException, "Currency not found"):
                await service.create_rate(ExchangeRateCreate(
                    company_id=COMPANY, currency_id=other_usd.id,
                    foreign_units_per_base="2", effective_at=datetime.now(timezone.utc),
                ), owner)
            base = await service.repo.base(COMPANY)
            with self.assertRaisesRegex(HTTPException, "always has an exchange rate of 1"):
                await service.create_rate(ExchangeRateCreate(
                    company_id=COMPANY, currency_id=base.id,
                    foreign_units_per_base="1", effective_at=datetime.now(timezone.utc),
                ), owner)
            older = datetime.now(timezone.utc) - timedelta(hours=2)
            newer = datetime.now(timezone.utc) - timedelta(hours=1)
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            first = await service.create_rate(ExchangeRateCreate(
                company_id=COMPANY, currency_id=zar.id,
                foreign_units_per_base="18.5000000000", effective_at=older,
            ), owner)
            second = await service.create_rate(ExchangeRateCreate(
                company_id=COMPANY, currency_id=zar.id,
                foreign_units_per_base="19.2500000000", effective_at=newer,
            ), owner)
            scheduled = await service.create_rate(ExchangeRateCreate(
                company_id=COMPANY, currency_id=zar.id,
                foreign_units_per_base="20.0000000000", effective_at=future,
            ), owner)
            manager_scheduled = await service.create_rate(ExchangeRateCreate(
                company_id=COMPANY, currency_id=zar.id,
                foreign_units_per_base="21.0000000000", effective_at=future + timedelta(hours=1),
            ), manager)
            self.assertEqual(first.actor_name, "phase5-owner@example.test")
            self.assertEqual(second.actor_id, USER)
            page_one, total = await service.rates(COMPANY, owner, limit=1, offset=0)
            page_two, _ = await service.rates(COMPANY, owner, limit=1, offset=1)
            self.assertEqual(total, 4)
            self.assertEqual(page_one[0]["id"], manager_scheduled.id)
            self.assertEqual(page_one[0]["actor_name"], "Cashier")
            self.assertEqual(page_two[0]["id"], scheduled.id)
            current = next(row for row in await service.list(COMPANY, owner) if row["code"] == "ZAR")
            self.assertEqual(current["current_rate"], Decimal("19.2500000000"))
            self.assertEqual(current["previous_rate"], Decimal("18.5000000000"))
            with self.assertRaisesRegex(HTTPException, "exchange-rate history"):
                await service.set_base(COMPANY, zar.id, owner)

    async def test_concurrent_open_shift_is_prevented_and_identity_isolated(self):
        async def attempt(key):
            async with AsyncSession(self.engine, expire_on_commit=False) as session:
                try:
                    return await ShiftService(ShiftRepository(session)).open(ShiftOpen(idempotency_key=key), self.actor)
                except HTTPException as exc:
                    return exc.status_code
        results = await asyncio.gather(attempt("parallel-open-a"), attempt("parallel-open-b"))
        self.assertEqual(sum(isinstance(value, dict) for value in results), 1)
        self.assertIn(409, results)
        shift = next(value for value in results if isinstance(value, dict))
        async with AsyncSession(self.engine) as session:
            with self.assertRaisesRegex(HTTPException, "active shift"):
                await resolve_shift_for_write(session, self.other_actor, OTHER_COMPANY, OTHER_BRANCH, shift["id"])
            jwt_fallback = AuthActor(
                "employee", COMPANY, "cashier",
                employee=SimpleNamespace(id=EMPLOYEE, branch_id=BRANCH),
                permissions={"sales": True},
            )
            with self.assertRaisesRegex(HTTPException, "opaque POS session"):
                await resolve_shift_for_write(session, jwt_fallback, COMPANY, BRANCH, shift["id"])
            wrong_identity = self.make_actor(
                OTHER_EMPLOYEE, OTHER_DEVICE, OTHER_POS_SESSION,
                COMPANY, SHOP, BRANCH,
            )
            with self.assertRaisesRegex(HTTPException, "active shift"):
                await resolve_shift_for_write(session, wrong_identity, COMPANY, BRANCH, shift["id"])
            wrong_branch_session = self.make_actor(
                EMPLOYEE, DEVICE, POS_SESSION, COMPANY, SHOP, OTHER_BRANCH,
            )
            with self.assertRaisesRegex(HTTPException, "branch mismatch"):
                await resolve_shift_for_write(session, wrong_branch_session, COMPANY, BRANCH, shift["id"])
            wrong_cashier_session = self.make_actor(
                EMPLOYEE, DEVICE, POS_SESSION, COMPANY, SHOP, BRANCH,
            )
            wrong_cashier_session.pos_session.employee_id = OTHER_EMPLOYEE
            with self.assertRaisesRegex(HTTPException, "cashier mismatch"):
                await resolve_shift_for_write(session, wrong_cashier_session, COMPANY, BRANCH, shift["id"])
        async with AsyncSession(self.engine) as session:
            wrong_identity = self.make_actor(
                OTHER_EMPLOYEE, OTHER_DEVICE, OTHER_POS_SESSION,
                COMPANY, SHOP, BRANCH,
            )
            open_key = (await session.execute(
                select(CashierShift.open_idempotency_key).where(CashierShift.id == shift["id"])
            )).scalar_one()
            with self.assertRaisesRegex(HTTPException, "idempotency key"):
                await ShiftService(ShiftRepository(session)).open(
                    ShiftOpen(idempotency_key=open_key), wrong_identity,
                )

    async def test_foreign_transactions_rate_snapshots_expected_cash_and_closed_immutability(self):
        rate = await self.add_rate()
        shift = await self.open_shift()
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            sale = await SalesService(SalesRepository(session)).create_sale(SaleCreate(
                company_id=COMPANY, branch_id=BRANCH, payment_method="cash",
                payment_currency_code="ZAR", tendered_amount_original="200.00",
                items=[SaleItemCreate(product_id=PRODUCT, quantity="1", unit_price="10", line_total="10")],
            ), actor=self.actor)
            self.assertEqual(sale.shift_id, shift["id"])
            self.assertEqual(sale.device_id, DEVICE)
            self.assertEqual(sale.total_amount, Decimal("10.00"))
            self.assertEqual(sale.payment_amount_original, Decimal("185.0000"))
            self.assertEqual(sale.change_amount_original, Decimal("15.0000"))
            self.assertEqual(sale.exchange_rate_snapshot, Decimal("18.5000000000"))
            for method in ("card", "mobile"):
                converted = await SalesService(SalesRepository(session)).create_sale(SaleCreate(
                    company_id=COMPANY, branch_id=BRANCH, payment_method=method,
                    payment_currency_code="ZAR",
                    items=[SaleItemCreate(product_id=PRODUCT, quantity="1", unit_price="10", line_total="10")],
                ), actor=self.actor)
                self.assertEqual(converted.shift_id, shift["id"])
                self.assertEqual(converted.total_amount, Decimal("10.00"))
                self.assertEqual(converted.payment_amount_original, Decimal("185.0000"))
                self.assertEqual(converted.payment_currency_code, "ZAR")
            credit_sale = await SalesService(SalesRepository(session)).create_sale(SaleCreate(
                company_id=COMPANY, branch_id=BRANCH, customer_id=CUSTOMER,
                payment_method="credit", items=[SaleItemCreate(product_id=PRODUCT, quantity="1", unit_price="10", line_total="10")],
            ), actor=self.actor)
            self.assertEqual(credit_sale.shift_id, shift["id"])
            receivable = (await session.execute(select(CreditReceivable).where(CreditReceivable.sale_id == credit_sale.id))).scalar_one()
            settlement = await CreditService(CreditRepository(session)).create_settlement(SettlementCreate(
                company_id=COMPANY, receivable_id=receivable.id, branch_id=BRANCH,
                original_amount="92.50", tendered_amount_original="100.00",
                payment_currency_code="ZAR", payment_method="cash", idempotency_key="phase5-settle-001",
            ), self.actor)
            self.assertEqual(settlement["amount"], Decimal("5.00"))
            self.assertEqual(settlement["original_amount"], Decimal("92.5000"))
            self.assertEqual(settlement["shift_id"], shift["id"])
            self.assertEqual(settlement["device_id"], DEVICE)
            self.assertEqual(settlement["cashier_employee_id"], EMPLOYEE)
            self.assertEqual(settlement["tendered_amount_original"], Decimal("100.0000"))
            self.assertEqual(settlement["change_amount_original"], Decimal("7.5000"))
            for method, currency_code, original in (("card", "USD", "1.00"), ("mobile", "ZAR", "18.50")):
                other_settlement = await CreditService(CreditRepository(session)).create_settlement(SettlementCreate(
                    company_id=COMPANY, receivable_id=receivable.id, branch_id=BRANCH,
                    original_amount=original, payment_currency_code=currency_code,
                    payment_method=method, idempotency_key=f"phase5-settle-{method}-001",
                ), self.actor)
                self.assertEqual(other_settlement["shift_id"], shift["id"])
                self.assertEqual(other_settlement["amount"], Decimal("1.00"))
                self.assertEqual(other_settlement["change_amount_original"], Decimal("0.00"))
            with self.assertRaisesRegex(HTTPException, "exceeds"):
                await CreditService(CreditRepository(session)).create_settlement(SettlementCreate(
                    company_id=COMPANY, receivable_id=receivable.id, branch_id=BRANCH, shift_id=shift["id"],
                    original_amount="100.00", payment_currency_code="ZAR", payment_method="cash", idempotency_key="phase5-overpay-001",
                ), self.actor)
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            expense = await ExpenseService(ExpenseRepository(session)).create_expense(ExpenseCreate(
                company_id=COMPANY, category_id=EXPENSE_CATEGORY, branch_id=BRANCH,
                original_amount="37.00", currency_code="ZAR", occurred_at=datetime.now(timezone.utc),
                payment_method="cash", description="Foreign cash expense", idempotency_key="phase5-expense-001",
            ), self.actor)
            self.assertEqual(expense.amount, Decimal("2.00"))
            self.assertEqual(expense.original_amount, Decimal("37.0000"))
            self.assertEqual(expense.shift_id, shift["id"])
            self.assertEqual(expense.device_id, DEVICE)
            self.assertEqual(expense.employee_id, EMPLOYEE)
            for method in ("card", "mobile"):
                noncash_expense = await ExpenseService(ExpenseRepository(session)).create_expense(ExpenseCreate(
                    company_id=COMPANY, category_id=EXPENSE_CATEGORY, branch_id=BRANCH,
                    original_amount="18.50", currency_code="ZAR", occurred_at=datetime.now(timezone.utc),
                    payment_method=method, description=f"{method} foreign expense", idempotency_key=f"phase5-expense-{method}-001",
                ), self.actor)
                self.assertEqual(noncash_expense.amount, Decimal("1.00"))
                self.assertEqual(noncash_expense.shift_id, shift["id"])
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            closed = await ShiftService(ShiftRepository(session)).close(shift["id"], ShiftClose(
                counted_balances=[ShiftClosingCount(currency_code="USD", amount="20"), ShiftClosingCount(currency_code="ZAR", amount="740.50")],
                idempotency_key="phase5-close-001", confirmed=True,
            ), self.actor)
            zar = next(row for row in closed["currencies"] if row["currency_code"] == "ZAR")
            self.assertEqual(zar["expected_cash"], Decimal("740.5000"))
            self.assertEqual(zar["variance"], Decimal("0.0000"))
            self.assertEqual(closed["summary"]["cash_sales_base"], Decimal("10.00"))
            self.assertEqual(closed["summary"]["card_sales_base"], Decimal("10.00"))
            self.assertEqual(closed["summary"]["mobile_sales_base"], Decimal("10.00"))
            self.assertEqual(closed["summary"]["credit_sales_base"], Decimal("10.00"))
            self.assertEqual(closed["summary"]["cash_expenses_base"], Decimal("2.00"))
            self.assertEqual(closed["summary"]["noncash_expenses_base"], Decimal("2.00"))
            with self.assertRaises(Exception):
                await session.execute(text("UPDATE cashier_shifts SET closing_note='changed' WHERE id=:id"), {"id": shift["id"]})
        async with AsyncSession(self.engine) as session:
            with self.assertRaisesRegex(HTTPException, "active shift"):
                await resolve_shift_for_write(session, self.actor, COMPANY, BRANCH, shift["id"])
            stored_rate = (await session.execute(select(CurrencyExchangeRate).where(CurrencyExchangeRate.id == rate.id))).scalar_one()
            self.assertEqual(stored_rate.foreign_units_per_base, Decimal("18.5000000000"))

    async def test_historical_rows_remain_nullable_and_valid(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            cutoff = datetime.now(timezone.utc).replace(microsecond=0)
            await session.execute(text(
                "UPDATE company_settings SET shift_required_from=:cutoff WHERE company_id=:company"
            ), {"cutoff": cutoff, "company": COMPANY})
            self.assertIsNone(await resolve_shift_for_write(
                session, None, COMPANY, BRANCH, occurred_at=cutoff.replace(year=cutoff.year - 1),
            ))
            jwt_fallback = AuthActor(
                "employee", COMPANY, "cashier",
                employee=SimpleNamespace(id=EMPLOYEE, branch_id=BRANCH),
                permissions={"sales": True},
            )
            with self.assertRaisesRegex(HTTPException, "opaque POS session"):
                await resolve_shift_for_write(
                    session, jwt_fallback, COMPANY, BRANCH, occurred_at=cutoff,
                )
            legacy = Sale(
                id=uuid4(), company_id=COMPANY, receipt_number=f"LEG-{uuid4().hex[:8]}",
                subtotal_amount=Decimal("1"), tax_rate=Decimal("0"), tax_amount=Decimal("0"),
                tax_inclusive=False, total_amount=Decimal("1"), amount_received=Decimal("1"),
                change_due=Decimal("0"), payment_method="cash", status="completed",
            )
            session.add(legacy)
            await session.commit()
            self.assertIsNone(legacy.shift_id)
            self.assertIsNone(legacy.exchange_rate_snapshot)
            self.assertIsNone(legacy.payment_currency_code)

    async def test_offline_sales_remain_unassigned_while_online_sales_auto_attach(self):
        shift = await self.open_shift()
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            offline_payload = SaleCreate(
                company_id=COMPANY, branch_id=BRANCH, client_sale_id=uuid4(),
                client_created_at=datetime.now(timezone.utc), payment_method="cash",
                amount_received="10", items=[SaleItemCreate(product_id=PRODUCT, quantity="1", unit_price="10", line_total="10")],
            )
            offline_sale = await SalesService(SalesRepository(session)).create_sale(offline_payload, actor=self.actor)
            self.assertIsNone(offline_sale.shift_id)
            offline_balance = (await session.execute(select(InventoryBalance).where(
                InventoryBalance.company_id == COMPANY, InventoryBalance.product_id == PRODUCT,
                InventoryBalance.branch_id == BRANCH,
            ))).scalar_one()
            after_first_sync = Decimal(offline_balance.quantity)
            replay = await SalesService(SalesRepository(session)).create_sale(offline_payload, actor=self.actor)
            self.assertEqual(replay.id, offline_sale.id)
            self.assertEqual(Decimal(offline_balance.quantity), after_first_sync)

        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            online_sale = await SalesService(SalesRepository(session)).create_sale(SaleCreate(
                company_id=COMPANY, branch_id=BRANCH, payment_method="card",
                items=[SaleItemCreate(product_id=PRODUCT, quantity="1", unit_price="10", line_total="10")],
            ), actor=self.actor)
            self.assertEqual(online_sale.shift_id, shift["id"])
            self.assertEqual(online_sale.base_currency_code, "USD")
            self.assertEqual(online_sale.exchange_rate_snapshot, Decimal("1"))

    async def test_online_sale_without_an_open_shift_remains_allowed(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            sale = await SalesService(SalesRepository(session)).create_sale(SaleCreate(
                company_id=COMPANY, branch_id=BRANCH, payment_method="card",
                items=[SaleItemCreate(product_id=PRODUCT, quantity="1", unit_price="10", line_total="10")],
            ), actor=self.actor)
            self.assertIsNone(sale.shift_id)
            self.assertEqual(sale.base_currency_code, "USD")
            self.assertEqual(sale.exchange_rate_snapshot, Decimal("1"))

    async def test_online_sale_rejects_client_device_that_differs_from_active_shift(self):
        await self.open_shift()
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            with self.assertRaisesRegex(HTTPException, "does not match"):
                await SalesService(SalesRepository(session)).create_sale(SaleCreate(
                    company_id=COMPANY, branch_id=BRANCH, device_id=OTHER_DEVICE,
                    payment_method="cash", amount_received="10",
                    items=[SaleItemCreate(product_id=PRODUCT, quantity="1", unit_price="10", line_total="10")],
                ), actor=self.actor)

    async def test_shift_report_filters_tenant_names_and_currency_variance(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = ShiftService(ShiftRepository(session))
            opened = await service.open(ShiftOpen(
                opening_balances=[
                    ShiftOpeningBalance(currency_code="USD", amount="20"),
                    ShiftOpeningBalance(currency_code="ZAR", amount="500"),
                ],
                idempotency_key="report-open-company-1",
            ), self.actor)
            closed = await service.close(opened["id"], ShiftClose(
                counted_balances=[
                    ShiftClosingCount(currency_code="USD", amount="19"),
                    ShiftClosingCount(currency_code="ZAR", amount="505"),
                ],
                idempotency_key="report-close-company-1",
                confirmed=True,
            ), self.actor)
            self.assertEqual(closed["cashier_name"], "Cashier")
            self.assertEqual(closed["branch_name"], "Main")
            self.assertEqual(closed["register_name"], "POS 1")

            other_open = await service.open(ShiftOpen(
                opening_balances=[ShiftOpeningBalance(currency_code="USD", amount="7")],
                idempotency_key="report-open-company-2",
            ), self.other_actor)
            await service.close(other_open["id"], ShiftClose(
                counted_balances=[ShiftClosingCount(currency_code="USD", amount="9")],
                idempotency_key="report-close-company-2",
                confirmed=True,
            ), self.other_actor)

            owner = AuthActor("user", COMPANY, "owner", user=SimpleNamespace(id=USER))
            items, total = await service.history(
                COMPANY, owner, employee_id=EMPLOYEE, branch_id=BRANCH,
                device_id=DEVICE, status="closed", limit=25, offset=0,
            )
            self.assertEqual(total, 1)
            self.assertEqual(items[0]["shift_number"], closed["shift_number"])
            self.assertEqual(items[0]["shop_name"], "Main")
            self.assertEqual(items[0]["summary"]["gross_sales_base"], Decimal("0.00"))

            report = await service.report_summary(
                COMPANY, owner, employee_id=EMPLOYEE, branch_id=BRANCH,
                device_id=DEVICE, status="closed",
                start_at=datetime.now(timezone.utc) - timedelta(days=1),
                end_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
            self.assertEqual(report["total_shifts"], 1)
            self.assertEqual(report["closed_shifts"], 1)
            self.assertEqual(report["base_currency_code"], "USD")
            self.assertEqual(
                {row["currency_code"]: Decimal(row["amount"]) for row in report["variance_by_currency"]},
                {"USD": Decimal("-1.0000"), "ZAR": Decimal("5.0000")},
            )
            no_date_matches = await service.report_summary(
                COMPANY, owner,
                start_at=datetime.now(timezone.utc) + timedelta(days=2),
            )
            self.assertEqual(no_date_matches["total_shifts"], 0)
            options = await service.filter_options(COMPANY, owner)
            self.assertEqual({row["id"] for row in options["devices"]}, {DEVICE})
            detail = await service.detail(COMPANY, closed["id"], owner)
            self.assertEqual(detail["currencies"][0]["expected_cash"], Decimal("19.0000"))

            cashier_items, cashier_total = await service.history(
                COMPANY, self.actor, limit=25, offset=0,
            )
            self.assertEqual(cashier_total, 1)
            self.assertEqual(cashier_items[0]["branch_id"], BRANCH)
            with self.assertRaisesRegex(HTTPException, "Branch access denied"):
                await service.history(COMPANY, self.actor, branch_id=OTHER_BRANCH)

            other_owner = AuthActor("user", OTHER_COMPANY, "owner", user=SimpleNamespace(id=uuid4()))
            other_report = await service.report_summary(OTHER_COMPANY, other_owner)
            self.assertEqual(other_report["total_shifts"], 1)
            with self.assertRaisesRegex(HTTPException, "Forbidden"):
                await service.report_summary(OTHER_COMPANY, owner)

    async def test_cash_movements_are_idempotent_scoped_immutable_and_reconciled_by_currency(self):
        shift = await self.open_shift("cash-move-open-0001")
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            service = ShiftService(ShiftRepository(session))
            cash_in_usd = CashMovementCreate(
                movement_type="cash_in", currency_code=" usd ", amount="10.00",
                reason="Float top-up", idempotency_key="cash-in-usd-0001",
            )
            first = await service.create_cash_movement(shift["id"], cash_in_usd, self.actor)
            repeated = await service.create_cash_movement(shift["id"], cash_in_usd, self.actor)
            self.assertEqual(first["id"], repeated["id"])
            self.assertEqual(first["actor_name"], "Cashier")

            await service.create_cash_movement(shift["id"], CashMovementCreate(
                movement_type="cash_out", currency_code="USD", amount="5.00",
                reason="Petty cash payout", idempotency_key="cash-out-usd-0001",
            ), self.actor)
            await service.create_cash_movement(shift["id"], CashMovementCreate(
                movement_type="cash_in", currency_code="ZAR", amount="40.00",
                reason="Float top-up", idempotency_key="cash-in-zar-0001",
            ), self.actor)
            with self.assertRaisesRegex(HTTPException, "decimal places"):
                await service.create_cash_movement(shift["id"], CashMovementCreate(
                    movement_type="cash_in", currency_code="USD", amount="1.001",
                    reason="Invalid precision", idempotency_key="cash-precision-0001",
                ), self.actor)
            with self.assertRaisesRegex(HTTPException, "exceeds"):
                await service.create_cash_movement(shift["id"], CashMovementCreate(
                    movement_type="cash_out", currency_code="USD", amount="26.00",
                    reason="Overdraw attempt", idempotency_key="cash-overdraw-0001",
                ), self.actor)

            foreign_actor = self.make_actor(OTHER_EMPLOYEE, OTHER_DEVICE, OTHER_POS_SESSION, COMPANY, SHOP, BRANCH)
            with self.assertRaisesRegex(HTTPException, "Only the cashier"):
                await service.create_cash_movement(shift["id"], CashMovementCreate(
                    movement_type="cash_in", currency_code="USD", amount="1.00",
                    reason="Wrong cashier", idempotency_key="cash-wrong-actor-001",
                ), foreign_actor)
            with self.assertRaisesRegex(HTTPException, "Shift not found"):
                await service.create_cash_movement(shift["id"], CashMovementCreate(
                    movement_type="cash_in", currency_code="USD", amount="1.00",
                    reason="Wrong company", idempotency_key="cash-wrong-company-1",
                ), self.other_actor)

            current = await service.current(self.actor)
            cash_by_code = {row["currency_code"]: row for row in current["currencies"]}
            self.assertEqual(cash_by_code["USD"]["cash_in"], Decimal("10.0000"))
            self.assertEqual(cash_by_code["USD"]["cash_out"], Decimal("5.0000"))
            self.assertEqual(cash_by_code["USD"]["expected_cash"], Decimal("25.0000"))
            self.assertEqual(cash_by_code["ZAR"]["expected_cash"], Decimal("540.0000"))
            self.assertEqual(len(current["cash_movements"]), 3)

            closed = await service.close(shift["id"], ShiftClose(
                counted_balances=[
                    ShiftClosingCount(currency_code="USD", amount="24.00"),
                    ShiftClosingCount(currency_code="ZAR", amount="540.00"),
                ], idempotency_key="cash-move-close-0001", confirmed=True,
            ), self.actor)
            closed_currency = {row["currency_code"]: row for row in closed["currencies"]}
            self.assertEqual(closed_currency["USD"]["expected_cash"], Decimal("25.0000"))
            self.assertEqual(closed_currency["USD"]["variance"], Decimal("-1.0000"))
            self.assertEqual(closed_currency["ZAR"]["variance"], Decimal("0.0000"))
            self.assertEqual(closed_currency["USD"]["cash_in"], Decimal("10.0000"))
            self.assertEqual(closed_currency["USD"]["cash_out"], Decimal("5.0000"))
            self.assertEqual(len(closed["cash_movements"]), 3)
            with self.assertRaises(HTTPException):
                await service.create_cash_movement(shift["id"], CashMovementCreate(
                    movement_type="cash_in", currency_code="USD", amount="1.00",
                    reason="After close", idempotency_key="cash-after-close-001",
                ), self.actor)
            count = (await session.execute(select(func.count()).select_from(CashierShiftCashMovement))).scalar_one()
            self.assertEqual(count, 3)


if __name__ == "__main__":
    unittest.main()
