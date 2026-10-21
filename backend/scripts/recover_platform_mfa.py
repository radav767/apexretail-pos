"""Operator-only platform factor recovery. Never runs on startup or via HTTP.

Requires authorized OS/DB access AND the administrator's current password.
Does not reset tenant passwords, issue sessions, or bypass new MFA enrollment.
"""
import asyncio,getpass,sys
from datetime import datetime,timezone
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.commercial import PlatformAdmin,PlatformSession,PlatformAudit
from app.auth.security import verify_password

async def main():
    if len(sys.argv)!=2:raise SystemExit('Usage: python -m scripts.recover_platform_mfa EMAIL')
    email=sys.argv[1].strip().lower()
    if input('Type RESET PLATFORM MFA '+email+': ')!='RESET PLATFORM MFA '+email:raise SystemExit('Cancelled')
    reason=input('Authorized identity verification reference (3–500 characters): ').strip()
    if not 3<=len(reason)<=500:raise SystemExit('Identity verification reference required')
    password=getpass.getpass('Current platform administrator password: ')
    async with SessionLocal() as db:
        row=(await db.execute(select(PlatformAdmin).where(PlatformAdmin.email==email).with_for_update())).scalar_one_or_none()
        if not row or not row.active or not verify_password(password,row.password_hash):raise SystemExit('Account unavailable or credentials rejected')
        row.mfa_secret=None;row.mfa_last_step=-1;row.failed_attempts=0;row.locked_until=None
        for session in (await db.execute(select(PlatformSession).where(PlatformSession.admin_id==row.id,PlatformSession.revoked_at.is_(None)))).scalars():session.revoked_at=datetime.now(timezone.utc)
        from app.models.commercial import PlatformChallenge
        for challenge in (await db.execute(select(PlatformChallenge).where(PlatformChallenge.admin_id==row.id,PlatformChallenge.used_at.is_(None)))).scalars():challenge.used_at=datetime.now(timezone.utc)
        db.add(PlatformAudit(admin_id=row.id,action='platform_mfa_operator_recovery',details={'method':'authorized_local_cli','identity_review_reference':reason}))
        await db.commit()
    print('Platform sessions and challenges revoked. New MFA enrollment is required. No tenant account was changed.')
if __name__=='__main__':asyncio.run(main())
