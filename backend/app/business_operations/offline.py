"""Atomic, cashier-bound synchronization of UNPAID restaurant drafts.

No payments, stock reservations, timestamp substitution or automatic KOTs.
Conflicts leave the client command intact for explicit review. Permissions are
rechecked using the current authenticated session, never cached client grants.
"""
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from app.models import Device, CommerceOrder, KitchenTicket, PrinterStation
from app.models.business_operations import OrderSyncReceipt
from app.printing.service import digest, permit
from .service import BusinessService


class OfflineOrderService(BusinessService):
    @staticmethod
    def validate_capture(captured):
        if captured.tzinfo is None or captured>datetime.now(timezone.utc)+timedelta(minutes=5):
            raise HTTPException(422,"An original timezone-aware capture timestamp is required")
    async def review(self,data,*,action):
        try:return await self.recover(data,action=action)
        except HTTPException as error:
            if error.status_code!=404:raise
        device_id=data.order.device_id if action=="draft" else data.device_id
        device=await self.db.get(Device,device_id)
        if action=="kds":
            ticket=(await self.db.execute(select(KitchenTicket).where(KitchenTicket.id==data.ticket_id,
                KitchenTicket.company_id==self.actor.company_id).with_for_update())).scalar_one_or_none()
            if not ticket:raise HTTPException(404,"Kitchen ticket not found")
            order=await self.db.get(CommerceOrder,ticket.order_id)
            await self.branch(order.branch_id)
            if order.branch_id!=device.branch_id:raise HTTPException(403,"Kitchen register belongs to another branch")
            station=await self.db.get(PrinterStation,ticket.station_id)
            permit(self.actor,"bar_update" if station.purpose=="bar" else "kitchen_update")
            return {"order":{"id":str(order.id)},"current_status":ticket.status}
        if action=="draft":
            order=(await self.db.execute(select(CommerceOrder).where(CommerceOrder.company_id==self.actor.company_id,
                CommerceOrder.request_id==data.order.request_id))).scalar_one_or_none()
            if not order:raise HTTPException(404,"Original draft has not reached the server; synchronize the unchanged draft")
            row=await self.order(order.id)
        else:row=await self.order(data.order_id)
        if row.device_id!=device_id or row.waiter_id!=data.employee_id:
            raise HTTPException(403,"Original command belongs to another employee/register")
        return {"order":await self.order_out(row),"current_version":row.version}

    async def resolve(self,data,*,action,observed_version=None,observed_status=None,reason):
        self.validate_capture(data.captured_at)
        if len(reason.strip())<3:raise HTTPException(422,"A review reason is required")
        device_id=data.order.device_id if action=="draft" else data.device_id
        # Same register-first lock as synchronize; resolution cannot race a
        # command into applying after the user accepted the current server state.
        await self.db.execute(select(Device).where(Device.id==device_id,
            Device.company_id==self.actor.company_id).with_for_update())
        result=await self.review(data,action=action)
        if result.get("already_synchronized") is not None:return result
        if action=="kds":
            if observed_status is None or result["current_status"]!=observed_status:
                raise HTTPException(409,"Kitchen status changed since review; review again")
        elif observed_version is None or result["current_version"]!=observed_version:
            raise HTTPException(409,"Order changed since review; review again")
        fingerprint=digest({"action":action,"data":data.model_dump(mode="json")})
        resolution={"decision":"accepted_server_state","reason":reason.strip(),
            "reviewed_by":str(self.actor.employee.id),"reviewed_at":datetime.now(timezone.utc).isoformat(),
            "observed_version":observed_version,"observed_status":observed_status}
        snapshot=jsonable_encoder({**result["order"],"_offline_resolution":resolution})
        try:
            self.db.add(OrderSyncReceipt(company_id=self.actor.company_id,employee_id=data.employee_id,
                device_id=device_id,request_id=data.request_id,payload_hash=fingerprint,captured_at=data.captured_at,result=snapshot))
            self.audit("offline_command_resolved",request_id=data.request_id,order_id=result["order"]["id"],
                command_type=action,decision="accepted_server_state",reason=reason.strip(),payload_hash=fingerprint)
            await self.db.commit()
            return {"order":snapshot,"already_synchronized":False,"request_id":str(data.request_id),"resolution":resolution}
        except Exception:
            await self.db.rollback();raise

    def command_permission(self,action):
        if action=="kds":
            from app.employees.permissions import has_permission
            if not any(has_permission(self.actor.permissions,p) for p in ("kitchen_update","bar_update")):
                raise HTTPException(403,"Kitchen/bar update permission required")
        else:
            permit(self.actor,"orders_manage")
            if action=="kitchen":permit(self.actor,"orders_send")

    @staticmethod
    def acknowledgement(receipt):
        return {"order":receipt.result,"already_synchronized":True,"request_id":str(receipt.request_id),
            **({"resolution":receipt.result["_offline_resolution"]} if receipt.result.get("_offline_resolution") else {})}

    async def recover(self, data, *, edit=False, action=None):
        """Read-only confirmation probe; never recreates an unknown command."""
        action=action or ("edit" if edit else "draft")
        self.command_permission(action)
        device_id = data.order.device_id if action=="draft" else data.device_id
        employee = self.actor.employee
        if (not employee or employee.id != data.employee_id or not employee.active or employee.deleted
                or not self.actor.pos_session or self.actor.pos_session.device_id != device_id):
            raise HTTPException(403, "Recover using the original employee/register")
        device = await self.db.get(Device, device_id)
        if not device or device.company_id != self.actor.company_id or not device.active or device.deleted or device.removed_at or device.deactivated_at:
            raise HTTPException(403, "Original register is unavailable")
        await self.branch(device.branch_id)
        receipt = (await self.db.execute(select(OrderSyncReceipt).where(OrderSyncReceipt.company_id == self.actor.company_id,
            OrderSyncReceipt.request_id == data.request_id))).scalar_one_or_none()
        if not receipt: raise HTTPException(404, "No server acknowledgement. Original command is retained for synchronization")
        fingerprint = digest({"action": action, "data": data.model_dump(mode="json")})
        if receipt.employee_id != employee.id or receipt.device_id != device_id or receipt.payload_hash != fingerprint:
            raise HTTPException(409, "Original command differs; retain it for review")
        return self.acknowledgement(receipt)

    async def commit_operation(self):
        # Persist the command receipt, order, lines and audit in ONE transaction.
        await self.db.flush()

    async def synchronize(self, data, *, edit=False, action=None):
        action=action or ("edit" if edit else "draft")
        self.command_permission(action)
        device_id = data.order.device_id if action=="draft" else data.device_id
        employee = self.actor.employee
        if (self.actor.actor_type != "employee" or not employee or employee.id != data.employee_id
                or not employee.active or employee.deleted or not self.actor.pos_session
                or self.actor.pos_session.device_id != device_id):
            raise HTTPException(403, "Reconnect as the original employee on the original register; retain this offline order")
        captured = data.captured_at
        self.validate_capture(captured)
        # Every sync and normal order-create locks this same register. This
        # serializes retries before checking the unique command receipt.
        device = (await self.db.execute(select(Device).where(Device.id == device_id,
            Device.company_id == self.actor.company_id).with_for_update())).scalar_one_or_none()
        if not device or not device.active or device.deleted or device.removed_at or device.deactivated_at:
            raise HTTPException(403, "Original register is not active")
        await self.branch(device.branch_id)
        fingerprint = digest({"action": action, "data": data.model_dump(mode="json")})
        receipt = (await self.db.execute(select(OrderSyncReceipt).where(
            OrderSyncReceipt.company_id == self.actor.company_id,
            OrderSyncReceipt.request_id == data.request_id))).scalar_one_or_none()
        if receipt:
            if (receipt.employee_id != employee.id or receipt.device_id != device_id
                    or receipt.payload_hash != fingerprint):
                raise HTTPException(409, "Offline command identity or payload mismatch; review without deleting the command")
            return self.acknowledgement(receipt)
        try:
            if action=="kitchen":
                row=await self.order(data.order_id,version=data.version,edit=True)
                if row.device_id!=device_id:raise HTTPException(403,"Kitchen request belongs to another register")
                result=(await self.send_kitchen(row.id,data.version))["order"]
            elif action=="kds":
                ticket=(await self.db.execute(select(KitchenTicket).where(KitchenTicket.id==data.ticket_id,
                    KitchenTicket.company_id==self.actor.company_id).with_for_update())).scalar_one_or_none()
                if not ticket:raise HTTPException(404,"Kitchen ticket not found")
                order=await self.db.get(CommerceOrder,ticket.order_id)
                if order.branch_id!=device.branch_id:raise HTTPException(403,"Kitchen register belongs to another branch")
                if ticket.status!=data.expected_status:raise HTTPException(409,"Kitchen ticket changed; review current server status")
                await self.kitchen_state(ticket.id,data.status)
                result={"id":str(order.id),"ticket_id":str(ticket.id),"ticket_status":data.status}
            elif action=="edit":
                row = await self.order(data.order_id, edit=True)
                if row.device_id != device_id:
                    raise HTTPException(403, "Offline command belongs to another register")
                result = await self.edit_item(data.order_id, data.item_id, data.change)
            else:
                if data.order.kind != "restaurant" or data.order.waiter_id not in (None, employee.id):
                    raise HTTPException(403, "Offline drafts must belong to their original waiter")
                # Do not append lines onto a previously created order when an
                # outbox is copied or a request identity is accidentally reused.
                existing = (await self.db.execute(select(CommerceOrder.id).where(
                    CommerceOrder.company_id == self.actor.company_id,
                    CommerceOrder.request_id == data.order.request_id))).first()
                if existing:
                    raise HTTPException(409, "Order identity already exists without this sync receipt; review the original order")
                result = await self.create_order(data.order)
                for item in data.items:
                    result = await self.add_item(result["id"], item.model_copy(update={"version": result["version"]}))
            result = jsonable_encoder(result)
            self.db.add(OrderSyncReceipt(company_id=self.actor.company_id, employee_id=employee.id,
                device_id=device_id, request_id=data.request_id, payload_hash=fingerprint,
                captured_at=captured, result=result))
            self.audit("offline_order_synchronized", order_id=result["id"], request_id=data.request_id,
                employee_id=employee.id, captured_at=captured.isoformat(), command_type=action)
            await self.db.commit()
            return {"order": result, "already_synchronized": False,"request_id":str(data.request_id)}
        except Exception:
            await self.db.rollback()
            raise
