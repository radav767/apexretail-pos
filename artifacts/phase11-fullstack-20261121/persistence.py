import asyncio,json,os
from pathlib import Path
from uuid import UUID
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from app.db.session import SessionLocal,engine
from app.models import InventoryMovement,WorkflowCommand,WorkflowRecord,WorkflowCancellation,InventoryBalance
u=make_url(os.environ['DATABASE_URL']);assert u.database=='apex_phase11_fullstack_20261121' and not u.host and u.query['host'].startswith('/tmp/apex-phase11-postgres-') and os.environ['APP_ENV']=='test'
async def main():
 r=json.loads(Path('/tmp/phase11-fullstack-result.json').read_text());c=UUID(r['tenant']);p=UUID(r['product_id'])
 async with SessionLocal() as db:
  quantity=(await db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==c,InventoryBalance.product_id==p))).scalar_one();assert quantity==208
  movements=[{'kind':kind,'count':n,'quantity':str(q)} for kind,n,q in (await db.execute(select(InventoryMovement.movement_type,func.count(),func.sum(InventoryMovement.quantity)).where(InventoryMovement.company_id==c).group_by(InventoryMovement.movement_type))).all()]
  commands=dict((await db.execute(select(WorkflowCommand.kind,func.count()).where(WorkflowCommand.company_id==c).group_by(WorkflowCommand.kind))).all());assert commands['po_receive']==102 and commands['supplier_return']==1 and commands['count_approve']==1
  fences=(await db.execute(select(func.count()).select_from(WorkflowCancellation).where(WorkflowCancellation.company_id==c))).scalar_one();assert fences==2
  count=await db.get(WorkflowRecord,UUID(r['count_id']));assert count.state=='approved'
  result={'synthetic_only':True,'stock':str(quantity),'command_counts':commands,'movements':movements,'cancellation_fences':fences,'count_state':count.state}
  print(json.dumps(result));Path('/tmp/phase11-fullstack-persistence.json').write_text(json.dumps(result,indent=2)+'\n')
 await engine.dispose()
asyncio.run(main())
