"""Synthetic-only one-sale multi-leg checkout owns stock and debt atomically."""
import copy,unittest
from uuid import UUID,uuid4
from decimal import Decimal
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.models import Product,Sale,SaleTender,SaleCommandReceipt,SaleItem,InventoryMovement,InventoryBalance,CreditReceivable,Customer,CompanySubscription,CompanySetting,CompanyCurrency,CurrencyExchangeRate
from app.core.config import get_settings,Settings
import test_phase11_procurement as fixtures
class SplitCheckoutTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.ProcurementTests.cleanup
    async def asyncSetUp(self):
        await fixtures.ProcurementTests.asyncSetUp(self)
        self.settings=get_settings().model_copy(update={'app_env':'test','split_checkout_mode':'test'})
        self.patch=patch('app.sales.split.get_settings',return_value=self.settings);self.patch.start();self.addCleanup(self.patch.stop)
        customer=Customer(company_id=self.c,customer_code='SPLIT',name='Synthetic split debtor',credit_enabled=True,unlimited_credit=False,credit_limit=4);self.db.add(customer);await self.db.commit();self.cid=customer.id
        self.body={'contract_version':'split-v2','company_id':str(self.c),'branch_id':str(self.b),'device_id':str(self.device.id),'device_key':self.device.device_key,'assignment_revision':self.device.assignment_revision,'currency_config_version':1,'client_sale_id':str(uuid4()),'customer_id':str(self.cid),'expected_total':'12.00','items':[{'product_id':str(self.p),'quantity':'1'}],'tenders':[{'id':str(uuid4()),'method':'cash','currency_code':'USD','applied_original':'8','tendered_original':'10','applied_base':'8','exchange_rate_snapshot':'1'},{'id':str(uuid4()),'method':'credit','currency_code':'USD','applied_original':'4','applied_base':'4','exchange_rate_snapshot':'1'}]}
    async def request(self,body=None,status=200,headers=None):
        response=await self.client.post('/api/sales/v2/split',json=body or self.body,headers=headers);self.assertEqual(response.status_code,status,response.text)
        return response.json() if response.headers.get('content-type','').startswith('application/json') else {}
    async def stock(self):return (await self.db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==self.c,InventoryBalance.product_id==self.p))).scalar_one()
    async def count(self,model):return (await self.db.execute(select(func.count()).select_from(model).where(model.company_id==self.c))).scalar_one()
    async def test_one_sale_cash_credit_portion_change_exact_expired_replay_and_immutable_legs(self):
        result=await self.request();sale=result['sale'];self.assertFalse(result['release_enabled']);self.assertEqual(len(result['tenders']),2);self.assertEqual(Decimal(sale['total_amount']),12);self.assertEqual(Decimal(sale['amount_received']),10);self.assertEqual(Decimal(sale['change_due']),2);self.assertIsNone(sale['payment_currency_code']);self.assertIsNone(sale['payment_amount_original'])
        self.assertEqual(await self.stock(),99);self.assertEqual(await self.count(SaleTender),2);self.assertEqual(await self.count(InventoryMovement),1)
        debt=(await self.db.execute(select(CreditReceivable).where(CreditReceivable.company_id==self.c))).scalar_one();self.assertEqual(debt.original_amount,4);self.assertEqual(debt.outstanding_balance,4)
        again=await self.request();self.assertEqual(again['sale']['id'],sale['id']);self.assertEqual(await self.stock(),99)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit();self.settings.split_checkout_mode='disabled'
        self.assertEqual((await self.request())['sale']['id'],sale['id'])
        for sql in ['UPDATE sale_tenders SET applied_base=1 WHERE sale_id=:id','DELETE FROM sale_tenders WHERE sale_id=:id','UPDATE sales SET total_amount=1 WHERE id=:id','UPDATE sale_items SET quantity=2 WHERE sale_id=:id']:
            with self.assertRaises(DBAPIError):
                async with self.db.begin_nested():await self.db.execute(text(sql),{'id':UUID(sale['id'])})
        self.assertEqual(await self.stock(),99)
    async def test_mismatch_credit_limit_provider_offline_scope_and_mode_fail_before_effects(self):
        bad=copy.deepcopy(self.body);bad['tenders'][0]['applied_base']='7.99';await self.request(bad,409)
        bad=copy.deepcopy(self.body);bad['expected_total']='11.99';await self.request(bad,409)
        bad=copy.deepcopy(self.body);bad['tenders'][0]['method']='card';await self.request(bad,422)
        bad=copy.deepcopy(self.body);bad['client_created_at']=datetime.now(timezone.utc).isoformat();await self.request(bad,422)
        bad=copy.deepcopy(self.body);bad['company_id']=str(uuid4());await self.request(bad,403)
        self.settings.split_checkout_mode='disabled';await self.request(status=503);self.settings.split_checkout_mode='test'
        customer=await self.db.get(Customer,self.cid);customer.credit_limit=3;await self.db.commit();await self.request(status=409)
        self.assertEqual(await self.stock(),100);self.assertEqual(await self.count(SaleTender),0);self.assertEqual(await self.count(CreditReceivable),0)
    async def test_leg_failure_rolls_back_sale_debt_stock_and_original_command(self):
        from app.sales.split import SplitRepository
        original=SplitRepository.save_tenders
        async def fail(repo,sale):await original(repo,sale);raise RuntimeError('Synthetic tender failure before commit')
        with patch.object(SplitRepository,'save_tenders',fail):await self.request(status=500)
        self.assertEqual(await self.stock(),100);self.assertEqual(await self.count(SaleTender),0);self.assertEqual(await self.count(CreditReceivable),0);self.assertIsNone(await self.db.get(SaleCommandReceipt,UUID(self.body['client_sale_id'])))
        result=await self.request();self.assertEqual(await self.stock(),99);self.assertEqual(await self.count(SaleTender),2)
    async def test_cash_fx_and_credit_use_frozen_rates_and_original_currency_change(self):
        settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.c))).scalar_one();settings.multi_currency_enabled=True
        currency=CompanyCurrency(company_id=self.c,code='SYN',display_name='Synthetic FX',symbol='SYN',decimal_places=2,active=True,is_base=False,cash_accepted=True);self.db.add(currency);await self.db.flush()
        rate=CurrencyExchangeRate(company_id=self.c,currency_id=currency.id,currency_code='SYN',foreign_units_per_base=2,effective_at=datetime.now(timezone.utc)-timedelta(days=1),created_by_user_id=self.u);self.db.add(rate);await self.db.commit()
        self.body['tenders'][0].update(currency_code='SYN',applied_original='16',tendered_original='20',exchange_rate_snapshot='2',exchange_rate_id=str(rate.id))
        result=await self.request();cash=next(r for r in result['tenders'] if r['method']=='cash');self.assertEqual(Decimal(cash['change_original']),4);self.assertEqual(Decimal(cash['applied_base']),8);self.assertEqual(Decimal(result['sale']['change_due']),2)
    async def test_legacy_refund_cannot_restore_split_stock_or_erase_debt(self):
        result=await self.request();sid=UUID(result['sale']['id']);item=(await self.db.execute(select(SaleItem.id).where(SaleItem.sale_id==sid))).scalar_one()
        r=await self.client.post('/api/sales/refunds',json={'request_id':str(uuid4()),'company_id':str(self.c),'branch_id':str(self.b),'device_id':self.body['device_id'],'original_sale_id':str(sid),'reason':'Must use original split allocations','items':[{'sale_item_id':str(item),'quantity':'1'}]});self.assertEqual(r.status_code,409,r.text);self.assertEqual(await self.stock(),99)
        debt=(await self.db.execute(select(CreditReceivable).where(CreditReceivable.company_id==self.c))).scalar_one();self.assertEqual(debt.outstanding_balance,4)
    async def test_tax_once_partial_credit_collection_and_credit_role_gate(self):
        settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.c))).scalar_one();settings.tax_rate=15;settings.tax_inclusive=False
        product=await self.db.get(Product,self.p);product.selling_price=Decimal('.05');await self.db.commit()
        self.body['items'][0]['quantity']='3';self.body['expected_total']='.17';self.body['tenders'][0].update(applied_original='.10',tendered_original='.20',applied_base='.10');self.body['tenders'][1].update(applied_original='.07',applied_base='.07')
        result=await self.request();self.assertEqual(Decimal(result['sale']['tax_amount']),Decimal('.02'));self.assertEqual(Decimal(result['sale']['total_amount']),Decimal('.17'));self.assertEqual(await self.stock(),97)
        debt=(await self.db.execute(select(CreditReceivable).where(CreditReceivable.company_id==self.c))).scalar_one();self.assertEqual(debt.original_amount,Decimal('.07'))
        from app.credit.service import CreditService
        from app.credit.repository import CreditRepository
        from app.credit.schema import SettlementCreate
        await CreditService(CreditRepository(self.db)).create_settlement(SettlementCreate(company_id=self.c,branch_id=self.b,receivable_id=debt.id,amount=Decimal('.01'),payment_method='cash',idempotency_key=str(uuid4())),self.owner)
        await self.db.refresh(debt);self.assertEqual(debt.outstanding_balance,Decimal('.06'));self.assertEqual(await self.stock(),97)
        proof=await self.client.get(f'/api/reports/credit-reconciliation/{self.c}');self.assertEqual(proof.status_code,200,proof.text);self.assertTrue(proof.json()['items'][0]['ledger_matches'])
    async def test_cashier_credit_permission_and_production_mode_denied(self):
        from app.auth.security import create_employee_access_token
        from pydantic import ValidationError
        token=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='cashier')
        await self.request(headers={'Authorization':'Bearer '+token},status=403)
        with self.assertRaises(ValidationError):Settings(_env_file=None,database_url='postgresql+asyncpg://synthetic@127.0.0.1:1/unreachable',jwt_secret='synthetic-split-settings-only-secret-123456789',app_env='production',split_checkout_mode='test')
        self.assertEqual(await self.stock(),100)
