"""Authorized preparation only: read-only production snapshot and NEW isolated clones.

No production migrations, ownership/grant changes, restores, application writes,
resets, service operations or arbitrary database arguments are supported.
Private backup/baseline files remain mode 0600 in a mode 0700 directory.
"""
import hashlib,json,os,subprocess,sys,tempfile,time
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
import psycopg2
from psycopg2 import sql
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT=Path(__file__).resolve().parents[1]
SOURCE='apexretail_pos'
START='p5h_runtime_write_permissions'
HEAD='p10a_platform_management'
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%S')
TARGETS=(f'apexretail_phase10_fresh_{STAMP}',f'apexretail_phase10_recovery_{STAMP}')
OUT=None

def connect(database,readonly=False,autocommit=False):
    if database not in (SOURCE,'postgres',*TARGETS):raise RuntimeError('Database is not allowlisted')
    if database==SOURCE and not readonly:raise RuntimeError('Production connections MUST be read-only')
    conn=psycopg2.connect(dbname=database,user='postgres',host='/var/run/postgresql',application_name='apexretail_phase10_release_preparation',
        options='-c lock_timeout=5000 -c statement_timeout=180000 -c timezone=UTC'+(' -c default_transaction_read_only=on' if readonly else ''))
    conn.autocommit=autocommit
    if readonly:conn.set_session(isolation_level='REPEATABLE READ',readonly=True)
    return conn

def one(conn,query,params=None):
    with conn.cursor() as cur:cur.execute(query,params);return cur.fetchone()[0]

def write(name,data):
    path=OUT/name
    with path.open('x') as f:json.dump(data,f,indent=2,default=str)
    path.chmod(0o600)

def snapshot(conn,columns=None):
    with conn.cursor() as cur:
        if columns is None:
            cur.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name<>'alembic_version' ORDER BY table_name,ordinal_position")
            columns={}
            for table,column in cur:columns.setdefault(table,[]).append(column)
        tables={};totals={}
        for table,names in columns.items():
            fields=sql.SQL(',').join(map(sql.Identifier,names))
            cur.execute(sql.SQL('SELECT row_to_json(t)::text FROM (SELECT {} FROM {}) t').format(fields,sql.Identifier(table)))
            canonical=sorted(json.dumps(json.loads(row[0],parse_float=Decimal),sort_keys=True,separators=(',',':'),default=lambda v:{'$decimal':str(v)}) for row in cur)
            tables[table]={'count':len(canonical),'sha256':hashlib.sha256('\n'.join(canonical).encode()).hexdigest()}
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND data_type IN ('smallint','integer','bigint','numeric','real','double precision') ORDER BY ordinal_position",(table,))
            numeric=[r[0] for r in cur if r[0] in names]
            if numeric:
                groups=[n for n in names if n=='company_id' or 'currency' in n and n.endswith(('code','currency'))]
                fields=[sql.Identifier(n) for n in groups]+[sql.SQL('sum({})::text AS {}').format(sql.Identifier(n),sql.Identifier(n)) for n in numeric]
                query=sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(fields),sql.Identifier(table))
                if groups:
                    group=sql.SQL(',').join(map(sql.Identifier,groups));query+=sql.SQL(' GROUP BY {} ORDER BY {}').format(group,group)
                cur.execute(query);totals[table]={'groups':groups,'numeric_columns':numeric,'rows':[[str(v) if v is not None else None for v in row] for row in cur]}
        cur.execute("SELECT relname,pg_get_userbyid(relowner),relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND relkind='r' ORDER BY relname")
        owners={r[0]:{'owner':r[1],'acl':r[2]} for r in cur if r[0] in columns}
    return {'columns':columns,'tables':tables,'numeric_control_totals':totals,'ownership':owners,
        'revision':one(conn,'SELECT version_num FROM alembic_version'),
        'enforcement_enabled':one(conn,'SELECT count(*) FROM company_settings WHERE shift_enforcement_enabled AND NOT deleted'),
        'open_shifts':one(conn,"SELECT count(*) FROM cashier_shifts WHERE status='open'"),
        'schema_create':one(conn,"SELECT has_schema_privilege('apex_user','public','CREATE')")}

def compare(before,after):
    for key in ('tables','numeric_control_totals','enforcement_enabled','open_shifts','schema_create'):
        if before[key]!=after[key]:raise RuntimeError('Preservation check failed: '+key)
    if any(before['ownership'][t]['owner']!=after['ownership'][t]['owner'] for t in before['columns']):raise RuntimeError('Historical table ownership changed')

def assert_clone(database):
    if database not in TARGETS or database==SOURCE:raise RuntimeError('Non-disposable migration refused')
    with connect(database,readonly=True) as conn:
        if one(conn,'SELECT current_database()')!=database:raise RuntimeError('Identity mismatch')
        if one(conn,"SELECT count(*) FROM pg_roles WHERE rolcanlogin AND NOT rolsuper AND has_database_privilege(oid,current_database(),'CONNECT')"):
            raise RuntimeError('A non-superuser login can access the clone')

def create_and_restore(database,dump):
    if database not in TARGETS:raise RuntimeError('Non-disposable restore refused')
    conn=connect('postgres',autocommit=True)
    try:
        if one(conn,'SELECT count(*) FROM pg_database WHERE datname=%s',(database,)):raise RuntimeError('Existing database will NOT be overwritten')
        with conn.cursor() as cur:
            cur.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(database)))
            cur.execute(sql.SQL('REVOKE CONNECT,TEMPORARY ON DATABASE {} FROM PUBLIC,apex_user').format(sql.Identifier(database)))
    finally:conn.close()
    assert_clone(database)
    result=subprocess.run(['pg_restore','--exit-on-error','--single-transaction','-h','/var/run/postgresql','-U','postgres','-d',database,str(dump)],capture_output=True,text=True)
    write(database+'-restore.json',{'exit_code':result.returncode,'stderr':result.stderr})
    if result.returncode:raise RuntimeError('Isolated restore failed; see protected restore evidence')
    assert_clone(database)

def migrate(database,direction,target,before,steps):
    assert_clone(database)
    allowed={r.revision for r in GRAPH}|{START}
    if target not in allowed or direction not in ('upgrade','downgrade'):raise RuntimeError('Unapproved migration target')
    env=dict(os.environ,DATABASE_URL=f'postgresql+asyncpg://postgres@/{database}?host=/var/run/postgresql',JWT_SECRET='disposable-phase10-rehearsal-only')
    started=time.monotonic()
    result=subprocess.run([sys.executable,'-m','alembic',direction,target],cwd=ROOT,env=env,capture_output=True,text=True)
    write(f'{database}-{len(steps):02d}-{direction}-{target}.json',{'exit_code':result.returncode,'stderr':result.stderr,'seconds':time.monotonic()-started})
    if result.returncode:raise RuntimeError('Disposable migration failed; production unchanged')
    with connect(database,readonly=True) as conn:after=snapshot(conn,before['columns'])
    compare(before,after)
    if after['revision']!=target:raise RuntimeError('Migration ended at unexpected revision')
    steps.append({'database':database,'direction':direction,'revision':target,'seconds':round(time.monotonic()-started,3),'historical_data_unchanged':True})
    write(f'{database}-{len(steps):02d}-preservation.json',after)
    print(f'PASS {database} {direction} {target}; historical hashes/totals preserved',flush=True)

def main():
    global OUT,GRAPH
    if sys.argv[1:]!=['--backup-and-rehearse']:raise SystemExit('Explicit --backup-and-rehearse required')
    if os.geteuid()!=one_uid():raise SystemExit('Run as authorized postgres OS account')
    os.umask(0o077)
    OUT=Path(tempfile.mkdtemp(prefix='apexretail-phase10-preparation-'))
    print('Protected preparation directory: '+str(OUT),flush=True)
    cfg=Config(str(ROOT/'alembic.ini'));cfg.set_main_option('script_location',str(ROOT/'migrations'))
    script=ScriptDirectory.from_config(cfg)
    if script.get_heads()!=[HEAD]:raise RuntimeError('Migration graph has unexpected heads')
    GRAPH=list(reversed(list(script.iterate_revisions(HEAD,START))))
    if len(GRAPH)!=14:raise RuntimeError('Pending migration chain changed; review required')
    dump=OUT/'apexretail_pos.dump'
    with connect(SOURCE,readonly=True) as conn:
        if one(conn,'SHOW transaction_read_only')!='on':raise RuntimeError('Production session is not read-only')
        before=snapshot(conn)
        if before['revision']!=START or before['enforcement_enabled']:raise RuntimeError('Production baseline safety gate failed')
        exported=one(conn,'SELECT pg_export_snapshot()')
        env=dict(os.environ,PGOPTIONS='-c default_transaction_read_only=on -c lock_timeout=5000')
        result=subprocess.run(['pg_dump','-h','/var/run/postgresql','-U','postgres','--format=custom','--lock-wait-timeout=5s','--snapshot='+exported,'--file='+str(dump),SOURCE],env=env,capture_output=True,text=True)
        write('backup-command.json',{'exit_code':result.returncode,'stderr':result.stderr,'snapshot_shared_with_baseline':True,'production_read_only':True})
        if result.returncode:raise RuntimeError('Read-only backup failed')
    digest=hashlib.sha256(dump.read_bytes()).hexdigest()
    subprocess.run(['pg_restore','--list',str(dump)],check=True,stdout=subprocess.DEVNULL)
    write('snapshot-baseline.json',before)
    steps=[]
    for database in TARGETS:
        create_and_restore(database,dump)
        with connect(database,readonly=True) as conn:restored=snapshot(conn,before['columns'])
        compare(before,restored)
        if database==TARGETS[0]:
            for revision in GRAPH:migrate(database,'upgrade',revision.revision,before,steps)
        else:
            for direction,target in [('upgrade',HEAD),('downgrade',START),('upgrade',HEAD)]:migrate(database,direction,target,before,steps)
    summary={'source':SOURCE,'source_revision':START,'target_revision':HEAD,'pending_migrations':[r.revision for r in GRAPH],
        'backup':str(dump),'backup_sha256':digest,'backup_bytes':dump.stat().st_size,'snapshot_consistent':True,'restored_clones':list(TARGETS),
        'historical_tables':len(before['tables']),'historical_rows':sum(t['count'] for t in before['tables'].values()),'open_shifts_preserved':before['open_shifts'],
        'historical_hashes_totals_owners_unchanged':True,'enforcement_enabled':before['enforcement_enabled'],'schema_create_unchanged':True,
        'production_writes':False,'steps':steps,'backup_scope':'single database; roles, server configuration and external credentials require separate protected recovery material'}
    write('summary.json',summary)
    print(json.dumps(summary,indent=2),flush=True)

def one_uid():
    import pwd
    return pwd.getpwnam('postgres').pw_uid

if __name__=='__main__':main()
