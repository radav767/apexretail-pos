"""Scoped presentation only; no terminal/payment authority or arbitrary payloads."""
from typing import Literal
from uuid import UUID,NAMESPACE_URL,uuid5
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,text
from app.auth.dependencies import get_auth_actor
from app.db.session import get_db
from app.models import Device,WorkflowRecord
from app.printing.service import permit
from app.workflows.core import WorkflowService

class Values(BaseModel):
    model_config=ConfigDict(extra='forbid')
    selector_view:Literal['table','cards']|None=None

class SavePreferences(BaseModel):
    model_config=ConfigDict(extra='forbid')
    company_id:UUID
    request_id:UUID
    scope:Literal['company','branch','device']
    branch_id:UUID|None=None
    device_id:UUID|None=None
    version:int=Field(ge=0,le=2147483646)
    preferences:Values


def key(company,branch=None,device=None,revision=None):
    return uuid5(NAMESPACE_URL,f'apexretail:selector-preferences:v1:{company}:{branch}:{device}:{revision}')

async def dimensions(svc,company,branch,device):
    if svc.actor.employee and svc.actor.role not in {'owner','administrator'}:
        branch=branch or svc.actor.employee.branch_id
    revision=None
    if device:
        row=(await svc.db.execute(select(Device).where(Device.id==device,Device.company_id==company).execution_options(populate_existing=True))).scalar_one_or_none()
        if not row or not row.active or row.deleted or row.removed_at or row.deactivated_at:raise HTTPException(404,'Active preference device not found')
        if branch and branch!=row.branch_id:raise HTTPException(403,'Device preference branch differs')
        if svc.actor.employee and (not svc.actor.pos_session or svc.actor.pos_session.device_id!=device):raise HTTPException(403,'Use the current assigned preference device')
        branch,revision=row.branch_id,row.assignment_revision
    if branch:await svc.branch(company,branch)
    await svc.current_context(company,branch)
    return branch,revision

async def effective(db,actor,company,branch=None,device=None):
    svc=WorkflowService(db,actor)
    await svc.current_context(company)
    branch,revision=await dimensions(svc,company,branch,device)
    ids=[('company',key(company))]
    if branch:ids.append(('branch',key(company,branch)))
    if device:ids.append(('device',key(company,branch,device,revision)))
    rows={row.id:row for row in (await db.execute(select(WorkflowRecord).where(WorkflowRecord.company_id==company,WorkflowRecord.kind=='ui_preferences',WorkflowRecord.id.in_([id for _,id in ids])))).scalars()}
    values={'selector_view':'table'};sources={'selector_view':'default'};scopes=[]
    for level,id in ids:
        row=rows.get(id);preferences=row.payload['preferences'] if row else {}
        values.update(preferences);sources.update({name:level for name in preferences})
        scopes.append({'scope':level,'version':row.version if row else 0,'preferences':preferences})
    return {'contract_version':'selector-preferences-v1','company_id':str(company),'branch_id':str(branch) if branch else None,'device_id':str(device) if device else None,'assignment_revision':revision,'effective':values,'sources':sources,'scopes':scopes}

async def save(db,actor,data):
    svc=WorkflowService(db,actor);await svc.current_context(data.company_id)
    permit(actor,'business_settings_manage')
    if data.scope=='company':
        if data.branch_id or data.device_id:raise HTTPException(422,'Company preference has no branch/device')
        svc.authorize(data.company_id,owner=True)
    elif not data.branch_id or data.scope=='branch' and data.device_id or data.scope=='device' and not data.device_id:
        raise HTTPException(422,'Select the exact preference branch/device scope')
    branch,revision=await dimensions(svc,data.company_id,data.branch_id,data.device_id)
    # Company scope remains tenant-wide even for an administrator with a branch.
    if data.scope=='company':branch=None
    record_id=key(data.company_id,branch,data.device_id,revision)
    old,proof=await svc.begin(data,'ui_preferences',branch,record_id)
    if old:return old
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'phase11-ui-preferences:'+str(record_id)})
    row=(await db.execute(select(WorkflowRecord).where(WorkflowRecord.id==record_id,WorkflowRecord.company_id==data.company_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if (row.version if row else 0)!=data.version:raise HTTPException(409,'Preferences changed; reload before saving')
    payload={'contract_version':'selector-preferences-v1','scope':data.scope,'device_id':str(data.device_id) if data.device_id else None,'assignment_revision':revision,'preferences':data.preferences.model_dump(exclude_none=True)}
    if row:row.payload=payload;row.version+=1
    else:row=WorkflowRecord(id=record_id,company_id=data.company_id,branch_id=branch,kind='ui_preferences',state='active',version=1,payload=payload);db.add(row)
    return await svc.finish(data,'ui_preferences',row,proof)

router=APIRouter(prefix='/settings/preferences',tags=['Scoped presentation preferences'])
@router.get('/{company_id}')
async def read_preferences(company_id:UUID,branch_id:UUID|None=None,device_id:UUID|None=None,db=Depends(get_db),actor=Depends(get_auth_actor)):
    return await effective(db,actor,company_id,branch_id,device_id)

@router.put('/{company_id}')
async def save_preferences(company_id:UUID,data:SavePreferences,db=Depends(get_db),actor=Depends(get_auth_actor)):
    if company_id!=data.company_id:raise HTTPException(422,'Preference tenant differs')
    return await save(db,actor,data)
