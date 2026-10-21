"""Reuse existing disposable Phase 7E databases. No database creation or live access."""
import json,os,subprocess,sys
from pathlib import Path
from verify_phase8_migration import CLONE,TESTS,ROOT,query,historical

def migrate(database,target):
    if database not in [CLONE,*TESTS] or target not in ('p9b_fiscal_protocol','p10a_platform_management'):raise RuntimeError('Unapproved target')
    if query(database,'SELECT current_database()')!=database:raise RuntimeError('Wrong database')
    if database==CLONE and query(database,"SELECT has_database_privilege('apex_user',current_database(),'CONNECT')")!='f':raise RuntimeError('Clone must remain isolated')
    env=dict(os.environ,JWT_SECRET='disposable-phase10-only',DATABASE_URL=f'postgresql+asyncpg://postgres@/{database}?host=/var/run/postgresql')
    subprocess.run([sys.executable,'-m','alembic','downgrade' if target=='p9b_fiscal_protocol' else 'upgrade',target],cwd=ROOT,env=env,check=True)

def main():
    results={'production_accessed':False,'created_databases':False,'clone':CLONE,'before':historical(),'steps':[]}
    for target in ('p10a_platform_management','p9b_fiscal_protocol','p10a_platform_management'):
        migrate(CLONE,target);results['steps'].append({'revision':query(CLONE,'SELECT version_num FROM alembic_version'),'historical':historical()})
    for database in TESTS:migrate(database,'p10a_platform_management')
    Path('/tmp/phase10-migration-results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
if __name__=='__main__':main()
