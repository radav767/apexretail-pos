"""A synthetic legacy business User used only to prove Backoffice role denial."""
import asyncio,os,sys,json
from uuid import UUID,uuid4
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.engine import make_url
from app.models import Company,User
from app.auth.security import hash_password
url=make_url(os.environ['DATABASE_URL']);assert os.environ['APP_ENV']=='test' and url.database=='apex_phase11_shell_20261121' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
async def main():
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 try:
  async with factory() as db:
   c=UUID(sys.argv[1]);company=await db.get(Company,c);assert company.name=='Synthetic daily navigation'
   email='restricted-'+str(uuid4())+'@example.com';user=User(company_id=c,email=email,password_hash=hash_password('Synthetic-Shell-Only-123!'),role='cashier');db.add(user);await db.commit();print(json.dumps({'email':email,'user_id':str(user.id)}))
 finally:await engine.dispose()
asyncio.run(main())
