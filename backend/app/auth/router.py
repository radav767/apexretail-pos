from fastapi import APIRouter, Depends, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.schema import RegisterRequest, LoginRequest, ForgotPasswordRequest, ResetPasswordRequest, HandoffCreate, HandoffInspect, HandoffConsume
from app.auth.repository import AuthRepository
from app.auth.service import AuthService
from app.auth.registration_currencies import serialize_registration_currencies
from app.auth.dependencies import AuthActor, get_auth_actor
from app.auth.sessions import revoke_user_sessions
from app.auth.remembered import check_origin, set_cookie, clear_cookie, new_session, access_result, refresh, COOKIE, retire_browser_session
from app.models import User, BusinessSession, AuditEvent

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get('/capabilities')
async def auth_capabilities(response: Response):
    # Public deployment availability only: never account or delivery evidence.
    from app.core.config import get_settings
    settings = get_settings()
    sink = settings.app_env == 'test' and settings.business_email_mode == 'sink'
    response.headers['Cache-Control'] = 'no-store'
    return {'password_recovery': 'test_sink' if sink else 'unavailable'}


@router.get("/registration-currencies")
async def registration_currencies():
    return {"items": serialize_registration_currencies()}


@router.post("/register")
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    repo = AuthRepository(db)
    service = AuthService(repo)
    return await service.register(data)


@router.post("/login")
async def login(data: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    if data.client == 'backoffice': check_origin(request)
    repo = AuthRepository(db)
    service = AuthService(repo)
    result = await service.login(data)
    response.headers['Cache-Control'] = 'no-store'
    if data.client == 'backoffice':
        user = await db.get(User, UUID(result['user']['id']))
        await retire_browser_session(db, request.cookies.get(COOKIE))
        session, secret = await new_session(db, user, data.remember_me)
        result = access_result(user, session)
        db.add(AuditEvent(company_id=user.company_id, actor_user_id=user.id,
                         action='business_session_created', details={'remembered': session.remembered}))
        await db.commit()
        set_cookie(response, secret, session)
    return result


@router.post('/logout-browser')
async def logout_browser(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    check_origin(request)
    await retire_browser_session(db, request.cookies.get(COOKIE))
    await db.commit()
    clear_cookie(response)
    return {'ok': True}


@router.post('/refresh')
async def refresh_session(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    check_origin(request)
    try:
        result, session, secret = await refresh(db, request.cookies.get(COOKIE))
    except HTTPException as error:
        response = JSONResponse({'detail': error.detail}, status_code=error.status_code)
        clear_cookie(response)
        return response
    set_cookie(response, secret, session)
    return result


@router.post('/logout')
async def logout(request: Request, response: Response, actor: AuthActor = Depends(get_auth_actor), db: AsyncSession = Depends(get_db)):
    check_origin(request)
    if actor.actor_type != 'user': raise HTTPException(403, 'Business user authentication required')
    if actor.business_session_id:
        await db.execute(update(BusinessSession).where(BusinessSession.id == actor.business_session_id,
                         BusinessSession.user_id == actor.user.id, BusinessSession.company_id == actor.company_id)
                         .values(revoked_at=datetime.now(timezone.utc)))
        db.add(AuditEvent(company_id=actor.company_id, actor_user_id=actor.user.id,
                         action='business_session_revoked', details={'scope': 'current_session'}))
        await db.commit()
    else: await revoke_user_sessions(db, actor)
    clear_cookie(response)
    return {'ok': True}


@router.post('/logout-all')
async def logout_all(actor: AuthActor = Depends(get_auth_actor), db: AsyncSession = Depends(get_db)):
    await revoke_user_sessions(db, actor)
    return {'ok': True, 'scope': 'all_user_sessions'}


@router.post('/forgot-password', status_code=202)
async def forgot_password(data: ForgotPasswordRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    from app.auth.recovery import request_reset
    response.headers['Cache-Control'] = 'no-store'
    return await request_reset(db, data.email, request.client.host if request.client else 'unknown')


@router.post('/reset-password')
async def reset_password_endpoint(data: ResetPasswordRequest, response: Response, db: AsyncSession = Depends(get_db)):
    from app.auth.recovery import reset_password
    result = await reset_password(db, data.token, data.password)
    clear_cookie(response)
    return result


@router.get("/test")
async def auth_test():
    return {"ok": True, "message": "ApexRetail POS Auth ready"}


@router.post('/handoff')
async def issue_handoff(data: HandoffCreate, response: Response, actor: AuthActor = Depends(get_auth_actor), db: AsyncSession = Depends(get_db)):
    from app.auth.handoff import issue
    response.headers['Cache-Control'] = 'no-store'
    if actor.actor_type == 'employee' and data.owner_email and data.owner_password:
        from app.auth.handoff import reauthenticate_owner
        actor = await reauthenticate_owner(db, actor, data)
    return await issue(db, actor, data.company_id, data.branch_id)


async def replace_handoff_context(request, response, db):
    check_origin(request)
    await retire_browser_session(db, request.cookies.get(COOKIE))
    await db.commit()
    clear_cookie(response)


@router.post('/handoff/inspect')
async def inspect_handoff(data: HandoffInspect, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    from app.auth.handoff import inspect
    await replace_handoff_context(request, response, db)
    try: return await inspect(db, data.code, data.receiver)
    except HTTPException as error:
        result = JSONResponse({'detail': error.detail}, status_code=error.status_code); clear_cookie(result); return result


@router.post('/handoff/consume')
async def consume_handoff(data: HandoffConsume, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    from app.auth.handoff import consume
    await replace_handoff_context(request, response, db)
    try: result, session, secret = await consume(db, data)
    except HTTPException as error:
        result = JSONResponse({'detail': error.detail}, status_code=error.status_code); clear_cookie(result); return result
    set_cookie(response, secret, session)
    return result
