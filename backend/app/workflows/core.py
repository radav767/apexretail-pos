from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select,text
from app.models import WorkflowRecord,WorkflowCommand,Branch,Device,AuditEvent
from app.sales.commands import actor_identity,fingerprint
from app.inventory.command_policy import context
from app.financial_access import enforce_actor_branch
from app.printing.service import permit
from app.subscriptions.write_policy import require_new_write

class WorkflowService:
    def __init__(self,db,actor):self.db,self.actor=db,actor
    def authorize(self,company,permission=None,owner=False):
        actor_identity(self.actor,company)
        if owner and self.actor.role not in {'owner','administrator'}:raise HTTPException(403,'Business owner or administrator approval is required')
        if permission:permit(self.actor,permission)
    async def record(self,company,record_id,kind=None,lock=False):
        self.authorize(company)
        query=select(WorkflowRecord).where(WorkflowRecord.company_id==company,WorkflowRecord.id==record_id)
        if lock:query=query.with_for_update()
        row=(await self.db.execute(query.execution_options(populate_existing=True))).scalar_one_or_none()
        if not row or kind and row.kind!=kind:raise HTTPException(404,'Workflow record not found')
        if row.branch_id:enforce_actor_branch(self.actor,row.branch_id)
        return row
    async def branch(self,company,branch):
        enforce_actor_branch(self.actor,branch)
        row=(await self.db.execute(select(Branch).where(Branch.id==branch,Branch.company_id==company,Branch.active.is_(True),Branch.deleted.is_(False)))).scalar_one_or_none()
        if not row:raise HTTPException(404,'Branch not found')
        return row
    def view(self,row):return {'id':str(row.id),'kind':row.kind,'state':row.state,'version':row.version,'company_id':str(row.company_id),'branch_id':str(row.branch_id) if row.branch_id else None,'payload':row.payload}
    async def begin(self,data,kind,branch=None,record_id=None,license_required=True):
        entity=self.actor.user if self.actor.actor_type=='user' else self.actor.employee
        await self.db.refresh(entity)
        if self.actor.pos_session:
            original_hash=self.actor.pos_session.token_hash
            await self.db.refresh(self.actor.pos_session)
            if self.actor.pos_session.token_hash!=original_hash:raise HTTPException(401,'POS session rotated; sign in again')
        proof=await context(self.db,self.actor,data.company_id,branch)
        await self.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'phase11-workflow:'+str(data.request_id)})
        old=await self.db.get(WorkflowCommand,data.request_id)
        if old:
            if old.company_id!=data.company_id or old.kind!=kind or record_id and old.record_id!=record_id or old.payload_hash!=fingerprint(data):raise HTTPException(409,'Workflow command identity has different values')
            if (old.actor_type,old.actor_id)!=(self.actor.actor_type,proof['actor_id']):raise HTTPException(403,'Original workflow command belongs to another actor')
            if (old.device_id,old.assignment_revision)!=(proof['device_id'],proof['assignment_revision']):raise HTTPException(403,'Original workflow register assignment changed')
            row=await self.record(data.company_id,old.record_id)
            if row.branch_id:await context(self.db,self.actor,data.company_id,row.branch_id)
            return old.result,None
        if license_required:await require_new_write(self.db,data.company_id)
        return None,proof
    async def finish(self,data,kind,row,proof,result=None):
        await self.db.flush()
        result=result or self.view(row)
        result={**result,'request_id':str(data.request_id)}
        self.db.add(WorkflowCommand(request_id=data.request_id,company_id=data.company_id,record_id=row.id,kind=kind,
            actor_type=self.actor.actor_type,actor_id=proof['actor_id'],device_id=proof['device_id'],assignment_revision=proof['assignment_revision'],payload_hash=fingerprint(data),result=result))
        self.db.add(AuditEvent(company_id=data.company_id,actor_user_id=proof['actor_id'] if self.actor.actor_type=='user' else None,
            actor_employee_id=proof['actor_id'] if self.actor.actor_type=='employee' else None,device_id=proof['device_id'],action='workflow_'+kind,details={'record_id':str(row.id),'request_id':str(data.request_id)}))
        await self.db.commit();return result
    def version(self,row,data,states):
        if row.version!=data.version or row.state not in states:raise HTTPException(409,'Workflow changed or is locked; reload before a new command')
    async def list(self,company,kind,branch=None):
        self.authorize(company,'inventory_receive' if kind in {'supplier','po'} else 'inventory_count' if kind=='count' else 'business_settings_manage')
        query=select(WorkflowRecord).where(WorkflowRecord.company_id==company,WorkflowRecord.kind==kind)
        if kind!='supplier' and self.actor.employee and self.actor.role not in {'owner','administrator'}:branch=self.actor.employee.branch_id
        if branch and kind!='supplier':await self.branch(company,branch);query=query.where(WorkflowRecord.branch_id==branch)
        result=[]
        for row in (await self.db.execute(query.order_by(WorkflowRecord.created_at.desc()).limit(100))).scalars():
            value=self.view(row)
            if row.kind=='count':value['payload']={'scope':row.payload['scope'],'positions':len(row.payload['rows']),'entered':sum(e['measured'] is not None for e in row.payload['rows'])}
            elif row.kind=='document':value['payload']={key:row.payload[key] for key in ('source_kind','source_id','template_id','content_digest')}
            elif row.kind=='template':value['payload']={key:row.payload[key] for key in ('family_id','document_version','paper')}
            result.append(value)
        return result


def atomic(method):
    from functools import wraps
    @wraps(method)
    async def execute(self,*args,**kwargs):
        try:return await method(self,*args,**kwargs)
        except Exception:
            await self.db.rollback()
            raise
    return execute
