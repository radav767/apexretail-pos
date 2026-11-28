"""Faulted synthetic payload, forward repair and aborted-transaction preservation."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
import psycopg2
root=Path('/tmp/apex-phase11-independent-release-5lrb0b7l');guard=Path((root/'latest-guard.txt').read_text());repo=Path(__file__).resolve().parents[2]
plan=json.loads((guard/'plan.json').read_text());assert plan['database']=='apex_phase11_release_rich_upgrade' and plan['port']==55443
clearance=json.loads((guard/'clearance.json').read_text());clearance['expires_at']=(datetime.now(timezone.utc)+timedelta(minutes=13)).isoformat();p=guard/'forward-clearance.json';p.write_text(json.dumps(clearance,indent=2));p.chmod(0o600)
queue=root/'rich/retained-browser-queue.json';before=hashlib.sha256(queue.read_bytes()).hexdigest()
env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1'}
file=Path(plan['payload'])/'backend/app/__init__.py';original=file.read_bytes()
def attempt(name,expected):
 out=guard/name;out.mkdir(mode=0o700)
 args=[str(root/'venv/bin/python'),str(repo/'ops/phase11/release_guard.py'),'--plan',str(guard/'plan.json'),'--plan-sha256',hashlib.sha256((guard/'plan.json').read_bytes()).hexdigest(),'--clearance',str(p),'--output',str(out),'--rehearse']
 with (guard/(name+'.log')).open('x') as log:r=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT)
 assert r.returncode==expected,(name,r.returncode)
try:
 file.write_bytes(original+b'\n# injected failed candidate payload\n');attempt('rejected-candidate',1)
finally:file.write_bytes(original)
attempt('forward-repair',0)
# Emulate a disconnected owner process in transactional DDL; no commit occurs.
code="""import psycopg2,os
c=psycopg2.connect(dbname='apex_phase11_release_rich_upgrade',user='postgres',host='/tmp/apex-phase11-release-pg-ysjagwtm',port=55443)
with c.cursor() as q:q.execute('CREATE TABLE phase11_uncommitted_probe(id int)');q.execute('INSERT INTO phase11_uncommitted_probe VALUES(1)')
os._exit(74)
"""
r=subprocess.run([str(root/'venv/bin/python'),'-c',code],env=env);assert r.returncode==74
c=psycopg2.connect(dbname=plan['database'],user='postgres',host=plan['socket'],port=plan['port']);c.set_session(readonly=True)
with c.cursor() as cur:
 cur.execute("SELECT to_regclass('public.phase11_uncommitted_probe')");assert cur.fetchone()[0] is None
 cur.execute('SELECT count(*),sum(total_amount)::text FROM sales');sales,total=cur.fetchone();assert sales==4 and total=='35.00'
 cur.execute('SELECT session_version FROM users');assert cur.fetchone()[0]==1
 cur.execute('SELECT count(*) FROM pos_sessions WHERE revoked_at IS NOT NULL');assert cur.fetchone()[0]==1
c.rollback();c.close();assert hashlib.sha256(queue.read_bytes()).hexdigest()==before
print(json.dumps({'tampered_payload_rejected':True,'forward_repair_preserves_latest_snapshot':True,'aborted_transaction_ddl_rolled_back':True,'newer_sales':sales,'net_sales':total,'revoked_user_version':1,'retained_original_queue_sha256':before,'production_touched':False}))
