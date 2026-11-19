"""Golden real-service ledger/report reconciliation; synthetic rollback fixture only."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
import unittest
import httpx
from sqlalchemy import select, func
from app.models import (CompanySubscription, Customer, CreditReceivable, SaleItem, InventoryMovement,
                        Sale, CreditSettlement, Expense, CompanySetting)
from app.auth.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.sales.service import SalesService
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate,SaleItemCreate,RefundCreate,RefundItemCreate
from app.credit.service import CreditService
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
from app.expenses.service import ExpenseService
from app.expenses.repository import ExpenseRepository
from app.expenses.schema import ExpenseCreate,ExpenseCategoryCreate
from app.reports.service import ReportsService
from app.reports.repository import ReportsRepository
from app.reports.schema import SalesHistoryQuery
import test_phase7d_operations as fixtures


INSTANT=datetime(2026,1,15,10,tzinfo=timezone.utc)
class FixtureClock(datetime):
    @classmethod
    def now(cls,tz=None):return INSTANT.astimezone(tz) if tz else INSTANT.replace(tzinfo=None)


class FinanceReconciliationTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        # Existing fixture sale remains untouched and outside this fixed report range.
        self.product.cost_price=Decimal('2.35');self.product.selling_price=Decimal('10.10')
        self.customer=Customer(company_id=self.company.id,customer_code='GOLDEN',name='Synthetic golden credit',credit_enabled=True,unlimited_credit=False,credit_limit=100)
        self.db.add(self.customer);await self.db.commit()
        self.sales=SalesService(SalesRepository(self.db));self.credit=CreditService(CreditRepository(self.db))
        self.expenses=ExpenseService(ExpenseRepository(self.db));self.reports=ReportsService(ReportsRepository(self.db))
        self.cash_command=self.command('cash',3,sale_discount_amount=Decimal('.30'),discount_amount=Decimal('.30'),amount_received=35)
        self.card_command=self.command('card',2)
        self.credit_command=self.command('credit',4,customer_id=self.customer.id)
        with patch('app.sales.service.datetime',FixtureClock):
            self.cash=await self.sales.create_sale(self.cash_command,actor=self.owner)
            self.card=await self.sales.create_sale(self.card_command,actor=self.owner)
            self.credit_sale=await self.sales.create_sale(self.credit_command,actor=self.owner)
            cash_item=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==self.cash.id))).scalar_one()
            self.refund_command=RefundCreate(company_id=self.company.id,branch_id=self.branch.id,device_id=self.device.id,
                device_key=self.device.device_key,assignment_revision=self.device.assignment_revision,request_id=uuid4(),
                original_sale_id=self.cash.id,reason='Synthetic partial return',items=[RefundItemCreate(sale_item_id=cash_item.id,quantity=1)])
            self.refund=await self.sales.create_refund(self.refund_command,actor=self.owner)
        self.receivable=(await self.db.execute(select(CreditReceivable).where(CreditReceivable.sale_id==self.credit_sale.id))).scalar_one()
        self.collection_commands=[]
        # Exactly midnight in the report's existing Africa/Harare timezone.
        for method,amount,day in [('cash','12.15',0),('card','8.25',1)]:
            command=SettlementCreate(company_id=self.company.id,branch_id=self.branch.id,receivable_id=self.receivable.id,
                amount=amount,payment_method=method,received_at=INSTANT.replace(hour=22)+timedelta(days=day),idempotency_key='golden-'+str(uuid4()))
            self.collection_commands.append(command);await self.credit.create_settlement(command,self.owner)
        category=await self.expenses.create_category(ExpenseCategoryCreate(company_id=self.company.id,name='Synthetic golden expenses'),self.owner)
        self.expense_command=ExpenseCreate(company_id=self.company.id,branch_id=self.branch.id,category_id=category.id,amount='3.25',
            occurred_at=INSTANT,payment_method='cash',description='Synthetic operating cost',idempotency_key='golden-'+str(uuid4()))
        await self.expenses.create_expense(self.expense_command,self.owner)
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test',headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)})
        self.addAsyncCleanup(self.client.aclose)
    def command(self,method,quantity,**extra):
        return SaleCreate(company_id=self.company.id,branch_id=self.branch.id,device_id=self.device.id,
            device_key=self.device.device_key,assignment_revision=self.device.assignment_revision,client_sale_id=uuid4(),
            payment_method=method,items=[SaleItemCreate(product_id=self.product.id,quantity=quantity,**({'line_total':Decimal('30.00')} if extra.get('discount_amount') else {}))],**extra)
    async def report(self,start=0,end=0):
        return await self.reports.financial_summary(self.company.id,date_from=INSTANT.date()+timedelta(days=start),date_to=INSTANT.date()+timedelta(days=end))
    def assert_money(self,row,**expected):
        for key,value in expected.items():self.assertEqual(row[key],Decimal(str(value)),(key,row))
    async def ledger(self):
        return {model.__tablename__:(await self.db.execute(select(func.count(model.id)).where(model.company_id==self.company.id))).scalar_one() for model in (Sale,InventoryMovement,CreditSettlement,Expense)}
    async def test_golden_snapshots_stock_cost_revenue_cashflow_and_history_agree(self):
        self.assert_money({'cash':self.cash.total_amount,'change':self.cash.change_due,'card':self.card.total_amount,'credit':self.credit_sale.total_amount,'refund':self.refund.total_amount},cash='30',change='5',card='20.20',credit='40.40',refund='-10')
        self.assertEqual(self.balance.quantity,92);self.assertEqual(self.product.stock_qty,92)
        self.assertEqual(self.receivable.original_amount,Decimal('40.40'));self.assertEqual(self.receivable.amount_settled,Decimal('20.40'));self.assertEqual(self.receivable.outstanding_balance,20)
        row=await self.report()
        self.assert_money(row,gross_sales='90.60',net_sales='80.60',discounts='.30',cost_of_sales='18.80',gross_profit='61.80',operating_expenses='3.25',net_profit='58.55',cash_sales=20,card_sales='20.20',mobile_sales=0,credit_sales='40.40',credit_settlements=0,outstanding_receivables=20,expected_cash_movement='16.75')
        history=await self.reports.sales_history(self.company.id,SalesHistoryQuery(date_from=INSTANT.date(),date_to=INSTANT.date()))
        self.assert_money(history['summary'],gross_sales='90.60',refunds=10,net_sales='80.60')
        self.assertEqual(history['summary']['cost_of_sales']['value'],row['cost_of_sales']);self.assertEqual(history['summary']['gross_profit']['value'],row['gross_profit'])
        self.assertEqual(await self.ledger(),{'sales':5,'inventory_movements':4,'credit_settlements':2,'expenses':1})
    async def test_later_collections_use_half_open_local_midnight_without_new_revenue(self):
        first=await self.report(1,1);second=await self.report(2,2);whole=await self.report(0,2)
        self.assert_money(first,net_sales=0,cost_of_sales=0,credit_settlements='12.15',cash_settlements='12.15',expected_cash_movement='12.15',outstanding_receivables=20)
        self.assert_money(second,net_sales=0,credit_settlements='8.25',card_settlements='8.25',cash_settlements=0,expected_cash_movement=0)
        self.assert_money(whole,net_sales='80.60',credit_settlements='20.40',expected_cash_movement='28.90',net_profit='58.55')
        self.assertEqual(self.balance.quantity,92)
    async def test_expired_exact_retries_leave_ledger_and_api_report_unchanged(self):
        before=await self.report(0,2);counts=await self.ledger()
        license=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one();license.status='expired';license.commercial_terms={'features':{}};await self.db.commit()
        for command,original in [(self.cash_command,self.cash),(self.card_command,self.card),(self.credit_command,self.credit_sale)]:
            self.assertEqual((await self.sales.create_sale(command,actor=self.owner)).id,original.id)
        self.assertEqual((await self.sales.create_refund(self.refund_command,actor=self.owner)).id,self.refund.id)
        for command in self.collection_commands:await self.credit.create_settlement(command,self.owner)
        await self.expenses.create_expense(self.expense_command,self.owner)
        self.assertEqual(await self.ledger(),counts);self.assertEqual(await self.report(0,2),before);self.assertEqual(self.balance.quantity,92)
        response=await self.client.get(f'/api/reports/financial-summary/{self.company.id}',params={'date_from':str(INSTANT.date()),'date_to':str(INSTANT.date()+timedelta(days=2))})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual({key:Decimal(str(value)) for key,value in response.json().items()},before)

    async def test_currency_rounding_and_later_catalog_rate_changes_preserve_snapshots(self):
        from app.currencies.service import CurrencyService
        from app.currencies.repository import CurrencyRepository
        from app.currencies.schema import CurrencyCreate,ExchangeRateCreate
        from app.products.service import ProductService
        from app.products.repository import ProductRepository
        from app.products.schema import ProductUpdate
        currencies=CurrencyService(CurrencyRepository(self.db))
        foreign=await currencies.create(CurrencyCreate(company_id=self.company.id,code='TST',display_name='Synthetic test units',symbol='T',decimal_places=2,cash_accepted=True),self.owner)
        await currencies.set_multi_currency(self.company.id,True,self.owner)
        rate=await currencies.create_rate(ExchangeRateCreate(company_id=self.company.id,currency_id=foreign['id'],foreign_units_per_base='3.3333333333',effective_at=INSTANT-timedelta(days=2)),self.owner)
        command=self.command('cash',1,payment_currency_code='TST',tendered_amount_original=40,exchange_rate_id=rate.id,exchange_rate_snapshot=rate.foreign_units_per_base)
        with patch('app.sales.service.datetime',FixtureClock):
            sale=await self.sales.create_sale(command,actor=self.owner)
        self.assert_money({'total':sale.total_amount,'payment':sale.payment_amount_original,'tender':sale.tendered_amount_original,'change':sale.change_amount_original,'base_tender':sale.amount_received,'base_change':sale.change_due},total='10.10',payment='33.67',tender=40,change='6.33',base_tender=12,base_change='1.90')
        before=await self.report(0,2);counts=await self.ledger()
        self.assert_money(before,net_sales='90.70',cost_of_sales='21.15',gross_profit='69.55',net_profit='66.30',cash_sales='30.10',expected_cash_movement='39.00')
        await currencies.create_rate(ExchangeRateCreate(company_id=self.company.id,currency_id=foreign['id'],foreign_units_per_base=9,effective_at=INSTANT-timedelta(days=1)),self.owner)
        await ProductService(ProductRepository(self.db)).update_product(self.company.id,self.product.id,ProductUpdate(cost_price=99,selling_price=99),actor=self.owner)
        replay=await self.sales.create_sale(command,actor=self.owner)
        self.assertEqual(replay.id,sale.id);self.assertEqual(replay.exchange_rate_snapshot,Decimal('3.3333333333'))
        self.assertEqual(replay.payment_amount_original,Decimal('33.67'));self.assertEqual(await self.report(0,2),before)
        self.assertEqual(await self.ledger(),counts);self.assertEqual(self.balance.quantity,91)
