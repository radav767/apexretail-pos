import asyncio,os,json
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timedelta,timezone
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase10_fresh_20261021t072213'
assert not url.host and url.query['host'].startswith('/tmp/apex-phase11-postgres-') and url.query['port']=='55441'
from fastapi import HTTPException
from app.auth.repository import AuthRepository
from app.auth.service import AuthService
from app.auth.schema import RegisterRequest,HandoffConsume,HandoffCreate
from app.auth.security import create_access_token,create_session_token,hash_session_token
from app.auth.dependencies import resolve_auth_actor
from app.auth.remembered import new_session,refresh
from app.auth.recovery import reset_password
from app.auth.handoff import issue,inspect,consume,reauthenticate_owner
from app.models import User,BusinessSession,PasswordResetGrant,AuditEvent
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  result=await AuthService(AuthRepository(db)).register(RegisterRequest(owner_name='Synthetic Concurrency Owner',owner_pin='1234',business_name='Synthetic Concurrency Business',business_type='Retail',country='Zimbabwe',phone='000000000',email=f'{uuid4()}@example.com',password='synthetic-concurrent-password',confirm_password='synthetic-concurrent-password',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
  employee_token=result['employee']['access_token']
  uid=result['user']['id'];branch=result['branch']['id'];company=result['company']['id']
  from uuid import UUID
  uid,branch,company=UUID(uid),UUID(branch),UUID(company)
  user=await db.get(User,uid);session,secret=await new_session(db,user,True);sid=session.id;await db.commit()
 async def attempt(action):
  async with factory() as db:
   try:await action(db);return 200
   except HTTPException as error:return error.status_code
 refresh_status=await asyncio.gather(attempt(lambda db:refresh(db,secret)),attempt(lambda db:refresh(db,secret)))
 assert sorted(refresh_status)==[200,401]
 async with factory() as db:
  assert (await db.get(BusinessSession,sid)).revoked_at is not None
  reset=create_session_token();db.add(PasswordResetGrant(token_hash=hash_session_token(reset),user_id=uid,company_id=company,session_version=0,expires_at=datetime.now(timezone.utc)+timedelta(minutes=15)));await db.commit()
 reset_status=await asyncio.gather(attempt(lambda db:reset_password(db,reset,'synthetic-concurrent-new-password')),attempt(lambda db:reset_password(db,reset,'synthetic-concurrent-new-password')))
 assert sorted(reset_status)==[200,400]
 async with factory() as db:
  user=await db.get(User,uid);assert user.session_version==1
  token=create_access_token(str(uid),user.email,session_version=1)
  actor=await resolve_auth_actor(token,db);handoff=await issue(db,actor,company,branch);code=handoff['url'].split('#handoff=')[1]
  receiver=str(uuid4());identity=await inspect(db,code,receiver)
 data=HandoffConsume(code=code,receiver=receiver,company_id=company,branch_id=branch,role=identity['role'])
 handoff_status=await asyncio.gather(attempt(lambda db:consume(db,data)),attempt(lambda db:consume(db,data)))
 assert sorted(handoff_status)==[200,401]
 async with factory() as db:
  audits=(await db.execute(select(AuditEvent.action,func.count()).where(AuditEvent.actor_user_id==uid).group_by(AuditEvent.action))).all()
  counts=dict(audits);assert counts['business_password_reset_completed']==1 and counts['backoffice_handoff_consumed']==1
 async def fresh_owner(db):
  employee=await resolve_auth_actor(employee_token,db)
  owner=await db.get(User,uid)
  data=HandoffCreate(company_id=company,branch_id=branch,owner_email=owner.email,owner_password='synthetic-concurrent-new-password')
  authenticated=await reauthenticate_owner(db,employee,data)
  await issue(db,authenticated,company,branch)
 owner_status=await asyncio.wait_for(asyncio.gather(attempt(fresh_owner),attempt(fresh_owner)),timeout=10)
 assert owner_status==[200,200]
 result={'fresh_owner_concurrent_statuses':owner_status,'fresh_owner_lock_order_no_deadlock':True,'synthetic_only':True,'refresh_concurrent_statuses':sorted(refresh_status),'refresh_family_revoked':True,'reset_concurrent_statuses':sorted(reset_status),'final_user_version':1,'handoff_concurrent_statuses':sorted(handoff_status),'single_reset_audit':True,'single_handoff_audit':True}
 Path('/tmp/phase11-identity-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
