"""Owned synthetic independent connections: saved quotation FX precision0–4."""
import asyncio,os,json
from pathlib import Path
from uuid import uuid4,UUID
from decimal import Decimal
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from fastapi import HTTPException
from app.auth.service import AuthService
from app.auth.repository import AuthRepository
from app.auth.schema import RegisterRequest
from app.auth.dependencies import resolve_auth_actor
from app.auth.security import hash_session_token
from app.models import Product,InventoryBalance,CompanySetting,CompanyCurrency,CurrencyExchangeRate,Employee,PosSession,SaleItem,CashierShift
from app.employees.permissions import normalize_permissions
from app.business_operations.service import BusinessService
from app.business_operations.schema import ProfileInput,OrderInput,OrderItemInput,QuotationTransition,SettlementInput
from app.business_operations.quotations import transition
from app.business_operations.saved_pricing import SavePricing,save,QuoteRepository
from app.business_operations.pricing_review import PricingReview,review
from app.sales.repository import SalesRepository
from app.sales.service import SalesService
from app.sales.schema import SaleCreate,RefundCreate,RefundItemCreate
from app.shifts.repository import ShiftRepository
from app.shifts.service import ShiftService
from app.shifts.schema import ShiftOpen,ShiftClose
from app.accounting.tender_flows import report
url=make_url(os.environ['DATABASE_URL']);assert os.environ['APP_ENV']=='test' and os.environ['QUOTATION_PRICING_MODE']=='test' and url.database=='apexretail_phase7c_test_phase7e' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  registration=await AuthService(AuthRepository(db)).register(RegisterRequest(owner_name='Synthetic precision owner',owner_pin='1234',business_name='Synthetic FX close acceptance',business_type='Retail',country='Zimbabwe',phone='000000000',email=str(uuid4())+'@example.com',password='Synthetic-Only-123!',confirm_password='Synthetic-Only-123!',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
  c,b,shop,d=[UUID(registration[k]['id']) for k in ('company','branch','shop','device')];owner=await resolve_auth_actor(registration['token'],db);await BusinessService(db,owner).save_profile(ProfileInput(profile='wholesale'))
  employee=Employee(company_id=c,shop_id=shop,branch_id=b,name='Synthetic authorized cashier',pin='test-no-pin-login',role='administrator',permissions=normalize_permissions('administrator',{}));product=Product(company_id=c,name='Synthetic precision stock',selling_price=Decimal('1.03'),cost_price=Decimal('.2'),stock_qty=100)
  db.add_all([employee,product]);await db.flush();pid=product.id;token='synthetic-FX-session-'+str(uuid4());db.add(PosSession(company_id=c,shop_id=shop,branch_id=b,device_id=d,employee_id=employee.id,token_hash=hash_session_token(token),expires_at=datetime.now(timezone.utc)+timedelta(hours=2)));db.add(InventoryBalance(company_id=c,branch_id=b,shop_id=shop,product_id=pid,quantity=100,reorder_level=0))
  settings=(await db.execute(select(CompanySetting).where(CompanySetting.company_id==c))).scalar_one();settings.multi_currency_enabled=True;settings.shift_enforcement_enabled=True;settings.tax_rate=15;settings.tax_inclusive=False
  currencies=[]
  for places in range(5):
   cur=CompanyCurrency(company_id=c,code='SY'+str(places),display_name='Synthetic precision '+str(places),symbol='S'+str(places),decimal_places=places,active=True,is_base=False);db.add(cur);await db.flush();currencies.append(cur.id);db.add(CurrencyExchangeRate(company_id=c,currency_id=cur.id,currency_code=cur.code,foreign_units_per_base=Decimal('1.23456789'),effective_at=datetime.now(timezone.utc)-timedelta(days=1),created_by_user_id=owner.user.id))
  await db.commit()
 async def opened():
  async with factory() as db:
   actor=await resolve_auth_actor(token,db);return await ShiftService(ShiftRepository(db)).open(ShiftOpen(idempotency_key=str(uuid4()),opening_balances=[{'currency_code':'USD','amount':20}]+[{'currency_code':'SY'+str(p),'amount':7} for p in range(5)]),actor)
 async def quote(code,shift):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db);svc=BusinessService(db,actor);row=await svc.create_order(OrderInput(branch_id=b,device_id=d,kind='quotation',request_id=uuid4()));row=await svc.add_item(row['id'],OrderItemInput(version=row['version'],product_id=pid,quantity=3))
   proposal=PricingReview(version=row['version'],lines=[{'item_id':row['items'][0]['id'],'quantity':3,'unit':'each','discount':Decimal('.01')}],sale_discount=Decimal('.02'),currency_code=code);reviewed=await review(svc,row['id'],proposal);await save(svc,row['id'],SavePricing(**proposal.model_dump(),request_id=uuid4(),expected_total=reviewed['total'],expected_display_total=reviewed['display_total']));row=await svc.order_out(await svc.order(row['id']))
   for action in ('sent','accepted'):row=await transition(svc,row['id'],QuotationTransition(version=row['version'],request_id=uuid4(),action=action,valid_until=datetime.now(timezone.utc)+timedelta(days=1) if action=='sent' else None))
   command=SettlementInput(version=row['version'],payment=SaleCreate(company_id=c,shift_id=shift,items=[],payment_method='cash',tendered_amount_original=Decimal(reviewed['display_total'])+1));return row,command,Decimal(reviewed['display_total'])
 async def settle(row,command):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,await BusinessService(db,actor).settle(row['id'],command)
   except HTTPException as error:await db.rollback();return error.status_code,None
 async def refund(command):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:
    result=await SalesService(SalesRepository(db,commit_on_save=False)).create_refund(command,actor=actor);await db.commit();return 200,result.id
   except HTTPException as error:await db.rollback();return error.status_code,None
 def count(view,code,amount):return ShiftClose(idempotency_key=str(uuid4()),confirmed=True,counted_balances=[{'currency_code':r['currency_code'],'amount':amount if r['currency_code']==code else r['opening_float']} for r in view['currencies'] if r['cash_accepted']])
 async def close(sid,command):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,await ShiftService(ShiftRepository(db)).close(sid,command,actor)
   except HTTPException as error:await db.rollback();return error.status_code,None
 async def locked(sid):
  async with factory() as db:
   try:
    await db.execute(select(CashierShift).where(CashierShift.id==sid).with_for_update(nowait=True));raise AssertionError('Expected actual held shift lock')
   except DBAPIError as error:
    assert getattr(error.orig,'sqlstate',None)=='55P03',str(error);await db.rollback()
 results=[]
 for places,curid in enumerate(currencies):
  code='SY'+str(places);view=await opened();sid=view['id'];row,command,original=await quote(code,sid)
  ready,release=asyncio.Event(),asyncio.Event();native=QuoteRepository.save_sale
  async def pause(repo,*args,**kwargs):
   result=await native(repo,*args,**kwargs);ready.set();await release.wait();return result
  closing=count(view,code,7+original)
  with patch.object(QuoteRepository,'save_sale',pause):
   pending=asyncio.create_task(settle(row,command))
   try:
    await asyncio.wait_for(ready.wait(),15);await locked(sid);waiting=asyncio.create_task(close(sid,closing));await asyncio.sleep(.05);assert not waiting.done()
   finally:release.set()
   posted=await asyncio.wait_for(pending,20);closed=await asyncio.wait_for(waiting,20)
  assert posted[0]==closed[0]==200,(posted,closed);snapshot=next(r for r in closed[1]['currencies'] if r['currency_code']==code);assert snapshot['decimal_places']==places and Decimal(snapshot['expected_cash'])==7+original and Decimal(snapshot['variance'])==0
  replay=await settle(row,command);assert replay[0]==200 and replay[1]['sale_id']==posted[1]['sale_id'];assert (await close(sid,closing))[1]['currencies']==closed[1]['currencies']
  # Close owns its shift lock first; an uncommitted quotation must wait then409.
  view=await opened();sid=view['id'];blocked,blocked_command,_=await quote(code,sid)
  async with factory() as db:
   actor=await resolve_auth_actor(token,db);await db.execute(select(CashierShift).where(CashierShift.id==sid).with_for_update());pending=asyncio.create_task(settle(blocked,blocked_command));await asyncio.sleep(.05);assert not pending.done();await ShiftService(ShiftRepository(db)).close(sid,count(view,code,7),actor)
  assert (await asyncio.wait_for(pending,20))[0]==409
  # Partial then final refund holds the original/shift locks before close.
  view=await opened();sid=view['id'];sold,payment,budget=await quote(code,sid);posted=await settle(sold,payment);assert posted[0]==200
  async with factory() as db:
   item=(await db.execute(select(SaleItem.id).where(SaleItem.sale_id==posted[1]['sale_id']))).scalar_one();cur=await db.get(CompanyCurrency,curid);cur.active=False;cur.decimal_places=(places+1)%5;db.add(CurrencyExchangeRate(company_id=c,currency_id=cur.id,currency_code=cur.code,foreign_units_per_base=99,effective_at=datetime.now(timezone.utc),created_by_user_id=owner.user.id));await db.commit()
  first=RefundCreate(request_id=uuid4(),company_id=c,original_sale_id=posted[1]['sale_id'],branch_id=b,device_id=d,shift_id=sid,reason='Synthetic precision partial return',items=[RefundItemCreate(sale_item_id=item,quantity=1)]);partial=await refund(first);assert partial[0]==200;assert (await refund(first))[1]==partial[1]
  final=first.model_copy(update={'request_id':uuid4(),'items':[RefundItemCreate(sale_item_id=item,quantity=2)]});ready,release=asyncio.Event(),asyncio.Event();native_refund=SalesRepository.save_sale
  async def pause_refund(repo,*args,**kwargs):
   result=await native_refund(repo,*args,**kwargs);ready.set();await release.wait();return result
  closing=count(view,code,7)
  with patch.object(SalesRepository,'save_sale',pause_refund):
   pending=asyncio.create_task(refund(final))
   try:await asyncio.wait_for(ready.wait(),15);await locked(sid);waiting=asyncio.create_task(close(sid,closing));await asyncio.sleep(.05);assert not waiting.done()
   finally:release.set()
   returned=await asyncio.wait_for(pending,20);closed=await asyncio.wait_for(waiting,20)
  assert returned[0]==closed[0]==200;(currency_row,)=tuple(r for r in closed[1]['currencies'] if r['currency_code']==code);assert currency_row['decimal_places']==places and Decimal(currency_row['expected_cash'])==7 and Decimal(currency_row['variance'])==0 and Decimal(currency_row['cash_sales'])==budget and Decimal(currency_row['cash_refunds'])==budget
  assert (await refund(final))[1]==returned[1];assert (await close(sid,closing))[1]['currencies']==closed[1]['currencies']
  async with factory() as db:
   cur=await db.get(CompanyCurrency,curid);cur.active=True;cur.decimal_places=places;await db.commit()
  results.append({'places':places,'original':str(budget),'actual_shift_lock_verified_nowait':True,'sale_first_close_waited':True,'close_first_conversion_409':True,'refund_first_close_waited':True,'deactivated_precision_drift_used_original_snapshot':True,'exact_sale_refund_close_recovery':True,'final_expected_original':'7','variance':'0'})
 # A catalogue writer commits after review but before the native product lock.
 view=await opened();sid=view['id'];race_row,race_command,race_budget=await quote('SY0',sid);entered=asyncio.Event();native_get=QuoteRepository.get_product
 async def entering(repo,*args):entered.set();return await native_get(repo,*args)
 async with factory() as writer:
  product=(await writer.execute(select(Product).where(Product.id==pid).with_for_update())).scalar_one();old_name=product.name;product.name='Concurrent catalogue rename';await writer.flush()
  with patch.object(QuoteRepository,'get_product',entering):
   pending=asyncio.create_task(settle(race_row,race_command));await asyncio.wait_for(entered.wait(),15);await locked(sid);assert not pending.done();await writer.commit();catalog_status=await asyncio.wait_for(pending,20)
 assert catalog_status[0]==409,catalog_status
 async with factory() as writer:
  product=await writer.get(Product,pid);product.name=old_name;await writer.commit()
 retried=await settle(race_row,race_command);assert retried[0]==200,retried;assert (await close(sid,count(view,'SY0',7+race_budget)))[0]==200
 Path('/tmp/phase11-shift-precision-concurrency.json').write_text(json.dumps({'synthetic_only':True,'results':results,'catalogue_writer_between_review_and_lock_409_then_exact_retry':True,'providers':False},indent=2)+'\n');print(json.dumps(results));await engine.dispose()
asyncio.run(main())
