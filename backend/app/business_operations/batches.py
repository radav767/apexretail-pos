"""Allocate EXISTING stock movements to FEFO lots; never deduct stock here."""
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from app.models import ProductBatch, BatchAllocation, CompanySetting


async def business_today(db, company_id):
    settings = (await db.execute(select(CompanySetting).where(CompanySetting.company_id == company_id))).scalar_one_or_none()
    return datetime.now(timezone.utc).astimezone(ZoneInfo(settings.reporting_timezone if settings else "UTC")).date()


async def allocate_batch_movements(db, movements):
    if not movements: return
    await db.flush()
    for movement in sorted(movements, key=lambda m: (str(m.company_id), str(m.branch_id), str(m.product_id))):
        delta = Decimal(movement.after_qty) - Decimal(movement.before_qty)
        if delta >= 0: continue  # Receipts/returns remain unallocated until inspected.
        batches = (await db.execute(select(ProductBatch).where(ProductBatch.company_id == movement.company_id,
            ProductBatch.branch_id == movement.branch_id, ProductBatch.product_id == movement.product_id).order_by(ProductBatch.expires_on, ProductBatch.id).with_for_update())).scalars().all()
        if not batches: continue  # Existing businesses retain their stock behavior.
        if (await db.execute(select(BatchAllocation.id).where(BatchAllocation.movement_id == movement.id))).first(): continue
        if movement.variant_id: raise HTTPException(409, "Variant batch allocation requires review")
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
