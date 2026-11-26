"""Synthetic-only large catalogue fixture; no stock/payment/provider actions."""
import asyncio,json,os,sys
from uuid import UUID
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.engine import make_url
from app.models import Company,Product,Sale,InventoryMovement
url=make_url(os.environ['DATABASE_URL']);assert os.environ['APP_ENV']=='test' and url.database=='apex_phase11_shell_20261121' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
c=UUID(sys.argv[1])
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 try:
  async with factory() as db:
   company=await db.get(Company,c);assert company and company.name=='Synthetic charge selector shells'
   existing=(await db.execute(select(func.count()).select_from(Product).where(Product.company_id==c))).scalar_one();assert existing<=1
   db.add_all([Product(company_id=c,name=f'Synthetic general filler {n:04}',product_type='standard',track_inventory=True,selling_price=5) for n in range(1005)]);await db.flush()
   eligible=[Product(company_id=c,name=f'Charge eligible {n:03}',product_type='service' if n%2 else 'non_stock',track_inventory=False,selling_price=2,cost_price=99) for n in range(32)];db.add_all(eligible)
   tail=Product(company_id=c,name='Saved charge beyond options',sku='TAIL-CHARGE',barcode='TAIL-SCAN',product_type='service',track_inventory=False,selling_price=3,cost_price=99);db.add(tail)
   tracked=Product(company_id=c,name='Tracked service excluded',product_type='service',track_inventory=True,selling_price=4);db.add(tracked)
   await db.commit()
   print(json.dumps({'company_id':str(c),'tail_id':str(tail.id),'first_id':str(eligible[0].id),'last_id':str(eligible[-1].id),'tracked_id':str(tracked.id),'eligible_total':33,'filler_count':1005}))
 finally:await engine.dispose()
asyncio.run(main())
