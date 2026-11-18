"""Real transaction services and API with isolated tenant rollback fixtures."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import unittest
import httpx
from fastapi import HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from app.models import CompanySubscription, CreditReceivable, CreditSettlement, Expense, Customer, CompanyCurrency
from app.auth.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.expenses.service import ExpenseService
from app.expenses.repository import ExpenseRepository
from app.expenses.schema import ExpenseCreate, ExpenseCategoryCreate, ExpenseCategoryUpdate
from app.credit.service import CreditService
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
from app.currencies.service import CurrencyService
from app.currencies.repository import CurrencyRepository
from app.currencies.schema import CurrencyCreate, CurrencyUpdate, ExchangeRateCreate
from app.customers.service import CustomerService
from app.customers.repository import CustomerRepository
from app.customers.schema import CustomerCreate, CustomerUpdate
from app.business_settings.service import BusinessSettingsService
from app.business_settings.schema import CompanySettingsUpdate
from app.sales.service import SalesService
from app.sales.repository import SalesRepository
from app.sales.schema import RefundCreate, RefundItemCreate
import test_phase7d_operations as fixtures


class FinancialReplayTests(unittest.IsolatedAsyncioTestCase):
    cleanup = fixtures.Phase7DOperationsTests.cleanup

    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.license = (await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id == self.company.id))).scalar_one()
        self.expenses = ExpenseService(ExpenseRepository(self.db))
        self.credit = CreditService(CreditRepository(self.db))
        self.category = await self.expenses.create_category(ExpenseCategoryCreate(company_id=self.company.id, name='Synthetic supplies'), self.owner)
        customer = Customer(company_id=self.company.id, customer_code='SYNTHETIC', name='Synthetic customer', credit_enabled=True, unlimited_credit=True)
        self.db.add(customer); await self.db.flush(); self.customer = customer
        self.receivable = CreditReceivable(company_id=self.company.id, customer_id=customer.id, sale_id=self.sale.id,
            shop_id=self.shop.id, branch_id=self.branch.id, currency_code='USD', original_amount=100,
            amount_settled=0, outstanding_balance=100, due_date=datetime.now(timezone.utc).date(), status='unpaid')
        self.db.add(self.receivable); await self.db.commit()
        async def override(): yield self.db
        app.dependency_overrides[get_db] = override; self.addCleanup(app.dependency_overrides.clear)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic.test')
        self.addAsyncCleanup(self.client.aclose)
        self.headers = {'Authorization': 'Bearer '+create_access_token(str(self.user.id), self.user.email)}

    def expense(self, **changes):
        values = dict(company_id=self.company.id, branch_id=self.branch.id, category_id=self.category.id,
            amount=Decimal('10'), occurred_at=datetime.now(timezone.utc), payment_method='cash', description='Synthetic expense', idempotency_key=str(uuid4()))
        values.update(changes); return ExpenseCreate(**values)

    def settlement(self, **changes):
        values = dict(company_id=self.company.id, branch_id=self.branch.id, receivable_id=self.receivable.id,
                      amount=Decimal('10'), payment_method='cash', idempotency_key=str(uuid4()))
        values.update(changes); return SettlementCreate(**values)

    async def post(self, path, data, headers=None):
        return await self.client.post('/api/'+path, headers=headers or self.headers, json=data.model_dump(mode='json'))

    async def test_expense_replay_requires_full_proof_after_expiry(self):
        data = self.expense(); first = await self.post('expenses', data)
        self.assertEqual(first.status_code, 200, first.text)
        self.license.status = 'suspended'; await self.db.commit()
        replay = await self.post('expenses', data); self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()['id'], first.json()['id'])
        for changes in ({'description':'Changed description'}, {'reference':'changed'}, {'occurred_at':datetime.now(timezone.utc)}):
            self.assertEqual((await self.post('expenses', data.model_copy(update=changes))).status_code, 409)
        self.assertEqual((await self.post('expenses', self.expense())).status_code, 402)
        self.assertEqual((await self.db.execute(select(func.count(Expense.id)).where(Expense.company_id == self.company.id))).scalar_one(), 1)
        self.assertEqual(self.balance.quantity, 100)
        self.assertEqual((await self.client.get(f'/api/expenses/{self.company.id}', headers=self.headers)).status_code, 200)

    async def test_collection_replay_does_not_reapply_full_settlement_or_changed_tender(self):
        data = self.settlement(settle_full=True, amount=None, tendered_amount_original=Decimal(110))
        first = await self.post('credit/settlements', data); self.assertEqual(first.status_code, 200, first.text)
        self.license.status = 'expired'; await self.db.commit()
        replay = await self.post('credit/settlements', data); self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()['id'], first.json()['id'])
        for changes in ({'tendered_amount_original':Decimal(120)}, {'note':'Changed'}, {'settle_full':False}):
            self.assertEqual((await self.post('credit/settlements', data.model_copy(update=changes))).status_code, 409)
        self.assertEqual((await self.post('credit/settlements', self.settlement())).status_code, 402)
        await self.db.refresh(self.receivable)
        self.assertEqual(self.receivable.outstanding_balance, 0); self.assertEqual(self.receivable.amount_settled, 100)
        self.assertEqual((await self.db.execute(select(func.count(CreditSettlement.id)).where(CreditSettlement.company_id == self.company.id))).scalar_one(), 1)

    async def test_legacy_proof_is_not_guessed_and_proofs_are_immutable(self):
        # A historical unproved row remains readable but cannot authorize POST replay.
        row = Expense(company_id=self.company.id, category_id=self.category.id, shop_id=self.shop.id,
            branch_id=self.branch.id, amount=10, original_amount=10, currency_code='USD',
            occurred_at=datetime.now(timezone.utc), payment_method='cash', description='Legacy', idempotency_key=str(uuid4()))
        self.db.add(row); await self.db.commit()
        self.assertEqual((await self.post('expenses', self.expense(idempotency_key=row.idempotency_key))).status_code, 409)
        data = self.expense(); result = await self.post('expenses', data); self.assertEqual(result.status_code, 200, result.text)
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():
                await self.db.execute(text("UPDATE expenses SET command_hash='changed' WHERE idempotency_key=:key AND company_id=:company"), {'key':data.idempotency_key, 'company':self.company.id})

    async def test_direct_new_mutations_and_api_shortcuts_deny_expired_license(self):
        self.license.status = 'expired'; await self.db.commit()
        currency = CurrencyService(CurrencyRepository(self.db)); customers = CustomerService(CustomerRepository(self.db))
        base = (await self.db.execute(select(CompanyCurrency).where(CompanyCurrency.company_id==self.company.id))).scalar_one()
        calls = [
            self.expenses.create_expense(self.expense(), self.owner),
            self.credit.create_settlement(self.settlement(), self.owner),
            self.expenses.create_category(ExpenseCategoryCreate(company_id=self.company.id, name='New'), self.owner),
            self.expenses.update_category(self.company.id, self.category.id, ExpenseCategoryUpdate(name='Changed'), self.owner),
            self.expenses.delete_category(self.company.id, self.category.id, self.owner),
            currency.create(CurrencyCreate(company_id=self.company.id, code='ZAR', display_name='Test rand', symbol='R'), self.owner),
            currency.set_multi_currency(self.company.id, True, self.owner),
            currency.update(self.company.id, base.id, CurrencyUpdate(display_name='Changed'), self.owner),
            currency.set_base(self.company.id, base.id, self.owner),
            currency.create_rate(ExchangeRateCreate(company_id=self.company.id, currency_id=base.id, foreign_units_per_base=2, effective_at=datetime.now(timezone.utc)), self.owner),
            customers.create(CustomerCreate(company_id=self.company.id, customer_code='NEW', name='New'), self.owner),
            customers.update(self.company.id, self.customer.id, CustomerUpdate(name='Changed'), self.owner),
            BusinessSettingsService(self.db).update(self.company.id, CompanySettingsUpdate(tax_name='Changed')),
            SalesService(SalesRepository(self.db)).create_refund(RefundCreate(company_id=self.company.id, original_sale_id=self.sale.id,
                reason='Synthetic return', items=[RefundItemCreate(sale_item_id=self.item.id, quantity=1)]), actor=self.owner),
        ]
        for call in calls:
            with self.assertRaises(HTTPException) as error: await call
            self.assertEqual(error.exception.status_code, 402)
        self.assertEqual((await self.client.patch(f'/api/currencies/configuration/{self.company.id}', headers=self.headers, json={'enabled':True})).status_code, 402)
        self.assertEqual((await self.client.patch(f'/api/expenses/categories/{self.company.id}/{self.category.id}', headers=self.headers, json={'name':'Changed'})).status_code, 402)
        self.assertEqual(self.category.name, 'Synthetic supplies'); self.assertEqual(self.customer.name, 'Synthetic customer')
        self.assertEqual(self.balance.quantity, 100)
