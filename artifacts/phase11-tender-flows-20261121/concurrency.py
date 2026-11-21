"""Independent connections: split posting/refund versus close; no providers."""
import asyncio,os,json,copy
from pathlib import Path
from datetime import datetime,timezone,timedelta
from uuid import UUID,uuid4
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from fastapi import HTTPException
from app.auth.service import AuthService
from app.auth.repository import AuthRepository
from app.auth.schema import RegisterRequest
from app.auth.dependencies import resolve_auth_actor
from app.auth.security import hash_session_token
from app.sales.split import create,SplitRepository
from app.sales.split_refunds import create as refund_create
from app.sales.split_refunds import SplitRefundRepository
from app.sales.split_schema import SplitSaleCreate,SplitRefundCreate
from app.shifts.service import ShiftService
from app.shifts.repository import ShiftRepository
from app.shifts.schema import ShiftOpen,ShiftClose
from app.accounting.tender_flows import report
from app.models import Product,Customer,InventoryBalance,CompanySetting,Device,Employee,PosSession,Sale,SaleItem,SaleTenderRefund,CashierShiftCurrencySnapshot

url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and os.environ['SPLIT_CHECKOUT_MODE']=='test' and url.database=='apexretail_phase7c_test_phase7e' and not url.host and url.query['host'].startswith('/tmp/apex-phase11-postgres-') and url.query['port']=='55441'
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  r=await AuthService(AuthRepository(db)).register(RegisterRequest(owner_name='Synthetic race owner',owner_pin='1234',business_name='Synthetic shift/tender races',business_type='Retail',country='Zimbabwe',phone='000000000',email=str(uuid4())+'@example.com',password='Synthetic-Only-123!',confirm_password='Synthetic-Only-123!',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
  company,branch,shop,device=[UUID(r[k]['id']) for k in ('company','branch','shop','device')];owner_token=r['token'];register=await db.get(Device,device);revision=register.assignment_revision
  employee=Employee(company_id=company,shop_id=shop,branch_id=branch,name='Synthetic race cashier',pin='synthetic-fixture-no-pin-login',role='cashier',permissions={k:True for k in ('sales_process','sales_history_view','sales_refund','credit_sales','credit_settlements','shifts_open','shifts_close')})
  product=Product(company_id=company,name='Synthetic stock',selling_price=12,cost_price=2,stock_qty=100);customer=Customer(company_id=company,customer_code='RACE',name='Synthetic debtor',credit_enabled=True,unlimited_credit=True)
  db.add_all([employee,product,customer]);await db.flush();pid,cid=product.id,customer.id;token='synthetic-race-session-'+str(uuid4())
  db.add(PosSession(company_id=company,shop_id=shop,branch_id=branch,device_id=device,employee_id=employee.id,token_hash=hash_session_token(token),expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
  db.add(InventoryBalance(company_id=company,shop_id=shop,branch_id=branch,product_id=pid,quantity=100,reorder_level=0));settings=(await db.execute(select(CompanySetting).where(CompanySetting.company_id==company))).scalar_one();settings.shift_enforcement_enabled=True;await db.commit()
 async def opened():
  async with factory() as db:
   actor=await resolve_auth_actor(token,db);return (await ShiftService(ShiftRepository(db)).open(ShiftOpen(opening_balances=[{'currency_code':'USD','amount':20}],idempotency_key=str(uuid4())),actor))['id']
 def sale(shift):return SplitSaleCreate.model_validate({'contract_version':'split-v2','company_id':company,'branch_id':branch,'device_id':device,'assignment_revision':revision,'shift_id':shift,'currency_config_version':1,'client_sale_id':uuid4(),'customer_id':cid,'expected_total':12,'items':[{'product_id':pid,'quantity':1}],'tenders':[{'id':uuid4(),'method':'cash','currency_code':'USD','applied_original':8,'tendered_original':10,'applied_base':8,'exchange_rate_snapshot':1},{'id':uuid4(),'method':'credit','currency_code':'USD','applied_original':4,'applied_base':4,'exchange_rate_snapshot':1}]})
 async def post(data,refund=False):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,await (refund_create(db,actor,data) if refund else create(db,actor,data))
   except HTTPException as error:return error.status_code,None
 async def close(shift,data):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,await ShiftService(ShiftRepository(db)).close(shift,data,actor)
   except HTTPException as error:await db.rollback();return error.status_code,None
 def count(amount):return ShiftClose(counted_balances=[{'currency_code':'USD','amount':amount}],idempotency_key=str(uuid4()),confirmed=True)
 async def flow(shift):
  async with factory() as db:
   actor=await resolve_auth_actor(owner_token,db);return await report(db,actor,company,datetime.now(timezone.utc)-timedelta(days=1),datetime.now(timezone.utc)+timedelta(days=1),shift=shift)
 shift=await opened();data=sale(shift);closing=count(20)
 first=await asyncio.wait_for(asyncio.gather(post(data),post(data),close(shift,closing)),30)
 statuses=[r[0] for r in first];assert statuses in ([200,200,200],[409,409,200]),statuses
 saved=statuses[0]==200
 if saved:assert first[0][1]['sale']['id']==first[1][1]['sale']['id']
 frozen=await close(shift,closing);assert frozen[0]==200
 row=next(r for r in frozen[1]['currencies'] if r['currency_code']=='USD');assert Decimal(row['expected_cash'])==(28 if saved else 20),row
 assert (await flow(shift))['event_count']==(2 if saved else 0)
 shift2=await opened();second=await post(sale(shift2));assert second[0]==200;sid=UUID(second[1]['sale']['id'])
 async with factory() as db:item=(await db.execute(select(SaleItem.id).where(SaleItem.sale_id==sid))).scalar_one()
 refund=SplitRefundCreate.model_validate({'contract_version':'split-refund-v2','request_id':uuid4(),'company_id':company,'branch_id':branch,'device_id':device,'assignment_revision':revision,'shift_id':shift2,'original_sale_id':sid,'reason':'Synthetic close race','expected_total':12,'items':[{'sale_item_id':item,'quantity':1}],'allocations':[{'tender_id':r['id'],'kind':'debt_reduction' if r['method']=='credit' else 'paid_refund','amount_base':r['applied_base'],'amount_original':r['applied_original']} for r in second[1]['tenders']]})
 closing2=count(28);second_race=await asyncio.wait_for(asyncio.gather(post(refund,True),post(refund,True),close(shift2,closing2)),30)
 refund_statuses=[r[0] for r in second_race];assert refund_statuses in ([200,200,200],[409,409,200]),refund_statuses
 returned=refund_statuses[0]==200;closed=await close(shift2,closing2);assert closed[0]==200
 row=next(r for r in closed[1]['currencies'] if r['currency_code']=='USD');assert Decimal(row['expected_cash'])==(20 if returned else 28),row
 assert (await flow(shift2))['event_count']==(4 if returned else 2)
 # Expose a staged sale header/items/debt/proof, but no tender commit, on another connection.
 shift3=await opened();staged=sale(shift3);ready=asyncio.Event();release=asyncio.Event();save=SplitRepository.save_tenders
 async def pause(repo,s):ready.set();await release.wait();await save(repo,s)
 with patch.object(SplitRepository,'save_tenders',pause):
  pending=asyncio.create_task(post(staged))
  try:
   await asyncio.wait_for(ready.wait(),10);waiting_close=asyncio.create_task(close(shift3,count(28)));await asyncio.sleep(.05);assert not waiting_close.done()
   during=await flow(shift3);assert during['event_count']==0 and during['revenue']==[],during
  finally:release.set()
  committed=await asyncio.wait_for(pending,20);assert committed[0]==200,committed
  post_first_close=await asyncio.wait_for(waiting_close,20);assert post_first_close[0]==200
  assert Decimal(next(r for r in post_first_close[1]['currencies'] if r['currency_code']=='USD')['expected_cash'])==28
 after=await flow(shift3);assert after['event_count']==2 and Decimal(after['revenue'][0]['billed'])==12,after
 recovered=await asyncio.wait_for(asyncio.gather(*[post(staged) for _ in range(3)]),30);assert all(code==200 for code,_ in recovered) and len({r['sale']['id'] for _,r in recovered})==1
 # Refund holds the original/shift locks before a concurrently waiting close.
 shift4=await opened();original=await post(sale(shift4));assert original[0]==200;sid=UUID(original[1]['sale']['id'])
 async with factory() as db:item=(await db.execute(select(SaleItem.id).where(SaleItem.sale_id==sid))).scalar_one()
 body=refund.model_dump();body.update(request_id=uuid4(),shift_id=shift4,original_sale_id=sid,items=[{'sale_item_id':item,'quantity':1}],allocations=[{'tender_id':r['id'],'kind':'debt_reduction' if r['method']=='credit' else 'paid_refund','amount_base':r['applied_base'],'amount_original':r['applied_original']} for r in original[1]['tenders']]);full=SplitRefundCreate.model_validate(body)
 ready=asyncio.Event();release=asyncio.Event();save_refund=SplitRefundRepository.save_allocations
 async def pause_refund(repo,s):await save_refund(repo,s);ready.set();await release.wait()
 with patch.object(SplitRefundRepository,'save_allocations',pause_refund):
  pending=asyncio.create_task(post(full,True))
  try:
   await asyncio.wait_for(ready.wait(),10);waiting_close=asyncio.create_task(close(shift4,count(20)));await asyncio.sleep(.05);assert not waiting_close.done()
   during=await flow(shift4);assert during['event_count']==2 and Decimal(during['revenue'][0]['billed'])==12
  finally:release.set()
  committed=await asyncio.wait_for(pending,20);assert committed[0]==200
  refund_first_close=await asyncio.wait_for(waiting_close,20);assert refund_first_close[0]==200
  assert Decimal(next(r for r in refund_first_close[1]['currencies'] if r['currency_code']=='USD')['expected_cash'])==20
 recovered=await asyncio.wait_for(asyncio.gather(*[post(full,True) for _ in range(3)]),30);assert all(code==200 for code,_ in recovered) and len({r['sale']['id'] for _,r in recovered})==1
 after=await flow(shift4);assert after['event_count']==4 and Decimal(after['revenue'][0]['billed'])==0
 result={'synthetic_only':True,'sale_vs_close_statuses':statuses,'refund_vs_close_statuses':refund_statuses,'posting_first_close_waited_and_froze_28':True,'refund_first_close_waited_and_froze_20':True,'one_receipt_per_equal_committed_sale_and_refund_id':True,'closed_expected_original_units_match_commits':True,'report_cannot_see_uncommitted_partial_legs':True,'no_provider_invoked':True,'split_release_enabled':False}
 Path('/tmp/phase11-tender-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
