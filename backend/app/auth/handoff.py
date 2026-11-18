"""One-use handoff, receiver-bound at preview, explicit identity confirmation."""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import get_settings
from app.models import User, Branch, Company, BackofficeHandoff, BusinessSession, AuditEvent
from app.auth.security import create_session_token, hash_session_token
from app.auth.remembered import new_session, access_result
from app.auth.recovery import throttle
from app.auth.security import verify_password
UTC = timezone.utc


def invalid():
    raise HTTPException(401, 'Backoffice handoff is invalid or expired. Return to POS and try again.')


async def reauthenticate_owner(db, employee_actor, data):
    from app.auth.dependencies import AuthActor
    if (not employee_actor.employee or employee_actor.company_id != data.company_id
            or employee_actor.employee.branch_id != data.branch_id
            or employee_actor.pos_session and employee_actor.pos_session.branch_id != data.branch_id):
        raise HTTPException(403, 'Business or branch context mismatch')
    if not await throttle(db, 'handoff-owner-password', str(employee_actor.employee.id), 5, 300):
        await db.commit(); raise HTTPException(429, 'Wait before trying owner authentication again')
    user = (await db.execute(select(User).where(User.email == str(data.owner_email).strip().lower(),
                            User.company_id == data.company_id, User.active.is_(True), User.deleted.is_(False))
                            .execution_options(populate_existing=True))).scalar_one_or_none()
    try: valid = user is not None and user.role in {'owner', 'administrator'} and verify_password(data.owner_password, user.password_hash)
    except (ValueError, TypeError): valid = False
    if not valid:
        db.add(AuditEvent(company_id=employee_actor.company_id, actor_employee_id=employee_actor.employee.id,
                          action='backoffice_owner_auth_failed', details={}))
        await db.commit()  # Keep the attempt budget even when credentials fail.
        raise HTTPException(403, 'Owner authentication failed for this business')
    # issue() rechecks the captured version/role under its User lock, preserving
    # throttle -> User lock order and rejecting any concurrent password reset.
    # Fresh password proof creates only a one-use grant. Never return or store
    # a reusable owner JWT, and never retry with the POS's cached owner token.
    db.add(AuditEvent(company_id=user.company_id, actor_user_id=user.id, actor_employee_id=employee_actor.employee.id,
                      action='backoffice_owner_auth_confirmed', details={}))
    return AuthActor('user', user.company_id, user.role, user=user, authenticated_session_version=user.session_version)


async def locked_user(db, uid):
    return (await db.execute(select(User).where(User.id == uid).with_for_update()
                            .execution_options(populate_existing=True))).scalar_one_or_none()


async def valid_source(db, sid, user):
    if sid is None: return
    session = (await db.execute(select(BusinessSession).where(BusinessSession.id == sid).with_for_update()
                               .execution_options(populate_existing=True))).scalar_one_or_none()
    if (not session or session.user_id != user.id or session.company_id != user.company_id
            or session.session_version != user.session_version or session.revoked_at or session.expires_at <= datetime.now(UTC)):
        invalid()


async def issue(db, actor, company_id, branch_id):
    if actor.actor_type != 'user' or not actor.user or actor.role not in {'owner', 'administrator'}:
        raise HTTPException(403, 'Sign in as the business owner or administrator in POS to open Backoffice')
    if company_id != actor.company_id: raise HTTPException(403, 'Business context mismatch')
    if not await throttle(db, 'handoff-user', str(actor.user.id), 10, 60):
        await db.commit(); raise HTTPException(429, 'Wait before opening Backoffice again')
    user = await locked_user(db, actor.user.id)
    if (not user or not user.active or user.deleted or user.company_id != company_id or user.role != actor.role
            or user.session_version != actor.authenticated_session_version):
        # A fresh owner proof can lose a reset/revocation race while the
        # requesting cashier is still valid. Do not label that cashier's
        # credential invalid (POS treats primary-auth 401 as session loss).
        raise HTTPException(409, 'Owner authentication changed. Retry owner authentication.')
    await valid_source(db, actor.business_session_id, user)
    branch = await db.get(Branch, branch_id)
    if not branch or branch.company_id != company_id or branch.deleted or not branch.active:
        raise HTTPException(403, 'Branch context mismatch')
    code = create_session_token()
    db.add(BackofficeHandoff(token_hash=hash_session_token(code), user_id=user.id, company_id=company_id, branch_id=branch_id,
                            session_version=user.session_version, source_session_id=actor.business_session_id,
                            role=user.role, audience='backoffice', expires_at=datetime.now(UTC) + timedelta(seconds=60)))
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action='backoffice_handoff_issued', details={'branch_id': str(branch_id)}))
    await db.commit()
    return {'url': get_settings().backoffice_origin + '/#handoff=' + code}


async def validate(db, code):
    grant = await db.get(BackofficeHandoff, hash_session_token(code))
    if grant is None: invalid()
    user = await locked_user(db, grant.user_id)
    if not user or not user.active or user.deleted: invalid()
    await valid_source(db, grant.source_session_id, user)
    grant = (await db.execute(select(BackofficeHandoff).where(BackofficeHandoff.token_hash == grant.token_hash)
                             .with_for_update().execution_options(populate_existing=True))).scalar_one()
    if (grant.consumed_at or grant.expires_at <= datetime.now(UTC) or grant.audience != 'backoffice'
            or user.company_id != grant.company_id or user.session_version != grant.session_version
            or user.role != grant.role or user.role not in {'owner', 'administrator'}): invalid()
    branch = await db.get(Branch, grant.branch_id)
    if not branch or branch.company_id != user.company_id or not branch.active or branch.deleted: invalid()
    return user, grant


async def inspect(db, code, receiver):
    user, grant = await validate(db, code)
    hashed = hash_session_token(receiver)
    if grant.receiver_hash and grant.receiver_hash != hashed: invalid()
    grant.receiver_hash = hashed
    company = await db.get(Company, grant.company_id)
    branch = await db.get(Branch, grant.branch_id)
    result = {'email': user.email, 'company_id': str(grant.company_id), 'branch_id': str(grant.branch_id),
              'company_name': company.name, 'branch_name': branch.name, 'role': grant.role}
    await db.commit()
    return result


async def consume(db, data):
    user, grant = await validate(db, data.code)
    if (grant.receiver_hash != hash_session_token(data.receiver) or grant.company_id != data.company_id
            or grant.branch_id != data.branch_id or grant.role != data.role): invalid()
    grant.consumed_at = datetime.now(UTC)
    session, secret = await new_session(db, user, False)
    result = access_result(user, session)
    db.add(AuditEvent(company_id=user.company_id, actor_user_id=user.id, action='backoffice_handoff_consumed',
                      details={'branch_id': str(grant.branch_id), 'role': grant.role}))
    await db.commit()
    return result, session, secret
