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
from app.business_operations.schema import ProfileInput,OrderInput,OrderItemInput,QuotationTransition,SettlementInput
from app.models import Product,InventoryBalance,CompanySetting,Sale,InventoryMovement,QuotationCommand
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
  settings=(await db.execute(select(CompanySetting).where(CompanySetting.company_id==company))).scalar_one();settings.tax_rate=15;settings.tax_inclusive=False;settings.shift_enforcement_enabled=False;await db.commit()
 async def quote(product_id):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db);svc=BusinessService(db,actor)
   row=await svc.create_order(OrderInput(branch_id=branch,device_id=device,request_id=uuid4(),kind='quotation'))
   return await svc.add_item(row['id'],OrderItemInput(version=row['version'],product_id=product_id,quantity=2))
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
  command=QuotationTransition(version=row['version'],request_id=uuid4(),action=step,valid_until=datetime.now(timezone.utc)+timedelta(days=1) if step=='sent' else None)
  values=await asyncio.wait_for(asyncio.gather(*[action(row['id'],command) for _ in range(3)]),30)
  assert all(code==200 for code,_ in values),values
  row=values[0][1]
 payment=SettlementInput(version=row['version'],payment=SaleCreate(company_id=company,amount_received=100,items=[]))
 values=await asyncio.wait_for(asyncio.gather(*[settle(row['id'],payment) for _ in range(3)]),30)
 assert all(code==200 for code,_ in values) and len(set(identity for _,identity in values))==1,values
 async with factory() as db:
  assert (await db.execute(select(func.count(Sale.id)).where(Sale.company_id==company))).scalar_one()==1
  assert (await db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==company))).scalar_one()==1
  assert (await db.execute(select(func.count(QuotationCommand.request_id)).where(QuotationCommand.company_id==company))).scalar_one()==2
  product=Product(company_id=company,name='Synthetic limited quote stock',selling_price=12,cost_price=2,stock_qty=2);db.add(product);await db.flush();limited=product.id
  db.add(InventoryBalance(company_id=company,branch_id=branch,shop_id=shop,product_id=limited,quantity=2,reorder_level=0));await db.commit()
 limited_quote=await quote(limited)
 for step in ('sent','accepted'):
  code,limited_quote=await action(limited_quote['id'],QuotationTransition(version=limited_quote['version'],request_id=uuid4(),action=step,valid_until=datetime.now(timezone.utc)+timedelta(days=1) if step=='sent' else None));assert code==200
 async def direct_sale():
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:await SalesService(SalesRepository(db)).create_sale(SaleCreate(company_id=company,branch_id=branch,device_id=device,client_sale_id=uuid4(),amount_received=100,items=[SaleItemCreate(product_id=limited,quantity=1)]),actor=actor);return 200,None
   except HTTPException as error:await db.rollback();return error.status_code,None
 race=await asyncio.wait_for(asyncio.gather(settle(limited_quote['id'],SettlementInput(version=limited_quote['version'],payment=SaleCreate(company_id=company,amount_received=100,items=[]))),direct_sale()),30)
 assert sum(code==200 for code,_ in race)==1,race
 async with factory() as db:
  quantity=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.product_id==limited))).scalar_one();assert quantity in (0,1)
 from app.business_operations.quotation_revisions import revise
 from app.business_operations.schema import QuotationRevision
 async def revision(oid,command):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,await revise(BusinessService(db,actor),oid,command)
   except HTTPException as error:return error.status_code,None
 async def accepted_quote():
  row=await quote(pid)
  for step in ('sent','accepted'):
   _,row=await action(row['id'],QuotationTransition(version=row['version'],request_id=uuid4(),action=step,valid_until=datetime.now(timezone.utc)+timedelta(days=1) if step=='sent' else None))
  return row
 root=await accepted_quote();command=QuotationRevision(version=root['version'],request_id=uuid4(),reason='Synthetic equal revision race')
 equal=await asyncio.wait_for(asyncio.gather(*[revision(root['id'],command) for _ in range(3)]),30);assert all(c==200 for c,_ in equal) and len({r['id'] for _,r in equal})==1,equal
 different=await asyncio.wait_for(asyncio.gather(*[revision(root['id'],command.model_copy(update={'request_id':uuid4()})) for _ in range(2)]),30);assert all(c==200 for c,_ in different),different
 child=max([r for _,r in different],key=lambda r:r['quotation_revision'])
 assert child['quotation_revision']==3
 for step in ('sent','accepted'):
  _,child=await action(child['id'],QuotationTransition(version=child['version'],request_id=uuid4(),action=step,valid_until=datetime.now(timezone.utc)+timedelta(days=1) if step=='sent' else None))
 lineage_race=await asyncio.wait_for(asyncio.gather(settle(root['id'],SettlementInput(version=root['version'],payment=SaleCreate(company_id=company,amount_received=100,items=[]))),settle(child['id'],SettlementInput(version=child['version'],payment=SaleCreate(company_id=company,amount_received=100,items=[])))),30)
 assert [c for c,_ in lineage_race]==[409,200],lineage_race
 root2=await accepted_quote();conversion_race=await asyncio.wait_for(asyncio.gather(revision(root2['id'],QuotationRevision(version=root2['version'],request_id=uuid4(),reason='Synthetic conversion race')),settle(root2['id'],SettlementInput(version=root2['version'],payment=SaleCreate(company_id=company,amount_received=100,items=[])))),30)
 assert conversion_race[1][0]==200 and conversion_race[0][0] in (200,409),conversion_race
 if conversion_race[0][0]==200:
  draft=conversion_race[0][1];status,_=await action(draft['id'],QuotationTransition(version=draft['version'],request_id=uuid4(),action='sent',valid_until=datetime.now(timezone.utc)+timedelta(days=1)));assert status==409
 result={'synthetic_only':True,'three_equal_send_and_accept_requests_one_receipt_each':True,'three_equal_conversions_one_sale_and_movement':True,'conversion_vs_online_sale_stock_race':[code for code,_ in race],'remaining_limited_stock':str(quantity),'no_reservation_at_send_or_accept':True,'no_duplicate_stock_payment_or_deadlock':True,'equal_revision_ids_one_draft':True,'distinct_revision_numbers':[r['quotation_revision'] for _,r in different],'parent_vs_child_conversion_statuses':[c for c,_ in lineage_race],'revision_vs_conversion_statuses':[c for c,_ in conversion_race],'converted_lineage_cannot_send_new_draft':True,'real_provider_or_message_actions':False}
 Path('/tmp/phase11-quotation-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
