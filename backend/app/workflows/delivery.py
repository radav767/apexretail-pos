"""Consent-bound encrypted TEST sink. No network/provider transport exists."""
import base64,hashlib,hmac,json
from uuid import uuid4,uuid5,NAMESPACE_URL,UUID
from cryptography.fernet import Fernet,InvalidToken
from fastapi import HTTPException,APIRouter,Depends
from sqlalchemy import select,text
from app.models import WorkflowRecord
from app.core.config import get_settings
from app.auth.dependencies import get_auth_actor
from app.db.session import get_db
from app.subscriptions.write_policy import require_new_write
from .core import WorkflowService,atomic
from .outputs import OutputService
from .schema import ConsentInput,DeliveryInput,DeliveryAction,VersionCommand

def cipher():
    settings=get_settings()
    if settings.app_env!='test' or settings.document_delivery_mode!='sink' or not settings.document_delivery_key:raise HTTPException(503,'Document delivery is disabled; only an explicitly configured test sink is available')
    return Fernet(settings.document_delivery_key.get_secret_value().encode())
def recipient(value):
    address=str(value).strip().lower();domain=address.rsplit('@',1)[-1]
    if domain not in {'example.com','example.test','example.invalid'} and not domain.endswith('.invalid'):raise HTTPException(422,'Test sink accepts synthetic example or invalid recipient domains only')
    return address

class DeliveryService(WorkflowService):
    def authorize_delivery(self,company):self.authorize(company,'business_settings_manage',owner=True)
    def metadata(self,row):
        value=self.view(row);value['payload']={k:v for k,v in row.payload.items() if k not in {'recipient_ciphertext','capture_ciphertext'}};return value
    @atomic
    async def consent(self,data):
        self.authorize_delivery(data.company_id)
        if data.branch_id:await self.branch(data.company_id,data.branch_id)
        old,proof=await self.begin(data,'delivery_consent',data.branch_id)
        if old:return old
        if not data.confirmed:raise HTTPException(422,'Explicit operator attestation of recipient consent is required')
        address=recipient(data.recipient);box=cipher();key=get_settings().document_delivery_key.get_secret_value().encode()
        tag=hmac.new(key,(str(data.company_id)+':document_copy:'+address).encode(),hashlib.sha256).hexdigest()
        await self.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'document-consent:'+str(data.company_id)+':'+tag})
        existing=(await self.db.execute(select(WorkflowRecord).where(WorkflowRecord.company_id==data.company_id,WorkflowRecord.kind=='delivery_consent',WorkflowRecord.state=='granted',WorkflowRecord.payload['recipient_hmac'].as_string()==tag))).scalar_one_or_none()
        if existing:
            if existing.branch_id!=data.branch_id:raise HTTPException(409,'Existing consent scope differs; review original consent before replacement')
            return await self.finish(data,'delivery_consent',existing,proof,self.metadata(existing))
        row=WorkflowRecord(id=uuid4(),company_id=data.company_id,branch_id=data.branch_id,kind='delivery_consent',state='granted',payload={'purpose':'document_copy','recipient_hmac':tag,'recipient_ciphertext':box.encrypt(address.encode()).decode(),'attested_actor_type':self.actor.actor_type,'attested_actor_id':str(proof['actor_id'])})
        self.db.add(row);await self.db.flush();return await self.finish(data,'delivery_consent',row,proof,self.metadata(row))
    @atomic
    async def revoke(self,consent_id,data):
        self.authorize_delivery(data.company_id)
        old,proof=await self.begin(data,'delivery_revoke',record_id=consent_id,license_required=False)
        if old:return old
        row=await self.record(data.company_id,consent_id,'delivery_consent',True);self.version(row,data,{'granted'})
        row.state='revoked';row.version+=1;return await self.finish(data,'delivery_revoke',row,proof,self.metadata(row))
    @atomic
    async def enqueue(self,data):
        self.authorize_delivery(data.company_id)
        output=await self.record(data.company_id,data.output_id,'document_output');self.authorize_record(output)
        old,proof=await self.begin(data,'delivery_enqueue',output.branch_id)
        if old:return old
        cipher()
        consent=await self.record(data.company_id,data.consent_id,'delivery_consent',True)
        if consent.state!='granted' or consent.payload['purpose']!='document_copy' or consent.branch_id and consent.branch_id!=output.branch_id:raise HTTPException(403,'Current consent does not authorize this document copy')
        existing=(await self.db.execute(select(WorkflowRecord).where(WorkflowRecord.company_id==data.company_id,WorkflowRecord.kind=='delivery_outbox',WorkflowRecord.payload['output_id'].as_string()==str(output.id),WorkflowRecord.payload['consent_id'].as_string()==str(consent.id)))).scalar_one_or_none()
        if existing:
            self.original_actor(existing,proof)
            if existing.state=='cancelled':raise HTTPException(409,'Original copy was cancelled; retain it and explicitly review new consent before another copy')
            return await self.finish(data,'delivery_enqueue',existing,proof,self.metadata(existing))
        entity=self.actor.user if self.actor.user else self.actor.employee
        row=WorkflowRecord(id=uuid4(),company_id=data.company_id,branch_id=output.branch_id,kind='delivery_outbox',state='queued',payload={'output_id':str(output.id),'source_kind':output.payload['source_kind'],'consent_id':str(consent.id),'consent_version':consent.version,'purpose':'document_copy','actor_type':self.actor.actor_type,'actor_id':str(proof['actor_id']),'actor_session_version':entity.session_version,'business_session_id':str(self.actor.business_session_id) if self.actor.business_session_id else None,'pos_session_id':str(self.actor.pos_session.id) if self.actor.pos_session else None,'device_id':str(proof['device_id']) if proof['device_id'] else None,'assignment_revision':proof['assignment_revision']})
        self.db.add(row);await self.db.flush();return await self.finish(data,'delivery_enqueue',row,proof,self.metadata(row))
    def original_actor(self,row,proof):
        if (row.payload['actor_type'],row.payload['actor_id'])!=(self.actor.actor_type,str(proof['actor_id'])):raise HTTPException(403,'Only the original currently authorized queue actor may process or cancel this copy')
    @atomic
    async def capture(self,job_id,data):
        self.authorize_delivery(data.company_id)
        old,proof=await self.begin(data,'delivery_capture',record_id=job_id,license_required=False)
        if old:return old
        row=await self.record(data.company_id,job_id,'delivery_outbox',True);self.authorize_record(row);self.original_actor(row,proof)
        if row.state=='captured':
            capture=(await self.db.execute(select(WorkflowRecord).where(WorkflowRecord.company_id==data.company_id,WorkflowRecord.kind=='delivery_capture',WorkflowRecord.payload['outbox_id'].as_string()==str(row.id)))).scalar_one()
            return await self.finish(data,'delivery_capture',row,proof,{**self.metadata(row),'capture_id':str(capture.id),'attempt_id':capture.payload['attempt_id'],'sink_status':'captured'})
        if row.state!='queued':raise HTTPException(409,'This document copy is no longer queued')
        if not data.reason.strip():raise HTTPException(422,'Sink processing reason is required')
        entity=self.actor.user if self.actor.user else self.actor.employee
        current={'actor_session_version':entity.session_version,'business_session_id':str(self.actor.business_session_id) if self.actor.business_session_id else None,'pos_session_id':str(self.actor.pos_session.id) if self.actor.pos_session else None,'device_id':str(proof['device_id']) if proof['device_id'] else None,'assignment_revision':proof['assignment_revision']}
        if any(row.payload[k]!=v for k,v in current.items()):raise HTTPException(403,'Original queue session or register authority changed; retain/cancel this copy and review')
        await require_new_write(self.db,data.company_id)
        box=cipher();consent=await self.record(data.company_id,UUID(row.payload['consent_id']),'delivery_consent',True)
        if consent.state!='granted' or consent.version!=row.payload['consent_version']:raise HTTPException(403,'Recipient consent was revoked or changed; no capture occurred')
        output,raw=await OutputService(self.db,self.actor).download(data.company_id,UUID(row.payload['output_id']))
        if len(raw)>1000000:raise HTTPException(413,'Sink copy exceeds one million bytes')
        try:address=recipient(box.decrypt(consent.payload['recipient_ciphertext'].encode()).decode())
        except InvalidToken:raise HTTPException(409,'Original test sink key is unavailable; preserve queue and review') from None
        envelope={'recipient':address,'purpose':'document_copy','output_id':str(output.id),'content_type':output.payload['content_type'],'data_base64':base64.b64encode(raw).decode('ascii')}
        attempt=uuid5(NAMESPACE_URL,'phase11-document-sink:'+str(row.id))
        capture=WorkflowRecord(id=uuid4(),company_id=data.company_id,branch_id=row.branch_id,kind='delivery_capture',state='captured',payload={'outbox_id':str(row.id),'output_id':str(output.id),'attempt_id':str(attempt),'mode':'test_sink','capture_ciphertext':box.encrypt(json.dumps(envelope,separators=(',',':')).encode()).decode()})
        self.db.add(capture);row.state='captured';row.version+=1
        return await self.finish(data,'delivery_capture',row,proof,{**self.metadata(row),'capture_id':str(capture.id),'attempt_id':str(attempt),'sink_status':'captured'})
    @atomic
    async def cancel(self,job_id,data):
        self.authorize_delivery(data.company_id)
        old,proof=await self.begin(data,'delivery_cancel',record_id=job_id,license_required=False)
        if old:return old
        row=await self.record(data.company_id,job_id,'delivery_outbox',True);self.authorize_record(row);self.original_actor(row,proof)
        if row.state!='queued':raise HTTPException(409,'Only a queued copy can be cancelled')
        if not data.reason.strip():raise HTTPException(422,'Cancellation reason is required')
        row.state='cancelled';row.version+=1;return await self.finish(data,'delivery_cancel',row,proof,self.metadata(row))
router=APIRouter(prefix='/inventory/workflows/delivery',tags=['Consent-aware test document sink'])
def service(db=Depends(get_db),actor=Depends(get_auth_actor)):return DeliveryService(db,actor)
@router.post('/consents')
async def consent(data:ConsentInput,svc=Depends(service)):return await svc.consent(data)
@router.post('/consents/{consent_id}/revoke')
async def revoke(consent_id:UUID,data:VersionCommand,svc=Depends(service)):return await svc.revoke(consent_id,data)
@router.post('/outbox')
async def enqueue(data:DeliveryInput,svc=Depends(service)):return await svc.enqueue(data)
@router.post('/outbox/{job_id}/capture')
async def capture(job_id:UUID,data:DeliveryAction,svc=Depends(service)):return await svc.capture(job_id,data)
@router.post('/outbox/{job_id}/cancel')
async def cancel(job_id:UUID,data:DeliveryAction,svc=Depends(service)):return await svc.cancel(job_id,data)
