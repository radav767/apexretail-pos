import asyncio,os,json,sys
from pathlib import Path
from tempfile import TemporaryDirectory
from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase10_fresh_20261021t072213'
assert not url.host and url.query['host'].startswith('/tmp/apex-phase11-postgres-') and url.query['port']=='55441'
os.environ['BUSINESS_EMAIL_MODE']='sink';os.environ['BUSINESS_EMAIL_KEY']=Fernet.generate_key().decode()
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.auth.recovery import request_reset,drain_sink
async def main():
 engine=create_async_engine(url)
 async with async_sessionmaker(engine,expire_on_commit=False)() as db:
  await request_reset(db,sys.argv[1],'synthetic-browser-acceptance')
  with TemporaryDirectory(prefix='apex-phase11-browser-mail-') as sink:
   paths=await drain_sink(db,sink)
   assert len(paths)==1
   print(json.loads(Path(paths[0]).read_text())['reset_url'])
 await engine.dispose()
asyncio.run(main())
