"""Archive controls never delete or rewrite source/output/command bytes."""
import base64,hashlib,io,json,unittest
from uuid import uuid4,UUID
from pypdf import PdfReader
from sqlalchemy import select,text,func
from sqlalchemy.exc import DBAPIError
from app.models import WorkflowRecord,CompanySubscription
import test_phase11_procurement as fixtures
from test_phase11_document_media import png
class RetentionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.ProcurementTests.asyncSetUp
    cleanup=fixtures.ProcurementTests.cleanup
    post=fixtures.ProcurementTests.post
    stock=fixtures.ProcurementTests.stock
    async def test_archive_duplicate_reuse_and_historical_immutability(self):
        upload={'branch_id':str(self.b),'content_type':'image/png','data_base64':base64.b64encode(png()).decode()}
        asset=await self.post('/media',upload);duplicate=await self.post('/media',upload);self.assertEqual(asset['id'],duplicate['id'])
        template=await self.post('/templates',{'branch_id':str(self.b),'blocks':[{'kind':'logo','media_id':asset['id']},{'kind':'contact','text':'Synthetic contact'}]})
        doc=await self.post('/documents',{'template_id':template['id'],'source_kind':'sale','source_id':str(self.sale.id)})
        output=await self.post('/outputs',{'document_id':doc['id'],'format':'pdf'})
        path=f"/api/inventory/workflows/outputs/{self.c}/{output['id']}/download";before=(await self.client.get(path)).content
        command={'media_id':asset['id'],'archived':True,'reason':'Synthetic retention review','request_id':str(uuid4())}
        retained=await self.post('/retention/media',command);self.assertEqual((await self.post('/retention/media',command))['id'],retained['id'])
        catalog=(await self.client.get(f'/api/inventory/workflows/retention/{self.c}/catalog')).json();self.assertEqual(catalog['retained_count'],1);self.assertFalse(catalog['deletion_enabled']);self.assertTrue(catalog['assets'][0]['archived']);self.assertEqual(catalog['assets'][0]['template_references'],1)
        await self.post('/media',upload,409)
        await self.post('/templates',{'branch_id':str(self.b),'blocks':[{'kind':'logo','media_id':asset['id']}]},409)
        self.assertEqual((await self.client.get(path)).content,before)
        historical=await self.post('/documents',{'template_id':template['id'],'source_kind':'sale','source_id':str(doc['payload']['source_id'])});self.assertEqual(historical['payload']['template_digest'],doc['payload']['template_digest']);self.assertIn('data:image/png;base64,',historical['payload']['html']);self.assertEqual((await self.client.get(f"/api/inventory/workflows/documents/{self.c}/{doc['id']}/html")).text,doc['payload']['html'])
        await self.post('/retention/media',{**command,'request_id':str(uuid4()),'archived':False});self.assertEqual((await self.post('/media',upload))['id'],asset['id'])
        self.assertEqual(await self.stock(),100)
    async def test_archive_after_expiry_but_reactivation_needs_license_and_scope(self):
        asset=await self.post('/media',{'content_type':'image/png','data_base64':base64.b64encode(png()).decode()})
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit()
        body={'media_id':asset['id'],'archived':True,'reason':'Evidence retained'};await self.post('/retention/media',body)
        await self.post('/retention/media',{**body,'archived':False},402)
        await self.post('/retention/media',{**body,'company_id':str(uuid4())},403)
        from app.auth.security import create_employee_access_token
        token=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='cashier')
        response=await self.client.get(f'/api/inventory/workflows/retention/{self.c}/catalog',headers={'Authorization':'Bearer '+token});self.assertEqual(response.status_code,403)
    async def test_bounded_unicode_pdf_accessible_new_layout_and_old_output_unchanged(self):
        phrase='Café Δοκιμή Москва ₦ € e\u0301'
        template=await self.post('/templates',{'blocks':[{'kind':'contact','text':phrase},{'kind':'items'},{'kind':'totals'}]})
        doc=await self.post('/documents',{'template_id':template['id'],'source_kind':'sale','source_id':str(self.sale.id)})
        html=doc['payload']['html'];self.assertIn('lang="en"',html);self.assertIn('<main>',html);self.assertIn('<caption>',html);self.assertIn('scope="col"',html);self.assertEqual(html.count('<h1>'),1)
        output=await self.post('/outputs',{'document_id':doc['id'],'format':'pdf'});self.assertIn('layout2;DejaVuSans-',output['payload']['engine'])
        path=f"/api/inventory/workflows/outputs/{self.c}/{output['id']}/download";before=(await self.client.get(path)).content
        extracted=''.join(p.extract_text() for p in PdfReader(io.BytesIO(before)).pages);self.assertIn('Café',extracted);self.assertIn('Москва',extracted);self.assertIn('Δοκιμή',extracted)
        from unittest.mock import patch
        with patch('app.workflows.outputs.pdf_bytes',side_effect=RuntimeError('Historical output must not rerender')):
            again=await self.post('/outputs',{'document_id':doc['id'],'format':'pdf'});self.assertEqual(again['id'],output['id'])
        self.assertEqual((await self.client.get(path)).content,before)
        for value in ['العربية','\u202eevil','漢']:
            t=await self.post('/templates',{'blocks':[{'kind':'contact','text':value}]})
            await self.db.refresh(self.sale);d=await self.post('/documents',{'template_id':t['id'],'source_kind':'sale','source_id':str(self.sale.id)})
            await self.post('/outputs',{'document_id':d['id'],'format':'pdf'},422)
