"""Uninstalled Phase11 owner-only migration guard; no service/config/data restore actions.

Production execution requires protected, hash-bound evidence and actual writer fence.
Rehearsal is restricted to a private Unix socket and synthetic database prefix.
"""
import argparse,fcntl,hashlib,json,os,re,stat,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
import psycopg2
from alembic.config import Config
from alembic.script import ScriptDirectory
from snapshot import capture,compare,PreservationError
START='p10a_platform_management';HEAD='p11ac_quote_refund_evidence'
class GateError(RuntimeError):pass

def need(condition,message):
    if not condition:raise GateError(message)

def protected(path,private=False):
    path=Path(path);info=path.lstat()
    need(not path.is_symlink() and info.st_uid==0 and not info.st_mode&0o022,'Unprotected path')
    if private:need(not info.st_mode&0o077,'Private root-only evidence required')
    for parent in path.absolute().parents:
        info=parent.lstat()
        if parent==Path('/tmp') and info.st_uid==0 and info.st_mode&stat.S_ISVTX:continue
        need(not parent.is_symlink() and info.st_uid==0 and not info.st_mode&0o022,'Unprotected ancestor')

def load(path,digest=None):
    protected(path,True);raw=Path(path).read_bytes()
    need(len(raw)<=8*1024*1024,'Evidence resource bound exceeded')
    if digest:need(hashlib.sha256(raw).hexdigest()==digest,'Evidence hash mismatch')
    return json.loads(raw)

def check_clearance(plan,clearance,production,now=None):
    now=now or datetime.now(timezone.utc);expires=datetime.fromisoformat(clearance['expires_at'])
    need(expires.tzinfo is not None and now<expires<=now+timedelta(minutes=15),'Bounded unexpired clearance required')
    need(bool(re.fullmatch('[a-f0-9]{40}',plan['commit'])),'Exact source commit required')
    for field in ['commit','database','manifest_sha256']:
        need(clearance.get(field)==plan.get(field),'Clearance binding mismatch')
    need(clearance.get('sales_paused') is True,'Genuine write-pause clearance required')
    need(type(clearance.get('open_shifts')) is int and clearance['open_shifts']>=0,'Explicit open-shift count required')
    need(clearance.get('queue_policy')=='retain-and-replay-original-context-v1','Retained original-queue protocol required')
    need(bool(re.fullmatch('[a-f0-9]{64}',str(clearance.get('device_queue_inventory_sha256','')))),'Device/queue inventory binding required')
    need(clearance.get('revocations_must_survive') is True,'Revocation preservation required')
    need(clearance.get('synthetic') is (not production),'Synthetic evidence is forbidden in production')

def payload(plan):
    root=Path(plan['payload']);protected(root)
    manifest=root/'PAYLOAD.sha256';protected(manifest)
    need(hashlib.sha256(manifest.read_bytes()).hexdigest()==plan['manifest_sha256'],'Pinned manifest mismatch')
    expected=set()
    for line in manifest.read_text().splitlines():
        digest,name=line.split('  ',1);rel=Path(name)
        need(not rel.is_absolute() and '..' not in rel.parts and name not in expected,'Unsafe/duplicate payload path')
        need(bool(re.fullmatch('[a-f0-9]{64}',digest)),'Invalid payload hash')
        p=root/rel;protected(p);need(p.is_file(),'Regular payload file required')
        need(hashlib.sha256(p.read_bytes()).hexdigest()==digest,'Payload content changed');expected.add(name)
    need(not any(p.is_symlink() for p in root.rglob('*')),'Payload symlinks forbidden')
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p!=manifest}
    need(actual==expected,'Unexpected/missing payload files')
    # The runner, snapshot implementation and migration interpreter are externally pinned.
    for field in ['runner','snapshot','python']:
        p=Path(plan[field]);protected(p)
        need(hashlib.sha256(p.read_bytes()).hexdigest()==plan[field+'_sha256'],'Pinned executable mismatch')
    need(Path(plan['runner']).resolve()==Path(__file__).resolve(),'Wrong runner identity')
    need(Path(plan['snapshot']).resolve()==Path(__file__).with_name('snapshot.py').resolve(),'Wrong snapshot identity')
    return root

def recovery(plan):
    proof=load(plan['recovery_review'],plan['recovery_review_sha256'])
    need(proof.get('commit')==plan['commit'] and proof.get('database')==plan['database'],'Recovery release binding mismatch')
    for field in ['custody_verified','offhost_readback_verified','independent_restore_verified','config_media_recovery_verified','reviewed']:
        need(proof.get(field) is True,'Genuine reviewed recovery evidence required')
    need(proof.get('synthetic') is False,'Synthetic restore cannot authorize production')
    # Review attestation must bind actual immutable receipts; it is not created here.
    for name in ['custody','offhost','restore','config_media']:
        load(proof[name+'_receipt'],proof[name+'_sha256'])

def write_private(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2,default=str);f.flush();os.fsync(f.fileno())

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--clearance',required=True);p.add_argument('--output',required=True);p.add_argument('--rehearse',action='store_true');p.add_argument('--interrupt-after',type=int);a=p.parse_args()
    need(os.geteuid()==0,'Protected owner runner requires root')
    plan=load(a.plan,a.plan_sha256);production=not a.rehearse
    need(plan['start']==START and plan['head']==HEAD,'Unexpected release revisions')
    check_clearance(plan,load(a.clearance),production)
    root=payload(plan);out=Path(a.output);protected(out,True);need(out.is_dir(),'Private output directory required')
    if production:
        need(plan['database']=='apexretail_pos' and plan['socket']=='/var/run/postgresql' and plan['port']==5432,'Wrong production connection')
        need(a.interrupt_after is None,'Fault injection forbidden in production');recovery(plan)
        for unit in ['apexpos.service','apexpos-health.timer','apexpos-health.service']:
            r=subprocess.run(['/usr/bin/systemctl','is-active',unit],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
            need(r.returncode in (3,4) and r.stdout.strip() in ('inactive','failed','unknown'),'Production writers/watchdog must be stopped through approved workflow')
        lock=Path('/run/lock/apexpos-production-deploy.lock')
    else:
        need(plan['database'].startswith('apex_phase11_release_') and plan['socket'].startswith('/tmp/apex-phase11-release-pg-') and plan['port']==55443,'Only isolated synthetic database allowed')
        lock=out/'rehearsal.lock'
    fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600);protected(lock,True)
    with os.fdopen(fd,'a') as lockfile:
        fcntl.flock(lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
        conn=psycopg2.connect(dbname=plan['database'],user='postgres',host=plan['socket'],port=plan['port'],application_name='phase11_protected_owner',options='-c default_transaction_read_only=on -c statement_timeout=180000 -c lock_timeout=5000 -c timezone=UTC')
        try:
            conn.set_session(readonly=True,isolation_level='REPEATABLE READ')
            with conn.cursor() as c:
                c.execute('SELECT current_database(),current_user');need(c.fetchone()==(plan['database'],'postgres'),'Owner database identity mismatch')
                c.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()");need(c.fetchone()[0]=='postgres','Unexpected database owner')
                c.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'");need(c.fetchone()[0]=='postgres','Unexpected schema owner')
                c.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend'");need(c.fetchone()[0]==0,'Other database writers/connections present')
                c.execute('SELECT pg_try_advisory_lock(1100110011)');need(c.fetchone()[0],'Another migration owns database lock')
            before=capture(conn)
            need(before['app_role'] is not None and before['app_role']['connect'] is False and before['app_role']['schema_create'] is False,'App connection/DDL fence required')
            need(before['open_shifts']==load(a.clearance)['open_shifts'],'Open-shift inventory changed')
            write_private(out/'before.json',before);conn.rollback()
            cfg=Config(str(root/'backend/alembic.ini'));cfg.set_main_option('script_location',str(root/'backend/migrations'));graph=ScriptDirectory.from_config(cfg)
            ordered=list(reversed(list(graph.iterate_revisions(HEAD,START))));ids=[r.revision for r in ordered]
            need(before['revision'] in [START,*ids],'Unknown starting/interrupted revision')
            # Capture current data at each attempt; never overwrite newer rows with old baseline.
            start=0 if before['revision']==START else ids.index(before['revision'])+1
            need(plan['ordered_revisions']==ids,'Pinned migration sequence changed')
            env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1','APP_ENV':'test' if a.rehearse else 'production','JWT_SECRET':'isolated-migration-import-only-secret-not-runtime-credentials','DATABASE_URL':f'postgresql+asyncpg://postgres@/{plan["database"]}?host={plan["socket"]}&port={plan["port"]}'}
            completed=[]
            for i,revision in enumerate(ids[start:]):
                current_clearance=load(a.clearance);check_clearance(plan,current_clearance,production)
                remaining=(datetime.fromisoformat(current_clearance['expires_at'])-datetime.now(timezone.utc)).total_seconds()
                need(remaining>1,'Clearance too close to expiry for another migration')
                # Capture table/column scope from this attempt, preserving all current revocations.
                with (out/f'{i:02d}-migration.log').open('x') as log:
                    os.chmod(log.name,0o600)
                    command=[plan['python'],'-m','alembic','upgrade',revision]
                    if production:command=['/usr/sbin/runuser','-u','postgres','--','/usr/bin/env','-i',*[f'{k}={v}' for k,v in env.items()],*command]
                    result=subprocess.run(command,cwd=root/'backend',env=env,stdout=log,stderr=subprocess.STDOUT,timeout=min(180,remaining))
                need(result.returncode==0,'Migration failed; preserve state and resume forward only')
                conn.rollback();after=capture(conn,before['columns']);compare(before,after);need(after['revision']==revision,'Revision mismatch');conn.rollback()
                completed.append(revision);write_private(out/f'{i:02d}-preserved.json',{'revision':revision,'preserved':True})
                if a.interrupt_after is not None and len(completed)==a.interrupt_after:
                    write_private(out/'interrupted.json',{'completed':completed,'schema':revision,'downgrade_allowed':False});return 75
            after=capture(conn,before['columns']);compare(before,after);need(after['revision']==HEAD,'Final head mismatch')
            write_private(out/'complete.json',{'commit':plan['commit'],'head':HEAD,'completed':completed,'preserved':True,'deployment_performed':False})
            print('Guarded migrations/preservation passed; no application switch or data restore performed')
        finally:conn.rollback();conn.close()
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        detail=str(exc) if isinstance(exc,(GateError,PreservationError)) else type(exc).__name__
        print('BLOCKED: '+detail+'; inspect private evidence; no downgrade/restore performed',file=sys.stderr);raise SystemExit(1)
