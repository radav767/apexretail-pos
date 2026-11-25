"""Real claim/ready/recovery checks; never invoke a print transport."""
import unittest
from uuid import UUID,uuid4
from sqlalchemy import select
from app.models import PrintJob,User
from app.auth.security import create_access_token
import test_phase11_split_receipts as fixtures

class PrintReadinessTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.SplitReceiptTests.cleanup
    asyncSetUp=fixtures.SplitReceiptTests.asyncSetUp
    checkout=fixtures.SplitReceiptTests.checkout
    original=fixtures.SplitReceiptTests.original
    stock=fixtures.SplitReceiptTests.stock
    async def test_readiness_rechecks_revocation_and_exact_enqueue_keeps_sending_job_evidence(self):
        await self.original();body={'sale_id':str(self.sid),'kind':'receipt','request_key':str(uuid4())};path=f'/api/printing/station/{self.station_id}/jobs'
        response=await self.client.post(path,json=body);self.assertEqual(response.status_code,200,response.text);job=response.json();token=str(uuid4())
        claimed=await self.client.post(f"/api/printing/jobs/{job['id']}/claim",json={'token':token});self.assertEqual(claimed.status_code,200,claimed.text)
        for _ in range(2):
            ready=await self.client.post(f"/api/printing/jobs/{job['id']}/ready",json={'token':token});self.assertEqual(ready.status_code,200,ready.text);self.assertEqual(ready.json()['payload_hash'],job['payload_hash']);self.assertEqual(ready.json()['attempts'],1)
        wrong=await self.client.post(f"/api/printing/jobs/{job['id']}/ready",json={'token':str(uuid4())});self.assertEqual(wrong.status_code,409)
        revoked=await self.client.post('/api/auth/logout-all');self.assertEqual(revoked.status_code,200,revoked.text)
        denied=await self.client.post(f"/api/printing/jobs/{job['id']}/ready",json={'token':token});self.assertEqual(denied.status_code,401)
        user=await self.db.get(User,self.u,populate_existing=True);fresh=create_access_token(str(user.id),user.email,session_version=user.session_version)
        recovered=await self.client.post(path,json=body,headers={'Authorization':'Bearer '+fresh});self.assertEqual(recovered.status_code,200,recovered.text);self.assertEqual(recovered.json()['id'],job['id']);self.assertEqual(recovered.json()['payload'],job['payload']);self.assertEqual(recovered.json()['status'],'sending')
        row=await self.db.get(PrintJob,UUID(job['id']),populate_existing=True);self.assertEqual(row.attempts,1);self.assertEqual(await self.stock(),99)
