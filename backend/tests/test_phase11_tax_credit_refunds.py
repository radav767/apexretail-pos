"""Tax and unpaid credit-note reconciliation with real services and atomic proofs."""
from datetime import datetime,timezone
from decimal import Decimal
from uuid import uuid4
import unittest
from unittest.mock import patch
import httpx
from fastapi import HTTPException
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.models import (CompanySetting,CompanySubscription,CreditReceivable,CreditRefundAdjustment,CreditSettlement,
    Customer,Sale,SaleItem,InventoryMovement,Product)
from app.sales.service import SalesService
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate,SaleItemCreate,RefundCreate,RefundItemCreate
from app.credit.service import CreditService
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
from app.customers.service import CustomerService
from app.customers.repository import CustomerRepository
from app.auth.security import create_access_token
from app.db.session import get_db
from app.main import app
import test_phase7d_operations as fixtures

class TaxCreditRefundTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.sales=SalesService(SalesRepository(self.db));self.credit=CreditService(CreditRepository(self.db))
        self.settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.company.id))).scalar_one()
        self.product.cost_price=Decimal('.01');self.product.selling_price=Decimal('.05')
        self.settings.tax_rate=15;self.settings.tax_inclusive=False
        self.customer=Customer(company_id=self.company.id,customer_code='TAXCREDIT',name='Synthetic debtor',credit_enabled=True,unlimited_credit=False,credit_limit=100)
        self.db.add(self.customer);await self.db.commit()
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test',headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)})
        self.addAsyncCleanup(self.client.aclose)
    async def sell(self,method='cash',quantity=3,items=None):
        sale=await self.sales.create_sale(SaleCreate(company_id=self.company.id,branch_id=self.branch.id,device_id=self.device.id,
            device_key=self.device.device_key,assignment_revision=self.device.assignment_revision,client_sale_id=uuid4(),payment_method=method,
            customer_id=self.customer.id if method=='credit' else None,amount_received=10 if method=='cash' else None,
            items=items or [SaleItemCreate(product_id=self.product.id,quantity=quantity)]),actor=self.owner)
        lines=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==sale.id))).scalars().all()
        return sale,lines
    def refund(self,sale,item,quantity=1,**extra):
        return RefundCreate(company_id=self.company.id,branch_id=self.branch.id,device_id=self.device.id,device_key=self.device.device_key,
            assignment_revision=self.device.assignment_revision,request_id=uuid4(),original_sale_id=sale.id,reason='Synthetic return',items=[RefundItemCreate(sale_item_id=item.id,quantity=quantity)],**extra)
    async def debt(self,sale):return (await self.db.execute(select(CreditReceivable).where(CreditReceivable.sale_id==sale.id))).scalar_one()
    async def collect(self,debt,amount):return await self.credit.create_settlement(SettlementCreate(company_id=self.company.id,branch_id=self.branch.id,receivable_id=debt.id,amount=amount,payment_method='cash',idempotency_key=str(uuid4())),self.owner)
    async def test_inclusive_and_exclusive_partial_returns_conserve_original_cents_tax_and_cost(self):
        for inclusive,total,amounts in [(True,'.15',['.05','.05','.05']),(False,'.17',['.06','.05','.06'])]:
            self.settings.tax_inclusive=inclusive;await self.db.commit()
            sale,lines=await self.sell();self.assertEqual(sale.total_amount,Decimal(total));self.assertEqual(sale.tax_amount,Decimal('.02'))
            refunds=[];taxes=[]
            for index in range(3):
                command=self.refund(sale,lines[0]);refund=await self.sales.create_refund(command,actor=self.owner)
                self.assertEqual(refund.total_amount,-Decimal(amounts[index]));self.assertEqual(refund.subtotal_amount+refund.tax_amount,refund.total_amount)
                repeat=await self.sales.create_refund(command,actor=self.owner);self.assertEqual(repeat.id,refund.id)
                refunds.append(refund.total_amount);taxes.append(refund.tax_amount)
            self.assertEqual(sum(refunds),-sale.total_amount);self.assertEqual(sum(taxes),-sale.tax_amount)
            returned=(await self.db.execute(select(SaleItem).where(SaleItem.original_sale_item_id==lines[0].id))).scalars().all()
            self.assertEqual(sum(item.line_cost for item in returned),-lines[0].line_cost)
            self.assertEqual(self.balance.quantity,100)
    async def test_aggregate_tax_residual_and_exempt_line_snapshots_match_full_reversal(self):
        self.settings.tax_inclusive=False
        extras=[Product(company_id=self.company.id,name=f'Synthetic penny {n}',selling_price=Decimal('.05'),cost_price=0,track_inventory=False,product_type='service') for n in range(2)]
        exempt=Product(company_id=self.company.id,name='Synthetic exempt',selling_price=Decimal('.05'),tax_exempt=True,track_inventory=False,product_type='service')
        self.db.add_all(extras+[exempt]);await self.db.commit()
        sale,items=await self.sell(items=[SaleItemCreate(product_id=p.id,quantity=1) for p in [self.product]+extras+[exempt]])
        self.assertEqual(sum(item.tax_amount for item in items),sale.tax_amount)
        self.assertEqual(next(item.tax_amount for item in items if item.product_id==exempt.id),0)
        command=self.refund(sale,items[0]);command.items=[RefundItemCreate(sale_item_id=item.id,quantity=1) for item in items]
        refund=await self.sales.create_refund(command,actor=self.owner);self.assertEqual(refund.total_amount,-sale.total_amount)
    async def test_unpaid_credit_note_preserves_original_debt_collections_history_and_replay(self):
        self.settings.tax_inclusive=False;await self.db.commit();sale,items=await self.sell('credit');debt=await self.debt(sale)
        await self.collect(debt,'.05');command=self.refund(sale,items[0]);refund=await self.sales.create_refund(command,actor=self.owner)
        self.assertEqual(refund.total_amount,Decimal('-.06'));self.assertEqual(refund.customer_id,self.customer.id)
        self.assertEqual((debt.original_amount,debt.amount_settled,debt.amount_credited,debt.outstanding_balance),(Decimal('.17'),Decimal('.05'),Decimal('.06'),Decimal('.06')))
        history=await CustomerService(CustomerRepository(self.db)).history(self.company.id,self.customer.id)
        self.assertEqual(sum(row['amount'] for row in history),debt.outstanding_balance)
        self.assertEqual({row['transaction_type'] for row in history},{'credit_sale','settlement','credit_refund'})
        response=await self.client.get(f'/api/credit/{self.company.id}/receivables/{debt.id}');self.assertEqual(response.status_code,200,response.text);self.assertEqual(Decimal(response.json()['amount_credited']),Decimal('.06'))
        license=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one();license.status='expired';await self.db.commit()
        repeated=await self.sales.create_refund(command,actor=self.owner);self.assertEqual(refund.id,repeated.id)
        self.assertEqual((await self.db.execute(select(func.count(CreditRefundAdjustment.id)).where(CreditRefundAdjustment.receivable_id==debt.id))).scalar_one(),1)
        self.assertEqual(self.balance.quantity,98)
        from app.reports.service import ReportsService
        from app.reports.repository import ReportsRepository
        from app.reports.accounting import REPORTING_TIMEZONE_NAME
        from zoneinfo import ZoneInfo
        today=datetime.now(ZoneInfo(REPORTING_TIMEZONE_NAME)).date()
        summary=await ReportsService(ReportsRepository(self.db)).financial_summary(self.company.id,date_from=today,date_to=today)
        # Fixture's earlier untaxed sale is included (12); tax note reverses .01.
        self.assertEqual(summary['tax_collected'],Decimal('.01'))
        self.assertEqual(summary['net_sales_ex_tax'],Decimal('12.10'))
        self.assertEqual(summary['credit_settlements'],Decimal('.05'))
        self.assertEqual(summary['outstanding_receivables'],Decimal('.06'))
    async def test_paid_refunds_and_method_overrides_fail_before_stock_debt_or_note_effects(self):
        sale,items=await self.sell('credit');debt=await self.debt(sale);await self.collect(debt,'.17')
        for command in [self.refund(sale,items[0]),self.refund(sale,items[0],refund_method='cash'),self.refund(sale,items[0],payment_currency_code='TST')]:
            with self.assertRaises(HTTPException) as error:await self.sales.create_refund(command,actor=self.owner)
            self.assertEqual(error.exception.status_code,409)
        self.assertEqual(self.balance.quantity,97);self.assertEqual(debt.amount_credited,0);self.assertEqual(debt.outstanding_balance,0)
        self.assertEqual((await self.db.execute(select(func.count(CreditRefundAdjustment.id)).where(CreditRefundAdjustment.receivable_id==debt.id))).scalar_one(),0)
    async def test_credit_note_is_immutable_and_fault_rolls_back_stock_and_debt(self):
        sale,items=await self.sell('credit');debt=await self.debt(sale);command=self.refund(sale,items[0]);ids=(debt.id,self.product.id,self.branch.id)
        with patch('app.business_operations.batches.allocate_batch_movements',side_effect=RuntimeError('synthetic save failure')):
            with self.assertRaisesRegex(RuntimeError,'synthetic save failure'):await self.sales.create_refund(command,actor=self.owner)
        await self.db.rollback()
        debt=await self.db.get(CreditReceivable,ids[0]);self.assertEqual(debt.amount_credited,0);self.assertEqual(debt.outstanding_balance,Decimal('.17'))
        self.assertEqual((await self.db.execute(select(func.count(CreditRefundAdjustment.id)).where(CreditRefundAdjustment.receivable_id==ids[0]))).scalar_one(),0)
        await self.db.refresh(self.user)
        refund=await self.sales.create_refund(command,actor=self.owner)
        note=(await self.db.execute(select(CreditRefundAdjustment).where(CreditRefundAdjustment.refund_sale_id==refund.id))).scalar_one()
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text('UPDATE credit_refund_adjustments SET amount=0 WHERE id=:id'),{'id':note.id})

    async def test_legacy_unknown_tax_requires_review_without_stock_change(self):
        sale,items=await self.sell()
        items[0].tax_amount=None;await self.db.commit()  # Synthetic legacy row.
        with self.assertRaises(HTTPException) as error:await self.sales.create_refund(self.refund(sale,items[0]),actor=self.owner)
        self.assertEqual(error.exception.status_code,409);self.assertEqual(self.balance.quantity,97)
