"""Real split cash/debt/collection/refund posting reconciles immutable closes."""
import unittest,copy
from uuid import UUID,uuid4
from decimal import Decimal
from datetime import datetime,timezone,timedelta
from sqlalchemy import select
from app.models import Employee,CompanySetting,CompanyCurrency,CurrencyExchangeRate,SaleItem,CreditReceivable
from app.auth.security import hash_session_token
from app.credit.service import CreditService
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
import test_phase11_split_refunds as fixtures

class SplitShiftTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.SplitRefundTests.cleanup
    checkout=fixtures.SplitRefundTests.checkout
    original=fixtures.SplitRefundTests.original
    command=fixtures.SplitRefundTests.command
    post=fixtures.SplitRefundTests.post
    stock=fixtures.SplitRefundTests.stock
    async def asyncSetUp(self):
        await fixtures.SplitRefundTests.asyncSetUp(self)
        employee=await self.db.get(Employee,self.e);employee.permissions={**employee.permissions,'shifts_open':True,'shifts_close':True,'credit_sales':True,'credit_settlements':True,'sales_process':True,'sales_refund':True,'sales_history_view':True}
        token='synthetic-split-shift-'+str(uuid4());self.session.token_hash=hash_session_token(token);await self.db.commit();self.cashier_headers={'Authorization':'Bearer '+token}
    async def open_shift(self):
        response=await self.client.post('/api/shifts/open',headers=self.cashier_headers,json={'opening_balances':[{'currency_code':'USD','amount':'20'}],'idempotency_key':str(uuid4())});self.assertEqual(response.status_code,200,response.text);return response.json()
    async def test_cash_debt_collection_refund_close_and_replay_conserve_float(self):
        shift=await self.open_shift();result=await self.checkout(headers=self.cashier_headers);self.sid=UUID(result['sale']['id']);self.item=(await self.db.execute(select(SaleItem.id).where(SaleItem.sale_id==self.sid))).scalar_one();self.cash=next(r['id'] for r in result['tenders'] if r['method']=='cash');self.credit=next(r['id'] for r in result['tenders'] if r['method']=='credit')
        debt=(await self.db.execute(select(CreditReceivable).where(CreditReceivable.sale_id==self.sid))).scalar_one()
        # Use the real collection endpoint and opaque shift-bound cashier.
        collection={'company_id':str(self.c),'branch_id':str(self.b),'receivable_id':str(debt.id),'amount':'1','payment_method':'cash','idempotency_key':str(uuid4())}
        received=await self.client.post('/api/credit/settlements',headers=self.cashier_headers,json=collection);self.assertEqual(received.status_code,200,received.text)
        replay=await self.client.post('/api/credit/settlements',headers=self.cashier_headers,json=collection);self.assertEqual(replay.status_code,200,replay.text)
        refund=self.command('.5','6',[(self.credit,'debt_reduction','3','3'),(self.cash,'paid_refund','3','3')]);await self.post(refund,headers=self.cashier_headers);await self.post(refund,headers=self.cashier_headers)
        current=await self.client.get('/api/shifts/current',headers=self.cashier_headers);self.assertEqual(current.status_code,200,current.text);current=current.json()
        row=next(r for r in current['currencies'] if r['currency_code']=='USD');self.assertEqual({key:Decimal(row[key]) for key in ('cash_sales','cash_refunds','cash_settlements','expected_cash')},{'cash_sales':8,'cash_refunds':3,'cash_settlements':1,'expected_cash':26})
        self.assertEqual(Decimal(current['summary']['cash_sales_base']),8);self.assertEqual(Decimal(current['summary']['credit_sales_base']),4);self.assertEqual(Decimal(current['summary']['net_sales_base']),6);self.assertEqual(Decimal(current['summary']['cash_paid_out_base']),3)
        closing={'counted_balances':[{'currency_code':'USD','amount':'26'}],'confirmed':True,'idempotency_key':str(uuid4())}
        closed=await self.client.post('/api/shifts/'+shift['id']+'/close',headers=self.cashier_headers,json=closing);self.assertEqual(closed.status_code,200,closed.text)
        repeat=await self.client.post('/api/shifts/'+shift['id']+'/close',headers=self.cashier_headers,json=closing);self.assertEqual(repeat.status_code,200,repeat.text)
        def numeric(value):
            if isinstance(value,dict):return {k:numeric(v) for k,v in value.items()}
            if isinstance(value,list):return [numeric(v) for v in value]
            if isinstance(value,str):
                try:return Decimal(value)
                except ArithmeticError:return value
            return value
        self.assertEqual(numeric(repeat.json()['currencies']),numeric(closed.json()['currencies']));self.assertEqual(numeric(repeat.json()['summary']),numeric(closed.json()['summary']))
        # Original committed proofs recover after close; no drawer/stock post.
        self.assertEqual((await self.checkout(headers=self.cashier_headers))['sale']['id'],str(self.sid));await self.post(refund,headers=self.cashier_headers);self.assertEqual(await self.stock(),Decimal('99.5'))
    async def test_currency_added_after_open_is_not_silently_omitted_from_drawer(self):
        await self.open_shift()
        settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.c))).scalar_one();settings.multi_currency_enabled=True
        currency=CompanyCurrency(company_id=self.c,code='SYN',display_name='Synthetic late cash',symbol='S',decimal_places=2,cash_accepted=True,active=True);self.db.add(currency);await self.db.flush()
        rate=CurrencyExchangeRate(company_id=self.c,currency_id=currency.id,currency_code='SYN',foreign_units_per_base=2,effective_at=datetime.now(timezone.utc)-timedelta(days=1));self.db.add(rate);await self.db.commit()
        self.body['tenders'][0].update(currency_code='SYN',applied_original='16',tendered_original='20',exchange_rate_snapshot='2',exchange_rate_id=str(rate.id))
        await self.checkout(status=409,headers=self.cashier_headers);self.assertEqual(await self.stock(),100)
    async def configured_fx(self):
        settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.c))).scalar_one();settings.multi_currency_enabled=True
        currency=CompanyCurrency(company_id=self.c,code='SYN',display_name='Synthetic drawer FX',symbol='S',decimal_places=2,cash_accepted=True,active=True);self.db.add(currency);await self.db.flush()
        rate=CurrencyExchangeRate(company_id=self.c,currency_id=currency.id,currency_code='SYN',foreign_units_per_base=2,effective_at=datetime.now(timezone.utc)-timedelta(days=1));self.db.add(rate);await self.db.commit()
        self.body['tenders'][0].update(currency_code='SYN',applied_original='16',tendered_original='20',exchange_rate_snapshot='2',exchange_rate_id=str(rate.id))
        return currency
    async def test_fx_original_cash_partial_final_refunds_and_frozen_close(self):
        currency=await self.configured_fx();shift=await self.open_shift();result=await self.checkout(headers=self.cashier_headers)
        self.sid=UUID(result['sale']['id']);self.item=(await self.db.execute(select(SaleItem.id).where(SaleItem.sale_id==self.sid))).scalar_one();self.cash=next(r['id'] for r in result['tenders'] if r['method']=='cash');self.credit=next(r['id'] for r in result['tenders'] if r['method']=='credit')
        currency.active=False;await self.db.commit()
        first=self.command('.5','6',[(self.credit,'debt_reduction','4','4'),(self.cash,'paid_refund','2','4')]);await self.post(first,headers=self.cashier_headers)
        current=(await self.client.get('/api/shifts/current',headers=self.cashier_headers)).json();fx=next(r for r in current['currencies'] if r['currency_code']=='SYN');self.assertEqual(Decimal(fx['cash_sales']),16);self.assertEqual(Decimal(fx['cash_refunds']),4);self.assertEqual(Decimal(fx['expected_cash']),12)
        final=self.command('.5','6',[(self.cash,'paid_refund','6','12')]);await self.post(final,headers=self.cashier_headers);await self.post(final,headers=self.cashier_headers)
        response=await self.client.post('/api/shifts/'+shift['id']+'/close',headers=self.cashier_headers,json={'counted_balances':[{'currency_code':'USD','amount':'20'},{'currency_code':'SYN','amount':'0'}],'confirmed':True,'idempotency_key':str(uuid4())});self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(Decimal(response.json()['summary']['cash_refunds_base']),8);self.assertEqual(Decimal(response.json()['summary']['net_sales_base']),0);self.assertEqual(await self.stock(),100)
        for row in response.json()['currencies']:self.assertEqual(Decimal(row['variance']),0)
    async def test_changed_fx_precision_requires_target_shift_review(self):
        currency=await self.configured_fx();await self.open_shift();currency.decimal_places=3;await self.db.commit()
        rejected=await self.checkout(status=409,headers=self.cashier_headers);self.assertIn('precision',rejected['detail']);self.assertEqual(await self.stock(),100)
