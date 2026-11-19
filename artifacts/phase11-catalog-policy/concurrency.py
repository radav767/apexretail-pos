import asyncio,os,json
from pathlib import Path
from uuid import uuid4,UUID
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
from app.products.service import ProductService
from app.products.repository import ProductRepository
from app.products.schema import ProductCreate
from app.models import Product,InventoryBalance,InventoryMovement,CompanySubscription
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  registration=await AuthService(AuthRepository(db)).register(RegisterRequest(business_name='Synthetic catalog concurrency',email=f'{uuid4()}@example.com',password='Synthetic-Catalog-Only-123!',confirm_password='Synthetic-Catalog-Only-123!',owner_name='Synthetic Owner',owner_pin='1234',business_type='Retail',country='Zimbabwe',phone='000000000',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
  company=UUID(str(registration['company']['id']));branch=UUID(str(registration['branch']['id']))
 command=ProductCreate(company_id=company,branch_id=branch,create_request_key='synthetic-catalog-'+str(uuid4()),name='Concurrent opening',stock_qty=9)
 async def submit():
  async with factory() as db:
   try:return 200,(await ProductService(ProductRepository(db)).create_product(command)).id
   except HTTPException as error:await db.rollback();return error.status_code,None
 outcomes=await asyncio.wait_for(asyncio.gather(submit(),submit(),submit()),30)
 assert all(status==200 for status,_ in outcomes),outcomes
 assert len(set(identity for _,identity in outcomes))==1,outcomes
 async with factory() as db:
  counts={model.__tablename__:(await db.execute(select(func.count(model.id)).where(model.company_id==company))).scalar_one() for model in (Product,InventoryBalance,InventoryMovement)}
  assert counts=={'products':1,'inventory_balances':1,'inventory_movements':1},counts
  quantity=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==company))).scalar_one();assert quantity==9
  license=(await db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company))).scalar_one();license.status='expired';await db.commit()
 assert (await submit())[0]==402
 result={'synthetic_only':True,'three_same_creation_keys_one_product':True,'counts':counts,'opening_quantity':str(quantity),'expired_legacy_retry_denied_without_new_effects':True,'altered_payload_replay_not_certified':True,'provider_or_production_actions':False}
 Path('/tmp/phase11-catalog-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
