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
from app.credit.service import CreditService
from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
from app.models import Product,InventoryBalance,CompanySetting,Customer,SaleItem,CreditReceivable,CreditRefundAdjustment,CreditSettlement
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  r=await AuthService(AuthRepository(db)).register(RegisterRequest(business_name='Synthetic tax credit race',email=f'{uuid4()}@example.com',password='Synthetic-Catalog-Only-123!',confirm_password='Synthetic-Catalog-Only-123!',owner_name='Synthetic Owner',owner_pin='1234',business_type='Retail',country='Zimbabwe',phone='000000000',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
  company,branch,shop,device=[UUID(r[k]['id']) for k in ('company','branch','shop','device')];token=r['token']
  product=Product(company_id=company,name='Synthetic tax penny',selling_price=Decimal('.05'),cost_price=Decimal('.01'),stock_qty=100)
  customer=Customer(company_id=company,customer_code='RACE',name='Synthetic race customer',credit_enabled=True,unlimited_credit=False,credit_limit=100)
  db.add_all([product,customer]);await db.flush();pid,cid=product.id,customer.id
  db.add(InventoryBalance(company_id=company,branch_id=branch,shop_id=shop,product_id=pid,quantity=100,reorder_level=0))
  settings=(await db.execute(select(CompanySetting).where(CompanySetting.company_id==company))).scalar_one();settings.tax_rate=15;settings.tax_inclusive=False;settings.shift_enforcement_enabled=False;await db.commit()
 async def sale():
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   result=await SalesService(SalesRepository(db)).create_sale(SaleCreate(company_id=company,branch_id=branch,device_id=device,client_sale_id=uuid4(),customer_id=cid,payment_method='credit',items=[SaleItemCreate(product_id=pid,quantity=3)]),actor=actor)
   item=(await db.execute(select(SaleItem.id).where(SaleItem.sale_id==result.id))).scalar_one()
   debt=(await db.execute(select(CreditReceivable.id).where(CreditReceivable.sale_id==result.id))).scalar_one()
   return result.id,item,debt
 def refund(sid,item):return RefundCreate(company_id=company,branch_id=branch,device_id=device,request_id=uuid4(),original_sale_id=sid,reason='Synthetic race return',items=[RefundItemCreate(sale_item_id=item,quantity=1)])
 async def submit(command):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:
    result=await SalesService(SalesRepository(db)).create_refund(command,actor=actor);return 200,str(result.id)
   except HTTPException as error:await db.rollback();return error.status_code,None
 sid,item,debt=await sale();command=refund(sid,item)
 equal=await asyncio.wait_for(asyncio.gather(*[submit(command) for _ in range(3)]),30)
 assert all(status==200 for status,_ in equal) and len(set(identity for _,identity in equal))==1,equal
 distinct=await asyncio.wait_for(asyncio.gather(submit(refund(sid,item)),submit(refund(sid,item))),30);assert all(status==200 for status,_ in distinct),distinct
 async with factory() as db:
  row=await db.get(CreditReceivable,debt);assert row.amount_credited==Decimal('.17') and row.outstanding_balance==0 and row.amount_settled==0
  assert (await db.execute(select(func.count(CreditRefundAdjustment.id)).where(CreditRefundAdjustment.receivable_id==debt))).scalar_one()==3
 sid,item,debt=await sale();command=refund(sid,item)
 async def collect():
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:await CreditService(CreditRepository(db)).create_settlement(SettlementCreate(company_id=company,branch_id=branch,receivable_id=debt,amount='.12',payment_method='cash',idempotency_key=str(uuid4())),actor);return 200,None
   except HTTPException as error:await db.rollback();return error.status_code,None
 race=await asyncio.wait_for(asyncio.gather(submit(command),collect()),30)
 assert sum(status==200 for status,_ in race)==1,race
 async with factory() as db:
  row=await db.get(CreditReceivable,debt);assert row.outstanding_balance>=0 and row.original_amount==row.amount_settled+row.amount_credited+row.outstanding_balance
  qty=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==company))).scalar_one();assert qty==(98 if race[0][0]==200 else 97)
 result={'synthetic_only':True,'equal_refunds_one_note':True,'distinct_partial_refunds_conserve_tax_and_debt_cents':True,'collection_refund_race_statuses':[status for status,_ in race],'no_negative_debt_or_duplicate_stock':True,'stock':str(qty),'provider_actions':False}
 Path('/tmp/phase11-tax-credit-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
