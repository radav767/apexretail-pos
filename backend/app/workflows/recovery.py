from fastapi import HTTPException
from sqlalchemy import text
from app.models import WorkflowCommand,WorkflowCancellation
from .core import WorkflowService,atomic
from . import schema
from app.sales.commands import fingerprint
INPUTS={
 "media_upload":schema.MediaInput,
 "document_output":schema.OutputInput,
 "supplier_create":schema.SupplierInput,"supplier_update":schema.SupplierUpdate,"po_create":schema.POInput,"po_edit":schema.PODraftUpdate,
 "po_approve":schema.VersionCommand,"po_cancel":schema.ReviewInput,"po_receive":schema.ReceiveInput,"supplier_return":schema.SupplierReturnInput,
 "count_create":schema.CountInput,"count_measure":schema.MeasureInput,"count_submit":schema.VersionCommand,"count_recount":schema.ReviewInput,
 "count_approve":schema.ReviewInput,"count_reject":schema.ReviewInput,"template_publish":schema.TemplateInput,"document_render":schema.DocumentInput}

class RecoveryService(WorkflowService):
    @atomic
    async def cancel_uncommitted(self,data):
        proof=await self.current_context(data.company_id)
        try:original=INPUTS[data.original_kind].model_validate(data.original_payload)
        except (KeyError,ValueError):raise HTTPException(422,'Original workflow input requires review')
        if original.company_id!=data.company_id or original.request_id!=data.request_id:raise HTTPException(409,'Original workflow identities differ')
        if not data.reason.strip():raise HTTPException(422,'Request cancellation reason is required')
        await self.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'phase11-workflow:'+str(data.request_id)})
        key=(data.request_id,data.company_id,self.actor.actor_type,proof['actor_id'])
        cancelled=await self.db.get(WorkflowCancellation,key)
        if not cancelled:
            committed=await self.db.get(WorkflowCommand,data.request_id)
            if committed:
                if committed.company_id!=data.company_id or (committed.actor_type,committed.actor_id)!=(self.actor.actor_type,proof['actor_id']):raise HTTPException(403,'Original request belongs to another actor')
                if committed.kind!=data.original_kind or committed.payload_hash!=fingerprint(original) or data.record_id and committed.record_id!=data.record_id:raise HTTPException(409,'Original committed command differs; recover the original evidence')
                if committed.kind in {'supplier_create','supplier_update','po_create','po_edit','po_approve','po_cancel'}:self.authorize(data.company_id,owner=True)
                elif committed.kind=='po_receive':self.authorize(data.company_id,'inventory_receive');self.costs(data.company_id)
                elif committed.kind=='supplier_return':self.authorize(data.company_id,'inventory_adjust');self.costs(data.company_id)
                elif committed.kind.startswith('count_'):self.authorize(data.company_id,'inventory_count',owner=committed.kind in {'count_approve','count_reject'})
                elif committed.kind in {'template_publish','media_upload'}:self.authorize(data.company_id,'business_settings_manage',owner=True)
                elif committed.kind=='document_render':
                    from .documents import PERMISSIONS
                    self.authorize(data.company_id,PERMISSIONS[original.source_kind])
                    if original.source_kind in {'purchase_order','supplier_receipt','supplier_return'}:self.costs(data.company_id)
                elif committed.kind=='document_output':
                    record=await self.record(data.company_id,committed.record_id,'document_output');self.authorize_record(record)
                if (committed.device_id,committed.assignment_revision)!=(proof['device_id'],proof['assignment_revision']):raise HTTPException(403,'Recover using the original authorized register assignment')
                record=await self.record(data.company_id,committed.record_id)
                if record.branch_id:await self.current_context(data.company_id,record.branch_id)
                return {'status':'committed','request_id':str(data.request_id),'company_id':str(data.company_id),'actor_id':str(proof['actor_id']),'result':committed.result}
            self.db.add(WorkflowCancellation(request_id=data.request_id,company_id=data.company_id,actor_type=self.actor.actor_type,actor_id=proof['actor_id'],reason=data.reason))
            await self.db.commit()
        return {'status':'cancelled','request_id':str(data.request_id),'company_id':str(data.company_id),'actor_id':str(proof['actor_id'])}
