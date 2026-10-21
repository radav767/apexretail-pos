"""RFC 6238 TOTP. No default key, password-only fallback, or live key generation."""
import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from datetime import datetime,timedelta,timezone
from urllib.parse import quote
from cryptography.fernet import Fernet,InvalidToken
from fastapi import HTTPException
from sqlalchemy import select
from app.models.commercial import PlatformAdmin,PlatformChallenge,PlatformAudit,PlatformSession
from app.auth.security import hash_session_token

UTC=timezone.utc

def cipher():
    from app.core.config import get_settings
    value=os.environ.get('PLATFORM_MFA_KEY')
    if value is None:
        configured=get_settings().platform_mfa_key
        value=configured.get_secret_value() if configured else ''
    try:return Fernet(value.encode())
    except ValueError:raise HTTPException(503,'Platform MFA encryption key requires authorized provisioning')

def totp(secret,step,digits=6):
    digest=hmac.new(base64.b32decode(secret),struct.pack('>Q',step),hashlib.sha1).digest()
    offset=digest[-1]&15
    return str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%10**digits).zfill(digits)

async def challenge(db,admin):
    key=cipher();secret=base64.b32encode(secrets.token_bytes(20)).decode() if not admin.mfa_secret else None
    token=secrets.token_urlsafe(48)
    db.add(PlatformChallenge(admin_id=admin.id,token_hash=hash_session_token(token),
        pending_secret=key.encrypt(secret.encode()).decode() if secret else None,expires_at=datetime.now(UTC)+timedelta(minutes=5)))
    db.add(PlatformAudit(admin_id=admin.id,action='platform_mfa_challenge',details={'enrollment':secret is not None}))
    await db.commit()
    result={'challenge':token,'mfa_required':True,'enrollment_required':secret is not None,'expires_in':300}
    if secret:result.update(secret=secret,otpauth_uri=f'otpauth://totp/{quote("ApexRetail:"+admin.email,safe="")}?secret={secret}&issuer=ApexRetail&algorithm=SHA1&digits=6&period=30')
    return result

async def verify(db,token,code):
    # Lock the administrator first to serialize codes across different challenges.
    aid=(await db.execute(select(PlatformChallenge.admin_id).where(PlatformChallenge.token_hash==hash_session_token(token)))).scalar_one_or_none()
    if not aid:raise HTTPException(401,'Invalid or expired MFA challenge')
    admin=(await db.execute(select(PlatformAdmin).where(PlatformAdmin.id==aid).with_for_update())).scalar_one()
    row=(await db.execute(select(PlatformChallenge).where(PlatformChallenge.token_hash==hash_session_token(token)).with_for_update())).scalar_one()
    now=datetime.now(UTC)
    if not admin.active or row.used_at or row.expires_at<=now or admin.locked_until and admin.locked_until>now:
        raise HTTPException(401,'Invalid or expired MFA challenge')
    encrypted=admin.mfa_secret or row.pending_secret
    try:secret=cipher().decrypt(encrypted.encode()).decode()
    except (InvalidToken,AttributeError):raise HTTPException(503,'MFA key unavailable; authorized recovery required')
    step=int(time.time())//30
    matched=next((s for s in (step,step-1,step+1) if s>admin.mfa_last_step and hmac.compare_digest(totp(secret,s),code)),None)
    if matched is None:
        admin.failed_attempts+=1
        if admin.failed_attempts>=5:admin.locked_until=now+timedelta(minutes=15)
        db.add(PlatformAudit(admin_id=admin.id,action='platform_mfa_rejected',details={}))
        await db.commit();raise HTTPException(401,'Invalid or already used authentication code')
    if not admin.mfa_secret:admin.mfa_secret=row.pending_secret
    admin.mfa_last_step=matched;admin.failed_attempts=0;admin.locked_until=None;row.used_at=now
    session_token='apx_platform_'+secrets.token_urlsafe(48)
    db.add(PlatformSession(admin_id=admin.id,token_hash=hash_session_token(session_token),expires_at=now+timedelta(minutes=30),mfa_verified=True))
    db.add(PlatformAudit(admin_id=admin.id,action='platform_login',details={'mfa':True}))
    await db.commit()
    return {'access_token':session_token,'expires_in':1800,'role':admin.role,'admin_id':str(admin.id)}
