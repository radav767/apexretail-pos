"""Read-only independent reconciliation of the synthetic navigation recovery fixture."""
import asyncio,json,os
from pathlib import Path
from uuid import UUID
from sqlalchemy import select,func,text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models import Company,InventoryBalance,InventoryMovement,Sale
url=make_url(os.environ['DATABASE_URL']);assert os.environ['APP_ENV']=='test' and url.database=='apex_phase11_shell_20261121' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
fixture=json.loads(Path('/tmp/phase11-daily-navigation-result.json').read_text());c,b,p=map(UUID,[fixture['company_id'],fixture['branch_id'],fixture['product_id']])
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 try:
  async with factory() as db:
   await db.execute(text('SET TRANSACTION READ ONLY'));assert (await db.execute(text('SHOW transaction_read_only'))).scalar_one()=='on'
   company=await db.get(Company,c);assert company.name=='Synthetic daily navigation'
   balances=(await db.execute(select(InventoryBalance).where(InventoryBalance.company_id==c,InventoryBalance.product_id==p))).scalars().all();assert next(row.quantity for row in balances if row.branch_id==b)==96;assert sum(row.quantity for row in balances if row.branch_id!=b)==2
   movements=(await db.execute(select(InventoryMovement).where(InventoryMovement.company_id==c,InventoryMovement.product_id==p))).scalars().all()
   assert len([row for row in movements if row.movement_type=='transfer_out'])==1 and len([row for row in movements if row.movement_type=='transfer_in'])==1
   assert len([row for row in movements if row.reference=='SYN-COUNT'])==1
   sales=(await db.execute(select(func.count()).select_from(Sale).where(Sale.company_id==c))).scalar_one();assert sales==1
   print(json.dumps({'company_id':str(c),'read_only':True,'source_stock':'96','destination_stock':'2','one_transfer_out_one_transfer_in_one_count':True,'original_sales':sales,'refunds':0,'movements':[{'type':row.movement_type,'quantity':str(row.quantity),'reference':row.reference} for row in movements]}))
 finally:await engine.dispose()
asyncio.run(main())
