from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from jose import JWTError
from sqlalchemy import select

from app.auth.security import decode_offline_shift_token
from app.models import CashierShift, CompanySetting


async def resolve_shift_for_write(
    db, actor, company_id, branch_id, requested_shift_id=None, *,
    occurred_at=None, attach_active=False, offline_shift_token=None,
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
    token_payload = None
    if offline_shift_token:
        try:
            # Expiry limits creation/use as a live credential, but it must not
            # strand a durable queued financial transaction. The signature and
            # every cashier/register/shift claim are still verified below; a
            # closed original shift is then quarantined for audited resolution.
            token_payload = decode_offline_shift_token(
                offline_shift_token, verify_expiration=False
            )
            token_shift_id = UUID(str(token_payload.get("shift_id")))
        except (JWTError, ValueError, TypeError) as exc:
            raise HTTPException(409, "Offline shift identity is invalid or expired") from exc
        if requested_shift_id is not None and requested_shift_id != token_shift_id:
            raise HTTPException(409, "Offline shift identity does not match the requested shift")
        requested_shift_id = token_shift_id
    elif is_offline_sync and requested_shift_id is not None:
        raise HTTPException(409, "Offline sales cannot attach an unverified shift")
    if requested_shift_id is None and not must_have_shift and (not attach_active or is_offline_sync):
        return None
    if actor is None or actor.actor_type != "employee" or actor.employee is None or actor.pos_session is None:
        if must_have_shift or requested_shift_id is not None:
            raise HTTPException(401, "A valid opaque POS session is required for shift-bound financial activity")
        return None
    session = actor.pos_session
    if session.company_id != company_id or session.branch_id != branch_id:
        raise HTTPException(403, "POS session company or branch mismatch")
    if session.employee_id != actor.employee.id:
        raise HTTPException(403, "POS session cashier mismatch")
    if is_offline_sync and must_have_shift and token_payload is None:
        raise HTTPException(409, "Offline sales require a verified shift snapshot")
    query = select(CashierShift).where(
        CashierShift.company_id == company_id,
        CashierShift.employee_id == actor.employee.id,
        CashierShift.device_id == session.device_id,
        CashierShift.shop_id == session.shop_id,
        CashierShift.branch_id == branch_id,
    ).with_for_update()
    if token_payload is None:
        query = query.where(CashierShift.status == "open")
    if requested_shift_id is not None:
        query = query.where(CashierShift.id == requested_shift_id)
    shift = (await db.execute(query)).scalar_one_or_none()
    if shift is None:
        if must_have_shift or requested_shift_id is not None:
            raise HTTPException(409, "An active shift for this cashier and register is required")
        return None
    if token_payload is not None:
        identities = {
            "company_id": company_id,
            "branch_id": branch_id,
            "device_id": session.device_id,
            "employee_id": actor.employee.id,
        }
        if any(str(value) != str(token_payload.get(name)) for name, value in identities.items()):
            raise HTTPException(409, "Offline shift identity does not belong to this cashier and register")
        if occurred_at is None:
            raise HTTPException(409, "Offline shift sales require their original transaction timestamp")
        if shift.status != "open":
            raise HTTPException(409, detail={
                "code": "offline_shift_closed",
                "message": "The original cashier shift is closed; this queued sale requires audited manager resolution",
            })
        if occurred_at < shift.opened_at:
            raise HTTPException(409, "Offline sale timestamp falls outside its original shift")
    return shift
