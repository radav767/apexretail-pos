"""Private decoded assets, bounded layout and unchanged historical proofs."""
import base64,io,unittest
from uuid import uuid4,UUID
from datetime import datetime,timezone
from PIL import Image,PngImagePlugin
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.models import WorkflowRecord,InventoryMovement
from app.workflows.schema import TemplateInput
from app.sales.commands import fingerprint
import test_phase11_procurement as fixtures

def png(size=(40,20),metadata=False):
    out=io.BytesIO();image=Image.new('RGB',size,'white');info=PngImagePlugin.PngInfo();info.add_text('private','must be stripped')
    image.save(out,format='PNG',pnginfo=info if metadata else None);return out.getvalue()
class DocumentMediaTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.ProcurementTests.asyncSetUp
    cleanup=fixtures.ProcurementTests.cleanup
    post=fixtures.ProcurementTests.post
    stock=fixtures.ProcurementTests.stock
    async def upload(self,raw=None,**changes):return await self.post('/media',{'content_type':'image/png','data_base64':base64.b64encode(raw if raw is not None else png(metadata=True)).decode(),**changes})
    async def test_decoded_logo_strips_metadata_and_frozen_layout_escapes_text(self):
        request=str(uuid4());asset=await self.upload(request_id=request)
        self.assertEqual((await self.upload(request_id=request))['id'],asset['id'])
        raw=base64.b64decode(asset['payload']['data_base64'])
        with Image.open(io.BytesIO(raw)) as decoded:self.assertNotIn('private',decoded.info);self.assertEqual(decoded.size,(40,20))
        template=await self.post('/templates',{'branch_id':str(self.b),'paper':'58mm','blocks':[{'kind':'logo','media_id':asset['id'],'width_mm':30,'alignment':'right'},{'kind':'contact','text':'<script>private</script>'},{'kind':'items'},{'kind':'tax'},{'kind':'totals'}]})
        doc=await self.post('/documents',{'template_id':template['id'],'source_kind':'sale','source_id':str(self.sale.id)})
        body=doc['payload']['html'];self.assertIn('data:image/png;base64,',body);self.assertIn('&lt;script&gt;',body);self.assertNotIn('<script>',body);self.assertEqual(doc['payload']['renderer_version'],2)
        self.assertEqual(template['payload']['media'][asset['id']]['sha256'],asset['payload']['sha256'])
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text("UPDATE workflow_records SET payload='{}'::jsonb,version=version+1 WHERE id=:id"),{'id':UUID(asset['id'])})
        self.assertEqual(await self.stock(),100);self.assertEqual((await self.db.execute(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.company_id==self.c))).scalar_one(),0)
    async def test_upload_type_decode_animation_dimensions_and_envelope_bounds(self):
        for raw,kind,status in [(b'<svg><script/></svg>','image/png',415),(b'\x89PNG\r\n\x1a\n'+'broken'.encode(),'image/png',415),(png(),'image/jpeg',415),(png((2049,1)),'image/png',413),(png((2048,2048)),'image/png',413),(b'x'*524289,'image/png',413)]:
            await self.post('/media',{'content_type':kind,'data_base64':base64.b64encode(raw).decode()},status)
        animation=io.BytesIO();Image.new('RGB',(2,2),'red').save(animation,format='PNG',save_all=True,append_images=[Image.new('RGB',(2,2),'blue')],duration=20,loop=0)
        await self.post('/media',{'content_type':'image/png','data_base64':base64.b64encode(animation.getvalue()).decode()},415)
        response=await self.client.post('/api/inventory/workflows/media',content=b'x'*720001,headers={'Content-Type':'application/json'});self.assertEqual(response.status_code,413)
        self.assertEqual((await self.db.execute(select(func.count()).select_from(WorkflowRecord).where(WorkflowRecord.company_id==self.c,WorkflowRecord.kind=='document_media'))).scalar_one(),0)
    async def test_tenant_branch_role_layout_and_quota_denials(self):
        from app.models import Branch
        from app.auth.security import create_employee_access_token
        asset=await self.upload();other=Branch(company_id=self.c,shop_id=self.shop.id,name='Synthetic other logo branch');self.db.add(other);await self.db.commit()
        branch_asset=await self.upload(branch_id=str(other.id))
        await self.post('/templates',{'branch_id':str(self.b),'blocks':[{'kind':'logo','media_id':branch_asset['id']}]},403)
        await self.post('/templates',{'blocks':[{'kind':'logo','media_id':str(uuid4())}]},404)
        await self.post('/media',{'company_id':str(uuid4()),'content_type':'image/png','data_base64':base64.b64encode(png()).decode()},403)
        token=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='cashier')
        response=await self.client.post('/api/inventory/workflows/media',headers={'Authorization':'Bearer '+token},json={'company_id':str(self.c),'request_id':str(uuid4()),'content_type':'image/png','data_base64':base64.b64encode(png()).decode()});self.assertEqual(response.status_code,403)
        await self.post('/templates',{'paper':'58mm','blocks':[{'kind':'logo','media_id':asset['id'],'width_mm':80}]},422)
        await self.post('/templates',{'blocks':[{'kind':'logo','media_id':asset['id']},{'kind':'logo','media_id':asset['id']}]},422)
        for i in range(62):self.db.add(WorkflowRecord(company_id=self.c,kind='document_media',state='validated',payload=asset['payload']))
        await self.db.commit();await self.post('/media',{'content_type':'image/png','data_base64':base64.b64encode(png()).decode()},409)
    async def test_legacy_template_fingerprint_keeps_original_shape(self):
        from app.sales.commands import normalized
        import hashlib,json
        data=TemplateInput(company_id=self.c,request_id=uuid4(),blocks=[{'kind':'title','text':'Legacy'}])
        original={'company_id':str(self.c),'request_id':str(data.request_id),'branch_id':None,'previous_id':None,'paper':'80mm','blocks':[{'kind':'title','text':'Legacy'}]}
        expected=hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':')).encode()).hexdigest();self.assertEqual(fingerprint(data),expected)
