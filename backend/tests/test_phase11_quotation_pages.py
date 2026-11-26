"""Historical bounded pages preserve scope and direct original-ID recovery."""
import unittest
from uuid import uuid4
from datetime import datetime,timezone
from fastapi import HTTPException
from app.models import CommerceOrder
import test_phase11_quotations as fixtures
class QuotationPageTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.QuotationTests.asyncSetUp
    cleanup=fixtures.QuotationTests.cleanup
    async def test_older_pages_tied_dates_stable_order_and_direct_old_reference(self):
        rows=[CommerceOrder(company_id=self.company.id,branch_id=self.branch.id,device_id=self.device.id,kind='quotation',quotation_status='draft',request_id=uuid4(),number='OLD-'+uuid4().hex,created_at=datetime(2001,1,1,tzinfo=timezone.utc)) for _ in range(130)]
        self.db.add_all(rows);await self.db.commit()
        expected=[self.order['id']]+sorted([r.id for r in rows],reverse=True)
        found=[]
        for offset in range(0,150,25):
            result=await self.client.get('/api/operations/orders',params={'kind':'quotation','limit':25,'offset':offset});self.assertEqual(result.status_code,200,result.text);found.extend(r['id'] for r in result.json())
        self.assertEqual(found,[str(r) for r in expected]);self.assertEqual(len(set(found)),131)
        old=await self.client.get('/api/operations/orders/'+str(expected[-1]));self.assertEqual(old.status_code,200,old.text);self.assertEqual(old.json()['id'],str(expected[-1]))
        with self.assertRaises(HTTPException) as denied:await self.waiter_svc.list_orders('quotation',limit=25,offset=100)
        self.assertEqual(denied.exception.status_code,403)
        rows[0].waiter_id=self.employee.id;await self.db.commit();self.assertEqual(await self.waiter_svc.list_orders(limit=25),[])
    async def test_bounds_and_current_epoch_on_historical_pages(self):
        for query in [{'limit':0},{'limit':101},{'offset':-1},{'offset':100001}]:
            result=await self.client.get('/api/operations/orders',params=query);self.assertEqual(result.status_code,422)
        with self.assertRaises(HTTPException):await self.svc.list_orders('quotation',limit=101)
        self.user.session_version+=1;await self.db.commit();result=await self.client.get('/api/operations/orders',params={'kind':'quotation','limit':25});self.assertEqual(result.status_code,401)
