from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.models import CashierShift, CompanySetting


async def resolve_shift_for_write(
    db, actor, company_id, branch_id, requested_shift_id=None, *,
    occurred_at=None, attach_active=False,
):
    if not hasattr(db, "execute"):
        if requested_shift_id is not None:
            raise HTTPException(409, "Shift validation requires a database transaction")
        return None
    settings = (await db.execute(select(CompanySetting).where(
        CompanySetting.company_id == company_id,
        CompanySetting.deleted.is_(False),
    ))).scalar_one_or_none()
    enforcement = bool(settings and settings.shift_enforcement_enabled)
    cutoff = settings.shift_required_from if settings else None
    must_have_shift = enforcement and (cutoff is None or (occurred_at or datetime.now(timezone.utc)) >= cutoff)
    is_offline_sync = occurred_at is not None
    if is_offline_sync and requested_shift_id is not None:
        raise HTTPException(409, "Offline sales cannot attach an unverified shift")
    if is_offline_sync and must_have_shift:
        raise HTTPException(409, "Offline sales require a verified shift snapshot")
    if requested_shift_id is None and not must_have_shift and (not attach_active or is_offline_sync):
        return None
    if actor is None or actor.actor_type != "employee" or actor.employee is None or actor.pos_session is None:
        if must_have_shift or requested_shift_id is not None:
            raise HTTPException(401, "A valid opaque POS session is required for shift-bound financial activity")
        return None
    session = actor.pos_session
    if session.company_id != company_id or session.branch_id != branch_id:
        raise HTTPException(403, "POS session company or branch mismatch")
    query = select(CashierShift).where(
        CashierShift.company_id == company_id,
        CashierShift.employee_id == actor.employee.id,
        CashierShift.device_id == session.device_id,
        CashierShift.shop_id == session.shop_id,
        CashierShift.branch_id == branch_id,
        CashierShift.status == "open",
    ).with_for_update()
    if requested_shift_id is not None:
        query = query.where(CashierShift.id == requested_shift_id)
    shift = (await db.execute(query)).scalar_one_or_none()
    if shift is None:
        if must_have_shift or requested_shift_id is not None:
            raise HTTPException(409, "An active shift for this cashier and register is required")
        return None
    return shift
