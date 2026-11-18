import asyncio,os,json
from pathlib import Path
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase10_fresh_20261021t072213'
assert not url.host and url.query['host'].startswith('/tmp/apex-phase11-postgres-') and url.query['port']=='55441'
from app.auth.dependencies import resolve_auth_actor
from app.auth.sessions import revoke_user_sessions
from app.auth.security import create_access_token
from app.models import User,AuditEvent
from fastapi import HTTPException
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  user=(await db.execute(select(User).order_by(User.id))).scalars().first()
  uid=user.id;company=user.company_id;initial=user.session_version
  assert initial==0
  token=create_access_token(str(uid),user.email,session_version=initial)
 async with factory() as first,factory() as second:
  actors=await asyncio.gather(resolve_auth_actor(token,first),resolve_auth_actor(token,second))
  await asyncio.gather(revoke_user_sessions(first,actors[0]),revoke_user_sessions(second,actors[1]))
 async with factory() as db:
  final=(await db.execute(select(User.session_version).where(User.id==uid))).scalar_one()
  audits=(await db.execute(select(func.count(AuditEvent.id)).where(AuditEvent.actor_user_id==uid,AuditEvent.action=='business_user_sessions_revoked'))).scalar_one()
  assert final==2 and audits==2
  try:await resolve_auth_actor(token,db)
  except HTTPException as error:assert error.status_code==401
  else:raise AssertionError('Revoked token authorized')
  fresh=create_access_token(str(uid),user.email,session_version=final)
  assert (await resolve_auth_actor(fresh,db)).user.id==uid
 result={'synthetic_only':True,'concurrent_revocations':2,'final_session_version':final,'audit_events':audits,'stale_token_denied':True,'fresh_token_accepted':True}
 Path('/tmp/apex-phase11-session-concurrency.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await engine.dispose()
asyncio.run(main())
