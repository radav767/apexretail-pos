"""Hash-pinned worker, invoked by the root runner as postgres on the local socket."""
import json,sys
from pathlib import Path
import psycopg2

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
from prepare_phase10_release import snapshot

database=sys.argv[1]
if database!='apexretail_pos' and not database.startswith('apexretail_phase10_'):raise SystemExit('Unapproved database')
columns=json.loads(sys.stdin.read())
conn=psycopg2.connect(dbname=database,user='postgres',host='/var/run/postgresql',
    application_name='apexretail_phase10_guarded_owner',options='-c default_transaction_read_only=on -c lock_timeout=5000 -c timezone=UTC')
try:
    conn.set_session(isolation_level='REPEATABLE READ',readonly=True)
    with conn.cursor() as c:
        c.execute('SELECT current_database(),current_user');identity=c.fetchone()
        if identity!=(database,'postgres'):raise RuntimeError('Owner connection identity mismatch')
        c.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()")
        if c.fetchone()[0]!='postgres':raise RuntimeError('Database owner mismatch')
        c.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'")
        if c.fetchone()[0]!='postgres':raise RuntimeError('Schema owner mismatch')
        c.execute("SELECT has_database_privilege('apex_user',current_database(),'CONNECT')")
        connect=c.fetchone()[0]
        c.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend'")
        sessions=c.fetchone()[0]
    result=snapshot(conn,columns)
    print(json.dumps({'snapshot':result,'app_connect':connect,'other_sessions':sessions},default=str))
finally:conn.close()
