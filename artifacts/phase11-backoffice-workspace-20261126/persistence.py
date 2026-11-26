"""Read-only independent counts and scoped preference reconciliation of browser fixture."""
import asyncio,json,os
from pathlib import Path
from uuid import UUID
from sqlalchemy import select,func,text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models import Company,WorkflowCommand,WorkflowRecord,InventoryMovement,InventoryBalance,Sale
url=make_url(os.environ['DATABASE_URL']);assert os.environ['APP_ENV']=='test' and url.database=='apex_phase11_shell_20261121' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
fixture=json.loads(Path('/tmp/phase11-workspace-result.json').read_text());company=UUID(fixture['company_id'])
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 try:
  async with factory() as db:
   await db.execute(text('SET TRANSACTION READ ONLY'));assert (await db.execute(text('SHOW transaction_read_only'))).scalar_one()=='on'
   assert (await db.get(Company,company)).name=='Synthetic daily navigation'
   rows=(await db.execute(select(WorkflowRecord).where(WorkflowRecord.company_id==company,WorkflowRecord.kind=='ui_preferences'))).scalars().all();assert len(rows)==3
   scopes={row.payload['scope']:row for row in rows};assert scopes['company'].version==3 and scopes['branch'].version==1 and scopes['device'].version==2
   prefs=scopes['company'].payload['preferences'];assert prefs=={'selector_view':'cards','tool_color_scheme':'system','backoffice_workspace_view':'list','backoffice_text_size':'large'}
   assert scopes['branch'].payload['preferences']=={'backoffice_text_size':'standard'} and scopes['device'].payload['preferences']=={}
   commands=(await db.execute(select(func.count()).select_from(WorkflowCommand).where(WorkflowCommand.company_id==company,WorkflowCommand.kind=='ui_preferences'))).scalar_one();assert commands==6
   sales=(await db.execute(select(func.count()).select_from(Sale).where(Sale.company_id==company))).scalar_one();assert sales==1
   movements=(await db.execute(select(InventoryMovement).where(InventoryMovement.company_id==company))).scalars().all();assert len(movements)==2 and {m.movement_type for m in movements}=={'opening_stock','sale'}
   assert (await db.execute(select(func.sum(InventoryBalance.quantity)).where(InventoryBalance.company_id==company))).scalar_one()==99
   print(json.dumps({'company_id':str(company),'verified_read_only':True,'company_list_large_preserved_through_v2_writer':True,'branch_standard_device_clear':True,'scope_versions':{name:row.version for name,row in scopes.items()},'commands':commands,'original_sale':sales,'stock':99,'only_original_opening_and_sale_movements':True}))
 finally:await engine.dispose()
asyncio.run(main())
