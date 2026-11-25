import asyncio,os,json
from pathlib import Path
from uuid import uuid4,UUID
from decimal import Decimal
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase7c_test_phase7e'
assert not url.host and url.query['host'].startswith('/tmp/apex-phase11-postgres-') and url.query['port']=='55441'
from fastapi import HTTPException
from app.auth.service import AuthService
from app.auth.repository import AuthRepository
from app.auth.schema import RegisterRequest
from app.auth.dependencies import resolve_auth_actor
from app.sales.service import SalesService
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate,SaleItemCreate,RefundCreate,RefundItemCreate
from app.business_operations.service import BusinessService
from app.business_operations.quotations import transition
from app.business_operations.saved_pricing import SavePricing,save
from app.business_operations.pricing_review import PricingReview,review
from app.business_operations.schema import ProfileInput,OrderInput,OrderItemInput,QuotationTransition,SettlementInput
from app.models import Product,InventoryBalance,CompanySetting,Sale,InventoryMovement,QuotationCommand,CompanyCurrency,CurrencyExchangeRate,SaleItem
from datetime import datetime,timezone,timedelta
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  r=await AuthService(AuthRepository(db)).register(RegisterRequest(business_name='Synthetic tax credit race',email=f'{uuid4()}@example.com',password='Synthetic-Catalog-Only-123!',confirm_password='Synthetic-Catalog-Only-123!',owner_name='Synthetic Owner',owner_pin='1234',business_type='Retail',country='Zimbabwe',phone='000000000',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
  company,branch,shop,device=[UUID(r[k]['id']) for k in ('company','branch','shop','device')];token=r['token']
  actor=await resolve_auth_actor(token,db);await BusinessService(db,actor).save_profile(ProfileInput(profile='wholesale'))
  product=Product(company_id=company,name='Synthetic quote stock',selling_price=12,cost_price=2,stock_qty=100)
  db.add(product);await db.flush();pid=product.id
  db.add(InventoryBalance(company_id=company,branch_id=branch,shop_id=shop,product_id=pid,quantity=100,reorder_level=0))
  settings=(await db.execute(select(CompanySetting).where(CompanySetting.company_id==company))).scalar_one();settings.tax_rate=15;settings.tax_inclusive=False;settings.shift_enforcement_enabled=False;settings.multi_currency_enabled=True
  currency=CompanyCurrency(company_id=company,code='JPY',display_name='Synthetic yen',symbol='JPY',decimal_places=0,active=True,is_base=False);db.add(currency);await db.flush();currency_id=currency.id
  db.add(CurrencyExchangeRate(company_id=company,currency_id=currency.id,currency_code='JPY',foreign_units_per_base=Decimal('1.05'),effective_at=datetime.now(timezone.utc)-timedelta(days=1),created_by_user_id=actor.user.id));await db.commit()
 async def quote(product_id):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db);svc=BusinessService(db,actor)
   row=await svc.create_order(OrderInput(branch_id=branch,device_id=device,request_id=uuid4(),kind='quotation'))
   row=await svc.add_item(row['id'],OrderItemInput(version=row['version'],product_id=product_id,quantity=2))
   proposal=PricingReview(currency_code='JPY',version=row['version'],lines=[{'item_id':row['items'][0]['id'],'quantity':2,'unit':'each','discount':1}])
   priced=await review(svc,row['id'],proposal)
   command=SavePricing(**proposal.model_dump(),request_id=uuid4(),expected_total=priced['total'],expected_display_total=priced['display_total'])
  async def saving(cmd):
   async with factory() as session:
    actor=await resolve_auth_actor(token,session)
    try:return 200,await save(BusinessService(session,actor),row['id'],cmd)
    except HTTPException as error:await session.rollback();return error.status_code,None
  equal=await asyncio.wait_for(asyncio.gather(*[saving(command) for _ in range(3)]),30)
  assert all(c==200 for c,_ in equal) and equal[0][1]==equal[1][1]==equal[2][1],equal
  stale=await asyncio.wait_for(asyncio.gather(*[saving(command.model_copy(update={'request_id':uuid4()})) for _ in range(2)]),30)
  assert all(c==409 for c,_ in stale),stale
  async with factory() as session:
   actor=await resolve_auth_actor(token,session);svc=BusinessService(session,actor)
   return await svc.order_out(await svc.order(row['id']))
 async def action(oid,command):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,await transition(BusinessService(db,actor),oid,command)
   except HTTPException as error:await db.rollback();return error.status_code,None
 async def settle(oid,command):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,(await BusinessService(db,actor).settle(oid,command))['sale_id']
   except HTTPException as error:await db.rollback();return error.status_code,None
 row=await quote(pid)
 for step in ('sent','accepted'):
  code,row=await action(row['id'],QuotationTransition(version=row['version'],request_id=uuid4(),action=step,valid_until=datetime.now(timezone.utc)+timedelta(days=1) if step=='sent' else None));assert code==200
 payment=SettlementInput(version=row['version'],payment=SaleCreate(company_id=company,tendered_amount_original=100,amount_received=100,items=[]))
 code,sale_id=await settle(row['id'],payment);assert code==200
 async with factory() as db:
  original=await db.get(Sale,sale_id);assert original.total_amount==Decimal('26.45') and original.payment_amount_original==28 and original.change_amount_original==72
  item=(await db.execute(select(SaleItem).where(SaleItem.sale_id==sale_id))).scalar_one();item_id=item.id
  currency=await db.get(CompanyCurrency,currency_id);currency.active=False;currency.decimal_places=4
  setting=(await db.execute(select(CompanySetting).where(CompanySetting.company_id==company))).scalar_one();setting.multi_currency_enabled=False;setting.currency_config_version+=1;await db.commit()
 async def refund(command,fault=False):
  from unittest.mock import patch
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:
    svc=SalesService(SalesRepository(db))
    if fault:
     with patch.object(svc.repo,'record_refund_command',side_effect=RuntimeError('Synthetic post-parent-flush failure')):await svc.create_refund(command,actor=actor)
    else:return 200,(await svc.create_refund(command,actor=actor)).id
   except HTTPException as error:await db.rollback();return error.status_code,None
   except RuntimeError:await db.rollback();return 599,None
 command=RefundCreate(company_id=company,original_sale_id=sale_id,branch_id=branch,device_id=device,request_id=uuid4(),reason='Synthetic original currency race',items=[RefundItemCreate(sale_item_id=item_id,quantity=Decimal('.001'))])
 zero=await refund(command);assert zero[0]==409,zero
 first=command.model_copy(update={'request_id':uuid4(),'items':[RefundItemCreate(sale_item_id=item_id,quantity=Decimal('.5'))]})
 fault=await refund(first,True);assert fault[0]==599
 async with factory() as db:
  assert (await db.execute(select(func.count(Sale.id)).where(Sale.original_sale_id==sale_id))).scalar_one()==0
  assert (await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.product_id==pid))).scalar_one()==98
 equal=await asyncio.wait_for(asyncio.gather(*[refund(first) for _ in range(3)]),30)
 assert all(c==200 for c,_ in equal) and len({i for _,i in equal})==1,equal
 final=first.model_copy(update={'request_id':uuid4(),'items':[RefundItemCreate(sale_item_id=item_id,quantity=Decimal('1.5'))]})
 race=await asyncio.wait_for(asyncio.gather(refund(final),refund(final.model_copy(update={'request_id':uuid4()}))),30)
 assert sum(c==200 for c,_ in race)==1 and any(c==400 for c,_ in race),race
 replay=await refund(first);assert replay[0]==200 and replay[1]==equal[0][1]
 async with factory() as db:
  rows=(await db.execute(select(Sale).where(Sale.original_sale_id==sale_id).order_by(Sale.created_at))).scalars().all()
  assert len(rows)==2 and sum(r.total_amount for r in rows)==Decimal('-26.45') and sum(r.payment_amount_original for r in rows)==-28
  assert (await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.product_id==pid))).scalar_one()==100
  assert (await db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==company))).scalar_one()==3
  from app.accounting.tender_flows import report
  actor=await resolve_auth_actor(token,db);now=datetime.now(timezone.utc)
  flow=await report(db,actor,company,now-timedelta(days=1),now+timedelta(days=1))
  assert flow['event_count']==3 and Decimal(flow['revenue'][0]['billed'])==0 and Decimal(flow['cash_original_units'][0]['known_net'])==0 and flow['cash_original_units'][0]['unknown_count']==0
  assert Decimal(flow['totals'][0]['applied_base'])==0 and Decimal(flow['totals'][0]['debt_delta'])==0

 result={'synthetic_only':True,'original_base':'26.45','original_JPY':'28','change_JPY':'72','deactivated_currency_and_changed_precision':True,'zero_original_unit_denied_before_stock':True,'post_parent_flush_fault_full_rollback':True,'three_equal_refunds_one_result':True,'competing_final_refund_statuses':[c for c,_ in race],'partial_final_original':[str(r.payment_amount_original) for r in rows],'refund_base_total':'-26.45','refund_original_total':'-28','stock':'100','stock_movements':3,'deferred_database_evidence_constraints_committed':True,'dated_flow_revenue_cash_and_debt_separate_and_zero_after_final':True,'providers':False}
 Path('/tmp/phase11-foreign-refund-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
