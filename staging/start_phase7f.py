"""Publish staging builds and start loopback-only services, never production."""
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = Path('/tmp/apexretail-phase7f-runtime')
SOURCE = Path(__file__).resolve().parents[1]
PYTHON = '/tmp/apexretail-phase7b-venv/bin/python'
ACCOUNT = 'apexstage7f'

def main():
    if os.geteuid() != 0 or str(SOURCE) != '/tmp/apexpos-phase7f':
        raise SystemExit('Approved root execution from staging worktree required')
    user = pwd.getpwnam(ACCOUNT)
    data = json.loads((ROOT/'runtime.json').read_text())
    if data['environment'] != 'phase7f-staging' or data['database'] != 'apexretail_phase7f_acceptance' or ROOT.stat().st_uid != user.pw_uid:
        raise SystemExit('Unexpected staging identity')
    if sys.argv[1:]==['--refresh-api-identity']:
        if subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip():
            raise SystemExit('Commit verified sources before refreshing staging identity')
        candidates=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                arguments=(proc/'cmdline').read_bytes().split(b'\0')
                if proc.stat().st_uid==user.pw_uid and b'phase7f_runtime:api_app' in arguments and b'18771' in arguments:
                    candidates.append(int(proc.name))
            except (FileNotFoundError,PermissionError,ProcessLookupError):continue
        if len(candidates)!=1:raise SystemExit('Expected exactly one dedicated staging API process')
        data['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
        temporary=ROOT/'runtime.json.new';temporary.write_text(json.dumps(data,indent=2));temporary.chmod(0o600)
        os.chown(temporary,user.pw_uid,user.pw_gid);os.replace(temporary,ROOT/'runtime.json')
        os.kill(candidates[0],signal.SIGTERM)
        for attempt in range(100):
            try:os.kill(candidates[0],0)
            except ProcessLookupError:break
            time.sleep(.1)
        else:raise SystemExit('Staging API did not stop; no other process will be touched')
        with (ROOT/'logs/api.log').open('ab') as log:
            process=subprocess.Popen(['/usr/sbin/runuser','-u',ACCOUNT,'--',PYTHON,'-m','uvicorn','phase7f_runtime:api_app','--factory','--host','127.0.0.1','--port','18771'],
                cwd=ROOT,env={'PATH':'/usr/bin:/bin','PYTHONPATH':f'{SOURCE}/backend:{SOURCE}/staging'},stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (ROOT/'api.pid').write_text(str(process.pid)+'\n')
        print('Restarted only the dedicated staging API with clean source identity');return
    if sys.argv[1:] in (['--refresh-backoffice'],['--refresh-pos']):
        project='backoffice' if sys.argv[1:]==['--refresh-backoffice'] else 'pos-web'
        name='backoffice' if project=='backoffice' else 'pos'
        source=SOURCE/project/'dist';target=ROOT/'web'/name
        if not target.is_dir() or not (source/'index.html').is_file():raise SystemExit('Missing staging build')
        for path in sorted(source.rglob('*'),key=lambda p:p.name=='index.html'):
            if not path.is_file():continue
            destination=target/path.relative_to(source);destination.parent.mkdir(parents=True,exist_ok=True)
            temporary=destination.with_name(destination.name+'.stage7f')
            shutil.copyfile(path,temporary);os.chown(temporary,user.pw_uid,user.pw_gid);os.replace(temporary,destination)
        print(f'Refreshed staging {name} assets only, index last');return
    for port in (18770,18771):
        with socket.socket() as check:
            check.bind(('127.0.0.1',port))
    for project, name in [('pos-web','pos'),('backoffice','backoffice')]:
        source = SOURCE/project/'dist'
        target = ROOT/'web'/name
        if not (source/'index.html').is_file() or target.exists():
            raise SystemExit('Missing tested build or staging assets already published; inspect rather than overwrite')
        shutil.copytree(source,target)
        for path in [target,*target.rglob('*')]:
            os.chown(path,user.pw_uid,user.pw_gid)
    env={'PATH':'/usr/bin:/bin','PYTHONPATH':f'{SOURCE}/backend:{SOURCE}/staging'}
    common=['/usr/sbin/runuser','-u',ACCOUNT,'--',PYTHON,'-m','uvicorn']
    for name, arguments in [('api',['phase7f_runtime:api_app','--factory','--host','127.0.0.1','--port','18771']),
                            ('gateway',['phase7f_runtime:gateway_app','--factory','--host','127.0.0.1','--port','18770','--ssl-certfile',str(ROOT/'keys/tls.pem'),'--ssl-keyfile',str(ROOT/'keys/tls-key.pem')])]:
        with (ROOT/f'logs/{name}.log').open('ab') as log:
            process = subprocess.Popen(common+arguments,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (ROOT/f'{name}.pid').write_text(str(process.pid)+'\n')
    print('Started isolated staging on loopback ports 18770/18771; verify identity before acceptance')

if __name__ == '__main__': main()
