"""Separate opaque sessions: business tokens never authorize platform actions."""
from datetime import datetime,timedelta,timezone
from secrets import token_urlsafe
from fastapi import Depends,HTTPException
from sqlalchemy import select
from app.auth.dependencies import bearer_scheme
from app.auth.security import hash_password,verify_password,hash_session_token
from app.db.session import get_db
from app.models.commercial import PlatformAdmin,PlatformSession,PlatformAudit

UTC=timezone.utc
DUMMY_HASH=hash_password(token_urlsafe(24))

async def login(db,email,password):
    now=datetime.now(UTC)
    admin=(await db.execute(select(PlatformAdmin).where(PlatformAdmin.email==email.strip().lower()).with_for_update())).scalar_one_or_none()
    try:valid=verify_password(password,admin.password_hash if admin else DUMMY_HASH)
    except (ValueError,TypeError):valid=False
    if not admin or not admin.active or admin.locked_until and admin.locked_until>now or not valid:
        if admin:
            admin.failed_attempts+=1
            if admin.failed_attempts>=5:admin.locked_until=now+timedelta(minutes=15)
            db.add(PlatformAudit(admin_id=admin.id,action='platform_login_rejected',details={}))
            await db.commit()
        raise HTTPException(401,'Invalid platform credentials or account unavailable')
    admin.failed_attempts=0;admin.locked_until=None
    token='apx_platform_'+token_urlsafe(48)
    db.add(PlatformSession(admin_id=admin.id,token_hash=hash_session_token(token),expires_at=now+timedelta(minutes=30)))
    db.add(PlatformAudit(admin_id=admin.id,action='platform_login',details={}))
    await db.commit()
    return {'access_token':token,'expires_in':1800,'role':admin.role,'admin_id':str(admin.id)}

async def authenticate(db,token):
    if not token.startswith('apx_platform_'):raise HTTPException(401,'Platform authentication required')
    result=(await db.execute(select(PlatformAdmin,PlatformSession).join(PlatformSession,PlatformSession.admin_id==PlatformAdmin.id).where(
        PlatformSession.token_hash==hash_session_token(token),PlatformSession.revoked_at.is_(None),
        PlatformSession.expires_at>datetime.now(UTC),PlatformAdmin.active==True))).first()
    if not result:raise HTTPException(401,'Platform session expired or revoked')
    return result

async def platform_actor(credentials=Depends(bearer_scheme),db=Depends(get_db)):
    if not credentials:raise HTTPException(401,'Platform authentication required')
    admin,_=await authenticate(db,credentials.credentials)
    return admin

def permit(admin,action):
    if admin.role=='super_admin' or admin.role=='billing' and action in {'read','invoice','payment','notifications'} or admin.role=='support' and action=='read':return
    raise HTTPException(403,'Platform role does not allow this action')
