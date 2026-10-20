"""Lot-specific stock operations through the existing inventory service/ledger.

Supplier returns are NOT customer refunds. Customer refunds remain on the
original financial refund API; returned lots require inspection/assignment.
"""
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.inventory.repository import InventoryRepository
from app.inventory.service import InventoryService
from app.inventory.schema import GRNCreate, StockAdjustmentCreate
from app.models import ProductVariant, ProductBatch, BatchAllocation
from app.models.business_operations import BatchStockOperation
from app.printing.service import permit, digest
from .service import BusinessService


class LotInventoryRepository(InventoryRepository):
    def __init__(self, db, batch):
        super().__init__(db, commit_on_save=False)
        self.batch = batch

    async def apply_movement(self, product, balance, movement):
        delta = Decimal(movement.after_qty) - Decimal(movement.before_qty)
        if self.batch.quantity + delta < 0:
            raise HTTPException(409, "Insufficient stock in the selected batch")
        self.batch.quantity += delta
        self.db.add(movement)
        await self.db.flush()
        # This records attribution only. Stock was changed by InventoryService.
        # The existing allocation hook recognizes the attribution and does not
        # allocate a second time (including expired-lot disposal).
        self.db.add(BatchAllocation(batch_id=self.batch.id, movement_id=movement.id, quantity=delta))
        await self.db.flush()
        return await super().apply_movement(product, balance, movement)


class BatchStockService(BusinessService):
    async def execute(self, data):
        permit(self.actor, "batches_manage")
        permit(self.actor, "inventory_receive" if data.operation == "receive" else "inventory_adjust")
        await self.feature("pharmacy")
        await self.branch(data.branch_id)
        # Same product-first lock order as sales, GRNs and FEFO allocation.
        repo = InventoryRepository(self.db)
        product = await repo.get_product_for_update(self.actor.company_id, data.product_id)
        if not product.track_inventory or product.product_type not in {"standard", "variable_weight"}:
            raise HTTPException(400, "Batch stock requires a standard stock-tracked product")
        if (await self.db.execute(select(ProductVariant.id).where(ProductVariant.product_id == product.id,
                ProductVariant.active == True, ProductVariant.deleted == False))).first():
            raise HTTPException(409, "Variant lot stock is not supported; no stock changed")
        fingerprint = digest(data.model_dump(mode="json"))
        old = (await self.db.execute(select(BatchStockOperation).where(
            BatchStockOperation.company_id == self.actor.company_id, BatchStockOperation.request_id == data.request_id))).scalar_one_or_none()
        if old:
            if old.payload_hash != fingerprint: raise HTTPException(409, "Batch request identity reused with different values")
            return {"movement_id": old.movement_id, "batch_id": old.batch_id, "already_processed": True}
        try:
            batch = (await self.db.execute(select(ProductBatch).where(ProductBatch.company_id == self.actor.company_id,
                ProductBatch.branch_id == data.branch_id, ProductBatch.product_id == product.id,
                ProductBatch.code == data.code).with_for_update())).scalar_one_or_none()
            if batch and batch.expires_on != data.expires_on:
                raise HTTPException(409, "Existing lot expiry differs; review the lot, do not rewrite its expiry")
            if not batch:
                if data.operation != "receive": raise HTTPException(404, "Batch not found")
                batch = ProductBatch(company_id=self.actor.company_id, branch_id=data.branch_id,
                    product_id=product.id, code=data.code, expires_on=data.expires_on, quantity=0)
                self.db.add(batch); await self.db.flush()
            inventory = InventoryService(LotInventoryRepository(self.db, batch))
            common = dict(company_id=self.actor.company_id, branch_id=data.branch_id,
                product_id=product.id, quantity=data.quantity, reason=data.reason,
                reference=f"batch:{data.request_id}")
            if data.operation == "receive":
                movement = await inventory.receive_stock(GRNCreate(**common, received_unit=data.received_unit))
            else:
                if data.received_unit: raise HTTPException(400, "Returns/disposal use base units")
                movement = await inventory.adjust_stock(StockAdjustmentCreate(**common, adjustment_type="remove"), actor=self.actor)
            self.db.add(BatchStockOperation(company_id=self.actor.company_id, request_id=data.request_id,
                payload_hash=fingerprint, batch_id=batch.id, movement_id=movement.id, operation=data.operation))
            self.audit("batch_stock_" + data.operation, batch_id=batch.id, movement_id=movement.id,
                request_id=data.request_id, reason=data.reason, quantity=str(data.quantity))
            await self.db.commit()
            return {"movement_id": movement.id, "batch_id": batch.id, "already_processed": False}
        except Exception:
            await self.db.rollback()
            raise
