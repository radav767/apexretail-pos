"""Bounded synthetic-only driver; all connections use a new private socket."""
import json,os,subprocess,sys,hashlib
from pathlib import Path
root=Path('/tmp/apex-phase11-independent-release-5lrb0b7l');pg=json.loads((root/'postgres.json').read_text());assert pg['port']==55443 and pg['root'].startswith('/tmp/apex-phase11-release-pg-')
script=Path(__file__).with_name('isolated_rehearsal.py').resolve();py=str(root/'venv/bin/python');out=root/'rehearsal';out.mkdir(exist_ok=True)
env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','APP_ENV':'test','JWT_SECRET':'synthetic-independent-release-secret-not-production-20261127'}
results=[]
def run(name,args,cwd=None,extra=None):
 with (out/(name+'.log')).open('w') as f:r=subprocess.run(args,cwd=cwd,env={**env,**(extra or {})},stdout=f,stderr=subprocess.STDOUT)
 results.append({'step':name,'exit':r.returncode});(out/'results.json').write_text(json.dumps(results,indent=2));assert r.returncode==0,name
 print(name+': pass',flush=True)
def snapshot(name,db,action='snapshot',baseline=None):
 args=[py,str(script),action,'--root',str(root),'--database',db]
 if baseline:args+=['--baseline',str(out/(baseline+'.log'))]
 run(name,args)
def migrate(name,db):
 run(name,[py,'-m','alembic','upgrade','head'],cwd=root/'source/backend',extra={'DATABASE_URL':f'postgresql+asyncpg://postgres@/{db}?host={pg["root"]}&port={pg["port"]}'})
db='apex_phase11_release_upgrade'
snapshot('before-upgrade',db);migrate('populated-upgrade',db);snapshot('original-columns-after-upgrade',db,'compare','before-upgrade');snapshot('before-backup',db)
run('dump',['/usr/lib/postgresql/14/bin/pg_dump','-h',pg['root'],'-p','55443','-U','postgres','-Fc','-f',str(out/'synthetic.dump'),db])
run('independent-restore',['/usr/lib/postgresql/14/bin/pg_restore','-h',pg['root'],'-p','55443','-U','postgres','--exit-on-error','--no-owner','-d','apex_phase11_release_restore',str(out/'synthetic.dump')])
snapshot('restore-compare','apex_phase11_release_restore','compare','before-backup')
run('newer-sale-revocation',[py,str(script),'newer','--root',str(root),'--database',db]);snapshot('newer-before-forward',db);migrate('compatible-head-forward',db);snapshot('newer-after-forward',db,'compare','newer-before-forward')
migrate('test-db-head','apexretail_phase7c_test_phase7e');migrate('shell-db-head','apex_phase11_release_shell')
print('Synthetic DB preservation only; not off-host recovery or interrupted deployment acceptance.')
