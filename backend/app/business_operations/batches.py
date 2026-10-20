"""Allocate EXISTING stock movements to FEFO lots; never deduct stock here."""
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import ProductBatch, BatchAllocation, CompanySetting, Company, BatchReturnHold, BatchReturnInspection, InventoryMovement


async def pending_return_quantity(db, company_id, branch_id, product_id, variant_id=None):
    return (await db.execute(select(func.coalesce(func.sum(BatchReturnHold.quantity),0)).join(
        InventoryMovement, InventoryMovement.id == BatchReturnHold.movement_id).outerjoin(
        BatchReturnInspection, BatchReturnInspection.hold_id == BatchReturnHold.id).where(
        BatchReturnHold.company_id == company_id, BatchReturnHold.branch_id == branch_id,
        BatchReturnHold.product_id == product_id, InventoryMovement.variant_id == variant_id,
        BatchReturnInspection.id.is_(None)))).scalar_one()


async def business_today(db, company_id):
    settings = (await db.execute(select(CompanySetting).where(CompanySetting.company_id == company_id))).scalar_one_or_none()
    return datetime.now(timezone.utc).astimezone(ZoneInfo(settings.reporting_timezone if settings else "UTC")).date()


async def allocate_batch_movements(db, movements):
    if not movements: return
    await db.flush()
    for movement in sorted(movements, key=lambda m: (str(m.company_id), str(m.branch_id), str(m.product_id))):
        delta = Decimal(movement.after_qty) - Decimal(movement.before_qty)
        if delta >= 0:
            if delta > 0 and movement.movement_type in {"refund", "composite_refund", "variant_refund"}:
                from .profiles import infer_profile
                company = await db.get(Company, movement.company_id)
                tracked = (await db.execute(select(ProductBatch.id).where(ProductBatch.company_id == movement.company_id,
                    ProductBatch.branch_id == movement.branch_id, ProductBatch.product_id == movement.product_id).limit(1))).first()
                if (company and infer_profile(company.business_type) == "pharmacy") or tracked:
                    if not (await db.execute(select(BatchReturnHold.id).where(BatchReturnHold.movement_id == movement.id))).first():
                        db.add(BatchReturnHold(company_id=movement.company_id, branch_id=movement.branch_id,
                            product_id=movement.product_id, movement_id=movement.id, quantity=delta))
                        await db.flush()
            continue  # GRNs remain on their existing receiving path.
        held = await pending_return_quantity(db, movement.company_id, movement.branch_id, movement.product_id, movement.variant_id)
        if Decimal(movement.after_qty) < held:
            raise HTTPException(409, "Returned stock is awaiting pharmacy/batch inspection; it cannot be sold or adjusted away")
        batches = (await db.execute(select(ProductBatch).where(ProductBatch.company_id == movement.company_id,
            ProductBatch.branch_id == movement.branch_id, ProductBatch.product_id == movement.product_id,
            ProductBatch.variant_id == movement.variant_id).order_by(ProductBatch.expires_on, ProductBatch.id).with_for_update())).scalars().all()
        if not batches:
            if movement.variant_id and (await db.execute(select(ProductBatch.id).where(
                    ProductBatch.company_id == movement.company_id, ProductBatch.branch_id == movement.branch_id,
                    ProductBatch.product_id == movement.product_id).limit(1))).first():
                raise HTTPException(409, "Assign inspected stock to the original variant lot before selling; parent lots cannot be reassigned")
            continue  # Products without lot tracking retain their existing stock behavior.
        if (await db.execute(select(BatchAllocation.id).where(BatchAllocation.movement_id == movement.id))).first(): continue
        today = await business_today(db, movement.company_id)
        available = [batch for batch in batches if batch.expires_on >= today and batch.quantity > 0]
        remaining = -delta
        if sum((b.quantity for b in available), Decimal("0")) < remaining:
            raise HTTPException(409, "Insufficient unexpired batch stock. Review batch assignments; queued sales must not be deleted")
        for batch in available:
            quantity = min(remaining, batch.quantity)
            batch.quantity -= quantity
            db.add(BatchAllocation(batch_id=batch.id, movement_id=movement.id, quantity=-quantity))
            remaining -= quantity
            if remaining == 0: break
    await transfer_batch_allocations(db, movements)


async def transfer_batch_allocations(db, movements):
    """Carry FEFO lot attribution with the existing paired transfer movements.

    Branch balances are changed only by TransferService. This hook moves lot
    attribution in the same transaction, never creates another stock movement,
    and never infers lots for historical or previously unassigned stock.
    """
    await db.flush()
    for outgoing in movements:
        if outgoing.movement_type != "transfer_out":
            continue
        incoming = [m for m in movements if m.movement_type == "transfer_in"
            and m.company_id == outgoing.company_id and m.product_id == outgoing.product_id
            and m.variant_id == outgoing.variant_id and m.reference == outgoing.reference
            and m.branch_id != outgoing.branch_id]
        if len(incoming) != 1:
            raise HTTPException(409, "Batch transfer requires one matching destination movement")
        incoming = incoming[0]
        quantity = Decimal(outgoing.before_qty) - Decimal(outgoing.after_qty)
        if quantity <= 0 or Decimal(incoming.after_qty) - Decimal(incoming.before_qty) != quantity:
            raise HTTPException(409, "Batch transfer quantities do not balance")
        allocations = (await db.execute(select(BatchAllocation, ProductBatch).join(
            ProductBatch, ProductBatch.id == BatchAllocation.batch_id).where(
            BatchAllocation.movement_id == outgoing.id))).all()
        if not allocations:
            tracked_destination = (await db.execute(select(ProductBatch.id).where(
                ProductBatch.company_id == incoming.company_id, ProductBatch.branch_id == incoming.branch_id,
                ProductBatch.product_id == incoming.product_id, ProductBatch.variant_id == incoming.variant_id).limit(1))).first()
            if tracked_destination:
                raise HTTPException(409, "Source stock has no lot attribution; assign inspected source batches before transfer")
            continue
        if sum((-a.quantity for a, _ in allocations), Decimal("0")) != quantity:
            raise HTTPException(409, "Source batch allocations do not balance with the transfer")
        existing = (await db.execute(select(BatchAllocation).where(
            BatchAllocation.movement_id == incoming.id))).scalars().all()
        if existing:
            if sum((a.quantity for a in existing), Decimal("0")) != quantity:
                raise HTTPException(409, "Destination batch allocations require reconciliation")
            continue
        for allocation, source in allocations:
            batch = (await db.execute(select(ProductBatch).where(
                ProductBatch.company_id == incoming.company_id, ProductBatch.branch_id == incoming.branch_id,
                ProductBatch.product_id == incoming.product_id, ProductBatch.variant_id == incoming.variant_id,
                ProductBatch.code == source.code).with_for_update())).scalar_one_or_none()
            if batch is not None and batch.expires_on != source.expires_on:
                raise HTTPException(409, "Destination batch code has a different expiry; transfer was not applied")
            if batch is None:
                batch = ProductBatch(company_id=incoming.company_id, branch_id=incoming.branch_id,
                    product_id=incoming.product_id, variant_id=incoming.variant_id, code=source.code,
                    expires_on=source.expires_on, quantity=Decimal("0"))
                db.add(batch)
                await db.flush()
            batch.quantity -= allocation.quantity
            db.add(BatchAllocation(batch_id=batch.id, movement_id=incoming.id, quantity=-allocation.quantity))
        await db.flush()
