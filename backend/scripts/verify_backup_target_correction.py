"""One-purpose backup/restore check. Never writes to the production database.

Run as postgres. Restores only into a newly created, application-inaccessible
database. Never invokes the old backup script or its retention command.
"""
import hashlib,json,os,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
import psycopg2
from psycopg2 import sql
from prepare_phase10_release import snapshot

SOURCE='apexretail_pos'

def connect(database,readonly=False,autocommit=False):
    if database not in (SOURCE,'postgres',TARGET):raise RuntimeError('Unapproved target')
    if database==SOURCE and not readonly:raise RuntimeError('Production writes forbidden')
    c=psycopg2.connect(dbname=database,user='postgres',host='/var/run/postgresql',application_name='backup_target_verification',
        options='-c timezone=UTC -c lock_timeout=5000 -c statement_timeout=180000'+(' -c default_transaction_read_only=on' if readonly else ''))
    c.autocommit=autocommit
    if readonly:c.set_session(isolation_level='REPEATABLE READ',readonly=True)
    return c

def compare(a,b):
    for key in ('tables','numeric_control_totals','ownership','revision','enforcement_enabled','open_shifts','schema_create'):
        if a[key]!=b[key]:raise RuntimeError('Preservation check failed: '+key)

def assert_isolated():
    with connect(TARGET,readonly=True) as c:
        with c.cursor() as cur:
            cur.execute("SELECT count(*) FROM pg_roles WHERE rolcanlogin AND NOT rolsuper AND has_database_privilege(oid,current_database(),'CONNECT')")
            if cur.fetchone()[0]:raise RuntimeError('Application can access clone')

def main():
    global TARGET
    if sys.argv[1:] not in (['--before-custom'],['--after-plain']):raise SystemExit('Select a verification stage')
    if os.geteuid()!=__import__('pwd').getpwnam('postgres').pw_uid:raise RuntimeError('Run as postgres')
    os.umask(0o077)
    stage=sys.argv[1][2:];stamp=datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%S%f')
    TARGET='apexretail_backup_target_'+stage.split('-')[0]+'_'+stamp
    out=Path(tempfile.mkdtemp(prefix='apexretail-backup-target-'+stage+'-'))
    print('Private verification directory: '+str(out),flush=True)
    dump=out/('apexretail_pos.dump' if stage=='before-custom' else 'apexretail_pos.sql')
    with connect(SOURCE,readonly=True) as c:
        before=snapshot(c)
        if before['revision']!='p5h_runtime_write_permissions':raise RuntimeError('Unexpected production revision')
        with c.cursor() as cur:
            cur.execute('SHOW transaction_read_only')
            if cur.fetchone()[0]!='on':raise RuntimeError('Production is not read-only')
            cur.execute('SELECT pg_export_snapshot()');export=cur.fetchone()[0]
        command=['pg_dump',SOURCE,'--snapshot='+export]
        if stage=='before-custom':command+=['--format=custom']
        with dump.open('xb') as f:
            result=subprocess.run(command,stdout=f,stderr=subprocess.PIPE,env=dict(os.environ,PGOPTIONS='-c default_transaction_read_only=on -c lock_timeout=5000'))
        (out/'dump-stderr.log').write_bytes(result.stderr)
        if result.returncode:raise RuntimeError('Backup failed')
    (out/'baseline.json').write_text(json.dumps(before,indent=2))
    if stage=='before-custom':subprocess.run(['pg_restore','--list',str(dump)],check=True,stdout=subprocess.DEVNULL)
    else:
        text=dump.read_text()
        if not text.startswith('--\n-- PostgreSQL database dump') or '-- PostgreSQL database dump complete' not in text:raise RuntimeError('Incomplete SQL dump')
    c=connect('postgres',autocommit=True)
    try:
        with c.cursor() as cur:
            cur.execute('SELECT 1 FROM pg_database WHERE datname=%s',(TARGET,))
            if cur.fetchone():raise RuntimeError('Existing database will never be overwritten')
            cur.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(TARGET)))
            cur.execute(sql.SQL('REVOKE CONNECT,TEMPORARY ON DATABASE {} FROM PUBLIC,apex_user').format(sql.Identifier(TARGET)))
    finally:c.close()
    assert_isolated()
    command=(['pg_restore','--exit-on-error','--single-transaction','-d',TARGET,str(dump)] if stage=='before-custom'
             else ['psql','-X','-v','ON_ERROR_STOP=1','--single-transaction','-d',TARGET,'-f',str(dump)])
    with (out/'restore-stdout.log').open('xb') as stdout,(out/'restore-stderr.log').open('xb') as stderr:
        result=subprocess.run(command,stdout=stdout,stderr=stderr)
    if result.returncode:raise RuntimeError('Isolated restore failed; evidence retained')
    assert_isolated()
    with connect(TARGET,readonly=True) as c:restored=snapshot(c,before['columns'])
    compare(before,restored)
    with connect(SOURCE,readonly=True) as c:current=snapshot(c,before['columns'])
    compare(before,current)
    summary={'stage':stage,'source':SOURCE,'source_read_only':True,'clone':TARGET,'clone_application_access':False,
        'revision':before['revision'],'backup':str(dump),'bytes':dump.stat().st_size,
        'sha256':hashlib.sha256(dump.read_bytes()).hexdigest(),'full_restore_passed':True,
        'historical_hashes_totals_ownership_unchanged':True,'source_unchanged_during_check':True,
        'tables':len(before['tables']),'rows':sum(t['count'] for t in before['tables'].values()),
        'open_shifts_preserved':before['open_shifts'],'enforcement_enabled':before['enforcement_enabled'],
        'production_mutations':False,'retention_command_invoked':False}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
