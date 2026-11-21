"""Immutable bounded PDF and authenticated-only QR; parser/software decoder tests."""
import base64,io,json,unittest
from uuid import UUID,uuid4
from unittest.mock import patch
from PIL import Image
from pypdf import PdfReader
import zxingcpp
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.models import WorkflowRecord,WorkflowCommand,CompanySubscription
import test_phase11_procurement as fixtures
class DocumentOutputTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.ProcurementTests.asyncSetUp
    cleanup=fixtures.ProcurementTests.cleanup
    post=fixtures.ProcurementTests.post
    stock=fixtures.ProcurementTests.stock
    async def document(self,blocks=None,paper='80mm'):
        template=await self.post('/templates',{'paper':paper,'blocks':blocks or [{'kind':'title','text':'Synthetic <script> plain PDF'}]})
        await self.db.refresh(self.sale)
        return await self.post('/documents',{'template_id':template['id'],'source_kind':'sale','source_id':str(self.sale.id)})
    async def download(self,row):
        response=await self.client.get(f"/api/inventory/workflows/outputs/{self.c}/{row['id']}/download");self.assertEqual(response.status_code,200,response.text[:100]);return response
    async def test_pdf_frozen_download_parser_replay_and_expired_history(self):
        document=await self.document();request=str(uuid4());data={'request_id':request,'document_id':document['id'],'format':'pdf'}
        output=await self.post('/outputs',data);self.assertNotIn('data_base64',output['payload'])
        content=await self.download(output);pdf=PdfReader(io.BytesIO(content.content));self.assertGreaterEqual(len(pdf.pages),1);self.assertIn('Synthetic <script>',pdf.pages[0].extract_text());self.assertNotIn('/OpenAction',pdf.trailer['/Root']);self.assertNotIn('/Annots',pdf.pages[0])
        self.assertEqual((await self.post('/outputs',data))['id'],output['id'])
        again=await self.post('/outputs',{**data,'request_id':str(uuid4())});self.assertEqual(again['id'],output['id']);self.assertEqual((await self.download(again)).content,content.content)
        await self.post('/outputs',{**data,'format':'authenticated_lookup_qr'},409)
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text("UPDATE workflow_records SET payload='{}'::jsonb,version=version+1 WHERE id=:id"),{'id':UUID(output['id'])})
        subscription=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();subscription.status='expired';await self.db.commit()
        historical=await self.post('/outputs',{**data,'request_id':str(uuid4())});self.assertEqual(historical['id'],output['id']);self.assertEqual(await self.stock(),100)
    async def test_qr_roundtrip_purpose_and_current_permission_resolution(self):
        document=await self.document();output=await self.post('/outputs',{'document_id':document['id'],'format':'authenticated_lookup_qr'})
        raw=(await self.download(output)).content;decoded=zxingcpp.read_barcode(Image.open(io.BytesIO(raw)));self.assertIsNotNone(decoded);payload=json.loads(decoded.text)
        self.assertEqual(set(payload),{'company_id','document_id','content_digest','purpose'});self.assertEqual(payload['purpose'],'authenticated_document_lookup')
        response=await self.client.post('/api/inventory/workflows/outputs/resolve-lookup',json=payload);self.assertEqual(response.status_code,200,response.text)
        response=await self.client.post('/api/inventory/workflows/outputs/resolve-lookup',json={**payload,'company_id':str(uuid4())});self.assertEqual(response.status_code,403)
        response=await self.client.post('/api/inventory/workflows/outputs/resolve-lookup',json={**payload,'content_digest':'0'*64});self.assertEqual(response.status_code,409)
        await self.post('/outputs',{'document_id':document['id'],'format':'payment_qr'},422)
        response=await self.client.get(f"/api/inventory/workflows/outputs/{self.c}/{output['id']}/download",headers={'Authorization':'Bearer invalid'});self.assertEqual(response.status_code,401)
        self.assertEqual(await self.stock(),100)
    async def test_unsupported_font_and_page_bound_fail_without_artifact_or_proof(self):
        document=await self.document([{'kind':'text','text':'Unsupported 漢'}]);request=str(uuid4())
        await self.post('/outputs',{'request_id':request,'document_id':document['id'],'format':'pdf'},422)
        self.assertIsNone(await self.db.get(WorkflowCommand,UUID(request)))
        document=await self.document([{'kind':'text','text':'x'*2000} for _ in range(3)],paper='58mm');request=str(uuid4())
        with patch('app.workflows.outputs.MAX_PAGES',1):await self.post('/outputs',{'request_id':request,'document_id':document['id'],'format':'pdf'},413)
        self.assertIsNone(await self.db.get(WorkflowCommand,UUID(request)))
        self.assertEqual((await self.db.execute(select(func.count()).select_from(WorkflowRecord).where(WorkflowRecord.company_id==self.c,WorkflowRecord.kind=='document_output'))).scalar_one(),0)
