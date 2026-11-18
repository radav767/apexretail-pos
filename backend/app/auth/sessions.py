"""Server-side revocation for business User access tokens.

Employee POS sessions retain their existing separate lifecycle. No offline
queue, shift identity, password, platform session or business record is cleared.
"""
from fastapi import HTTPException
from sqlalchemy import update

from app.models import AuditEvent, User


async def revoke_user_sessions(db, actor):
    if actor.actor_type != 'user' or actor.user is None:
        raise HTTPException(403, 'Business user authentication required')
    # Atomic increment serializes concurrent revocations without stale ORM
    # read/modify/write. Audit and revocation commit together.
    version = (await db.execute(update(User).where(
        User.id == actor.user.id, User.company_id == actor.company_id,
        User.active.is_(True), User.deleted.is_(False),
    ).values(session_version=User.session_version + 1).returning(User.session_version))).scalar_one_or_none()
    if version is None:
        raise HTTPException(401, 'User session is no longer valid')
    db.add(AuditEvent(company_id=actor.company_id, actor_user_id=actor.user.id,
                      action='business_user_sessions_revoked', details={'scope': 'all_user_sessions'}))
    await db.commit()
