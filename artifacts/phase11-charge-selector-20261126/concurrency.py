"""Independent committed synthetic export snapshots and in-flight revocation."""
import asyncio,io,json,os
from datetime import datetime,timezone,timedelta
from uuid import UUID,uuid4
from zipfile import ZipFile
from unittest.mock import patch
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from fastapi import HTTPException
from app.auth.service import AuthService
from app.auth.repository import AuthRepository
from app.auth.schema import RegisterRequest
from app.auth.dependencies import resolve_auth_actor
from app.models import Sale
from app.accounting.exports import export_bundle,EXPORT_SQL
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase7c_test_phase7e' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 try:
  async with factory() as db:
   registration=await AuthService(AuthRepository(db)).register(RegisterRequest(owner_name='Synthetic export owner',owner_pin='1234',business_name='Synthetic export concurrency',business_type='Retail',country='Zimbabwe',phone='000000000',email=str(uuid4())+'@example.com',password='Synthetic-Only-123!',confirm_password='Synthetic-Only-123!',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
   c,b=UUID(registration['company']['id']),UUID(registration['branch']['id']);token=registration['token']
  from app.models import Product,InventoryMovement,Sale
  from app.business_operations.service import BusinessService
  from app.business_operations.schema import ProfileInput
  from app.products.selection import selection
  from sqlalchemy import select,func
  from sqlalchemy.exc import DBAPIError
  async with factory() as db:
   product=Product(company_id=c,name='Synthetic charge lock',product_type='service',track_inventory=False,selling_price=2);db.add(product);await db.commit();pid=product.id
  async with factory() as reader:
   actor=await resolve_auth_actor(token,reader);cached=await reader.get(Product,pid)
   async with factory() as writer:
    item=await writer.get(Product,pid);item.active=False;await writer.commit()
   assert cached.active
   try:await BusinessService(reader,actor).save_profile(ProfileInput(profile='retail',tip_product_id=pid));raise AssertionError('stale charge accepted')
   except HTTPException as exc:assert exc.status_code==400
  async with factory() as db:
   item=await db.get(Product,pid);item.active=True;await db.commit()
  locked,release,writer_started=asyncio.Event(),asyncio.Event(),asyncio.Event()
  async def configure():
   async with factory() as db:
    actor=await resolve_auth_actor(token,db);commit=db.commit
    async def held():locked.set();await asyncio.wait_for(release.wait(),10);await commit()
    with patch.object(db,'commit',held):return await BusinessService(db,actor).save_profile(ProfileInput(profile='retail',tip_product_id=pid))
  async def deactivate():
   async with factory() as db:
    writer_started.set();await db.execute(text('UPDATE products SET active=false WHERE id=:id'),{'id':pid});await db.commit()
  task=asyncio.create_task(configure());await asyncio.wait_for(locked.wait(),10)
  async with factory() as probe:
   try:await probe.execute(select(Product.id).where(Product.id==pid).with_for_update(nowait=True));raise AssertionError('charge row was not share-locked')
   except DBAPIError as exc:assert getattr(exc.orig,'sqlstate',None)=='55P03'
  writer=asyncio.create_task(deactivate());await asyncio.wait_for(writer_started.wait(),10);await asyncio.sleep(.05);assert not writer.done()
  release.set();configured=await asyncio.wait_for(task,10);await asyncio.wait_for(writer,10);assert str(configured['tip_product_id'])==str(pid)
  async with factory() as db:
   actor=await resolve_auth_actor(token,db);page=await selection(db,c,b,actor=actor,purpose='charge',selected_id=pid);assert page['total']==0
   assert (await db.execute(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.company_id==c))).scalar_one()==0
   assert (await db.execute(select(func.count()).select_from(Sale).where(Sale.company_id==c))).scalar_one()==0
  print(json.dumps({'company_id':str(c),'product_id':str(pid),'writer_first_stale_cache_status':400,'profile_first_share_lock_NOWAIT_sqlstate':'55P03','catalog_writer_waited_for_profile_commit':True,'later_deactivation_excluded_from_search':True,'stock_or_sale_effects':0}))
 finally:await engine.dispose()
asyncio.run(main())
