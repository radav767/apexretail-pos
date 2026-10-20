"""Atomic, cashier-bound synchronization of UNPAID restaurant drafts.

No payments, stock reservations, timestamp substitution or automatic KOTs.
Conflicts leave the client command intact for explicit review. Permissions are
rechecked using the current authenticated session, never cached client grants.
"""
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from app.models import Device
from app.models.business_operations import OrderSyncReceipt
from app.printing.service import digest, permit
from .service import BusinessService


class OfflineOrderService(BusinessService):
    async def recover(self, data, *, edit=False):
        """Read-only confirmation probe; never recreates an unknown command."""
        permit(self.actor, "orders_manage")
        device_id = data.device_id if edit else data.order.device_id
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
        fingerprint = digest({"action": "edit" if edit else "draft", "data": data.model_dump(mode="json")})
        if receipt.employee_id != employee.id or receipt.device_id != device_id or receipt.payload_hash != fingerprint:
            raise HTTPException(409, "Original command differs; retain it for review")
        return {"order": receipt.result, "already_synchronized": True}

    async def commit_operation(self):
        # Persist the command receipt, order, lines and audit in ONE transaction.
        await self.db.flush()

    async def synchronize(self, data, *, edit=False):
        permit(self.actor, "orders_manage")
        device_id = data.device_id if edit else data.order.device_id
        employee = self.actor.employee
        if (self.actor.actor_type != "employee" or not employee or employee.id != data.employee_id
                or not employee.active or employee.deleted or not self.actor.pos_session
                or self.actor.pos_session.device_id != device_id):
            raise HTTPException(403, "Reconnect as the original employee on the original register; retain this offline order")
        captured = data.captured_at
        if captured.tzinfo is None or captured > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise HTTPException(422, "An original timezone-aware capture timestamp is required")
        # Every sync and normal order-create locks this same register. This
        # serializes retries before checking the unique command receipt.
        device = (await self.db.execute(select(Device).where(Device.id == device_id,
            Device.company_id == self.actor.company_id).with_for_update())).scalar_one_or_none()
        if not device or not device.active or device.deleted or device.removed_at or device.deactivated_at:
            raise HTTPException(403, "Original register is not active")
        await self.branch(device.branch_id)
        fingerprint = digest({"action": "edit" if edit else "draft", "data": data.model_dump(mode="json")})
        receipt = (await self.db.execute(select(OrderSyncReceipt).where(
            OrderSyncReceipt.company_id == self.actor.company_id,
            OrderSyncReceipt.request_id == data.request_id))).scalar_one_or_none()
        if receipt:
            if (receipt.employee_id != employee.id or receipt.device_id != device_id
                    or receipt.payload_hash != fingerprint):
                raise HTTPException(409, "Offline command identity or payload mismatch; review without deleting the command")
            return {"order": receipt.result, "already_synchronized": True}
        try:
            if edit:
                row = await self.order(data.order_id, edit=True)
                if row.device_id != device_id:
                    raise HTTPException(403, "Offline command belongs to another register")
                result = await self.edit_item(data.order_id, data.item_id, data.change)
            else:
                if data.order.kind != "restaurant" or data.order.waiter_id not in (None, employee.id):
                    raise HTTPException(403, "Offline drafts must belong to their original waiter")
                # Do not append lines onto a previously created order when an
                # outbox is copied or a request identity is accidentally reused.
                from app.models import CommerceOrder
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
                employee_id=employee.id, captured_at=captured.isoformat(), command_type="edit" if edit else "draft")
            await self.db.commit()
            return {"order": result, "already_synchronized": False}
        except Exception:
            await self.db.rollback()
            raise
