from datetime import date
from uuid import UUID
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import BatchReturnHold, BatchReturnInspection, BatchInspectionDisposal, ProductBatch, BatchAllocation, Product, InventoryMovement, ProductVariant
from app.inventory.repository import InventoryRepository
from app.inventory.service import InventoryService
from app.inventory.schema import StockAdjustmentCreate
from app.printing.service import permit, digest
from .service import BusinessService
from .batch_stock import LotInventoryRepository
from .batches import business_today


class InspectionInput(BaseModel):
    request_id: UUID
    hold_id: UUID
    code: str = Field(min_length=1, max_length=80)
    expires_on: date
    disposition: Literal["restock", "dispose"]
    reason: str = Field(min_length=3, max_length=500)
    confirmed: bool


class ReturnService(BusinessService):
    async def pending(self):
        permit(self.actor, "batches_view")
        query = select(BatchReturnHold, Product.name, InventoryMovement.reference, InventoryMovement.variant_id, ProductVariant.name).join(Product,
            Product.id == BatchReturnHold.product_id).join(InventoryMovement, InventoryMovement.id == BatchReturnHold.movement_id).outerjoin(
            ProductVariant, ProductVariant.id == InventoryMovement.variant_id).outerjoin(
            BatchReturnInspection, BatchReturnInspection.hold_id == BatchReturnHold.id).where(
            BatchReturnHold.company_id == self.actor.company_id, BatchReturnInspection.id.is_(None))
        if self.actor.employee: query = query.where(BatchReturnHold.branch_id == self.actor.employee.branch_id)
        return [{"id": row.id, "product": name, "quantity": str(row.quantity), "refund_reference": reference,
            "branch_id": row.branch_id, "variant_id": variant_id, "variant_name": variant_name}
            for row, name, reference, variant_id, variant_name in (await self.db.execute(query.order_by(BatchReturnHold.created_at).limit(1000))).all()]

    async def inspect(self, data):
        permit(self.actor, "batches_manage")
        if data.disposition == "dispose": permit(self.actor, "inventory_adjust")
        if not data.confirmed: raise HTTPException(400, "Confirm physical inspection before releasing or disposing of a return")
        hold = await self.db.get(BatchReturnHold, data.hold_id)
        if not hold or hold.company_id != self.actor.company_id: raise HTTPException(404, "Return hold not found")
        branch = await self.branch(hold.branch_id)
        stock = InventoryRepository(self.db)
        product = await stock.get_product_for_update(self.actor.company_id, hold.product_id)
        # The immutable refund movement is authoritative, including historical
        # holds. Never choose a variant from the current UI or product defaults.
        original_movement = await self.db.get(InventoryMovement, hold.movement_id)
        variant_id = original_movement.variant_id
        fingerprint = digest(data.model_dump(mode="json"))
        existing = (await self.db.execute(select(BatchReturnInspection).where(BatchReturnInspection.company_id == self.actor.company_id,
            BatchReturnInspection.request_id == data.request_id))).scalar_one_or_none()
        if existing:
            if existing.payload_hash != fingerprint: raise HTTPException(409, "Return request identity reused with different values")
            return {"id": existing.id, "already_inspected": True}
        if (await self.db.execute(select(BatchReturnInspection.id).where(BatchReturnInspection.hold_id == hold.id))).first():
            raise HTTPException(409, "This customer return has already been inspected")
        if data.disposition == "restock" and data.expires_on < await business_today(self.db, self.actor.company_id):
            raise HTTPException(409, {"code": "expired_return_requires_disposal", "message": "Expired returns cannot be released for sale; review disposal instead"})
        if variant_id:
            from app.sales.repository import SalesRepository
            balance = await SalesRepository(self.db).get_variant_balance(self.actor.company_id, branch, product.id, variant_id)
        else: balance = await stock.get_balance_for_update(self.actor.company_id, branch, product)
        assigned = (await self.db.execute(select(func.coalesce(func.sum(ProductBatch.quantity),0)).where(
            ProductBatch.company_id == hold.company_id, ProductBatch.branch_id == hold.branch_id, ProductBatch.product_id == hold.product_id, ProductBatch.variant_id == variant_id))).scalar_one()
        if balance.quantity - assigned < hold.quantity: raise HTTPException(409, "Returned stock needs reconciliation; nothing was released")
        try:
            batch = (await self.db.execute(select(ProductBatch).where(ProductBatch.company_id == hold.company_id,
                ProductBatch.branch_id == hold.branch_id, ProductBatch.product_id == hold.product_id, ProductBatch.variant_id == variant_id, ProductBatch.code == data.code).with_for_update())).scalar_one_or_none()
            if batch and batch.expires_on != data.expires_on: raise HTTPException(409, "Lot expiry differs; review the physical lot")
            if not batch:
                batch = ProductBatch(company_id=hold.company_id, branch_id=hold.branch_id, product_id=hold.product_id,
                    variant_id=variant_id, code=data.code, expires_on=data.expires_on, quantity=0)
                self.db.add(batch); await self.db.flush()
            batch.quantity += hold.quantity
            self.db.add(BatchAllocation(batch_id=batch.id, movement_id=hold.movement_id, quantity=hold.quantity))
            inspection = BatchReturnInspection(company_id=hold.company_id, hold_id=hold.id, batch_id=batch.id,
                request_id=data.request_id, payload_hash=fingerprint, disposition=data.disposition, reason=data.reason)
            self.db.add(inspection); await self.db.flush()
            if data.disposition == "dispose":
                movement = await InventoryService(LotInventoryRepository(self.db, batch)).adjust_stock(StockAdjustmentCreate(
                    company_id=hold.company_id, branch_id=hold.branch_id, product_id=hold.product_id,
                    adjustment_type="remove", quantity=hold.quantity, reason=data.reason,
                    reference=f"return:{data.request_id}"), actor=self.actor)
                disposal_id = movement.id
                self.db.add(BatchInspectionDisposal(inspection_id=inspection.id, movement_id=disposal_id))
            else: disposal_id = None
            self.audit("customer_return_inspected", hold_id=hold.id, batch_id=batch.id,
                disposition=data.disposition, disposal_movement_id=disposal_id, reason=data.reason, quantity=str(hold.quantity))
            await self.db.commit()
            return {"id": inspection.id, "already_inspected": False}
        except Exception:
            await self.db.rollback(); raise
