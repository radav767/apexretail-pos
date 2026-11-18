"""Lot-specific stock operations through the existing inventory service/ledger.

Supplier returns are NOT customer refunds. Customer refunds remain on the
original financial refund API; returned lots require inspection/assignment.
"""
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.inventory.repository import InventoryRepository
from app.inventory.service import InventoryService
from app.inventory.schema import GRNCreate, StockAdjustmentCreate, StockTakeCreate
from app.models import ProductVariant, ProductBatch, BatchAllocation
from app.models.business_operations import BatchStockOperation
from app.printing.service import permit, digest
from .service import BusinessService
from app.inventory.command_policy import context, lock_request, verify_row


async def resolve_batch_variant(db, company_id, product_id, variant_id, *, include_inactive=False):
    """Resolve the explicit identity; never infer it from existing parent lots."""
    query = select(ProductVariant).where(ProductVariant.company_id == company_id,
        ProductVariant.product_id == product_id, ProductVariant.deleted == False)
    if not include_inactive:query=query.where(ProductVariant.active==True)
    if variant_id:
        variant = (await db.execute(query.where(ProductVariant.id == variant_id).with_for_update())).scalar_one_or_none()
        if variant is None: raise HTTPException(404, "Variant not found or inactive")
        return variant
    if (await db.execute(query.limit(1))).first():
        raise HTTPException(409, "Select the product variant; existing parent lots are not reassigned")
    return None


class LotInventoryRepository(InventoryRepository):
    def __init__(self, db, batch):
        super().__init__(db, commit_on_save=False)
        self.batch = batch

    async def get_balance_for_update(self, company_id, branch, product):
        if self.batch.variant_id:
            from app.sales.repository import SalesRepository
            return await SalesRepository(self.db).get_variant_balance(company_id, branch, product.id, self.batch.variant_id)
        return await super().get_balance_for_update(company_id, branch, product)

    async def sync_product_total(self, product):
        # Variant balances are independent, exactly as in the existing sale/refund
        # path. Do not overwrite the legacy parent balance with a variant total.
        if not self.batch.variant_id: return await super().sync_product_total(product)

    async def apply_movement(self, product, balance, movement):
        movement.variant_id = self.batch.variant_id
        if self.batch.variant_id:
            variant = await self.db.get(ProductVariant, self.batch.variant_id)
            movement.product_name = f"{product.name} — {variant.name}"
            if variant.cost_price is not None: movement.unit_cost = variant.cost_price
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

    async def apply_movements(self, products, balances, movements):
        # A selected-lot count uses InventoryService's stock-take arithmetic and
        # this same attribution hook, not a parallel balance/movement writer.
        if len(movements) != 1:
            raise HTTPException(400, "Count one selected batch at a time")
        return [await self.apply_movement(products[0], balances[0], movements[0])]


class BatchStockService(BusinessService):
    async def execute(self, data):
        permit(self.actor, "batches_manage")
        permit(self.actor, "inventory_receive" if data.operation == "receive" else
            "inventory_count" if data.operation == "count" else "inventory_adjust")
        await self.branch(data.branch_id)
        proof = await context(self.db, self.actor, self.actor.company_id, data.branch_id)
        await lock_request(self.db, 'batch', self.actor.company_id, data.request_id)
        payload = data.model_dump(mode="json")
        if data.variant_id is None: payload.pop("variant_id")  # Preserve pre-p7j retry hashes.
        if data.expected_qty is None: payload.pop("expected_qty")  # Preserve existing operation receipts.
        fingerprint = digest(payload)
        old = (await self.db.execute(select(BatchStockOperation).where(
            BatchStockOperation.company_id == self.actor.company_id, BatchStockOperation.request_id == data.request_id))).scalar_one_or_none()
        if old:
            verify_row(old, proof)
            if old.payload_hash != fingerprint: raise HTTPException(409, "Batch request identity reused with different values")
            return {"movement_id": old.movement_id, "batch_id": old.batch_id, "already_processed": True}
        await self.require_write('pharmacy', *(['variants'] if data.variant_id else []))
        await self.feature('pharmacy')
        # Same product-first lock order as sales, GRNs and FEFO allocation.
        repo = InventoryRepository(self.db)
        product = await repo.get_product_for_update(self.actor.company_id, data.product_id)
        if not product.track_inventory or product.product_type not in {"standard", "variable_weight"}:
            raise HTTPException(400, "Batch stock requires a standard stock-tracked product")
        await resolve_batch_variant(self.db, self.actor.company_id, product.id, data.variant_id,include_inactive=data.operation=="count")
        try:
            batch = (await self.db.execute(select(ProductBatch).where(ProductBatch.company_id == self.actor.company_id,
                ProductBatch.branch_id == data.branch_id, ProductBatch.product_id == product.id,
                ProductBatch.variant_id == data.variant_id, ProductBatch.code == data.code).with_for_update())).scalar_one_or_none()
            if batch and batch.expires_on != data.expires_on:
                raise HTTPException(409, "Existing lot expiry differs; review the lot, do not rewrite its expiry")
            if data.expected_qty is not None and (batch is None or batch.quantity!=data.expected_qty):
                raise HTTPException(409,"Stock changed since counting started. Original count retained; review current stock")
            if not batch:
                if data.operation != "receive": raise HTTPException(404, "Batch not found")
                batch = ProductBatch(company_id=self.actor.company_id, branch_id=data.branch_id,
                    product_id=product.id, variant_id=data.variant_id, code=data.code, expires_on=data.expires_on, quantity=0)
                self.db.add(batch); await self.db.flush()
            inventory = InventoryService(LotInventoryRepository(self.db, batch))
            common = dict(company_id=self.actor.company_id, branch_id=data.branch_id,
                product_id=product.id, quantity=data.quantity, reason=data.reason,
                reference=f"batch:{data.request_id}")
            if data.operation == "receive":
                movement = await inventory.receive_stock(GRNCreate(**common, received_unit=data.received_unit), actor=self.actor)
            elif data.operation == "count":
                if data.received_unit:
                    raise HTTPException(400, "Batch counts use base units")
                branch = await repo.resolve_branch(self.actor.company_id, data.branch_id)
                balance = await inventory.repo.get_balance_for_update(self.actor.company_id, branch, product)
                physical_total = Decimal(balance.quantity) + data.quantity - Decimal(batch.quantity)
                if physical_total < 0:
                    raise HTTPException(409, "Batch count conflicts with physical inventory; reconcile before counting")
                movement = (await inventory.stock_take(StockTakeCreate(company_id=self.actor.company_id,
                    branch_id=data.branch_id, items=[{"product_id":product.id,"physical_qty":physical_total}],
                    reference=common["reference"], notes=data.reason), actor=self.actor))[0]
            else:
                if data.received_unit: raise HTTPException(400, "Returns/disposal use base units")
                movement = await inventory.adjust_stock(StockAdjustmentCreate(**common, adjustment_type="remove"), actor=self.actor)
            self.db.add(BatchStockOperation(**proof, company_id=self.actor.company_id, request_id=data.request_id,
                payload_hash=fingerprint, batch_id=batch.id, movement_id=movement.id, operation=data.operation))
            self.audit("batch_stock_" + data.operation, batch_id=batch.id, movement_id=movement.id,
                request_id=data.request_id, reason=data.reason, quantity=str(data.quantity))
            await self.db.commit()
            return {"movement_id": movement.id, "batch_id": batch.id, "already_processed": False}
        except Exception:
            await self.db.rollback()
            raise
