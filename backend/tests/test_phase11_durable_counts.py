"""Frozen scope, DB revisions and reviewed count approval through existing counts."""
from uuid import UUID,uuid4
from datetime import date,timedelta
from decimal import Decimal
from unittest.mock import patch
import unittest
from sqlalchemy import select,func
from app.models import (InventoryBalance,InventoryMovement,Product,ProductBatch,CompanySubscription,SaleItem,WorkflowCommand)
from app.inventory.repository import InventoryRepository
import test_phase11_procurement as procurement_fixtures

class DurableCountTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=procurement_fixtures.ProcurementTests.asyncSetUp
    cleanup=procurement_fixtures.ProcurementTests.cleanup
    post=procurement_fixtures.ProcurementTests.post
    stock=procurement_fixtures.ProcurementTests.stock
    async def open_count(self,scope='partial'):
        return await self.post('/counts',{'branch_id':str(self.b),'scope':scope,**({'product_ids':[str(self.p)]} if scope=='partial' else {})})
    async def submit_count(self,row,delta=-3):
        measurements=[{'key':e['key'],'quantity':str(Decimal(e['baseline'])+(Decimal(delta) if e['kind'] not in {'unassigned','hold'} else 0))} for e in row['payload']['rows']]
        row=await self.post(f"/counts/{row['id']}/measure",{'version':row['version'],'measurements':measurements})
        self.assertEqual(await self.stock(),100)
        return await self.post(f"/counts/{row['id']}/submit",{'version':row['version']})
    async def test_draft_variance_review_approval_and_expired_exact_recovery(self):
        row=await self.open_count();self.assertEqual(row['payload']['rows'][0]['measured'],None)
        await self.post(f"/counts/{row['id']}/submit",{'version':row['version']},409)
        row=await self.submit_count(row);self.assertEqual(await self.stock(),100);self.assertEqual(row['payload']['rows'][0]['variance'],'-3.000')
        request=str(uuid4());command={'request_id':request,'version':row['version'],'reason':'Synthetic variance reviewed'}
        result=await self.post(f"/counts/{row['id']}/approve",command);self.assertEqual(await self.stock(),97);self.assertEqual(len(result['movement_ids']),1)
        await self.post(f"/counts/{row['id']}/approve",command);self.assertEqual(await self.stock(),97)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit()
        await self.post(f"/counts/{row['id']}/approve",command);self.assertEqual(await self.stock(),97)
        await self.post(f"/counts/{row['id']}/approve",{**command,'reason':'changed'},409)
        await self.post(f"/counts/{row['id']}/approve",{**command,'request_id':str(uuid4())},402)
    async def test_sale_then_refund_net_zero_requires_explicit_recount_and_new_measurement(self):
        row=await self.submit_count(await self.open_count(),0)
        sale=await self.client.post('/api/sales',json={'company_id':str(self.c),'branch_id':str(self.b),'device_id':str(self.device.id),'client_sale_id':str(uuid4()),'payment_method':'cash','amount_received':'100','items':[{'product_id':str(self.p),'quantity':'1'}]})
        self.assertEqual(sale.status_code,200,sale.text);sid=UUID(sale.json()['id'])
        item=(await self.db.execute(select(SaleItem.id).where(SaleItem.sale_id==sid))).scalar_one()
        returned=await self.client.post('/api/sales/refunds',json={'request_id':str(uuid4()),'company_id':str(self.c),'branch_id':str(self.b),'device_id':str(self.device.id),'original_sale_id':str(sid),'reason':'Synthetic net-zero return','items':[{'sale_item_id':str(item),'quantity':'1'}]})
        self.assertEqual(returned.status_code,200,returned.text);self.assertEqual(await self.stock(),100)
        await self.post(f"/counts/{row['id']}/approve",{'version':row['version'],'reason':'Stale net zero'},409)
        recounted=await self.post(f"/counts/{row['id']}/recount",{'version':row['version'],'reason':'Actual recount after movements'})
        self.assertIsNone(recounted['payload']['rows'][0]['measured']);self.assertIn('previous_baseline',recounted)
        approved=await self.submit_count(recounted,0);result=await self.post(f"/counts/{row['id']}/approve",{'version':approved['version'],'reason':'Confirmed after recount'})
        self.assertEqual(result['movement_ids'],[]);self.assertEqual(await self.stock(),100)
    async def test_full_scope_detects_new_positions_partial_scope_keeps_other_goods_independent(self):
        full=await self.submit_count(await self.open_count('full'),0)
        partial=await self.submit_count(await self.open_count(),0)
        other=Product(company_id=self.c,name='Synthetic newly received position',selling_price=2,stock_qty=1);self.db.add(other);await self.db.flush()
        self.db.add(InventoryBalance(company_id=self.c,shop_id=self.shop.id,branch_id=self.b,product_id=other.id,quantity=1,reorder_level=0));await self.db.commit()
        await self.post(f"/counts/{full['id']}/approve",{'version':full['version'],'reason':'Full stale scope'},409)
        result=await self.post(f"/counts/{partial['id']}/approve",{'version':partial['version'],'reason':'Selected product unchanged'})
        self.assertEqual(result['movement_ids'],[])
    async def test_selected_lot_count_uses_existing_stock_and_attribution_once(self):
        batch=ProductBatch(company_id=self.c,branch_id=self.b,product_id=self.p,code='COUNT-SYN',expires_on=date.today()+timedelta(days=60),quantity=100);self.db.add(batch);await self.db.commit();bid=batch.id
        row=await self.submit_count(await self.open_count(),-2)
        result=await self.post(f"/counts/{row['id']}/approve",{'version':row['version'],'reason':'Synthetic lot variance reviewed'})
        self.assertEqual(await self.stock(),98);self.assertEqual(len(result['movement_ids']),1)
        self.assertEqual((await self.db.execute(select(ProductBatch.quantity).where(ProductBatch.id==bid))).scalar_one(),98)
    async def test_multiple_position_failure_rolls_back_stock_child_proofs_and_session(self):
        other=Product(company_id=self.c,name='Synthetic second count position',selling_price=2,stock_qty=10);self.db.add(other);await self.db.flush();pid=other.id
        self.db.add(InventoryBalance(company_id=self.c,shop_id=self.shop.id,branch_id=self.b,product_id=pid,quantity=10,reorder_level=0));await self.db.commit()
        row=await self.open_count('full')
        row=await self.post(f"/counts/{row['id']}/measure",{'version':row['version'],'measurements':[{'key':e['key'],'quantity':str(Decimal(e['baseline'])-1)} for e in row['payload']['rows']]})
        row=await self.post(f"/counts/{row['id']}/submit",{'version':row['version']})
        original=InventoryRepository.apply_movements;calls=0
        async def fail(repo,*args):
            nonlocal calls
            calls+=1
            if calls==2:raise RuntimeError('synthetic second count failure')
            return await original(repo,*args)
        request=str(uuid4());command={'request_id':request,'version':row['version'],'reason':'Reviewed synthetic set'}
        with patch.object(InventoryRepository,'apply_movements',fail):await self.post(f"/counts/{row['id']}/approve",command,500)
        self.assertEqual(await self.stock(),100);self.assertIsNone(await self.db.get(WorkflowCommand,UUID(request)))
        self.assertEqual((await self.db.execute(select(InventoryBalance.quantity).where(InventoryBalance.product_id==pid))).scalar_one(),10)
        await self.post(f"/counts/{row['id']}/approve",command);self.assertEqual(await self.stock(),99)

    async def test_count_permission_cannot_grant_approval_or_foreign_branch_access(self):
        from app.auth.security import create_employee_access_token
        from app.employees.permissions import normalize_permissions
        row=await self.submit_count(await self.open_count(),0)
        await self.db.refresh(self.employee);self.employee.role='inventory_clerk';self.employee.permissions=normalize_permissions('inventory_clerk',{});await self.db.commit()
        employee=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='inventory_clerk')
        response=await self.client.post(f"/api/inventory/workflows/counts/{row['id']}/approve",headers={'Authorization':'Bearer '+employee},json={'company_id':str(self.c),'request_id':str(uuid4()),'version':row['version'],'reason':'Not an approver'})
        self.assertEqual(response.status_code,403,response.text)
        await self.post('/counts',{'branch_id':str(uuid4()),'scope':'full'},404)
        self.assertEqual(await self.stock(),100)

    async def test_lot_metadata_cutoff_and_rejection_preserve_stock_and_history(self):
        batch=ProductBatch(company_id=self.c,branch_id=self.b,product_id=self.p,code='SYN-CUTOFF',expires_on=date.today()+timedelta(days=30),quantity=100);self.db.add(batch);await self.db.commit()
        row=await self.submit_count(await self.open_count(),0)
        batch.expires_on=date.today()+timedelta(days=60);await self.db.commit()
        await self.post(f"/counts/{row['id']}/approve",{'version':row['version'],'reason':'Stale lot metadata'},409)
        rejected=await self.post(f"/counts/{row['id']}/reject",{'version':row['version'],'reason':'Recount changed lot scope'})
        self.assertEqual(rejected['state'],'rejected');self.assertEqual(await self.stock(),100)
        history=await self.client.get(f"/api/inventory/workflows/{self.c}/{row['id']}/history")
        self.assertEqual(history.status_code,200,history.text);self.assertIn('count_reject',{e['kind'] for e in history.json()})
