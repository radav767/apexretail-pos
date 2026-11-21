"""Independent synthetic connections; no providers, UI or offline enablement."""
import asyncio,os,json,copy
from pathlib import Path
from uuid import UUID,uuid4
from decimal import Decimal
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from fastapi import HTTPException
from app.auth.service import AuthService
from app.auth.repository import AuthRepository
from app.auth.schema import RegisterRequest
from app.auth.dependencies import resolve_auth_actor
from app.sales.split import create
from app.sales.split_schema import SplitSaleCreate,SplitRefundCreate
from app.sales.split_refunds import create as refund_create
from app.credit.service import CreditService
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
from app.models import Product,InventoryBalance,Customer,CompanySetting,Sale,SaleTender,CreditReceivable,InventoryMovement,Device,SaleItem,SaleTenderRefund,CreditRefundAdjustment
url=make_url(os.environ['DATABASE_URL']);assert os.environ['APP_ENV']=='test' and os.environ['SPLIT_CHECKOUT_MODE']=='test' and url.database=='apexretail_phase7c_test_phase7e' and not url.host and url.query['host'].startswith('/tmp/apex-phase11-postgres-') and url.query['port']=='55441'
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  r=await AuthService(AuthRepository(db)).register(RegisterRequest(owner_name='Synthetic split owner',owner_pin='1234',business_name='Synthetic split races',business_type='Retail',country='Zimbabwe',phone='000000000',email=str(uuid4())+'@example.com',password='Synthetic-Only-123!',confirm_password='Synthetic-Only-123!',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
  company,branch,shop,device=[UUID(r[k]['id']) for k in ('company','branch','shop','device')];token=r['token'];register=await db.get(Device,device);revision=register.assignment_revision
  product=Product(company_id=company,name='Synthetic mixed-tender stock',selling_price=12,cost_price=2,stock_qty=100);customer=Customer(company_id=company,customer_code='RACE',name='Synthetic split debtor',credit_enabled=True,unlimited_credit=False,credit_limit=100)
  db.add_all([product,customer]);await db.flush();pid,cid=product.id,customer.id
  db.add(InventoryBalance(company_id=company,branch_id=branch,shop_id=shop,product_id=pid,quantity=100,reorder_level=0));settings=(await db.execute(select(CompanySetting).where(CompanySetting.company_id==company))).scalar_one();settings.shift_enforcement_enabled=False;await db.commit()
 base={'contract_version':'split-v2','company_id':str(company),'branch_id':str(branch),'device_id':str(device),'assignment_revision':revision,'currency_config_version':1,'client_sale_id':str(uuid4()),'customer_id':str(cid),'expected_total':'12','items':[{'product_id':str(pid),'quantity':'1'}],'tenders':[{'id':str(uuid4()),'method':'cash','currency_code':'USD','applied_original':'8','tendered_original':'10','applied_base':'8','exchange_rate_snapshot':'1'},{'id':str(uuid4()),'method':'credit','currency_code':'USD','applied_original':'4','applied_base':'4','exchange_rate_snapshot':'1'}]}
 async def post(body):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,await create(db,actor,SplitSaleCreate.model_validate(body))
   except HTTPException as error:return error.status_code,None
 first=await post(base);assert first[0]==200,first;sid=UUID(first[1]['sale']['id'])
 async with factory() as db:
  item=(await db.execute(select(SaleItem.id).where(SaleItem.sale_id==sid))).scalar_one()
 cash,credit=[next(r['id'] for r in first[1]['tenders'] if r['method']==method) for method in ('cash','credit')]
 def command(qty,total,parts):
  return {'contract_version':'split-refund-v2','request_id':str(uuid4()),'company_id':str(company),'original_sale_id':str(sid),'branch_id':str(branch),'device_id':str(device),'assignment_revision':revision,'reason':'Synthetic concurrent original-leg return','expected_total':total,'items':[{'sale_item_id':str(item),'quantity':qty}],'allocations':[{'tender_id':leg,'kind':kind,'amount_base':amount,'amount_original':amount} for leg,kind,amount in parts]}
 async def refund(body):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,await refund_create(db,actor,SplitRefundCreate.model_validate(body))
   except HTTPException as error:return error.status_code,None
 quarter=command('.25','3',[(credit,'debt_reduction','3')])
 equal=await asyncio.wait_for(asyncio.gather(*[refund(copy.deepcopy(quarter)) for _ in range(3)]),30);assert all(c==200 for c,_ in equal) and len({r['sale']['id'] for _,r in equal})==1,equal
 next_quarter=command('.25','3',[(credit,'debt_reduction','1'),(cash,'paid_refund','2')]);changed={**next_quarter,'request_id':str(uuid4())}
 race=await asyncio.wait_for(asyncio.gather(refund(next_quarter),refund(changed)),30);assert sorted(c for c,_ in race)==[200,409],race
 final=await refund(command('.5','6',[(cash,'paid_refund','6')]));assert final[0]==200,final
 # A separate original races full return against a positive credit collection.
 original2=copy.deepcopy(base);original2['client_sale_id']=str(uuid4());original2['tenders']=[{**r,'id':str(uuid4())} for r in base['tenders']]
 second=await post(original2);assert second[0]==200,second;sid=UUID(second[1]['sale']['id'])
 cash,credit=[next(r['id'] for r in second[1]['tenders'] if r['method']==method) for method in ('cash','credit')]
 async with factory() as db:
  item=(await db.execute(select(SaleItem.id).where(SaleItem.sale_id==sid))).scalar_one();recv=(await db.execute(select(CreditReceivable.id).where(CreditReceivable.sale_id==sid))).scalar_one()
 async def collect():
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:
    await CreditService(CreditRepository(db)).create_settlement(SettlementCreate(company_id=company,branch_id=branch,receivable_id=recv,amount=2,payment_method='cash',idempotency_key=str(uuid4())),actor);return 200
   except HTTPException as error:await db.rollback();return error.status_code
 collected=await asyncio.wait_for(asyncio.gather(collect(),refund(command('1','12',[(credit,'debt_reduction','4'),(cash,'paid_refund','8')]))),30)
 collection_status,refund_status=collected[0],collected[1][0];assert sorted((collection_status,refund_status))==[200,409],collected
 async with factory() as db:
  stock=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.product_id==pid))).scalar_one();assert stock==(99 if collection_status==200 else 100),stock
  debt=await db.get(CreditReceivable,recv);assert debt.outstanding_balance==(2 if collection_status==200 else 0)
  allocations=(await db.execute(select(func.sum(SaleTenderRefund.amount_base)).where(SaleTenderRefund.company_id==company))).scalar_one();assert allocations==(12 if collection_status==200 else 24)
  assert (await db.execute(select(func.sum(CreditRefundAdjustment.amount)).where(CreditRefundAdjustment.company_id==company))).scalar_one()==(4 if collection_status==200 else 8)
 result={'synthetic_only':True,'equal_refund_ids_one_receipt':True,'distinct_refund_stale_allocations':[c for c,_ in race],'collection_vs_full_refund':[collection_status,refund_status],'original_allocation_budget_conserved':True,'stock':str(stock),'provider_invoked':False,'release_enabled':False}
 Path('/tmp/phase11-split-refund-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
