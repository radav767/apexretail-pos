import asyncio,os,json
from pathlib import Path
from uuid import UUID,uuid4
from decimal import Decimal
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase10_fresh_20261021t072213'
assert not url.host and url.query['host'].startswith('/tmp/apex-phase11-postgres-') and url.query['port']=='55441'
from fastapi import HTTPException
from app.auth.service import AuthService
from app.auth.repository import AuthRepository
from app.auth.schema import RegisterRequest
from app.auth.dependencies import resolve_auth_actor
from app.sales.service import SalesService
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate,SaleItemCreate
from app.models import Product,InventoryBalance,Sale,SaleItem,InventoryMovement,Customer,CreditReceivable,CompanySubscription
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  registered=await AuthService(AuthRepository(db)).register(RegisterRequest(owner_name='Synthetic Replay Owner',owner_pin='1234',business_name='Synthetic Sale Race',business_type='Retail',country='Zimbabwe',phone='000000000',email=f'{uuid4()}@example.com',password='synthetic-replay-password',confirm_password='synthetic-replay-password',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
  company,shop,branch,device,employee=[UUID(registered[k]['id']) for k in ('company','shop','branch','device','employee')]
  token=registered['token']
  product=Product(company_id=company,name='Synthetic race item',selling_price=12,stock_qty=100)
  customer=Customer(company_id=company,customer_code='SYNTHETIC',name='Synthetic credit customer',credit_enabled=True,unlimited_credit=False,credit_limit=100)
  db.add_all([product,customer]);await db.flush();product_id,customer_id=product.id,customer.id
  db.add(InventoryBalance(company_id=company,shop_id=shop,branch_id=branch,product_id=product_id,quantity=100,reorder_level=0));await db.commit()
 def command(key,**extra):
  return SaleCreate(company_id=company,branch_id=branch,device_id=device,employee_id=employee,client_sale_id=key,amount_received=100,items=[SaleItemCreate(product_id=product_id,quantity=2)],**extra)
 async def submit(data):
  async with factory() as db:
   actor=await resolve_auth_actor(token,db)
   try:return 200,str((await SalesService(SalesRepository(db)).create_sale(data,actor=actor)).id)
   except HTTPException as error:return error.status_code,None
 same=command(uuid4());results=await asyncio.wait_for(asyncio.gather(*(submit(same) for _ in range(3))),20)
 assert all(status==200 for status,_ in results) and len({sale for _,sale in results})==1
 other=command(uuid4());changed=other.model_copy(update={'amount_received':Decimal(101)})
 conflict=await asyncio.wait_for(asyncio.gather(submit(other),submit(changed)),20)
 assert sorted(status for status,_ in conflict)==[200,409]
 credit=command(uuid4(),payment_method='credit',customer_id=customer_id)
 credit_results=await asyncio.wait_for(asyncio.gather(submit(credit),submit(credit)),20)
 assert [status for status,_ in credit_results]==[200,200] and credit_results[0][1]==credit_results[1][1]
 async with factory() as db:
  counts={name:(await db.execute(select(func.count()).select_from(model).where(model.company_id==company))).scalar_one() for name,model in [('sales',Sale),('movements',InventoryMovement),('receivables',CreditReceivable)]}
  quantity=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==company))).scalar_one()
  outstanding=(await db.execute(select(CreditReceivable.outstanding_balance).where(CreditReceivable.company_id==company))).scalar_one()
  assert counts=={'sales':3,'movements':3,'receivables':1} and quantity==94 and outstanding==24
  sub=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();sub.status='suspended';await db.commit()
 assert (await submit(credit))[0]==200 and (await submit(command(uuid4())))[0]==402
 result={'synthetic_only':True,'same_command_statuses':[s for s,_ in results],'same_command_one_sale':True,'conflicting_payload_statuses':sorted(s for s,_ in conflict),'credit_retry_one_receivable':True,'counts':counts,'final_stock':str(quantity),'outstanding_credit':str(outstanding),'committed_replay_after_suspension':True,'new_write_after_suspension_denied':True}
 Path('/tmp/phase11-sale-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
