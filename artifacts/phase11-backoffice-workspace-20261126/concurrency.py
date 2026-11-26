"""Independent synthetic v2/v3 writers preserve current workspace and legacy proof."""
import asyncio,json,os
from uuid import UUID,uuid4
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from fastapi import HTTPException
from app.auth.service import AuthService
from app.auth.repository import AuthRepository
from app.auth.schema import RegisterRequest
from app.auth.dependencies import resolve_auth_actor
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase7c_test_phase7e' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 try:
  async with factory() as db:
   registration=await AuthService(AuthRepository(db)).register(RegisterRequest(owner_name='Synthetic workspace owner',owner_pin='1234',business_name='Synthetic workspace concurrency',business_type='Retail',country='Zimbabwe',phone='000000000',email=str(uuid4())+'@example.com',password='Synthetic-Only-123!',confirm_password='Synthetic-Only-123!',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
   c,b=UUID(registration['company']['id']),UUID(registration['branch']['id']);token=registration['token']
  from app.business_settings.preferences import SavePreferences,SaveAppearance,SaveWorkspace,save,effective
  from app.models import WorkflowCommand,InventoryMovement,Sale
  from sqlalchemy import select,func
  async def write(body):
   async with factory() as db:
    actor=await resolve_auth_actor(token,db)
    try:return await save(db,actor,body)
    except HTTPException as exc:return exc.status_code
  legacy=SavePreferences(company_id=c,request_id=uuid4(),scope='company',version=0,preferences={'selector_view':'cards'})
  old=await write(legacy)
  dark=SaveAppearance(contract_version='presentation-preferences-v2',company_id=c,request_id=uuid4(),scope='company',version=1,preferences={'tool_color_scheme':'dark','selector_view':'cards'})
  assert isinstance(await write(dark),dict)
  branch=SaveWorkspace(contract_version='backoffice-workspace-preferences-v3',company_id=c,request_id=uuid4(),scope='branch',branch_id=b,version=0,preferences={'tool_color_scheme':'system','backoffice_workspace_view':'list','backoffice_text_size':'large'})
  equal=await asyncio.gather(*(write(branch) for _ in range(3)));assert all(isinstance(row,dict) for row in equal) and len({row['id'] for row in equal})==1
  first=SaveWorkspace(contract_version='backoffice-workspace-preferences-v3',company_id=c,request_id=uuid4(),scope='company',version=2,preferences={'tool_color_scheme':'system','backoffice_workspace_view':'list'})
  second=SaveAppearance(contract_version='presentation-preferences-v2',company_id=c,request_id=uuid4(),scope='company',version=2,preferences={'selector_view':'table'})
  competing=await asyncio.gather(write(first),write(second));assert sum(isinstance(row,dict) for row in competing)==1 and competing.count(409)==1
  assert await write(legacy)==old
  recovery=SaveAppearance(contract_version='presentation-preferences-v2',company_id=c,request_id=uuid4(),scope='branch',branch_id=b,version=1,preferences={'selector_view':'table'})
  assert isinstance(await write(recovery),dict)
  async with factory() as db:
   actor=await resolve_auth_actor(token,db);result=await effective(db,actor,c)
   assert result['effective']['tool_color_scheme'] in {'light','system'}
   branch_result=await effective(db,actor,c,b)
   assert branch_result['effective']['backoffice_workspace_view']=='list' and branch_result['effective']['backoffice_text_size']=='large'
   count=(await db.execute(select(func.count()).select_from(WorkflowCommand).where(WorkflowCommand.company_id==c,WorkflowCommand.kind=='ui_preferences'))).scalar_one();assert count==5
   assert (await db.execute(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.company_id==c))).scalar_one()==0
   assert (await db.execute(select(func.count()).select_from(Sale).where(Sale.company_id==c))).scalar_one()==0
  print(json.dumps({'company_id':str(c),'three_equal_v3_requests_one_projection':True,'mixed_v2_v3_same_version_one_winner_one_409':True,'legacy_acknowledgement_unchanged':True,'v2_write_never_erases_workspace':True,'immutable_commands':count,'stock_or_sale_effects':0}))
 finally:await engine.dispose()
asyncio.run(main())
