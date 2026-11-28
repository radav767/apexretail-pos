"""Default-disabled synthetic APIs before/after a failed activation and forward resume."""
import asyncio,hashlib,json,os,sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.engine import make_url
from sqlalchemy import text
import httpx
from app.main import app
from app.db.session import get_db
from app.auth.security import create_access_token
from app.core.config import get_settings
root=Path('/tmp/apex-phase11-independent-release-5lrb0b7l');saved=root/'rich';ids=json.loads((saved/'ids.json').read_text());url=make_url(os.environ['DATABASE_URL']);assert url.database=='apex_phase11_release_rich_upgrade' and url.query['host']=='/tmp/apex-phase11-release-pg-ysjagwtm' and url.query['port']=='55443'
assert all(getattr(get_settings(),n)=='disabled' for n in ['split_checkout_mode','quotation_pricing_mode','business_email_mode','document_delivery_mode'])
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async def override():
  async with factory() as db:yield db
 app.dependency_overrides[get_db]=override
 old=create_access_token(ids['user'],'rich@example.invalid')
 try:
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.invalid',headers={'Authorization':'Bearer '+old}) as client:
   async def post(path,body):
    r=await client.post('/api'+path,json=body);assert r.status_code==200,(path,r.status_code,r.text);return r.json()
   action=sys.argv[1]
   if action=='before':
    # The historical preservation fixture deliberately used generic false
    # booleans. Activate its synthetic actors only now for API acceptance;
    # no preservation snapshot is rewritten or comparison waived.
    async with factory() as db:
     for table in ['companies','users','shops','branches','devices','employees','company_settings']:
      await db.execute(text('UPDATE '+table+' SET active=true WHERE active=false'))
     from app.subscriptions.service import SubscriptionService
     from uuid import UUID
     await SubscriptionService(db).get_or_create_trial(UUID(ids['company']),commit=False)
     await db.commit()
    common={'company_id':ids['company'],'request_id':str(uuid4())}
    template=await post('/inventory/workflows/templates',{**common,'branch_id':ids['branch'],'paper':'80mm','blocks':[{'kind':'title','text':'Immutable synthetic recovery document'}]})
    document=await post('/inventory/workflows/documents',{**common,'request_id':str(uuid4()),'template_id':template['id'],'source_kind':'sale','source_id':ids['cash']})
    output=await post('/inventory/workflows/outputs',{**common,'request_id':str(uuid4()),'document_id':document['id'],'format':'pdf'})
    download=f"/api/inventory/workflows/outputs/{ids['company']}/{output['id']}/download"
    data=await client.get(download);assert data.status_code==200 and data.content.startswith(b'%PDF')
    (saved/'immutable.pdf').write_bytes(data.content)
    sale_body={'company_id':ids['company'],'branch_id':ids['branch'],'device_id':ids['device'],'client_sale_id':str(uuid4()),'payment_method':'cash','amount_received':'20','items':[{'product_id':ids['product'],'quantity':'1'}]}
    sale=await post('/sales',sale_body)
    r=await client.get(f"/api/sales/receipt/{ids['company']}/{sale['id']}?mark_reprint=false");assert r.status_code==200;receipt=r.json()
    await post('/auth/logout-all',{})
    r=await client.get(f"/api/fiscal/{ids['company']}/configuration");assert r.status_code==401
    (saved/'forward.json').write_text(json.dumps({'sale':sale,'body':sale_body,'receipt':receipt,'download':download,'output_sha256':hashlib.sha256(data.content).hexdigest()},indent=2))
    print('New real API sale/immutable PDF committed, logout-all revoked old token; activation failure simulated before any service switch')
   else:
    state=json.loads((saved/'forward.json').read_text())
    r=await client.get(f"/api/fiscal/{ids['company']}/configuration");assert r.status_code==401
    fresh=create_access_token(ids['user'],'rich@example.invalid',session_version=1)
    client.headers['Authorization']='Bearer '+fresh
    r=await client.get(f"/api/sales/receipt/{ids['company']}/{state['sale']['id']}?mark_reprint=false");assert r.status_code==200 and r.json()==state['receipt']
    r=await client.get(state['download']);assert r.status_code==200 and r.content==(saved/'immutable.pdf').read_bytes()
    # Current same-owner credentials can recover the original complete proof;
    # the revoked credential itself must remain rejected by authentication.
    replay=await client.post('/api/sales',json=state['body']);assert replay.status_code==200 and replay.json()['id']==state['sale']['id']
    print('Forward application process: old token401, fresh current read200, immutable PDF/receipt identical, authorized exact replay retains original sale ID')
 finally:app.dependency_overrides.clear();await engine.dispose()
asyncio.run(main())
