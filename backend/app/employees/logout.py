"""Revocation-only POS logout; cached owner proof never grants domain authority."""
from datetime import datetime, timezone
from fastapi import HTTPException
from pydantic import BaseModel, Field
from jwt import PyJWTError
from sqlalchemy import update
from app.auth.dependencies import resolve_auth_actor
from app.models import AuditEvent, Employee, PosSession, User


class LogoutContext(BaseModel):
    cached_user_token: str | None = Field(default=None, max_length=4096)


async def logout_context(db, actor, data):
    owner = None
    if data and data.cached_user_token:
        # Resolve the same JWT/session checks as normal auth. This endpoint
        # returns no credentials and cannot use the owner for a domain action.
        # User resolution is read-only; never accept an employee/opaque token.
        from app.auth.security import decode_access_token
        try:
            payload = decode_access_token(data.cached_user_token)
        except PyJWTError:
            payload = None
        if payload and payload.get('token_type', 'user') == 'user':
            try:
                candidate = await resolve_auth_actor(data.cached_user_token, db)
            except HTTPException as error:
                if error.status_code not in (401, 403): raise
                candidate = None
            if candidate:
                if candidate.actor_type != 'user' or candidate.company_id != actor.company_id:
                    raise HTTPException(403, 'Logout context belongs to another business')
                owner = candidate.user
        # Already invalid owner proofs cannot be resurrected and require no
        # additional revocation. They do not stop logout of the current actor.
    if actor.actor_type == 'employee':
        version = (await db.execute(update(Employee).where(Employee.id == actor.employee.id,
            Employee.company_id == actor.company_id).values(session_version=Employee.session_version+1)
            .returning(Employee.session_version))).scalar_one_or_none()
        if version is None: raise HTTPException(401, 'Employee session is no longer valid')
        await db.execute(update(PosSession).where(PosSession.employee_id == actor.employee.id,
            PosSession.company_id == actor.company_id, PosSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc), revoke_reason='logout'))
        db.add(AuditEvent(company_id=actor.company_id, actor_employee_id=actor.employee.id,
            device_id=actor.pos_session.device_id if actor.pos_session else None,
            action='employee_logout', details={'scope':'all_employee_sessions'}))
    elif actor.actor_type == 'user':
        owner = actor.user
    else:
        raise HTTPException(403, 'Business authentication required')
    if owner:
        await db.execute(update(User).where(User.id == owner.id, User.company_id == actor.company_id)
                         .values(session_version=User.session_version+1))
        db.add(AuditEvent(company_id=actor.company_id, actor_user_id=owner.id,
            action='business_user_sessions_revoked', details={'scope':'all_user_sessions', 'source':'pos_logout'}))
    await db.commit()
    return {'ok':True}
