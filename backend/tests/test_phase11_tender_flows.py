"""Real synthetic payments/refunds: event dates, exact FX and independent ledgers."""
import copy,unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from uuid import UUID,uuid4
from unittest.mock import patch
from sqlalchemy import select
from app.models import CreditReceivable,CompanySubscription,Product,CompanySetting,CompanyCurrency,CurrencyExchangeRate,SaleItem
from app.credit.service import CreditService
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
import test_phase11_split_refunds as fixtures

def clock(at):
    class Frozen(datetime):
        @classmethod
        def now(cls,tz=None):return at.astimezone(tz) if tz else at.replace(tzinfo=None)
    return patch('app.sales.service.datetime',Frozen)

class TenderFlowTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.SplitRefundTests.cleanup
    asyncSetUp=fixtures.SplitRefundTests.asyncSetUp
    checkout=fixtures.SplitRefundTests.checkout
    original=fixtures.SplitRefundTests.original
    command=fixtures.SplitRefundTests.command
    post=fixtures.SplitRefundTests.post
    stock=fixtures.SplitRefundTests.stock
    debt=fixtures.SplitRefundTests.debt
    async def flow(self,start,end,**params):
        response=await self.client.get(f'/api/reports/tender-flows/{self.c}',params={'start':start.isoformat(),'end':end.isoformat(),**params})
        self.assertEqual(response.status_code,200,response.text);return response.json()
    async def test_dated_payment_collection_refund_boundaries_and_replay_never_multiply_revenue(self):
        t=datetime(2004,3,1,tzinfo=timezone.utc)
        product=await self.db.get(Product,self.p);product.cost_price=1;product.selling_price=6
        other=Product(company_id=self.c,name='Synthetic second priced line',selling_price=6,cost_price=1,track_inventory=False,product_type='service');self.db.add(other);await self.db.commit()
        self.body['items']=[{'product_id':str(self.p),'quantity':'1'},{'product_id':str(other.id),'quantity':'1'}]
        with clock(t):result=await self.checkout()
        self.sid=UUID(result['sale']['id']);self.cash=next(r['id'] for r in result['tenders'] if r['method']=='cash');self.credit=next(r['id'] for r in result['tenders'] if r['method']=='credit')
        # Two original items and two later collections must not multiply billed/cost/tender sums.
        items=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==self.sid))).scalars().all()
        self.item=items[0].id
        debt=await self.debt();service=CreditService(CreditRepository(self.db))
        for index in range(2):
            payment=SettlementCreate(company_id=self.c,branch_id=self.b,receivable_id=debt.id,amount=Decimal('.5'),payment_method='cash',received_at=t+timedelta(days=1,microseconds=index),idempotency_key=str(uuid4()))
            await service.create_settlement(payment,self.owner);await service.create_settlement(payment,self.owner)
        command=self.command('.5','6',[(self.credit,'debt_reduction','3','3'),(self.cash,'paid_refund','3','3')])
        command['items']=[{'sale_item_id':str(item.id),'quantity':'.5'} for item in items]
        with clock(t+timedelta(days=2)):await self.post(command)
        await self.post(command);await self.checkout()
        original=await self.flow(t,t+timedelta(days=1));self.assertEqual(original['event_count'],2);self.assertEqual(Decimal(original['revenue'][0]['billed']),12)
        collection=await self.flow(t+timedelta(days=1),t+timedelta(days=2));self.assertEqual(collection['event_count'],2);self.assertEqual(collection['events'][0]['kind'],'credit_collection');self.assertEqual(collection['revenue'],[])
        refund=await self.flow(t+timedelta(days=2),t+timedelta(days=3));self.assertEqual(refund['event_count'],2);self.assertEqual(Decimal(refund['revenue'][0]['billed']),-6)
        all_rows=await self.flow(t,t+timedelta(days=3),limit=1);self.assertEqual(all_rows['event_count'],6);self.assertEqual(len(all_rows['events']),1);self.assertEqual(Decimal(all_rows['revenue'][0]['billed']),6);self.assertEqual(Decimal(all_rows['revenue'][0]['cost']),1)
        cash=next(r for r in all_rows['totals'] if r['method']=='cash');credit=next(r for r in all_rows['totals'] if r['method']=='credit');self.assertEqual(Decimal(cash['applied_base']),6);self.assertEqual(Decimal(cash['debt_delta']),-1);self.assertEqual(Decimal(credit['debt_delta']),1)
        self.assertEqual(Decimal(all_rows['cash_original_units'][0]['known_net']),6);self.assertEqual(Decimal(all_rows['cash_original_units'][0]['known_change']),2)
        offset=await self.flow(t.astimezone(timezone(timedelta(hours=2))),t+timedelta(days=3));self.assertEqual(offset['totals'],all_rows['totals'])
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit();self.settings.split_checkout_mode='disabled'
        self.assertEqual((await self.flow(t,t+timedelta(days=3)))['totals'],all_rows['totals']);self.assertEqual(await self.stock(),Decimal('99.5'))
    async def test_two_fx_residuals_and_final_refund_do_not_become_debt_or_hidden_cash(self):
        t=datetime.now(timezone.utc)-timedelta(seconds=1)
        product=await self.db.get(Product,self.p);product.selling_price=Decimal('.03')
        settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.c))).scalar_one();settings.multi_currency_enabled=True
        currency=CompanyCurrency(company_id=self.c,code='SYN',display_name='Synthetic thirds',symbol='S',decimal_places=2,active=True,cash_accepted=True);self.db.add(currency);await self.db.flush()
        rate=CurrencyExchangeRate(company_id=self.c,currency_id=currency.id,currency_code='SYN',foreign_units_per_base=3,effective_at=t-timedelta(days=1));self.db.add(rate);await self.db.commit()
        ids=sorted([str(uuid4()),str(uuid4())]);self.body['expected_total']='.03'
        for index,leg in enumerate(self.body['tenders']):leg.update(id=ids[index],method='cash',currency_code='SYN',applied_original='.04',tendered_original='.05' if index==0 else '.04',applied_base='.02' if index==0 else '.01',exchange_rate_snapshot='3',exchange_rate_id=str(rate.id))
        result=await self.checkout();self.sid=UUID(result['sale']['id']);self.item=(await self.db.execute(select(SaleItem.id).where(SaleItem.sale_id==self.sid))).scalar_one()
        report=await self.flow(t,datetime.now(timezone.utc)+timedelta(seconds=1));events=[r for r in report['events'] if r['source_id']==str(self.sid)]
        self.assertEqual(len(events),2)
        for event in events:self.assertEqual(Decimal(event['drawer_valuation']),Decimal(event['applied_base'])-Decimal(event['allocation_variance'])+Decimal(event['tender_change_variance']))
        first=next(r for r in events if r['event_id'].endswith(ids[0]));self.assertEqual(Decimal(first['allocation_variance']),Decimal('.01'));self.assertEqual(Decimal(first['tender_change_variance']),Decimal('.01'))
        command=self.command('1','.03',[(r['id'],'paid_refund',r['applied_base'],r['applied_original']) for r in result['tenders']]);await self.post(command);await self.post(command)
        final=await self.flow(t,datetime.now(timezone.utc)+timedelta(seconds=1));units=next(r for r in final['cash_original_units'] if r['currency_code']=='SYN');self.assertEqual(Decimal(units['known_net']),0)
        cash=next(r for r in final['totals'] if r['method']=='cash');self.assertEqual(Decimal(cash['applied_base']),0);self.assertEqual(Decimal(cash['debt_delta']),0)
    async def test_bounds_tenant_and_permission_fail_closed(self):
        from app.auth.security import create_employee_access_token
        t=datetime.now(timezone.utc)
        for start,end in [(t.replace(tzinfo=None),t),(t,t),(t,t+timedelta(days=367))]:
            r=await self.client.get(f'/api/reports/tender-flows/{self.c}',params={'start':start.isoformat(),'end':end.isoformat()});self.assertEqual(r.status_code,422,r.text)
        params={'start':(t-timedelta(days=1)).isoformat(),'end':t.isoformat()}
        r=await self.client.get(f'/api/reports/tender-flows/{uuid4()}',params=params);self.assertEqual(r.status_code,403)
        token=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='cashier')
        r=await self.client.get(f'/api/reports/tender-flows/{self.c}',params=params,headers={'Authorization':'Bearer '+token});self.assertEqual(r.status_code,403,r.text)
    async def test_legacy_missing_snapshots_remain_unknown_and_revoked_reader_cannot_recover(self):
        t=datetime.now(timezone.utc);result=await self.flow(t-timedelta(days=1),t+timedelta(seconds=1))
        event=next(r for r in result['events'] if r['source_id']==str(self.sale.id));self.assertTrue(event['unknown_provenance']);self.assertFalse(event['original_units_known']);self.assertIsNone(event['currency_code']);self.assertIsNone(event['rate'])
        units=next(r for r in result['cash_original_units'] if r['currency_code'] is None);self.assertEqual(units['unknown_count'],1);self.assertIsNone(units['known_net'])
        from app.models import User
        user=await self.db.get(User,self.u);user.session_version+=1;await self.db.commit()
        response=await self.client.get(f'/api/reports/tender-flows/{self.c}',params={'start':(t-timedelta(days=1)).isoformat(),'end':t.isoformat()});self.assertEqual(response.status_code,401)
