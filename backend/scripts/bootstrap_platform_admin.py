"""Explicit offline provisioning; no default/platform credentials or public signup.

Run only after an authorized deployment/migration. Never called by startup.
"""
import asyncio
import getpass
import sys
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.commercial import PlatformAdmin,PlatformAudit
from app.auth.security import hash_password

async def main():
    if len(sys.argv)!=2:raise SystemExit('Usage: python -m scripts.bootstrap_platform_admin EMAIL')
    email=sys.argv[1].strip().lower()
    password=getpass.getpass('New platform password (12–72 UTF-8 bytes): ')
    if len(password)<12 or len(password.encode())>72 or password!=getpass.getpass('Confirm password: '):raise SystemExit('Password does not meet requirements or confirmation differs')
    if '@' not in email or len(email)>160:raise SystemExit('Valid email required')
    async with SessionLocal() as db:
        if (await db.execute(select(PlatformAdmin.id).where(PlatformAdmin.email==email))).first():raise SystemExit('Existing account; refusing overwrite')
        row=PlatformAdmin(email=email,password_hash=hash_password(password),role='super_admin')
        db.add(row);await db.flush();db.add(PlatformAudit(admin_id=row.id,action='platform_admin_bootstrapped',details={'method':'explicit_local_cli'}));await db.commit()
    print('Platform administrator provisioned; no business account was changed.')
if __name__=='__main__':asyncio.run(main())
