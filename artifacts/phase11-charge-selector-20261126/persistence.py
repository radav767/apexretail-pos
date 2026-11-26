"""Independent read-only persistence of the controlled synthetic shell tenant."""
import asyncio,json,os
from pathlib import Path
from uuid import UUID
from sqlalchemy import select,func,text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models import Company,BusinessProfile,Product,Sale,InventoryMovement,WorkflowCommand
url=make_url(os.environ['DATABASE_URL']);assert os.environ['APP_ENV']=='test' and url.database=='apex_phase11_shell_20261121' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
fixture=json.loads(Path('/tmp/phase11-charge-shell-result.json').read_text());c=UUID(fixture['company_id'])
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 try:
  async with factory() as db:
   await db.execute(text('SET TRANSACTION READ ONLY'))
   assert (await db.execute(text('SHOW transaction_read_only'))).scalar_one()=='on'
   company=await db.get(Company,c);assert company.name=='Synthetic charge selector shells'
   profile=await db.get(BusinessProfile,c);assert str(profile.tip_product_id)==fixture['tail_id'] and profile.service_product_id is None
   products=(await db.execute(select(func.count()).select_from(Product).where(Product.company_id==c))).scalar_one();assert products==1039
   for model in (Sale,InventoryMovement,WorkflowCommand):assert (await db.execute(select(func.count()).select_from(model).where(model.company_id==c))).scalar_one()==0
   print(json.dumps({'company_id':str(c),'read_only':True,'products':products,'tip_product_id':str(profile.tip_product_id),'service_product_id':profile.service_product_id,'sales_stock_movements_and_workflow_commands':0}))
 finally:await engine.dispose()
asyncio.run(main())
