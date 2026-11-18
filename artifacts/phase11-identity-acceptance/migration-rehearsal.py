import os,json,hashlib
from pathlib import Path
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from alembic.config import Config
from alembic import command
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase10_fresh_20261021t072213'
assert not url.host and url.query['host'].startswith('/tmp/apex-phase11-postgres-') and url.query['port']=='55441'
engine=create_engine(url.set(drivername='postgresql+psycopg2'))
def snapshot():
 with engine.connect() as conn:
  data=conn.execute(text('SELECT to_jsonb(u) FROM users u ORDER BY id')).scalars().all()
  return {'users':len(data),'sha256':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(),'head':conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()}
root=Path('/tmp/apexpos-phase11/backend');cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'migrations'))
before=snapshot();assert before['head']=='p11a_user_session_revocation'
command.upgrade(cfg,'head');after=snapshot();assert before['sha256']==after['sha256']
admin=create_engine(url.set(drivername='postgresql+psycopg2',database='postgres'),isolation_level='AUTOCOMMIT')
with admin.connect() as conn:conn.execute(text('CREATE DATABASE apex_phase11_identity_fresh'))
os.environ['DATABASE_URL']=url.set(database='apex_phase11_identity_fresh').render_as_string(hide_password=False)
command.upgrade(cfg,'head')
fresh=create_engine(url.set(drivername='postgresql+psycopg2',database='apex_phase11_identity_fresh'))
with fresh.connect() as conn:head=conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
result={'synthetic_only':True,'populated_before':before,'populated_after':after,'fresh_head':head,'all_existing_user_fields_preserved':True,'rollback':'Every new migration refuses downgrade; compatible application must retain p11a epoch and p11b session enforcement'}
Path('/tmp/phase11-identity-migrations.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));fresh.dispose();admin.dispose();engine.dispose()
