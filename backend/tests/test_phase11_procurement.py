"""Synthetic rollback fixtures: procurement owns existing GRNs exactly once."""
from uuid import uuid4,UUID
from datetime import date,timedelta
from decimal import Decimal
from unittest.mock import patch
import unittest
import httpx
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.models import (WorkflowRecord,WorkflowCommand,InventoryBalance,InventoryMovement,CompanySubscription,Product,ProductVariant,VariantInventoryBalance,ProductBatch,Sale)
from app.auth.security import create_access_token,create_employee_access_token
from app.db.session import get_db
from app.main import app
from app.inventory.repository import InventoryRepository
import test_phase7d_operations as fixtures

class ProcurementTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.c,self.b,self.p,self.u,self.e=self.company.id,self.branch.id,self.product.id,self.user.id,self.employee.id
        self.owner_token=create_access_token(str(self.u),self.user.email)
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),base_url='http://synthetic.test',headers={'Authorization':'Bearer '+self.owner_token});self.addAsyncCleanup(self.client.aclose)
    async def post(self,path,values,expected=200):
        response=await self.client.post('/api/inventory/workflows'+path,json={'company_id':str(self.c),'request_id':str(uuid4()),**values})
        self.assertEqual(response.status_code,expected,response.text)
        return response.json() if response.headers.get("content-type","").startswith("application/json") else {"error":response.text}
    async def stock(self):return (await self.db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==self.c,InventoryBalance.product_id==self.p))).scalar_one()
    async def prepare(self,lines=None):
        supplier=await self.post('/suppliers',{'name':'Synthetic supplier','contact':'Sink only'})
        self.line=str(uuid4());self.lines=lines or [{'line_id':self.line,'product_id':str(self.p),'quantity':'10','unit':'each','unit_cost':'3'}]
        po=await self.post('/purchase-orders',{'supplier_id':supplier['id'],'branch_id':str(self.b),'lines':self.lines})
        self.assertEqual(await self.stock(),100)
        approved=await self.post(f"/purchase-orders/{po['id']}/approve",{'version':po['version']})
        self.assertEqual(await self.stock(),100)
        return approved
    async def test_partial_final_grn_and_returns_exact_replay_preserve_stock_and_budget(self):
        po=await self.prepare();path=f"/purchase-orders/{po['id']}/receive";request=str(uuid4())
        payload={'request_id':request,'version':po['version'],'reference':'SYN-1','lines':[{'line_id':self.line,'quantity':'4'}]}
        received=await self.post(path,payload);self.assertEqual(received['order']['state'],'partially_received');self.assertEqual(await self.stock(),104)
        await self.post(path,payload);self.assertEqual(await self.stock(),104)
        returned={'receipt_id':request,'line_id':self.line,'quantity':'2','reason':'Synthetic supplier return','request_id':str(uuid4())}
        await self.post(f"/purchase-orders/{po['id']}/returns",returned);await self.post(f"/purchase-orders/{po['id']}/returns",returned);self.assertEqual(await self.stock(),102)
        await self.post(f"/purchase-orders/{po['id']}/returns",{**returned,'request_id':str(uuid4()),'quantity':'3'},409);self.assertEqual(await self.stock(),102)
        current=(await self.client.get(f"/api/inventory/workflows/{self.c}/{po['id']}")).json()
        final=await self.post(path,{'version':current['version'],'reference':'SYN-2','lines':[{'line_id':self.line,'quantity':'6'}]});self.assertEqual(final['order']['state'],'received');self.assertEqual(await self.stock(),108)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.c))).scalar_one(),3)
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id==self.c))).scalar_one(),1) # only fixture sale
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit()
        await self.post(path,payload);self.assertEqual(await self.stock(),108)
        await self.post(path,{**payload,'request_id':str(uuid4())},402)
        await self.post(path,{**payload,'reference':'changed'},409)
    async def test_tenant_branch_role_and_frozen_approval(self):
        po=await self.prepare()
        employee=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='cashier')
        denied=await self.client.post('/api/inventory/workflows/suppliers',headers={'Authorization':'Bearer '+employee},json={'company_id':str(self.c),'request_id':str(uuid4()),'name':'Denied'})
        self.assertEqual(denied.status_code,403)
        await self.post('/purchase-orders',{'supplier_id':po['payload']['supplier_id'],'branch_id':str(uuid4()),'lines':self.lines},404)
        await self.post('/purchase-orders',{'supplier_id':str(uuid4()),'branch_id':str(self.b),'lines':self.lines},404)
        foreign=await self.client.get(f'/api/inventory/workflows/{uuid4()}/{po["id"]}');self.assertEqual(foreign.status_code,403)
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text("UPDATE workflow_records SET payload='{}'::jsonb,version=version+1 WHERE id=:id"),{'id':UUID(po['id'])})
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text('DELETE FROM workflow_commands WHERE request_id=:id'),{'id':UUID(po['request_id'])})
    async def test_second_line_failure_rolls_back_all_grns_cost_po_and_parent_proof(self):
        other=Product(company_id=self.c,name='Synthetic second receiving line',selling_price=5,cost_price=1,stock_qty=0);self.db.add(other);await self.db.commit();other_id=other.id
        first=str(uuid4());second=str(uuid4())
        po=await self.prepare([{'line_id':first,'product_id':str(self.p),'quantity':'2','unit':'each','unit_cost':'7'},{'line_id':second,'product_id':str(other_id),'quantity':'2','unit':'each','unit_cost':'8'}])
        original=InventoryRepository.apply_movement;calls=0
        async def fail(repo,*args):
            nonlocal calls
            calls+=1
            if calls==2:raise RuntimeError('synthetic second GRN failure')
            return await original(repo,*args)
        request=str(uuid4());payload={'request_id':request,'version':po['version'],'reference':'SYN-FAIL','lines':[{'line_id':first,'quantity':'1'},{'line_id':second,'quantity':'1'}]}
        with patch.object(InventoryRepository,'apply_movement',fail):await self.post(f"/purchase-orders/{po['id']}/receive",payload,500)
        self.assertEqual(await self.stock(),100);self.assertIsNone(await self.db.get(WorkflowCommand,UUID(request)))
        current=(await self.client.get(f"/api/inventory/workflows/{self.c}/{po['id']}")).json();self.assertEqual(current['state'],'approved');self.assertEqual(current['version'],po['version'])
        await self.post(f"/purchase-orders/{po['id']}/receive",payload);self.assertEqual(await self.stock(),101)
    async def test_variant_lot_receipt_and_supplier_return_keep_original_attribution(self):
        variant=ProductVariant(company_id=self.c,product_id=self.p,name='Synthetic lot variant',cost_price=2);self.db.add(variant);await self.db.commit();vid=variant.id
        line=str(uuid4());po=await self.prepare([{'line_id':line,'product_id':str(self.p),'variant_id':str(vid),'quantity':'5','unit':'each','unit_cost':'4'}])
        receipt=str(uuid4());payload={'request_id':receipt,'version':po['version'],'reference':'LOT-SINK','lines':[{'line_id':line,'quantity':'2','lot_code':'SYN-LOT','expires_on':str(date.today()+timedelta(days=60))}]}
        result=await self.post(f"/purchase-orders/{po['id']}/receive",payload)
        self.assertEqual(await self.stock(),100)
        self.assertEqual((await self.db.execute(select(VariantInventoryBalance.quantity).where(VariantInventoryBalance.variant_id==vid))).scalar_one(),2)
        returned=await self.post(f"/purchase-orders/{po['id']}/returns",{'receipt_id':receipt,'line_id':line,'quantity':'1','reason':'Synthetic lot return'})
        self.assertEqual((await self.db.execute(select(ProductBatch.quantity).where(ProductBatch.id==UUID(result['lines'][0]['batch_id'])))).scalar_one(),1)
        self.assertEqual((await self.db.execute(select(VariantInventoryBalance.quantity).where(VariantInventoryBalance.variant_id==vid))).scalar_one(),1)

    async def test_editable_draft_and_cancelled_remainder_preserve_receipts(self):
        supplier=await self.post('/suppliers',{'name':'Editable synthetic vendor'})
        lid=str(uuid4());body={'company_id':str(self.c),'request_id':str(uuid4()),'supplier_id':supplier['id'],'branch_id':str(self.b),'lines':[{'line_id':lid,'product_id':str(self.p),'quantity':'5','unit':'each','unit_cost':'3'}]}
        po=await self.post('/purchase-orders',body)
        changed={**body,'request_id':str(uuid4()),'version':po['version'],'lines':[{**body['lines'][0],'quantity':'6'}]}
        response=await self.client.put(f"/api/inventory/workflows/purchase-orders/{po['id']}",json=changed);self.assertEqual(response.status_code,200,response.text);po=response.json()
        po=await self.post(f"/purchase-orders/{po['id']}/approve",{'version':po['version']})
        received=await self.post(f"/purchase-orders/{po['id']}/receive",{'version':po['version'],'reference':'SYN-CANCEL','lines':[{'line_id':lid,'quantity':'2'}]})
        cancelled=await self.post(f"/purchase-orders/{po['id']}/cancel",{'version':received['order']['version'],'reason':'Cancel unused remainder'})
        self.assertEqual(cancelled['state'],'cancelled');self.assertEqual(await self.stock(),102)
        await self.post(f"/purchase-orders/{po['id']}/receive",{'version':cancelled['version'],'reference':'DENIED','lines':[{'line_id':lid,'quantity':'1'}]},409)
        self.assertEqual(await self.stock(),102)

    async def test_direct_service_cannot_skip_current_actor_or_tenant_authority(self):
        from app.workflows.procurement import ProcurementService
        from app.workflows.schema import SupplierInput
        from app.auth.dependencies import AuthActor
        from fastapi import HTTPException
        data=SupplierInput(company_id=self.c,request_id=uuid4(),name='Denied direct supplier')
        for actor,expected in [(None,401),(AuthActor(actor_type='user',company_id=uuid4(),role='owner'),403)]:
            with self.assertRaises(HTTPException) as error:await ProcurementService(self.db,actor).supplier(data)
            self.assertEqual(error.exception.status_code,expected)
        self.assertEqual(await self.stock(),100)

    async def test_receiver_without_cost_visibility_cannot_read_or_post_cost_bearing_po(self):
        from app.employees.permissions import normalize_permissions
        po=await self.prepare()
        template=await self.post('/templates',{'paper':'80mm','blocks':[{'kind':'title','text':'Synthetic purchasing'}]})
        document=await self.post('/documents',{'template_id':template['id'],'source_kind':'purchase_order','source_id':po['id']})
        await self.db.refresh(self.employee);self.employee.role='inventory_clerk';self.employee.permissions=normalize_permissions('inventory_clerk',{'product_costs_view':False});await self.db.commit()
        bearer=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='inventory_clerk')
        headers={'Authorization':'Bearer '+bearer}
        read=await self.client.get(f"/api/inventory/workflows/{self.c}/{po['id']}",headers=headers);self.assertEqual(read.status_code,403,read.text)
        for path in [f"/{self.c}/{po['id']}/history",f"/{self.c}/{document['id']}",f"/{self.c}/{document['id']}/history",f"/documents/{self.c}/{document['id']}/html"]:
            read=await self.client.get('/api/inventory/workflows'+path,headers=headers);self.assertEqual(read.status_code,403,read.text)
        response=await self.client.post(f"/api/inventory/workflows/purchase-orders/{po['id']}/receive",headers=headers,json={'company_id':str(self.c),'request_id':str(uuid4()),'version':po['version'],'reference':'DENIED-COST','lines':[{'line_id':self.line,'quantity':'1'}]})
        self.assertEqual(response.status_code,403,response.text);self.assertEqual(await self.stock(),100)

    async def test_workflow_record_and_history_pages_are_bounded_scoped_and_stable(self):
        suppliers=[await self.post('/suppliers',{'name':f'Synthetic paged supplier {i}'}) for i in range(5)]
        path=f'/api/inventory/workflows/{self.c}'
        pages=[await self.client.get(path,params={'kind':'supplier','limit':2,'offset':i}) for i in (0,2,4)]
        for response in pages:self.assertEqual(response.status_code,200,response.text)
        ids=[r['id'] for response in pages for r in response.json()]
        self.assertEqual(len(set(ids)),5);self.assertEqual(set(ids),{r['id'] for r in suppliers})
        again=await self.client.get(path,params={'kind':'supplier','limit':2,'offset':2});self.assertEqual(again.json(),pages[1].json())
        for params in [{'kind':'supplier','limit':101},{'kind':'supplier','offset':-1}]:self.assertEqual((await self.client.get(path,params=params)).status_code,422)
        self.assertEqual((await self.client.get(f'/api/inventory/workflows/{uuid4()}',params={'kind':'supplier','offset':2})).status_code,403)
        supplier=suppliers[0]
        for i in range(3):
            response=await self.client.put(f"/api/inventory/workflows/suppliers/{supplier['id']}",json={'company_id':str(self.c),'request_id':str(uuid4()),'version':supplier['version'],'name':f'Synthetic revision {i}','contact':'','active':True})
            self.assertEqual(response.status_code,200,response.text);supplier=response.json()
        history=f"{path}/{supplier['id']}/history"
        a=await self.client.get(history,params={'limit':2});b=await self.client.get(history,params={'limit':2,'offset':2})
        self.assertEqual(a.status_code,200,a.text);self.assertEqual(b.status_code,200,b.text)
        self.assertEqual(len({r['request_id'] for r in a.json()+b.json()}),4)
        self.assertEqual(await self.stock(),100)
