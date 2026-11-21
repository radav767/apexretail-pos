"""API receipt and new frozen print jobs disclose the same original allocations."""
import json,unittest,io,re
from pathlib import Path
from uuid import UUID,uuid4
from decimal import Decimal
from unittest.mock import patch
from app.printing.service import PrintingService
from app.printing.schema import JobInput
from pypdf import PdfReader
from fastapi import HTTPException
import test_phase11_split_refunds as fixtures

class SplitReceiptTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.SplitRefundTests.cleanup
    asyncSetUp=fixtures.SplitRefundTests.asyncSetUp
    checkout=fixtures.SplitRefundTests.checkout
    original=fixtures.SplitRefundTests.original
    command=fixtures.SplitRefundTests.command
    post=fixtures.SplitRefundTests.post
    collect=fixtures.SplitRefundTests.collect
    debt=fixtures.SplitRefundTests.debt
    stock=fixtures.SplitRefundTests.stock
    async def receipt(self,sid,company=None,status=200):
        response=await self.client.get(f'/api/sales/receipt/{company or self.c}/{sid}',params={'mark_reprint':'false'});self.assertEqual(response.status_code,status,response.text);return response.json()
    async def test_original_api_and_queued_print_metadata_survive_collections_refunds_and_replay(self):
        await self.original();before=await self.receipt(self.sid);accounting=before['split_accounting'];self.assertEqual(accounting['version'],'split-receipt-v2');self.assertFalse(accounting['provider_confirmed'])
        self.assertEqual({r['kind'] for r in accounting['legs']},{'cash_payment','unpaid_credit'});credit=next(r for r in accounting['legs'] if r['method']=='credit');self.assertIsNone(credit['tendered_original']);self.assertIsNone(credit['change_original'])
        printer=PrintingService(self.db,self.owner);command=JobInput(sale_id=self.sid,request_key=str(uuid4()))
        queued=await printer.enqueue(self.station_id,command);self.assertEqual(queued['payload']['split_accounting'],accounting)
        await self.collect('1');returned=await self.post(self.command('.5','6',[(self.credit,'debt_reduction','3','3'),(self.cash,'paid_refund','3','3')]))
        refund_id=UUID(returned['sale']['id']);receipt=await self.receipt(refund_id);reverse=receipt['split_accounting'];self.assertEqual(reverse['original_sale_id'],str(self.sid));self.assertEqual({r['kind'] for r in reverse['legs']},{'cash_refund','debt_reduction'});self.assertEqual(sum(Decimal(r['applied_base']) for r in reverse['legs']),6)
        self.assertEqual((await self.receipt(self.sid))['split_accounting'],accounting)
        # Exact queue recovery must never regenerate or overwrite an existing job.
        with patch('app.sales.split_receipts.snapshot',side_effect=RuntimeError('must not regenerate saved print payload')):
            again=await printer.enqueue(self.station_id,command)
        self.assertEqual(again['payload_hash'],queued['payload_hash']);self.assertEqual(again['payload'],queued['payload'])
        refund_job=await printer.enqueue(self.station_id,JobInput(sale_id=refund_id,request_key=str(uuid4())));self.assertEqual(refund_job['payload']['split_accounting'],reverse)
        Path('/tmp/phase11-split-receipt-fixtures.json').write_text(json.dumps({'original':queued['payload'],'refund':refund_job['payload']},indent=2)+'\n')
        await self.receipt(self.sid,company=uuid4(),status=403);self.assertEqual(await self.stock(),Decimal('99.5'))
    async def workflow(self,path,**body):
        response=await self.client.post('/api/inventory/workflows'+path,json={'company_id':str(self.c),'request_id':str(uuid4()),**body});self.assertEqual(response.status_code,200,response.text);return response.json()
    async def test_direct_receipt_and_cached_split_print_replay_require_current_identity(self):
        await self.original();printer=PrintingService(self.db,self.owner);command=JobInput(sale_id=self.sid,request_key=str(uuid4()));await printer.enqueue(self.station_id,command)
        from app.sales.service import SalesService
        from app.sales.repository import SalesRepository
        from app.models import User
        with self.assertRaises(HTTPException) as anonymous:await SalesService(SalesRepository(self.db)).get_sale_receipt(self.c,self.sid,actor=None)
        self.assertEqual(anonymous.exception.status_code,401)
        user=await self.db.get(User,self.u);self.owner.authenticated_session_version=user.session_version;user.session_version+=1;await self.db.commit()
        with self.assertRaises(HTTPException) as revoked:await printer.enqueue(self.station_id,command)
        self.assertEqual(revoked.exception.status_code,401);self.assertEqual(await self.stock(),99)
    async def test_new_58_80_a4_documents_and_pdfs_keep_original_disclosures_and_saved_bytes(self):
        await self.original();saved=[]
        for paper in ('58mm','80mm','A4'):
            template=await self.workflow('/templates',paper=paper,blocks=[{'kind':'title','text':'Synthetic split receipt'},{'kind':'items'},{'kind':'totals'}])
            document=await self.workflow('/documents',template_id=template['id'],source_kind='sale',source_id=str(self.sid));self.assertIn('Original unpaid credit',document['payload']['html'])
            output=await self.workflow('/outputs',document_id=document['id'],format='pdf')
            path=f"/api/inventory/workflows/outputs/{self.c}/{output['id']}/download";response=await self.client.get(path);self.assertEqual(response.status_code,200,response.text[:100] if response.status_code!=200 else '')
            content=response.content;text=' '.join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages);text=re.sub(r'\s+',' ',text)
            for label in ('Cash payment','Original unpaid credit','Tendered','Change','Recorded accounting only'):self.assertIn(label,text)
            Path('/tmp/phase11-split-receipt-'+paper+'.pdf').write_bytes(content);saved.append((path,content,document['id'],document['payload']['html']))
        await self.collect('1');returned=await self.post(self.command('.5','6',[(self.credit,'debt_reduction','3','3'),(self.cash,'paid_refund','3','3')]))
        refund_document=await self.workflow('/documents',template_id=template['id'],source_kind='sale',source_id=returned['sale']['id'])
        refund_output=await self.workflow('/outputs',document_id=refund_document['id'],format='pdf');refund_pdf=await self.client.get(f"/api/inventory/workflows/outputs/{self.c}/{refund_output['id']}/download");self.assertEqual(refund_pdf.status_code,200)
        refund_text=' '.join(page.extract_text() for page in PdfReader(io.BytesIO(refund_pdf.content)).pages)
        self.assertIn('Cash refund',refund_text);self.assertIn('Debt reduction',refund_text);Path('/tmp/phase11-split-receipt-refund-A4.pdf').write_bytes(refund_pdf.content)
        for path,content,document_id,html in saved:
            self.assertEqual((await self.client.get(path)).content,content)
            self.assertEqual((await self.client.get(f'/api/inventory/workflows/documents/{self.c}/{document_id}/html')).text,html)
