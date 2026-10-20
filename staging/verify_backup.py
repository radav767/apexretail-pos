"""Back up and restore only the separate staging cluster, without resetting data."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import psycopg2

ROOT=Path('/tmp/apexretail-phase7f-runtime')
PG='/usr/lib/postgresql/14/bin/'
DATABASE='apexretail_phase7f_acceptance'
COMMON=['-h',str(ROOT/'socket'),'-p','55437']

def query(database,sql):
    return subprocess.check_output([PG+'psql','-X','-At','-v','ON_ERROR_STOP=1',*COMMON,'-d',database,'-c',sql],text=True).strip()

def fingerprint(connection):
    cursor=connection.cursor()
    cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    tables=[row[0] for row in cursor.fetchall()]
    result={}
    for table in tables:
        quoted='"'+table.replace('"','""')+'"'
        cursor.execute(f"SELECT json_build_object('count',count(*),'content_md5',md5(COALESCE(string_agg(row_to_json(t)::text, E'\\n' ORDER BY row_to_json(t)::text),''))) FROM {quoted} t")
        result[table]=cursor.fetchone()[0]
    cursor.close()
    return result

def main():
    identity=query(DATABASE,"SELECT current_database()||':'||current_setting('data_directory')")
    if identity!=DATABASE+':'+str(ROOT/'postgres'):raise RuntimeError('Wrong cluster')
    timestamp=datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    folder=ROOT/'backups';folder.mkdir(mode=0o700,exist_ok=True)
    backup=folder/f'phase7f-{timestamp}.dump';restore='apexretail_phase7f_restore_'+timestamp
    connection=psycopg2.connect(dbname=DATABASE,host=str(ROOT/'socket'),port=55437)
    connection.set_session(isolation_level='REPEATABLE READ',readonly=True)
    cursor=connection.cursor();cursor.execute('SELECT pg_export_snapshot()');snapshot=cursor.fetchone()[0];cursor.close()
    before=fingerprint(connection)
    subprocess.run([PG+'pg_dump',*COMMON,'--format=custom','--snapshot',snapshot,'--file',str(backup),DATABASE],check=True)
    connection.rollback();connection.close()
    subprocess.run([PG+'pg_restore','--list',str(backup)],check=True,stdout=subprocess.DEVNULL)
    subprocess.run([PG+'createdb',*COMMON,restore],check=True)
    subprocess.run([PG+'pg_restore',*COMMON,'--exit-on-error','--dbname',restore,str(backup)],check=True)
    with psycopg2.connect(dbname=restore,host=str(ROOT/'socket'),port=55437) as restored:
        after=fingerprint(restored)
    if before!=after:raise RuntimeError('Restored staging content differs')
    result={'database':DATABASE,'backup':str(backup),'sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),
        'restore_database':restore,'tables':len(before),'rows':sum(v['count'] for v in before.values()),'content_preserved':True,
        'fingerprints':before,'production_backup':False}
    (ROOT/'backup-verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='fingerprints'}))

if __name__=='__main__':main()
