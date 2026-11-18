from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal
import unittest
import httpx
from fastapi import HTTPException
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.models import CompanySubscription,Sale,InventoryMovement,CommerceOrder
from app.models.business_operations import OrderSyncReceipt
from app.auth.security import create_access_token,hash_session_token
from app.employees.permissions import normalize_permissions
from app.db.session import get_db
from app.main import app
from app.business_operations.schema import OrderInput,OrderItemInput,SettlementInput,OfflineDraftInput
from app.sales.schema import SaleCreate
from app.business_operations.offline import OfflineOrderService
import test_phase7d_operations as fixtures


class OperationReplayTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    open=fixtures.Phase7DOperationsTests.open
    add=fixtures.Phase7DOperationsTests.add
    ready=fixtures.Phase7DOperationsTests.ready
    payment=fixtures.Phase7DOperationsTests.payment

    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.license=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one()
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test')
        self.addAsyncCleanup(self.client.aclose)
        self.headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)}

    async def post(self,path,data,headers=None):
        return await self.client.post('/api/operations/'+path,headers=headers or self.headers,json=data.model_dump(mode='json'))

    async def test_creation_and_settlement_replay_after_expiry_preserve_one_sale(self):
        create=OrderInput(branch_id=self.branch.id,device_id=self.device.id,request_id=uuid4(),waiter_id=self.employee.id)
        first=await self.post('orders',create);self.assertEqual(first.status_code,200,first.text)
        order=await self.add(first.json());order=(await self.svc.send_kitchen(order['id'],order['version']))['order']
        payment=self.payment(order)
        settled=await self.post(f"orders/{order['id']}/settle",payment)
        self.assertEqual(settled.status_code,200,settled.text)
        self.license.status='expired';self.license.commercial_terms={'features':{}};await self.db.commit()
        duplicate=await self.post(f"orders/{order['id']}/settle",payment)
        self.assertEqual(duplicate.status_code,200,duplicate.text)
        self.assertEqual(duplicate.json()['sale_id'],settled.json()['sale_id'])
        self.assertTrue(duplicate.json()['already_settled'])
        self.assertEqual((await self.post('orders',create)).status_code,200)
        changed=payment.model_copy(update={'payment':payment.payment.model_copy(update={'amount_received':Decimal(101)})})
        self.assertEqual((await self.post(f"orders/{order['id']}/settle",changed)).status_code,409)
        self.assertEqual((await self.post('orders',create.model_copy(update={'request_id':uuid4()}))).status_code,402)
        self.assertEqual(self.balance.quantity,98)
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id==self.company.id))).scalar_one(),2)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(),1)
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text('UPDATE commerce_orders SET settlement_payload_hash=\'changed\' WHERE company_id=:company'),{'company':self.company.id})

    async def test_direct_mutating_service_paths_deny_expired_license_before_effects(self):
        order=await self.open();self.license.status='suspended';await self.db.commit()
        with self.assertRaises(HTTPException) as error:await self.svc.add_item(order['id'],OrderItemInput(version=order['version'],product_id=self.product.id,quantity=2))
        self.assertEqual(error.exception.status_code,402)
        row=await self.svc.order(order['id']);self.assertEqual(len(await self.svc.order_items(row)),0)
        self.assertEqual(self.balance.quantity,100)

    async def test_room_service_dispatch_keeps_hospitality_feature_policy(self):
        from app.business_operations.schema import ProfileInput
        await self.svc.save_profile(ProfileInput(profile='hospitality'))
        self.license.commercial_terms={'features':{'hospitality':True,'restaurant':False,'kitchen_printing':True}}
        await self.db.commit()
        order=await self.add(await self.open(kind='room_service'))
        result=await self.svc.send_kitchen(order['id'],order['version'])
        self.assertEqual(len(result['jobs']),1)
        self.assertEqual(self.balance.quantity,100)

    async def test_offline_receipt_replay_bypasses_only_license_not_payload_or_actor(self):
        self.employee.role='waiter';self.employee.permissions=normalize_permissions('waiter',{})
        secret='synthetic-original-register-secret';self.session.token_hash=hash_session_token(secret);await self.db.commit()
        headers={'Authorization':'Bearer '+secret}
        data=OfflineDraftInput(request_id=uuid4(),employee_id=self.employee.id,captured_at=datetime.now(timezone.utc),
            order=OrderInput(branch_id=self.branch.id,device_id=self.device.id,request_id=uuid4()),
            items=[OrderItemInput(version=1,product_id=self.product.id,quantity=2)])
        original=await self.post('offline/drafts',data,headers);self.assertEqual(original.status_code,200,original.text)
        self.license.status='expired';self.license.commercial_terms={'features':{}};await self.db.commit()
        replay=await self.post('offline/drafts',data,headers)
        self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['already_synchronized'])
        altered=data.model_copy(update={'items':[OrderItemInput(version=1,product_id=self.product.id,quantity=3)]})
        self.assertEqual((await self.post('offline/drafts',altered,headers)).status_code,409)
        pending=data.model_copy(update={'request_id':uuid4(),'order':data.order.model_copy(update={'request_id':uuid4()})})
        self.assertEqual((await self.post('offline/drafts',pending,headers)).status_code,402)
        self.assertEqual((await self.db.execute(select(func.count(OrderSyncReceipt.id)).where(OrderSyncReceipt.company_id==self.company.id))).scalar_one(),1)
        self.assertEqual(self.balance.quantity,100)
