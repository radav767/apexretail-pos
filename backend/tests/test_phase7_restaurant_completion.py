"""Offline kitchen/KDS intents are unpaid, atomic and original-actor bound."""
import unittest
from datetime import datetime,timezone,timedelta
from uuid import uuid4
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import select,func
from app.auth.dependencies import AuthActor
from app.employees.permissions import normalize_permissions
from app.models import PrintJob,KitchenTicket,InventoryMovement,Sale,CommerceOrder,AuditEvent,Device
from app.models.business_operations import OrderSyncReceipt
from app.business_operations.offline import OfflineOrderService
from app.business_operations.schema import OfflineKitchenInput,OfflineKDSInput,OfflineEditInput,ItemUpdate
import test_phase7d_operations as fixtures


class RestaurantCompletionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.Phase7DOperationsTests.asyncSetUp
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    open=fixtures.Phase7DOperationsTests.open
    add=fixtures.Phase7DOperationsTests.add

    def kitchen_command(self,order,**changes):
        data=dict(request_id=uuid4(),employee_id=self.employee.id,device_id=self.device.id,
            captured_at=datetime.now(timezone.utc),order_id=order["id"],version=order["version"])
        data.update(changes);return OfflineKitchenInput(**data)

    def kitchen_actor(self):
        return AuthActor(actor_type="employee",company_id=self.company.id,role="kitchen_staff",
            employee=self.employee,pos_session=self.session,permissions=normalize_permissions("kitchen_staff",{}))

    async def refresh(self):
        for row in (self.employee,self.session,self.device,self.company,self.branch,self.product,self.balance):await self.db.refresh(row)

    async def test_offline_kitchen_intent_creates_one_ticket_without_sale_payment_or_stock(self):
        order=await self.add(await self.open())
        command=self.kitchen_command(order);svc=OfflineOrderService(self.db,self.waiter)
        before=(await self.db.execute(select(func.count(Sale.id)))).scalar_one()
        first=await svc.synchronize(command,action="kitchen")
        repeat=await svc.synchronize(command,action="kitchen")
        self.assertEqual(first["order"],repeat["order"]);self.assertTrue(repeat["already_synchronized"])
        self.assertEqual((await self.db.execute(select(func.count(KitchenTicket.id)).where(KitchenTicket.order_id==order["id"]))).scalar_one(),1)
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)))).scalar_one(),before)
        self.assertEqual(self.balance.quantity,100)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(),0)
        recovery=await svc.recover(command,action="kitchen")
        self.assertEqual(recovery["request_id"],str(command.request_id))

    async def test_kitchen_receipt_and_jobs_rollback_together_after_dispatch_failure(self):
        order=await self.add(await self.open());command=self.kitchen_command(order)
        svc=OfflineOrderService(self.db,self.waiter);audit=svc.audit;company=self.company.id
        def fail(action,**details):
            if action=="offline_order_synchronized":raise RuntimeError("Synthetic receipt failure")
            return audit(action,**details)
        with patch.object(svc,"audit",side_effect=fail):
            with self.assertRaises(RuntimeError):await svc.synchronize(command,action="kitchen")
        self.assertEqual((await self.db.execute(select(func.count(PrintJob.id)).where(PrintJob.company_id==company,PrintJob.order_id==order["id"]))).scalar_one(),0)
        self.assertEqual((await self.db.execute(select(func.count(OrderSyncReceipt.id)).where(OrderSyncReceipt.request_id==command.request_id))).scalar_one(),0)
        await self.refresh()
        retry=await svc.synchronize(command,action="kitchen")
        self.assertFalse(retry["already_synchronized"])

    async def test_kitchen_stale_version_is_retained_then_explicitly_resolved_without_dispatch(self):
        order=await self.add(await self.open());command=self.kitchen_command(order)
        current=await self.add(order,quantity="1");svc=OfflineOrderService(self.db,self.waiter)
        with self.assertRaises(HTTPException) as conflict:await svc.synchronize(command,action="kitchen")
        self.assertEqual(conflict.exception.status_code,409);await self.refresh()
        reviewed=await svc.review(command,action="kitchen")
        self.assertEqual(reviewed["current_version"],current["version"])
        resolved=await svc.resolve(command,action="kitchen",observed_version=current["version"],reason="Accept amended server order")
        self.assertEqual(resolved["resolution"]["decision"],"accepted_server_state")
        repeat=await svc.synchronize(command,action="kitchen")
        self.assertIn("resolution",repeat)
        self.assertEqual((await self.db.execute(select(func.count(KitchenTicket.id)).where(KitchenTicket.order_id==order["id"]))).scalar_one(),0)
        self.assertEqual(self.balance.quantity,100)

    async def test_kds_sync_recovery_conflict_resolution_does_not_regress_status_or_print(self):
        order=await self.add(await self.open());await self.svc.send_kitchen(order["id"],order["version"])
        ticket=(await self.db.execute(select(KitchenTicket).where(KitchenTicket.order_id==order["id"]))).scalar_one()
        command=OfflineKDSInput(request_id=uuid4(),employee_id=self.employee.id,device_id=self.device.id,
            captured_at=datetime.now(timezone.utc),ticket_id=ticket.id,expected_status="queued",status="preparing")
        svc=OfflineOrderService(self.db,self.kitchen_actor())
        await svc.synchronize(command,action="kds");repeat=await svc.synchronize(command,action="kds")
        self.assertEqual(repeat["order"]["ticket_status"],"preparing")
        self.assertNotIn("items",repeat["order"])
        stale=command.model_copy(update={"request_id":uuid4()})
        with self.assertRaises(HTTPException):await svc.synchronize(stale,action="kds")
        await self.refresh()
        reviewed=await svc.review(stale,action="kds")
        self.assertEqual(reviewed["current_status"],"preparing")
        await svc.resolve(stale,action="kds",observed_status="preparing",reason="Keep verified kitchen state")
        await svc.synchronize(stale,action="kds")
        await self.db.refresh(ticket);self.assertEqual(ticket.status,"preparing")
        self.assertEqual((await self.db.execute(select(func.count(PrintJob.id)).where(PrintJob.order_id==order["id"]))).scalar_one(),1)

    async def test_original_actor_register_permissions_and_capture_time_remain_required(self):
        order=await self.add(await self.open());command=self.kitchen_command(order)
        svc=OfflineOrderService(self.db,self.waiter)
        for changed in ({"employee_id":uuid4()},{"device_id":uuid4()},{"captured_at":datetime.now()}):
            with self.assertRaises(HTTPException):await svc.synchronize(command.model_copy(update=changed),action="kitchen")
        self.waiter.permissions["orders_send"]=False
        with self.assertRaises(HTTPException):await svc.synchronize(command,action="kitchen")
        self.waiter.permissions["orders_send"]=True
        with self.assertRaises(HTTPException):await svc.resolve(command.model_copy(update={"captured_at":datetime.now()}),
            action="kitchen",observed_version=order["version"],reason="Reject invented timestamp")

    async def test_unknown_recovery_is_read_only_and_changed_review_cannot_force_resolution(self):
        order=await self.add(await self.open());command=self.kitchen_command(order)
        svc=OfflineOrderService(self.db,self.waiter)
        with self.assertRaises(HTTPException) as missing:await svc.recover(command,action="kitchen")
        self.assertEqual(missing.exception.status_code,404)
        with self.assertRaises(HTTPException):await svc.resolve(command,action="kitchen",observed_version=order["version"]+1,reason="Stale review")
        self.assertEqual((await self.db.execute(select(func.count(OrderSyncReceipt.id)).where(OrderSyncReceipt.request_id==command.request_id))).scalar_one(),0)
