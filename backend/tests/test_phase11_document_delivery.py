"""Consent-aware sink only, encrypted private evidence and revocation-safe jobs."""
import json,unittest
from uuid import uuid4,UUID
from unittest.mock import patch
from cryptography.fernet import Fernet
from pydantic import SecretStr,ValidationError
from sqlalchemy import select,func,update,text
from sqlalchemy.exc import DBAPIError
from app.core.config import get_settings,Settings
from app.models import WorkflowRecord,WorkflowCommand,CompanySubscription,User
import test_phase11_procurement as fixtures

class DocumentDeliveryTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.ProcurementTests.cleanup
    post=fixtures.ProcurementTests.post
    stock=fixtures.ProcurementTests.stock
    async def asyncSetUp(self):
        await fixtures.ProcurementTests.asyncSetUp(self)
        self.key=Fernet.generate_key();self.settings=get_settings().model_copy(update={'document_delivery_mode':'sink','document_delivery_key':SecretStr(self.key.decode()),'app_env':'test'})
        self.patch=patch('app.workflows.delivery.get_settings',return_value=self.settings);self.patch.start();self.addCleanup(self.patch.stop)
        template=await self.post('/templates',{'blocks':[{'kind':'title','text':'Synthetic sink document'}]})
        document=await self.post('/documents',{'template_id':template['id'],'source_kind':'sale','source_id':str(self.sale.id)})
        self.output=await self.post('/outputs',{'document_id':document['id'],'format':'pdf'})
    async def consent(self,**updates):return await self.post('/delivery/consents',{'branch_id':str(self.b),'recipient':'synthetic@example.com','purpose':'document_copy','confirmed':True,**updates})
    async def job(self,consent):return await self.post('/delivery/outbox',{'output_id':self.output['id'],'consent_id':consent['id']})
    async def test_encrypted_consent_queue_capture_replay_and_new_ids_coalesce(self):
        consent=await self.consent();same=await self.consent();self.assertEqual(same['id'],consent['id']);self.assertNotIn('synthetic@example.com',json.dumps(consent))
        job=await self.job(consent);self.assertEqual((await self.job(consent))['id'],job['id'])
        request=str(uuid4());body={'request_id':request,'reason':'Synthetic capture only'};result=await self.post(f"/delivery/outbox/{job['id']}/capture",body)
        again=await self.post(f"/delivery/outbox/{job['id']}/capture",body);self.assertEqual(result,again)
        another=await self.post(f"/delivery/outbox/{job['id']}/capture",{'reason':'Recover original capture'});self.assertEqual(another['capture_id'],result['capture_id']);self.assertEqual(result['sink_status'],'captured')
        capture=await self.db.get(WorkflowRecord,UUID(result['capture_id']));envelope=json.loads(Fernet(self.key).decrypt(capture.payload['capture_ciphertext'].encode()));self.assertEqual(envelope['recipient'],'synthetic@example.com');self.assertEqual(envelope['output_id'],self.output['id'])
        rows=(await self.db.execute(select(WorkflowRecord).where(WorkflowRecord.company_id==self.c,WorkflowRecord.kind.in_(['delivery_consent','delivery_outbox','delivery_capture'])))).scalars().all()
        self.assertEqual(len(rows),3);self.assertNotIn('synthetic@example.com',json.dumps([r.payload for r in rows]));self.assertNotIn('Synthetic sink document',json.dumps([r.payload for r in rows]))
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text("UPDATE workflow_records SET payload='{}'::jsonb,version=version+1 WHERE id=:id"),{'id':capture.id})
        self.assertEqual(await self.stock(),100)
    async def test_consent_revocation_and_queue_cancel_survive_expiry(self):
        consent=await self.consent();job=await self.job(consent)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit()
        revoked=await self.post(f"/delivery/consents/{consent['id']}/revoke",{'version':consent['version']});self.assertEqual(revoked['state'],'revoked')
        await self.post(f"/delivery/outbox/{job['id']}/capture",{'reason':'Denied expired processing'},402)
        cancelled=await self.post(f"/delivery/outbox/{job['id']}/cancel",{'reason':'Consent revoked during expiry'});self.assertEqual(cancelled['state'],'cancelled')
        self.assertEqual((await self.db.execute(select(func.count()).select_from(WorkflowRecord).where(WorkflowRecord.company_id==self.c,WorkflowRecord.kind=='delivery_capture'))).scalar_one(),0)
    async def test_revoked_consent_and_changed_origin_epoch_block_capture(self):
        consent=await self.consent();job=await self.job(consent)
        await self.post(f"/delivery/consents/{consent['id']}/revoke",{'version':consent['version']})
        await self.post(f"/delivery/outbox/{job['id']}/capture",{'reason':'No consent'},403)
        consent=await self.consent();job=await self.job(consent)
        await self.db.execute(update(User).where(User.id==self.u).values(session_version=User.session_version+1).execution_options(synchronize_session=False));await self.db.commit()
        await self.db.refresh(self.user)
        from app.auth.security import create_access_token
        self.client.headers['Authorization']='Bearer '+create_access_token(str(self.u),'synthetic@example.com',session_version=1)
        await self.post(f"/delivery/outbox/{job['id']}/capture",{'reason':'Old queue epoch'},403)
        await self.post(f"/delivery/outbox/{job['id']}/cancel",{'reason':'Retain revoked origin evidence'})
        self.assertEqual((await self.db.execute(select(func.count()).select_from(WorkflowRecord).where(WorkflowRecord.company_id==self.c,WorkflowRecord.kind=='delivery_capture'))).scalar_one(),0)
    async def test_injected_capture_failure_rolls_back_capture_job_and_proof(self):
        consent=await self.consent();job=await self.job(consent);request=str(uuid4());body={'request_id':request,'reason':'Synthetic injected capture failure'}
        original=self.db.flush
        async def fail(*args,**kwargs):
            if any(isinstance(r,WorkflowRecord) and r.kind=='delivery_capture' for r in self.db.new):raise RuntimeError('Synthetic capture failure')
            return await original(*args,**kwargs)
        with patch.object(self.db,'flush',side_effect=fail):await self.post(f"/delivery/outbox/{job['id']}/capture",body,500)
        self.assertIsNone(await self.db.get(WorkflowCommand,UUID(request)));row=await self.db.get(WorkflowRecord,UUID(job['id']));self.assertEqual(row.state,'queued')
        self.assertEqual((await self.db.execute(select(func.count()).select_from(WorkflowRecord).where(WorkflowRecord.company_id==self.c,WorkflowRecord.kind=='delivery_capture'))).scalar_one(),0)
        await self.post(f"/delivery/outbox/{job['id']}/capture",body)
    async def test_sink_disabled_production_wrong_tenant_and_real_recipient_denied(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None,database_url='postgresql+asyncpg://synthetic@127.0.0.1:1/phase11_unreachable',jwt_secret='synthetic-phase11-settings-only-secret-123456789',app_env='production',document_delivery_mode='sink',document_delivery_key=SecretStr(self.key.decode()))
        await self.post('/delivery/consents',{'recipient':'synthetic@example.com','purpose':'document_copy','confirmed':False},422)
        await self.post('/delivery/consents',{'recipient':'synthetic@example.org','purpose':'document_copy','confirmed':True},422)
        self.settings.document_delivery_mode='disabled';await self.post('/delivery/consents',{'recipient':'synthetic@example.com','purpose':'document_copy','confirmed':True},503)
        self.settings.document_delivery_mode='sink';self.settings.app_env='production';await self.post('/delivery/consents',{'recipient':'synthetic@example.com','purpose':'document_copy','confirmed':True},503)
        self.settings.app_env='test';await self.post('/delivery/consents',{'company_id':str(uuid4()),'recipient':'synthetic@example.com','purpose':'document_copy','confirmed':True},403)
