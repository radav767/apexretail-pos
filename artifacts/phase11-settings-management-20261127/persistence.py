"""Read-only reconciliation of settings/navigation and catalogue management acceptance."""
import asyncio,json,os
from pathlib import Path
from uuid import UUID
from sqlalchemy import select,text,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models import Company,Product,CompanySetting,Sale,InventoryMovement,InventoryBalance,WorkflowRecord,WorkflowCommand
url=make_url(os.environ['DATABASE_URL']);assert os.environ['APP_ENV']=='test' and url.database=='apex_phase11_shell_20261121' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
f=json.loads(Path('/tmp/phase11-settings-management-result.json').read_text());c=UUID(f['company_id'])
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 try:
  async with factory() as db:
   await db.execute(text('SET TRANSACTION READ ONLY'));assert (await db.execute(text('SHOW transaction_read_only'))).scalar_one()=='on';assert (await db.get(Company,c)).name=='Synthetic taxonomy and management'
   products=(await db.execute(select(Product).where(Product.company_id==c))).scalars().all();assert len(products)==38
   active=sum(p.active and not p.deleted for p in products);inactive=sum(not p.active and not p.deleted for p in products);deleted=sum(bool(p.deleted) for p in products);assert (active,inactive,deleted)==(30,7,1)
   tail=await db.get(Product,UUID(f['tail_product_id']));assert not tail.active and not tail.deleted and tail.name=='Renamed current management source'
   settings=(await db.execute(select(CompanySetting).where(CompanySetting.company_id==c))).scalar_one();assert settings.receipt_header=='Synthetic <logo> configuration' and settings.receipt_footer=='Original synthetic footer' and settings.tax_rate==5 and settings.currency_code=='USD'
   template=await db.get(WorkflowRecord,UUID(f['template_id']));assert template.company_id==c and template.kind=='template' and template.version==1 and template.payload['blocks'][0]['text']=='Synthetic preserved template'
   original=await db.get(WorkflowCommand,UUID(f['template_request_id']));assert original.record_id==template.id and original.result['version']==1
   commands=(await db.execute(select(WorkflowCommand).where(WorkflowCommand.company_id==c))).scalars().all();assert len(commands)==2 and {row.kind for row in commands}=={'template_publish','ui_preferences'}
   preferences=(await db.execute(select(WorkflowRecord).where(WorkflowRecord.company_id==c,WorkflowRecord.kind=='ui_preferences'))).scalar_one();assert preferences.version==1 and preferences.payload['preferences']=={'backoffice_workspace_view':'list','backoffice_text_size':'large'}
   for model in [Sale,InventoryMovement]:assert (await db.execute(select(func.count()).select_from(model).where(model.company_id==c))).scalar_one()==0
   assert (await db.execute(select(func.coalesce(func.sum(InventoryBalance.quantity),0)).where(InventoryBalance.company_id==c))).scalar_one()==0
   print(json.dumps({'company_id':str(c),'verified_read_only':True,'active':active,'inactive':inactive,'deleted_excluded':deleted,'tail_remains_inactive_current_name':True,'original_settings_retained':True,'original_template_version':1,'exact_original_template_request_retained':True,'company_preferences_version':1,'immutable_commands':2,'sales':0,'stock_movements':0,'stock':0}))
 finally:await engine.dispose()
asyncio.run(main())
