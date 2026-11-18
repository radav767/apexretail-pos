"""Business password recovery. Only disabled delivery and a test sink exist."""
import asyncio
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import HTTPException
from cryptography.fernet import Fernet
from sqlalchemy import select, case
from sqlalchemy.dialects.postgresql import insert
from app.core.config import get_settings
from app.models import User, PasswordResetGrant, BusinessEmailOutbox, BusinessAuthThrottle, AuditEvent
from app.auth.security import create_session_token, hash_session_token, hash_password
UTC = timezone.utc
GENERIC = {'ok': True, 'message': 'If this account is eligible, recovery instructions will be sent through the configured delivery service.'}


def cipher():
    settings = get_settings()
    if settings.business_email_mode != 'sink' or settings.app_env != 'test' or not settings.business_email_key:
        raise RuntimeError('Business email sink is available only with explicit test configuration')
    return Fernet(settings.business_email_key.get_secret_value().encode())


async def throttle(db, label, value, limit, seconds=3600):
    now = datetime.now(UTC)
    key = hmac.new(get_settings().jwt_secret.encode(), f'{label}:{value}'.encode(), hashlib.sha256).hexdigest()
    statement = insert(BusinessAuthThrottle).values(bucket=key, attempts=1, expires_at=now + timedelta(seconds=seconds))
    expired = BusinessAuthThrottle.expires_at <= now
    count = (await db.execute(statement.on_conflict_do_update(index_elements=['bucket'], set_={
        'attempts': case((expired, 1), else_=BusinessAuthThrottle.attempts + 1),
        'expires_at': case((expired, now + timedelta(seconds=seconds)), else_=BusinessAuthThrottle.expires_at),
    }).returning(BusinessAuthThrottle.attempts))).scalar_one()
    return count <= limit


async def request_reset(db, email, address):
    started = time.monotonic()
    email = str(email).strip().lower()
    # Always acquire the IP bucket first to keep concurrent requests ordered.
    ip_ok = await throttle(db, 'recovery-ip', address, 10)
    account_ok = await throttle(db, 'recovery-email', email, 3)
    settings = get_settings()
    if ip_ok and account_ok and settings.business_email_mode == 'sink':
        user = (await db.execute(select(User).where(User.email == email, User.active.is_(True), User.deleted.is_(False))
                                 .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if user and user.role in {'owner', 'administrator'}:
            token = create_session_token()
            db.add(PasswordResetGrant(token_hash=hash_session_token(token), user_id=user.id, company_id=user.company_id,
                                     session_version=user.session_version, expires_at=datetime.now(UTC) + timedelta(minutes=15)))
            payload = {'to': user.email, 'subject': 'Reset your ApexRetail password',
                       'reset_url': settings.backoffice_origin + '/#reset=' + token}
            db.add(BusinessEmailOutbox(user_id=user.id, company_id=user.company_id, ciphertext=cipher().encrypt(json.dumps(payload).encode())))
            db.add(AuditEvent(company_id=user.company_id, actor_user_id=user.id, action='business_password_reset_requested', details={}))
    await db.commit()
    await asyncio.sleep(max(0, .15 - (time.monotonic() - started)))
    return GENERIC


async def reset_password(db, token, password):
    hashed = hash_session_token(token)
    grant = await db.get(PasswordResetGrant, hashed)
    if grant is None: raise HTTPException(400, 'Recovery link is invalid or expired')
    user = (await db.execute(select(User).where(User.id == grant.user_id).with_for_update()
                            .execution_options(populate_existing=True))).scalar_one_or_none()
    grant = (await db.execute(select(PasswordResetGrant).where(PasswordResetGrant.token_hash == hashed).with_for_update()
                             .execution_options(populate_existing=True))).scalar_one()
    if (not user or not user.active or user.deleted or user.role not in {'owner', 'administrator'}
            or user.company_id != grant.company_id or user.session_version != grant.session_version
            or grant.consumed_at or grant.expires_at <= datetime.now(UTC)):
        raise HTTPException(400, 'Recovery link is invalid or expired')
    user.password_hash = hash_password(password)
    user.session_version += 1
    grant.consumed_at = datetime.now(UTC)
    db.add(AuditEvent(company_id=user.company_id, actor_user_id=user.id, action='business_password_reset_completed', details={'scope': 'all_user_sessions'}))
    await db.commit()
    return {'ok': True, 'message': 'Password reset. Sign in with your new password.'}


async def drain_sink(db, directory):
    """Operator/test function only. No SMTP, provider or network capability."""
    decrypt = cipher()
    root = Path(directory)
    if root.is_symlink() or not str(root.resolve()).startswith('/tmp/'):
        raise RuntimeError('Use a private disposable sink directory under /tmp')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_mode & 0o077: raise RuntimeError('Sink directory must be private')
    rows = (await db.execute(select(BusinessEmailOutbox).where(BusinessEmailOutbox.status == 'queued')
                             .with_for_update(skip_locked=True))).scalars().all()
    written = []
    for row in rows:
        payload = json.loads(decrypt.decrypt(row.ciphertext))
        token = payload['reset_url'].split('#reset=', 1)[1]
        grant = await db.get(PasswordResetGrant, hash_session_token(token))
        user = await db.get(User, row.user_id)
        if (not grant or not user or grant.consumed_at or grant.expires_at <= datetime.now(UTC)
                or grant.session_version != user.session_version or not user.active or user.deleted):
            row.status = 'cancelled'; row.ciphertext = b''; continue
        content = json.dumps(payload, sort_keys=True).encode()
        target = root / (str(row.id) + '.json')
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream: stream.write(content)
        except FileExistsError:
            if target.is_symlink() or target.read_bytes() != content: raise RuntimeError('Sink identity conflict')
        row.status = 'sink_written'; row.sink_written_at = datetime.now(UTC); row.ciphertext = b''
        written.append(target)
    await db.commit()
    return written
