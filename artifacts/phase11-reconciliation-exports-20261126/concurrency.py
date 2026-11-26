"""Independent committed synthetic export snapshots and in-flight revocation."""
import asyncio,io,json,os
from datetime import datetime,timezone,timedelta
from uuid import UUID,uuid4
from zipfile import ZipFile
from unittest.mock import patch
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from fastapi import HTTPException
from app.auth.service import AuthService
from app.auth.repository import AuthRepository
from app.auth.schema import RegisterRequest
from app.auth.dependencies import resolve_auth_actor
from app.models import Sale
from app.accounting.exports import export_bundle,EXPORT_SQL
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase7c_test_phase7e' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 try:
  async with factory() as db:
   registration=await AuthService(AuthRepository(db)).register(RegisterRequest(owner_name='Synthetic export owner',owner_pin='1234',business_name='Synthetic export concurrency',business_type='Retail',country='Zimbabwe',phone='000000000',email=str(uuid4())+'@example.com',password='Synthetic-Only-123!',confirm_password='Synthetic-Only-123!',base_currency_code='USD',base_currency_symbol='$',base_currency_decimal_places=2))
   c,b=UUID(registration['company']['id']),UUID(registration['branch']['id']);token=registration['token']
  now=datetime.now(timezone.utc);start,end=now-timedelta(days=1),now+timedelta(days=1)
  def row():return Sale(company_id=c,branch_id=b,receipt_number='SYN-'+uuid4().hex,total_amount=1,subtotal_amount=1,tax_amount=0,base_currency_code='USD',payment_method='cash',payment_currency_code='USD',payment_amount_original=1,tendered_amount_original=2,change_amount_original=1,exchange_rate_snapshot=1,created_at=now)
  async def read():
   async with factory() as db:
    actor=await resolve_auth_actor(token,db);response=await export_bundle(db,actor,c,start,end)
    z=ZipFile(io.BytesIO(response.body));return json.loads(z.read('snapshot.json')),json.loads(z.read('manifest.json'))
  assert (await read())[0]['event_count']==0
  async with factory() as writer:
   writer.add_all([row() for _ in range(201)]);await writer.flush()
   before,_=await read();assert before['event_count']==before['receipt_count']==0
   await writer.commit()
  committed,manifest=await read();assert committed['event_count']==committed['receipt_count']==201
  assert len([name for name in manifest['files'] if name.startswith('events-')])==2
  assert sum(float(r['billed']) for r in committed['receipts'])==201
  async with factory() as writer:
   writer.add(row());await writer.flush();during,_=await read();assert during['events']==committed['events'];await writer.rollback()
  after,_=await read();assert after['events']==committed['events']
  queried,released=asyncio.Event(),asyncio.Event()
  async with factory() as reader:
   actor=await resolve_auth_actor(token,reader);execute=reader.execute
   async def held(statement,*args,**kwargs):
    result=await execute(statement,*args,**kwargs)
    if statement is EXPORT_SQL:queried.set();await asyncio.wait_for(released.wait(),10)
    return result
   with patch.object(reader,'execute',held):
    pending=asyncio.create_task(export_bundle(reader,actor,c,start,end));await asyncio.wait_for(queried.wait(),10)
    async with factory() as writer:
     await writer.execute(text('UPDATE users SET session_version=session_version+1 WHERE id=:id'),{'id':actor.user.id});await writer.commit()
    released.set()
    try:await pending;raise AssertionError('revoked download returned bytes')
    except HTTPException as exc:assert exc.status_code==401
  print(json.dumps({'company_id':str(c),'committed_receipts':201,'committed_events':201,'internal_event_pages':2,'uncommitted_insert_visible':False,'rollback_changed_snapshot':False,'independent_revoked_download_status':401,'posting_enabled':False}))
 finally:await engine.dispose()
asyncio.run(main())
