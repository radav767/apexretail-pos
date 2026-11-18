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
  data=conn.execute(text("SELECT to_jsonb(u)-'session_version' FROM users u ORDER BY id")).scalars().all()
  return {'users':len(data),'sha256':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(),'head':conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()}
root=Path('/tmp/apexpos-phase11/backend');cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'migrations'))
before=snapshot();assert before['users']==2 and before['head']=='p10a_platform_management'
command.upgrade(cfg,'head');after=snapshot()
with engine.connect() as conn:assert conn.execute(text('SELECT count(*) FROM users WHERE session_version=0')).scalar()==2
command.downgrade(cfg,'p10a_platform_management');downgraded=snapshot()
command.upgrade(cfg,'head');recovered=snapshot()
assert before['sha256']==after['sha256']==downgraded['sha256']==recovered['sha256']
admin=create_engine(url.set(drivername='postgresql+psycopg2',database='postgres'),isolation_level='AUTOCOMMIT')
with admin.connect() as conn:conn.execute(text('CREATE DATABASE apex_phase11_fresh_sessions'))
os.environ['DATABASE_URL']=url.set(database='apex_phase11_fresh_sessions').render_as_string(hide_password=False)
command.upgrade(cfg,'head')
fresh_engine=create_engine(url.set(drivername='postgresql+psycopg2',database='apex_phase11_fresh_sessions'))
with fresh_engine.connect() as conn:fresh=conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
result={'synthetic_only':True,'before':before,'upgraded':after,'zero_version_downgrade':downgraded,'forward_recovery':recovered,'fresh_database_head':fresh,'user_hashes_preserved':True}
Path('/tmp/apex-phase11-session-migrations.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
fresh_engine.dispose();admin.dispose();engine.dispose()
