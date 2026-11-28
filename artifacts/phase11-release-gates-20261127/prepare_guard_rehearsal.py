"""Create only a new disposable payload/clearance; never production approval."""
import os,hashlib,json,shutil,subprocess,sys,tempfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
import psycopg2
from alembic.config import Config
from alembic.script import ScriptDirectory
repo=Path(__file__).resolve().parents[2];root=Path('/tmp/apex-phase11-independent-release-5lrb0b7l');db='apex_phase11_release_rich_qualification';socket='/tmp/apex-phase11-release-pg-ysjagwtm';os.umask(0o077)
connection=psycopg2.connect(dbname=db,user='postgres',host=socket,port=55443);connection.autocommit=True
with connection.cursor() as c:
 c.execute('SHOW port');assert c.fetchone()[0]=='55443'
 c.execute("DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN CREATE ROLE apex_user NOLOGIN; END IF; END $$")
 c.execute('REVOKE CONNECT,TEMPORARY ON DATABASE apex_phase11_release_rich_qualification FROM PUBLIC,apex_user');c.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC,apex_user')
connection.close()
payload=Path(tempfile.mkdtemp(prefix='apex-phase11-guard-payload-'));payload.chmod(0o755)
paths=subprocess.check_output(['git','ls-files','backend/app','backend/migrations','backend/alembic.ini','backend/requirements-runtime.lock','backend/requirements-documents.lock'],cwd=repo,text=True).splitlines()
for name in paths:
 target=payload/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/name,target)
# Bundle the verified supported interpreter and standard library, with no
# dependence on an unpinned external venv home. Everything is payload-hashed.
shutil.copytree('/tmp/apex-phase11-python31118-20261128-attempt2/python',payload/'runtime',symlinks=False)
subprocess.run([str(payload/'runtime/bin/python3.11'),'-m','venv',str(payload/'venv')],check=True)
shutil.copytree('/tmp/apex-phase11-release-qualified-311/lib/python3.11/site-packages',payload/'venv/lib/python3.11/site-packages',dirs_exist_ok=True,symlinks=False)
for p in (payload/'venv/bin').iterdir():
 if p.is_symlink():
  data=p.read_bytes();p.unlink();p.write_bytes(data)

# venv's optional lib64 alias is unnecessary; retain one fully sealed lib tree.
if (payload/'venv/lib64').is_symlink():(payload/'venv/lib64').unlink()
# This is a newly created disposable copy only. Do not touch the source venv.
for p in sorted(payload.rglob('__pycache__'),reverse=True):shutil.rmtree(p)
for p in payload.rglob('*'):
 if p.is_dir():p.chmod(0o755)
 elif p.is_file():p.chmod(0o755 if p.parent.name=='bin' else 0o644)
lines=[hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(payload)) for p in sorted(payload.rglob('*')) if p.is_file()]
manifest=payload/'PAYLOAD.sha256';manifest.write_text('\n'.join(lines)+'\n');manifest.chmod(0o644)
cfg=Config(str(repo/'backend/alembic.ini'));cfg.set_main_option('script_location',str(repo/'backend/migrations'));graph=ScriptDirectory.from_config(cfg);start='p10a_platform_management';head='p11ac_quote_refund_evidence'
plan={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'database':db,'socket':socket,'port':55443,'start':start,'head':head,'payload':str(payload),'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'ordered_revisions':[r.revision for r in reversed(list(graph.iterate_revisions(head,start)))]}
for k,p in [('runner',repo/'ops/phase11/release_guard.py'),('snapshot',repo/'ops/phase11/snapshot.py'),('python',payload/'venv/bin/python')]:plan[k]=str(p);plan[k+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
clearance={k:plan[k] for k in ['commit','database','manifest_sha256']};clearance.update({'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=14)).isoformat(),'sales_paused':True,'open_shifts':1,'queue_policy':'retain-and-replay-original-context-v1','device_queue_inventory_sha256':hashlib.sha256((root/'qualification-rich/retained-browser-queue.json').read_bytes()).hexdigest(),'revocations_must_survive':True,'synthetic':True})
output=Path(tempfile.mkdtemp(prefix='guard-',dir=root));output.chmod(0o700)
(root/'latest-guard.txt').write_text(str(output))
for name,data in [('plan.json',plan),('clearance.json',clearance)]:
 p=output/name;p.write_text(json.dumps(data,indent=2));p.chmod(0o600)
print(json.dumps({'plan':str(output/'plan.json'),'plan_sha256':hashlib.sha256((output/'plan.json').read_bytes()).hexdigest(),'payload':str(payload),'files':len(lines)}))
