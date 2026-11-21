"""Cancellation fences reject late packets without discarding committed work."""
from uuid import UUID,uuid4
import unittest
from sqlalchemy import select,func,text,update
from sqlalchemy.exc import DBAPIError
from app.models import WorkflowRecord,WorkflowCancellation,CompanySubscription,User
import test_phase11_procurement as fixtures

class WorkflowRecoveryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.ProcurementTests.asyncSetUp
    cleanup=fixtures.ProcurementTests.cleanup
    post=fixtures.ProcurementTests.post
    async def test_cancel_uncommitted_fences_late_original_and_is_immutable(self):
        subscription=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one()
        subscription.status='expired';await self.db.commit()
        request=str(uuid4());original={'company_id':str(self.c),'request_id':request,'name':'Synthetic delayed contact'}
        cancel={'request_id':request,'reason':'Explicit synthetic review','original_kind':'supplier_create','original_payload':original}
        result=await self.post(f'/commands/{request}/cancel',cancel);self.assertEqual(result['status'],'cancelled')
        await self.post('/suppliers',original,409)
        repeated=await self.post(f'/commands/{request}/cancel',cancel);self.assertEqual(repeated['status'],'cancelled')
        self.assertEqual((await self.db.execute(select(func.count()).select_from(WorkflowRecord).where(WorkflowRecord.company_id==self.c))).scalar_one(),0)
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text('DELETE FROM workflow_cancellations WHERE request_id=:id'),{'id':UUID(request)})
    async def test_committed_request_recovers_original_only_for_exact_input(self):
        request=str(uuid4());original={'company_id':str(self.c),'request_id':request,'name':'Synthetic committed contact'}
        created=await self.post('/suppliers',original)
        subscription=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one()
        subscription.status='expired';await self.db.commit()
        body={'request_id':request,'reason':'Review unknown outcome','original_kind':'supplier_create','original_payload':original}
        result=await self.post(f'/commands/{request}/cancel',body);self.assertEqual(result['status'],'committed');self.assertEqual(result['result']['id'],created['id'])
        self.assertEqual((await self.db.execute(select(func.count()).select_from(WorkflowCancellation).where(WorkflowCancellation.company_id==self.c))).scalar_one(),0)
        await self.post(f'/commands/{request}/cancel',{**body,'original_payload':{**original,'name':'Changed unconfirmed input'}},409)
        await self.post(f'/commands/{request}/cancel',{**body,'company_id':str(uuid4())},403)
    async def test_scope_body_or_command_identity_cannot_be_substituted(self):
        request=str(uuid4());original={'company_id':str(self.c),'request_id':request,'name':'Synthetic review'}
        await self.post(f'/commands/{request}/cancel',{'request_id':str(uuid4()),'reason':'Mismatch','original_kind':'supplier_create','original_payload':original},409)
        await self.post(f'/commands/{request}/cancel',{'request_id':request,'reason':'Mismatch','original_kind':'unknown','original_payload':original},422)
    async def test_direct_recovery_refreshes_revoked_actor_before_fencing(self):
        from app.auth.dependencies import resolve_auth_actor
        from app.workflows.recovery import RecoveryService
        from app.workflows.schema import CancellationInput
        from fastapi import HTTPException
        actor=await resolve_auth_actor(self.owner_token,self.db)
        await self.db.execute(update(User).where(User.id==self.u).values(session_version=User.session_version+1).execution_options(synchronize_session=False));await self.db.commit()
        request=uuid4();original={'company_id':str(self.c),'request_id':str(request),'name':'Synthetic revoked request'}
        data=CancellationInput(company_id=self.c,request_id=request,reason='Synthetic revoked recovery',original_kind='supplier_create',original_payload=original)
        with self.assertRaises(HTTPException) as error:await RecoveryService(self.db,actor).cancel_uncommitted(data)
        self.assertEqual(error.exception.status_code,401)
        self.assertEqual((await self.db.execute(select(func.count()).select_from(WorkflowCancellation).where(WorkflowCancellation.company_id==self.c))).scalar_one(),0)
