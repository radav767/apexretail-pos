"""Rotating HttpOnly credentials. No refresh secrets enter JS or audit records."""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, update
from app.core.config import get_settings
from app.models import User, BusinessSession, BusinessRefreshCredential, AuditEvent
from app.auth.security import create_access_token, create_session_token, hash_session_token

COOKIE = '__Host-apex_business_refresh'
UTC = timezone.utc


def check_origin(request):
    if request.headers.get('origin') != get_settings().backoffice_origin:
        raise HTTPException(403, 'Backoffice origin required')


def set_cookie(response, secret, session):
    seconds = max(0, int((session.expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(COOKIE, secret, httponly=True, secure=True, samesite='strict', path='/',
                        max_age=seconds if session.remembered else None)
    response.headers['Cache-Control'] = 'no-store'


def clear_cookie(response):
    response.delete_cookie(COOKIE, path='/', httponly=True, secure=True, samesite='strict')
    response.headers['Cache-Control'] = 'no-store'


def access_result(user, session):
    return {'ok': True, 'token': create_access_token(str(user.id), user.email,
            session_version=user.session_version, session_id=str(session.id)),
            'company_id': str(user.company_id), 'user': {'id': str(user.id), 'email': user.email, 'role': user.role}}


async def new_session(db, user, remembered=False):
    session = BusinessSession(user_id=user.id, company_id=user.company_id, session_version=user.session_version,
                              remembered=remembered, audience='backoffice',
                              expires_at=datetime.now(UTC) + (timedelta(days=30) if remembered else timedelta(hours=12)))
    db.add(session); await db.flush()
    secret = create_session_token()
    db.add(BusinessRefreshCredential(token_hash=hash_session_token(secret), session_id=session.id, expires_at=session.expires_at))
    return session, secret


async def retire_browser_session(db, secret):
    if not secret or len(secret) > 200: return
    credential = await db.get(BusinessRefreshCredential, hash_session_token(secret))
    if credential:
        await db.execute(update(BusinessSession).where(BusinessSession.id == credential.session_id)
                         .values(revoked_at=datetime.now(UTC)))


async def refresh(db, secret):
    if not secret or len(secret) > 200: raise HTTPException(401, 'Sign in required')
    hashed = hash_session_token(secret)
    credential = await db.get(BusinessRefreshCredential, hashed)
    session = await db.get(BusinessSession, credential.session_id) if credential else None
    if session is None: raise HTTPException(401, 'Sign in required')
    # Match reset/revocation lock order: User -> Session -> Credential.
    user = (await db.execute(select(User).where(User.id == session.user_id).with_for_update()
                            .execution_options(populate_existing=True))).scalar_one_or_none()
    session = (await db.execute(select(BusinessSession).where(BusinessSession.id == session.id).with_for_update()
                               .execution_options(populate_existing=True))).scalar_one()
    credential = (await db.execute(select(BusinessRefreshCredential).where(BusinessRefreshCredential.token_hash == hashed)
                                  .with_for_update().execution_options(populate_existing=True))).scalar_one()
    now = datetime.now(UTC)
    if credential.consumed_at is not None:
        session.revoked_at = now
        db.add(AuditEvent(company_id=session.company_id, actor_user_id=session.user_id,
                          action='business_refresh_replay', details={'session_id': str(session.id)}))
        await db.commit()
        raise HTTPException(401, 'Sign in required')
    if (not user or not user.active or user.deleted or user.role not in {'owner', 'administrator'}
            or user.company_id != session.company_id or user.session_version != session.session_version
            or session.audience != 'backoffice' or session.revoked_at or session.expires_at <= now
            or credential.expires_at <= now):
        raise HTTPException(401, 'Sign in required')
    credential.consumed_at = now
    next_secret = create_session_token()
    db.add(BusinessRefreshCredential(token_hash=hash_session_token(next_secret), session_id=session.id, expires_at=session.expires_at))
    result = access_result(user, session)
    await db.commit()
    return result, session, next_secret
