"""Immutable safe templates/snapshots never move stock/payment/fiscal state."""
from uuid import UUID,uuid4
import unittest
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.models import InventoryMovement,WorkflowRecord,CompanySubscription,Sale,SaleItem
import test_phase11_procurement as fixtures

class WorkflowDocumentTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.ProcurementTests.asyncSetUp
    cleanup=fixtures.ProcurementTests.cleanup
    post=fixtures.ProcurementTests.post
    stock=fixtures.ProcurementTests.stock
    async def template(self,**changes):return await self.post('/templates',{'paper':'80mm','blocks':[{'kind':'title','text':'Synthetic business <script>bad()</script>'},{'kind':'footer','text':'Synthetic terms & conditions'}],**changes})
    async def test_render_snapshot_escape_reprint_versions_and_expired_historical_render(self):
        template=await self.template();sid=self.sale.id
        await self.db.refresh(self.item);self.item.product_name='<img src=x onerror=bad()>Synthetic';await self.db.commit()
        request=str(uuid4());payload={'request_id':request,'template_id':template['id'],'source_kind':'sale','source_id':str(sid)}
        document=await self.post('/documents',payload);same=await self.post('/documents',payload);self.assertEqual(document['id'],same['id'])
        body=document['payload']['html'];self.assertIn('&lt;script&gt;',body);self.assertIn('&lt;img',body);self.assertNotIn('<script>',body);self.assertNotIn('<img',body)
        second=await self.template(previous_id=template['id'],paper='A4',blocks=[{'kind':'title','text':'New approved synthetic layout'}]);self.assertEqual(second['payload']['document_version'],2)
        self.assertEqual((await self.client.get(f"/api/inventory/workflows/documents/{self.c}/{document['id']}/html")).text,body)
        self.assertEqual(await self.stock(),100);self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.c))).scalar_one(),0)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit()
        historical=await self.post('/documents',{**payload,'request_id':str(uuid4())});self.assertEqual(historical['payload']['html'],body)
        await self.post('/templates',{'paper':'80mm','blocks':[{'kind':'text','text':'Denied new configuration'}]},402)
        response=await self.client.get(f"/api/inventory/workflows/documents/{self.c}/{document['id']}/html")
        self.assertEqual(response.status_code,200);self.assertIn("default-src 'none'",response.headers['content-security-policy']);self.assertEqual(response.headers['x-content-type-options'],'nosniff')
    async def test_tenant_template_branch_and_unsafe_fields_denied(self):
        from app.models import Branch
        branch=Branch(company_id=self.c,shop_id=self.shop.id,name='Synthetic other template branch');self.db.add(branch);await self.db.commit();other=branch.id
        template=await self.template(branch_id=str(other));sid=self.sale.id
        await self.post('/documents',{'template_id':template['id'],'source_kind':'sale','source_id':str(sid)},403)
        await self.post('/documents',{'template_id':str(uuid4()),'source_kind':'sale','source_id':str(sid)},404)
        await self.post('/templates',{'paper':'80mm','blocks':[{'kind':'html','text':'<script>bad()</script>'}]},422)
        await self.post('/templates',{'paper':'80mm','blocks':[{'kind':'text','text':'Plain'}],'logo_url':'http://127.0.0.1/private'},422)
        await self.post('/documents',{'company_id':str(uuid4()),'template_id':template['id'],'source_kind':'sale','source_id':str(sid)},403)
    async def test_template_and_document_are_immutable_and_old_version_cannot_fork(self):
        template=await self.template();document=await self.post('/documents',{'template_id':template['id'],'source_kind':'sale','source_id':str(self.sale.id)})
        for record in [template,document]:
            with self.assertRaises(DBAPIError):
                async with self.db.begin_nested():await self.db.execute(text("UPDATE workflow_records SET payload='{}'::jsonb,version=version+1 WHERE id=:id"),{'id':UUID(record['id'])})
        await self.template(previous_id=template['id'])
        await self.post('/templates',{'previous_id':template['id'],'paper':'80mm','blocks':[{'kind':'text','text':'Fork denied'}]},409)
