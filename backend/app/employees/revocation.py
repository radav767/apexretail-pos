"""Atomic employee epoch changes, without committing caller work."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import update
from app.models import Employee, PosSession


async def revoke(db, company_id, employee_id, reason):
    version = (await db.execute(update(Employee).where(Employee.id == employee_id,
        Employee.company_id == company_id).values(session_version=Employee.session_version+1)
        .returning(Employee.session_version))).scalar_one_or_none()
    if version is None: raise HTTPException(404, 'Employee not found')
    await db.execute(update(PosSession).where(PosSession.company_id == company_id,
        PosSession.employee_id == employee_id, PosSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc), revoke_reason=reason))
    return version
