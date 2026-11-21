"""Independent synthetic connections; no providers, UI, offline or refund enablement."""
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
from app.sales.split_schema import SplitSaleCreate
from app.models import Product,InventoryBalance,Customer,CompanySetting,Sale,SaleTender,CreditReceivable,InventoryMovement,Device
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
 equal=await asyncio.wait_for(asyncio.gather(*[post(copy.deepcopy(base)) for _ in range(3)]),30);assert all(c==200 for c,_ in equal) and len({r['sale']['id'] for _,r in equal})==1,equal
 same_legs=copy.deepcopy(base);same_legs['tenders']=[{**leg,'id':str(uuid4())} for leg in base['tenders']];a={**same_legs,'client_sale_id':str(uuid4())};b={**same_legs,'client_sale_id':str(uuid4())}
 collision=await asyncio.wait_for(asyncio.gather(post(a),post(b)),30);assert sorted(c for c,_ in collision)==[200,409],collision
 async with factory() as db:
  customer=await db.get(Customer,cid);customer.credit_limit=11;await db.commit()
 attempts=[]
 for _ in range(2):
  body=copy.deepcopy(base);body['client_sale_id']=str(uuid4());body['tenders'][0].update(id=str(uuid4()),applied_original='9',applied_base='9');body['tenders'][1].update(id=str(uuid4()),applied_original='3',applied_base='3');attempts.append(body)
 budget=await asyncio.wait_for(asyncio.gather(*[post(body) for body in attempts]),30);assert sorted(c for c,_ in budget)==[200,409],budget
 async with factory() as db:
  stock=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.product_id==pid))).scalar_one();assert stock==97
  sales=(await db.execute(select(func.count()).select_from(Sale).where(Sale.company_id==company))).scalar_one();legs=(await db.execute(select(func.count()).select_from(SaleTender).where(SaleTender.company_id==company))).scalar_one();movements=(await db.execute(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.company_id==company))).scalar_one();debt=(await db.execute(select(func.sum(CreditReceivable.original_amount)).where(CreditReceivable.company_id==company))).scalar_one()
  assert (sales,legs,movements,debt)==(3,6,3,Decimal(11)),(sales,legs,movements,debt)
 result={'synthetic_only':True,'equal_ids_one_sale':True,'distinct_sales_same_legs_statuses':[c for c,_ in collision],'credit_limit_race_statuses':[c for c,_ in budget],'sales':sales,'legs':legs,'movements':movements,'stock':str(stock),'original_unpaid_credit':str(debt),'provider_invoked':False,'release_enabled':False}
 Path('/tmp/phase11-split-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
