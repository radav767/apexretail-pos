"""Append-only retention evidence; immutable assets/documents are never erased."""
from uuid import uuid4,UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select,text,func,Integer
from app.models import WorkflowRecord,Branch
from app.auth.dependencies import get_auth_actor
from app.db.session import get_db
from app.financial_access import enforce_actor_branch
from .core import WorkflowService,atomic
from .schema import MediaRetentionInput

async def quota_lock(db,company):
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'document-media-quota:'+str(company)})
async def policy(db,company,media_id):
    return (await db.execute(select(WorkflowRecord).where(WorkflowRecord.company_id==company,WorkflowRecord.kind=='media_retention',WorkflowRecord.payload['media_id'].as_string()==str(media_id)).execution_options(populate_existing=True))).scalar_one_or_none()
async def ensure_active(db,company,media_id):
    row=await policy(db,company,media_id)
    if row and row.state=='archived':raise HTTPException(409,'Logo is archived for new template selection; retained templates/documents remain available')

class RetentionService(WorkflowService):
    @atomic
    async def retain(self,data):
        self.authorize(data.company_id,'business_settings_manage',owner=True)
        old,proof=await self.begin(data,'media_retention',license_required=False)
        if old:return old
        if not data.reason.strip():raise HTTPException(422,'Retention reason is required')
        asset=await self.record(data.company_id,data.media_id,'document_media')
        # Same lock as uploads and new template selection, never asset mutation.
        await quota_lock(self.db,data.company_id)
        row=await policy(self.db,data.company_id,asset.id)
        if not data.archived:
            from app.subscriptions.write_policy import require_new_write
            await require_new_write(self.db,data.company_id)
        if not row:
            row=WorkflowRecord(id=uuid4(),company_id=data.company_id,branch_id=asset.branch_id,kind='media_retention',state='archived' if data.archived else 'active',payload={'media_id':str(asset.id),'reason':data.reason})
            self.db.add(row)
        else:
            row.state='archived' if data.archived else 'active';row.version+=1;row.payload={**row.payload,'reason':data.reason}
        return await self.finish(data,'media_retention',row,proof)
    async def catalog(self,company,branch=None):
        self.authorize(company,'business_settings_manage',owner=True)
        if branch:
            enforce_actor_branch(self.actor,branch)
            if not (await self.db.execute(select(Branch.id).where(Branch.id==branch,Branch.company_id==company))).scalar_one_or_none():raise HTTPException(404,'Retention branch not found')
        query=select(WorkflowRecord).where(WorkflowRecord.company_id==company,WorkflowRecord.kind.in_(['document_media','media_retention']))
        records=(await self.db.execute(query)).scalars().all()
        policies={r.payload['media_id']:r for r in records if r.kind=='media_retention'}
        result=[]
        for row in records:
            if row.kind!='document_media' or branch and row.branch_id not in (None,branch):continue
            p=policies.get(str(row.id));references=(await self.db.execute(select(func.count()).select_from(WorkflowRecord).where(WorkflowRecord.company_id==company,WorkflowRecord.kind=='template',func.jsonb_exists(WorkflowRecord.payload['media'],str(row.id))))).scalar_one()
            result.append({'id':str(row.id),'company_id':str(company),'branch_id':str(row.branch_id) if row.branch_id else None,'archived':p.state=='archived' if p else False,'template_references':references,**{k:row.payload[k] for k in ('sha256','width','height','size_bytes')}})
        result.sort(key=lambda r:r['id'])
        return {'assets':result,'retained_count':sum(r.kind=='document_media' for r in records),'archive_limit':64,'retained_bytes':sum(r.payload['size_bytes'] for r in records if r.kind=='document_media'),'deletion_enabled':False,'archiving_reclaims_quota':False}
router=APIRouter(prefix='/inventory/workflows/retention',tags=['Private evidence retention'])
def service(db=Depends(get_db),actor=Depends(get_auth_actor)):return RetentionService(db,actor)
@router.post('/media')
async def retain(data:MediaRetentionInput,svc=Depends(service)):return await svc.retain(data)
@router.get('/{company_id}/catalog')
async def catalog(company_id:UUID,branch_id:UUID|None=None,svc=Depends(service)):return await svc.catalog(company_id,branch_id)
