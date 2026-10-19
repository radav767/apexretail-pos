import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import func, select

from app.auth.security import verify_password
from app.employees.permissions import has_permission
from app.models import AuditEvent, Employee, ManagerAuthorization


ALLOWED_ACTIONS = {
    "large_discount", "refund", "price_override", "stock_adjustment",
    "cash_movement", "shift_exception",
    "receipt_reprint", "print_retry",
}
APPROVAL_TTL_SECONDS = 120
ACTION_PERMISSIONS = {
    "large_discount": "sales_discount", "refund": "sales_refund",
    "price_override": "sales_price_override", "stock_adjustment": "inventory_adjust",
    "cash_movement": "cash_movements_manage", "shift_exception": "shifts_close",
    "receipt_reprint": "sales_receipt_reprint", "print_retry": "printers_manage",
}


def context_hash(context: dict | None) -> str | None:
    if not context:
        return None
    def canonicalize(value, key=""):
        if isinstance(value, dict):
            return {k: canonicalize(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [canonicalize(v) for v in value]
        if key in {"quantity", "amount", "discount_amount"}:
            try:
                number = Decimal(str(value))
                if number.is_finite():
                    return format(number.normalize(), "f")
            except InvalidOperation:
                pass
        return value
    canonical = json.dumps(canonicalize(context), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_manager_authorization(db, actor, data):
    if actor.actor_type != "employee" or actor.employee is None or actor.pos_session is None:
        raise HTTPException(403, "A signed-in POS employee must request manager approval")
    if actor.company_id != data.company_id:
        raise HTTPException(403, "Forbidden")
    if data.action not in ALLOWED_ACTIONS:
        raise HTTPException(400, "Unsupported manager approval action")

    # Serialize attempts for this requester across API workers, and count
    # protected audit events rather than keeping a per-process counter.
    await db.execute(select(Employee.id).where(Employee.id == actor.employee.id).with_for_update())
    failures = (await db.execute(select(func.count(AuditEvent.id)).where(
        AuditEvent.company_id == actor.company_id,
        AuditEvent.actor_employee_id == actor.employee.id,
        AuditEvent.action == "manager_authorization_rejected",
        AuditEvent.created_at > datetime.now(timezone.utc) - timedelta(minutes=5),
    ))).scalar_one()
    if failures >= 5:
        raise HTTPException(429, "Too many manager approval attempts. Try again in five minutes.")

    result = await db.execute(select(Employee).where(
        Employee.company_id == data.company_id,
        Employee.active == True,
        Employee.deleted == False,
    ))
    approver = None
    for candidate in result.scalars().all():
        try:
            valid_pin = candidate.pin.startswith("$2") and verify_password(data.manager_pin, candidate.pin)
        except ValueError:
            valid_pin = False
        if not candidate.pin.startswith("$2"):
            valid_pin = hmac.compare_digest(data.manager_pin, candidate.pin)
        # Resolve custom roles live so revocation/deactivation takes effect
        # immediately rather than trusting a previously stored role snapshot.
        from app.employees.service import EmployeeService
        permissions = await EmployeeService.effective_permissions(candidate, db) if valid_pin else {}
        if valid_pin and has_permission(permissions, "approve_restricted_actions") and has_permission(permissions, ACTION_PERMISSIONS[data.action]):
            approver = candidate
            break
    if approver is None:
        db.add(AuditEvent(
            company_id=actor.company_id, actor_employee_id=actor.employee.id,
            device_id=actor.pos_session.device_id,
            action="manager_authorization_rejected",
            details={"action": data.action},
        ))
        await db.commit()
        raise HTTPException(401, "Manager approval was not authorized")
    if approver.id == actor.employee.id:
        raise HTTPException(403, "A restricted action requires approval from another authorized employee")
    if approver.branch_id != actor.pos_session.branch_id and approver.role not in {"owner", "administrator"}:
        raise HTTPException(403, "The manager is not authorized for this branch")

    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    authorization = ManagerAuthorization(
        company_id=data.company_id,
        requester_employee_id=actor.employee.id,
        approver_employee_id=approver.id,
        device_id=actor.pos_session.device_id,
        action=data.action,
        context_hash=context_hash(data.context),
        token_hash=token_hash(raw_token),
        reason=data.reason.strip(),
        expires_at=now + timedelta(seconds=APPROVAL_TTL_SECONDS),
    )
    db.add(authorization)
    db.add(AuditEvent(
        company_id=data.company_id,
        actor_employee_id=approver.id,
        device_id=actor.pos_session.device_id,
        action="manager_authorization_issued",
        reason=data.reason.strip(),
        details={
            "requester_employee_id": str(actor.employee.id),
            "action": data.action,
            "context_hash": authorization.context_hash,
        },
    ))
    await db.commit()
    return {
        "authorization_token": raw_token,
        "action": data.action,
        "approver_employee_id": approver.id,
        "expires_at": authorization.expires_at,
    }


async def consume_manager_authorization(db, actor, raw_token: str | None, action: str, context: dict | None = None):
    if not raw_token or actor is None or actor.actor_type != "employee" or actor.employee is None or actor.pos_session is None:
        raise HTTPException(403, "Manager approval required")
    now = datetime.now(timezone.utc)
    result = await db.execute(select(ManagerAuthorization).where(
        ManagerAuthorization.token_hash == token_hash(raw_token),
        ManagerAuthorization.company_id == actor.company_id,
    ).with_for_update())
    authorization = result.scalar_one_or_none()
    expected_context = context_hash(context)
    valid = bool(
        authorization
        and authorization.requester_employee_id == actor.employee.id
        and authorization.action == action
        and authorization.used_at is None
        and authorization.expires_at > now
        and authorization.context_hash == expected_context
        and authorization.device_id == actor.pos_session.device_id
    )
    if not valid:
        raise HTTPException(403, "Manager approval is invalid, expired, used, or for another action")
    approver = (await db.execute(select(Employee).where(
        Employee.id == authorization.approver_employee_id,
        Employee.company_id == actor.company_id,
        Employee.active == True, Employee.deleted == False,
    ))).scalar_one_or_none()
    from app.employees.service import EmployeeService
    permissions = await EmployeeService.effective_permissions(approver, db) if approver else {}
    if (
        approver is None or approver.id == actor.employee.id
        or not has_permission(permissions, "approve_restricted_actions")
        or not has_permission(permissions, ACTION_PERMISSIONS.get(action, ""))
        or (approver.branch_id != actor.pos_session.branch_id and approver.role not in {"owner", "administrator"})
    ):
        raise HTTPException(403, "Manager authorization has been revoked")
    authorization.used_at = now
    db.add(AuditEvent(
        company_id=actor.company_id,
        actor_employee_id=authorization.approver_employee_id,
        device_id=authorization.device_id,
        action="manager_authorization_used",
        details={
            "requester_employee_id": str(actor.employee.id),
            "action": action,
            "context_hash": expected_context,
        },
    ))
    return authorization
