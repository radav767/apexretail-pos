"""Independent read-only reconciliation of the real pharmacy recovery fixture."""
import asyncio,json,os
from pathlib import Path
from uuid import UUID
from decimal import Decimal
from sqlalchemy import select,text,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models import Company,Sale,InventoryMovement,ProductBatch,BatchAllocation,BatchReturnHold,BatchReturnInspection,VariantInventoryBalance,InventoryBalance,Device
from app.models.business_operations import BatchStockOperation
url=make_url(os.environ['DATABASE_URL']);assert os.environ['APP_ENV']=='test' and url.database=='apex_phase11_shell_20261121' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
f=json.loads(Path('/tmp/phase11-pharmacy-recovery-result.json').read_text());c,b,p,v,d,e=map(UUID,[f[key] for key in ['company_id','branch_id','product_id','variant_id','device_id','employee_id']])
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 try:
  async with factory() as db:
   await db.execute(text('SET TRANSACTION READ ONLY'));assert (await db.execute(text('SHOW transaction_read_only'))).scalar_one()=='on';assert (await db.get(Company,c)).name=='Synthetic pharmacy recovery'
   balance=(await db.execute(select(VariantInventoryBalance.quantity).where(VariantInventoryBalance.company_id==c,VariantInventoryBalance.variant_id==v,VariantInventoryBalance.branch_id==b))).scalar_one();assert balance==8
   assert (await db.execute(select(func.coalesce(func.sum(InventoryBalance.quantity),0)).where(InventoryBalance.company_id==c,InventoryBalance.product_id==p))).scalar_one()==0
   lots=(await db.execute(select(ProductBatch).where(ProductBatch.company_id==c))).scalars().all();assert len(lots)==2 and sum(row.quantity for row in lots)==8
   assert {row.code:row.quantity for row in lots}=={'SYN-ORIGINAL-LOT':Decimal('6'),'SYN-INSPECTED-LOT':Decimal('2')}
   operations=(await db.execute(select(BatchStockOperation).where(BatchStockOperation.company_id==c))).scalars().all();inspections=(await db.execute(select(BatchReturnInspection).where(BatchReturnInspection.company_id==c))).scalars().all();holds=(await db.execute(select(BatchReturnHold).where(BatchReturnHold.company_id==c))).scalars().all()
   assert len(operations)==len(inspections)==len(holds)==1
   assert str(operations[0].request_id)==f['batch_request_id'] and str(inspections[0].request_id)==f['inspection_request_id']
   for row in [operations[0],inspections[0]]:assert row.actor_type=='employee' and row.actor_id==e and row.device_id==d and row.assignment_revision==1
   assert (await db.get(Device,d)).assignment_revision==3
   moves=(await db.execute(select(InventoryMovement).where(InventoryMovement.company_id==c))).scalars().all();assert len(moves)==3
   sales=(await db.execute(select(Sale).where(Sale.company_id==c))).scalars().all();assert len(sales)==2
   assert {str(row.id) for row in sales}=={f['sale_id'],f['refund_id']}
   allocations=(await db.execute(select(func.count()).select_from(BatchAllocation).where(BatchAllocation.batch_id.in_([row.id for row in lots])))).scalar_one();assert allocations==3
   print(json.dumps({'company_id':str(c),'verified_read_only':True,'variant_stock':str(balance),'parent_stock':0,'lot_quantities':{row.code:str(row.quantity) for row in lots},'batch_operations':1,'inspections':1,'return_holds':1,'allocations':allocations,'original_sale_and_refund':2,'original_movements':len(moves),'original_proofs_revision':1,'current_register_revision':3,'movements':[{'id':str(row.id),'type':row.movement_type,'quantity':str(row.quantity),'reference':row.reference} for row in moves]}))
 finally:await engine.dispose()
asyncio.run(main())
