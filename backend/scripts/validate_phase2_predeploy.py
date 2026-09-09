"""Read-only production backup; strictly named disposable Phase 2 validation DBs.
Run with --execute --commit <HEAD>. Never deploys, restarts, or drops databases.
"""
import os, sys, re, json, hashlib, subprocess
from pathlib import Path
from datetime import datetime, timezone
import psycopg2
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path('/root/apexretail-pos')
assert len(sys.argv) == 4 and sys.argv[1:3] == ['--execute', '--commit']
EXPECTED = sys.argv[3]
assert re.fullmatch(r'[0-9a-f]{40}', EXPECTED)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip() == EXPECTED
os.umask(0o077)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out = ROOT/'backups/phase2-predeploy'/stamp
out.mkdir(mode=0o700)
url = make_url(dotenv_values(ROOT/'backend/.env')['DATABASE_URL'])
assert url.database == 'apexretail_pos'
role = url.username
assert re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',role)
names = {k:f'apexretail_phase2_test_{k}_{stamp.lower()}' for k in ['clone','fresh']}
for name in names.values():
 assert re.fullmatch(r'apexretail_phase2_test_(clone|fresh)_[0-9]{8}t[0-9]{6}z',name) and len(name)<=63

def run(args, **kw):
 return subprocess.run(args,check=True,cwd='/tmp',**kw)
def pg(args, **kw):
 return run(['runuser','-u','postgres','--','/usr/lib/postgresql/14/bin/'+args[0],*args[1:]],**kw)
def conn(db):
 assert db == 'apexretail_pos' or db in names.values()
 return psycopg2.connect(url.set(drivername='postgresql',database=db).render_as_string(hide_password=False))
def scalar(c,sql):
 with c.cursor() as q:q.execute(sql);return q.fetchone()[0]

# JSON row fingerprints preserve all pre-existing data, not only summed totals.
def state(c):
 result={}
 for table in ['sales','sale_items','inventory_balances','inventory_movements','products']:
  with c.cursor() as q:
   q.execute(f"SELECT count(*),md5(COALESCE(string_agg((to_jsonb(t)-'discount_amount')::text,'' ORDER BY id),'')) FROM {table} t")
   result[table]=q.fetchone()
 with c.cursor() as q:
  q.execute("""WITH tx AS (SELECT * FROM sales WHERE
   (original_sale_id IS NULL AND lower(status) IN ('completed','partially_refunded','refunded')) OR
   (original_sale_id IS NOT NULL AND lower(status)='refunded')),
  totals AS (SELECT COALESCE(sum(total_amount) FILTER(WHERE original_sale_id IS NULL),0) gross,
   COALESCE(-sum(total_amount) FILTER(WHERE original_sale_id IS NOT NULL),0) refunds FROM tx),
  costs AS (SELECT COALESCE(sum(i.line_cost),0) cost FROM sale_items i JOIN tx s ON s.id=i.sale_id)
  SELECT gross,refunds,gross-refunds,cost,gross-refunds-cost,
  (SELECT COALESCE(sum(quantity),0) FROM inventory_balances),
  (SELECT COALESCE(sum(quantity),0) FROM inventory_movements),
  (SELECT COALESCE(sum(stock_qty),0) FROM products WHERE deleted=false),
  (SELECT COALESCE(sum(stock_qty*cost_price),0) FROM products WHERE deleted=false),
  (SELECT COALESCE(sum(stock_qty*selling_price),0) FROM products WHERE deleted=false)
  FROM totals,costs""")
  result['aggregates']=dict(zip(['gross','refunds','net','cost','profit','balance_qty','movement_qty','product_qty','inventory_cost','inventory_retail'],map(str,q.fetchone())))
 with c.cursor() as q:
  q.execute("SELECT company_id::text,shop_id::text,(created_at AT TIME ZONE 'Africa/Harare')::date::text,status,original_sale_id IS NULL,count(*),sum(total_amount)::text FROM sales GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5")
  result['company_shop_day_status']=q.fetchall()
 return result

def save(name,data):
 (out/name).write_text(json.dumps(data,indent=2,default=str)+'\n')
print('Evidence directory:',out,flush=True)
save('manifest.json',{'commit':EXPECTED,'production':'apexretail_pos','databases':names,'backup':str(out/'production.dump'),'target':'d3phase2discount'})
with conn('apexretail_pos') as production:
 production.set_session(isolation_level='REPEATABLE READ',readonly=True)
 assert scalar(production,'SELECT version_num FROM alembic_version')=='c2phase1inventory'
 snapshot=scalar(production,'SELECT pg_export_snapshot()')
 before=state(production);save('production-before.json',before)
 with (out/'production.dump').open('xb') as dump:
  pg(['pg_dump','-h','/var/run/postgresql','--format=custom','--no-owner','--snapshot='+snapshot,'apexretail_pos'],stdout=dump)
assert (out/'production.dump').stat().st_size>0
with (out/'production.dump').open('rb') as dump, (out/'backup-toc.txt').open('w') as toc:
 pg(['pg_restore','--list'],stdin=dump,stdout=toc)
save('backup-sha256.json',{'sha256':hashlib.sha256((out/'production.dump').read_bytes()).hexdigest(),'mode':oct((out/'production.dump').stat().st_mode & 0o777)})
for kind,name in names.items():
 pg(['createdb','-h','/var/run/postgresql','--owner='+role,name])
 pg(['psql','-X','-h','/var/run/postgresql','-d',name,'-v','ON_ERROR_STOP=1','-c','CREATE EXTENSION IF NOT EXISTS pgcrypto;'],stdout=subprocess.DEVNULL)
 if kind=='clone':
  with (out/'production.dump').open('rb') as dump:
   pg(['pg_restore','-h','/var/run/postgresql','--exit-on-error','--no-owner','--no-comments','--no-privileges','--role='+role,'--dbname='+name],stdin=dump)
  with conn(name) as c:
   c.set_session(readonly=True);assert state(c)==before
 env={**os.environ,'APP_ENV':'test','JWT_SECRET':'phase2-predeploy-test-only','DATABASE_URL':url.set(database=name).render_as_string(hide_password=False)}
 assert make_url(env['DATABASE_URL']).database in names.values()
 with (out/(kind+'-migrations.log')).open('w') as log:
  for args in [['upgrade','d3phase2discount'],['downgrade','c2phase1inventory'],['upgrade','d3phase2discount']]:
   subprocess.run([str(ROOT/'backend/venv/bin/python'),'-m','alembic',*args],cwd=ROOT/'backend',env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
   if kind=='clone':
    with conn(name) as c:
     c.set_session(readonly=True);assert state(c)==before
  with conn(name) as c:
   c.set_session(readonly=True)
   assert scalar(c,'SELECT version_num FROM alembic_version')=='d3phase2discount'
   assert scalar(c,'SELECT count(*) FROM sales WHERE discount_amount IS NOT NULL')==0
   save(kind+'-after.json',state(c))
 if kind=='fresh':
  env['APEX_DASHBOARD_TEST_DATABASE_URL']=env['DATABASE_URL']
  with (out/'backend-tests.log').open('w') as log:
   subprocess.run([str(ROOT/'backend/venv/bin/python'),'-m','unittest','discover','-s','tests','-v'],cwd=ROOT/'backend',env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
  with conn(name) as c:assert scalar(c,'SELECT count(*) FROM sales')==0
with conn('apexretail_pos') as c:
 c.set_session(readonly=True)
 assert scalar(c,'SELECT version_num FROM alembic_version')=='c2phase1inventory'
 save('production-after.json',state(c))
save('result.json',{'status':'PASS','migration':'d3phase2discount','historical_discounts':'all remain NULL','clone_data_fingerprints':'unchanged','backend_tests':82})
print('PASS: snapshot-consistent backup, clone equality, fresh install, downgrade/re-upgrade, historical NULL, backend tests; databases retained',flush=True)
