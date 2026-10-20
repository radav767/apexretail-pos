"""Additive migration on EXISTING allowlisted disposable databases only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from prepare_phase7d_tests import DATABASES

ROOT=Path(__file__).resolve().parents[1]
CLONE='apexretail_phase7e_stabilization_clone_20261020'
TESTS=[name.replace('phase7d','phase7e') for name in DATABASES]
def query(database,sql):return subprocess.check_output(['psql','-X','-At','-v','ON_ERROR_STOP=1','-d',database,'-c',sql],text=True).strip()
def migrate(database,target):
    if database not in [*TESTS,CLONE]:raise RuntimeError('Non-disposable database refused')
    if query(database,'SELECT current_database()')!=database:raise RuntimeError('Wrong identity')
    env=dict(os.environ,JWT_SECRET='disposable-phase8-only',DATABASE_URL=f'postgresql+asyncpg://postgres@/{database}?host=/var/run/postgresql')
    direction='downgrade' if target=='p7j_variant_batches' else 'upgrade'
    subprocess.run([sys.executable,'-m','alembic',direction,target],cwd=ROOT,env=env,check=True)
def historical():
    baseline=json.loads(Path('/tmp/'+CLONE+'-rehearsal.json').read_text())['baseline']
    for table,columns in baseline['columns'].items():
        quote=lambda n:'"'+n.replace('"','""')+'"'
        raw=query(CLONE,f"SELECT row_to_json(t)::text FROM (SELECT {','.join(map(quote,columns))} FROM {quote(table)}) t")
        rows=[json.dumps(json.loads(line),sort_keys=True,separators=(',',':')) for line in raw.splitlines()]
        actual={'count':len(rows),'sha256':hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()}
        if actual!=baseline['tables'][table]:raise RuntimeError('Historical data changed: '+table)
    return {'tables':len(baseline['tables']),'rows':sum(r['count'] for r in baseline['tables'].values()),'hashes_unchanged':True}
def main():
    result={'production_accessed':False,'created_databases':False,'clone':CLONE,'before':historical(),'steps':[]}
    for target in ('p8a_commercial_billing','p7j_variant_batches','p8a_commercial_billing'):
        migrate(CLONE,target);result['steps'].append({'revision':query(CLONE,'SELECT version_num FROM alembic_version'),'historical':historical()})
    if query(CLONE,"SELECT has_database_privilege('apex_user',current_database(),'CONNECT')")!='f':raise RuntimeError('Restored clone must remain application-inaccessible')
    for database in TESTS:migrate(database,'p8a_commercial_billing')
    Path('/tmp/phase8-migration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
