"""Versioned synthetic split refund budgets, native tax/stock and atomic evidence."""
import copy,unittest
from uuid import UUID,uuid4
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import select,text
from sqlalchemy.exc import DBAPIError
from app.models import Sale,SaleItem,SaleTenderRefund,InventoryMovement,CreditReceivable,CreditRefundAdjustment,CompanySubscription,Product,CompanySetting,CompanyCurrency,CurrencyExchangeRate
from app.credit.service import CreditService
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
import test_phase11_split_checkout as fixtures

class SplitRefundTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.SplitCheckoutTests.cleanup
    asyncSetUp=fixtures.SplitCheckoutTests.asyncSetUp
    checkout=fixtures.SplitCheckoutTests.request
    stock=fixtures.SplitCheckoutTests.stock
    count=fixtures.SplitCheckoutTests.count
    async def original(self):
        result=await self.checkout()
        self.sid=UUID(result['sale']['id'])
        self.item=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==self.sid))).scalar_one().id
        self.cash=next(leg['id'] for leg in result['tenders'] if leg['method']=='cash')
        self.credit=next(leg['id'] for leg in result['tenders'] if leg['method']=='credit')
        return result
    def command(self,quantity,total,allocations):
        return {'contract_version':'split-refund-v2','request_id':str(uuid4()),'company_id':str(self.c),'original_sale_id':str(self.sid),'branch_id':str(self.b),'device_id':self.body['device_id'],'device_key':self.body['device_key'],'assignment_revision':self.body['assignment_revision'],'reason':'Synthetic original-leg return','expected_total':total,'items':[{'sale_item_id':str(self.item),'quantity':quantity}],'allocations':[{'tender_id':leg,'kind':kind,'amount_base':base,'amount_original':original} for leg,kind,base,original in allocations]}
    async def post(self,body,status=200,headers=None):
        response=await self.client.post('/api/sales/v2/split/refunds',json=body,headers=headers)
        self.assertEqual(response.status_code,status,response.text);return response.json() if response.headers.get('content-type','').startswith('application/json') else {}
    async def debt(self):return (await self.db.execute(select(CreditReceivable).where(CreditReceivable.sale_id==self.sid))).scalar_one()
    async def collect(self,value):
        debt=await self.debt()
        await CreditService(CreditRepository(self.db)).create_settlement(SettlementCreate(company_id=self.c,branch_id=self.b,receivable_id=debt.id,amount=value,payment_method='cash',idempotency_key=str(uuid4())),self.owner)
    async def test_debt_first_partial_final_and_expired_disabled_exact_replay(self):
        await self.original();commands=[]
        for qty,total,parts in [('.25','3',[(self.credit,'debt_reduction','3','3')]),('.25','3',[(self.credit,'debt_reduction','1','1'),(self.cash,'paid_refund','2','2')]),('.5','6',[(self.cash,'paid_refund','6','6')])]:
            command=self.command(qty,total,parts);result=await self.post(command);commands.append((command,result))
            self.assertEqual(result['sale']['payment_method'],'split_refund');self.assertIsNone(result['sale']['payment_currency_code']);self.assertFalse(result['release_enabled']);self.assertFalse(result['provider_invoked'])
            self.assertEqual((await self.post(command))['sale']['id'],result['sale']['id'])
        debt=await self.debt();self.assertEqual((debt.original_amount,debt.amount_credited,debt.amount_settled,debt.outstanding_balance),(4,4,0,0));self.assertEqual(await self.stock(),100)
        self.assertEqual(await self.count(InventoryMovement),4);self.assertEqual(await self.count(SaleTenderRefund),4);self.assertEqual(await self.count(CreditRefundAdjustment),2)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit();self.settings.split_checkout_mode='disabled'
        self.assertEqual((await self.post(commands[0][0]))['sale']['id'],commands[0][1]['sale']['id']);self.assertEqual(await self.stock(),100)
        changed=copy.deepcopy(commands[0][0]);changed['allocations'][0]['amount_base']='2';await self.post(changed,409)
        for sql in ['UPDATE sale_tender_refunds SET amount_base=1 WHERE refund_sale_id=:id','DELETE FROM sale_tender_refunds WHERE refund_sale_id=:id','UPDATE sales SET tax_amount=1 WHERE id=:id','DELETE FROM sale_items WHERE sale_id=:id']:
            with self.assertRaises(DBAPIError):
                async with self.db.begin_nested():await self.db.execute(text(sql),{'id':UUID(commands[0][1]['sale']['id'])})
    async def test_collected_credit_excess_and_stale_allocation_before_stock(self):
        await self.original();await self.collect('2')
        full=self.command('1','12',[(self.credit,'debt_reduction','2','2'),(self.cash,'paid_refund','10','10')]);await self.post(full,409);self.assertEqual(await self.stock(),99)
        stale=self.command('.5','6',[(self.credit,'debt_reduction','4','4'),(self.cash,'paid_refund','2','2')]);await self.post(stale,409);self.assertEqual(await self.stock(),99)
        correct=self.command('.5','6',[(self.credit,'debt_reduction','2','2'),(self.cash,'paid_refund','4','4')]);await self.post(correct)
        debt=await self.debt();self.assertEqual((debt.amount_settled,debt.amount_credited,debt.outstanding_balance),(2,2,0));self.assertEqual(await self.stock(),Decimal('99.5'))
        await self.post(self.command('.5','6',[(self.cash,'paid_refund','6','6')]),409);self.assertEqual(await self.stock(),Decimal('99.5'))
    async def test_allocation_failure_rolls_back_all_native_effects_then_exact_retry(self):
        await self.original();command=self.command('1','12',[(self.credit,'debt_reduction','4','4'),(self.cash,'paid_refund','8','8')])
        original_sale_count=await self.count(Sale);calls=[]
        from app.sales.split_refunds import SplitRefundRepository
        save=SplitRefundRepository.save_allocations
        async def fail(repo,sale):await save(repo,sale);calls.append(sale.id);raise RuntimeError('synthetic allocation failure')
        with patch.object(SplitRefundRepository,'save_allocations',fail):
            await self.post(command,500)
        self.assertEqual(len(calls),1);self.assertEqual(await self.stock(),99);self.assertEqual(await self.count(Sale),original_sale_count);self.assertEqual(await self.count(InventoryMovement),1);self.assertEqual(await self.count(CreditRefundAdjustment),0);self.assertEqual(await self.count(SaleTenderRefund),0)
        debt=await self.debt();self.assertEqual((debt.amount_credited,debt.outstanding_balance),(0,4))
        await self.post(command);self.assertEqual(await self.stock(),100)
    async def test_wrong_tenant_revision_and_unversioned_override_denied(self):
        await self.original();command=self.command('1','12',[(self.credit,'debt_reduction','4','4'),(self.cash,'paid_refund','8','8')])
        bad=copy.deepcopy(command);bad['company_id']=str(uuid4());await self.post(bad,403)
        bad=copy.deepcopy(command);bad['assignment_revision']+=1;await self.post(bad,403)
        bad=copy.deepcopy(command);bad['refund_method']='cash';await self.post(bad,422)
        bad=copy.deepcopy(command);bad['allocations'][0]['tender_id']=str(uuid4());await self.post(bad,409)
        from app.models import Branch
        branch=await self.db.get(Branch,self.b);other=Branch(company_id=self.c,shop_id=branch.shop_id,name='Synthetic unauthorized refund branch');self.db.add(other);await self.db.commit()
        bad=copy.deepcopy(command);bad['branch_id']=str(other.id);await self.post(bad,403)
        from app.auth.security import create_employee_access_token
        bearer=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='cashier')
        await self.post(command,403,{'Authorization':'Bearer '+bearer})
        self.settings.split_checkout_mode='disabled';await self.post(command,503);self.assertEqual(await self.stock(),99)
    async def test_committed_replay_retains_register_revision_and_user_revocation(self):
        await self.original();command=self.command('.25','3',[(self.credit,'debt_reduction','3','3')]);await self.post(command)
        from app.models import Device,User
        device=await self.db.get(Device,UUID(self.body['device_id']));device.assignment_revision+=1;await self.db.commit()
        await self.post(command,403);self.assertEqual(await self.stock(),Decimal('99.25'))
        user=await self.db.get(User,self.u);user.session_version+=1;await self.db.commit()
        await self.post(command,401);self.assertEqual(await self.stock(),Decimal('99.25'))
    async def test_extra_cash_refund_credit_note_and_missing_collection_proof_fail_closed(self):
        await self.original();await self.collect('4')
        command=self.command('.5','6',[(self.cash,'paid_refund','6','6')]);result=await self.post(command);debt=await self.debt()
        # A later insert cannot attach a debt adjustment to an existing cash-only refund.
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():
                self.db.add(CreditRefundAdjustment(company_id=self.c,receivable_id=debt.id,refund_sale_id=UUID(result['sale']['id']),amount=1));await self.db.flush()
                await self.db.execute(text('SET CONSTRAINTS split_credit_note_evidence IMMEDIATE'))
        self.assertEqual(await self.count(CreditRefundAdjustment),0);self.assertEqual(await self.stock(),Decimal('99.5'))
        debt=await self.debt();debt.amount_settled=2;debt.outstanding_balance=2;await self.db.commit()
        rejected=await self.post(self.command('.5','6',[(self.credit,'debt_reduction','2','2'),(self.cash,'paid_refund','4','4')]),409)
        self.assertIn('collection/credit allocation proof',rejected['detail']);self.assertEqual(await self.stock(),Decimal('99.5'))
    async def test_two_cash_legs_full_refund_has_no_debt_or_credit_note(self):
        self.body['tenders'][1].update(method='cash',tendered_original='4')
        result=await self.checkout();self.sid=UUID(result['sale']['id']);self.item=(await self.db.execute(select(SaleItem.id).where(SaleItem.sale_id==self.sid))).scalar_one()
        command=self.command('1','12',[(r['id'],'paid_refund',r['applied_base'],r['applied_original']) for r in result['tenders']]);await self.post(command)
        self.assertEqual(await self.count(CreditReceivable),0);self.assertEqual(await self.count(CreditRefundAdjustment),0);self.assertEqual(await self.stock(),100)
    async def test_credit_note_cannot_bind_another_original_receivable(self):
        await self.original();await self.collect('4');result=await self.post(self.command('.5','6',[(self.cash,'paid_refund','6','6')]))
        other=copy.deepcopy(self.body);other['client_sale_id']=str(uuid4());other['tenders']=[{**r,'id':str(uuid4())} for r in other['tenders']];second=await self.checkout(other)
        recv=(await self.db.execute(select(CreditReceivable.id).where(CreditReceivable.sale_id==UUID(second['sale']['id'])))).scalar_one()
        with self.assertRaisesRegex(DBAPIError,'original tenant/receivable differs'):
            async with self.db.begin_nested():
                self.db.add(CreditRefundAdjustment(company_id=self.c,receivable_id=recv,refund_sale_id=UUID(result['sale']['id']),amount=1));await self.db.flush();await self.db.execute(text('SET CONSTRAINTS split_credit_note_evidence IMMEDIATE'))
        self.assertEqual(await self.count(CreditRefundAdjustment),0);self.assertEqual(await self.stock(),Decimal('98.5'))
    async def test_original_fx_and_tax_penny_residuals_survive_configuration_change(self):
        product=await self.db.get(Product,self.p);product.selling_price=Decimal('.05')
        settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.c))).scalar_one();settings.tax_rate=15;settings.tax_inclusive=False;settings.multi_currency_enabled=True
        currency=CompanyCurrency(company_id=self.c,code='SYN',display_name='Synthetic FX',symbol='S',decimal_places=2,is_base=False,cash_accepted=True,active=True);self.db.add(currency);await self.db.flush()
        from datetime import datetime,timezone,timedelta
        rate=CurrencyExchangeRate(company_id=self.c,currency_id=currency.id,currency_code='SYN',foreign_units_per_base=2,effective_at=datetime.now(timezone.utc)-timedelta(seconds=1));self.db.add(rate);await self.db.commit()
        self.body.update(expected_total='.17',items=[{'product_id':str(self.p),'quantity':'3'}]);self.body['tenders'][0].update(currency_code='SYN',applied_original='.20',tendered_original='.30',applied_base='.10',exchange_rate_id=str(rate.id),exchange_rate_snapshot='2');self.body['tenders'][1].update(applied_original='.07',applied_base='.07')
        await self.original();settings.multi_currency_enabled=False;currency.active=False;await self.db.commit()
        amounts=[];taxes=[]
        for total,parts in [('.06',[(self.credit,'debt_reduction','.06','.06')]),('.05',[(self.credit,'debt_reduction','.01','.01'),(self.cash,'paid_refund','.04','.08')]),('.06',[(self.cash,'paid_refund','.06','.12')])]:
            result=await self.post(self.command('1',total,parts));amounts.append(Decimal(result['sale']['total_amount']));taxes.append(Decimal(result['sale']['tax_amount']))
        self.assertEqual(sum(amounts),Decimal('-.17'));self.assertEqual(sum(taxes),Decimal('-.02'));self.assertEqual(await self.stock(),100)
