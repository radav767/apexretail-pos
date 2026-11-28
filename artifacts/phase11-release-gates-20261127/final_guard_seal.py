"""Revalidate final symlink-free sealing and current head without touching old evidence."""
import hashlib,json,os,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[2];root=Path('/tmp/apex-phase11-independent-release-5lrb0b7l');py='/tmp/apex-phase11-release-qualified-311/bin/python';env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1'}
r=subprocess.run([py,str(Path(__file__).with_name('prepare_guard_rehearsal.py'))],env=env,capture_output=True,text=True);assert r.returncode==0,r.stderr
planinfo=json.loads(r.stdout);g=Path(planinfo['plan']).parent;out=g/'final-head';out.mkdir(mode=0o700)
with (g/'final-head.log').open('x') as log:r=subprocess.run([py,str(repo/'ops/phase11/release_guard.py'),'--plan',str(g/'plan.json'),'--plan-sha256',planinfo['plan_sha256'],'--clearance',str(g/'clearance.json'),'--output',str(out),'--rehearse'],env=env,stdout=log,stderr=subprocess.STDOUT)
assert r.returncode==0,'Final sealed guard check failed'
r=subprocess.run([py,str(Path(__file__).with_name('check_worker_access.py'))],env=env,capture_output=True,text=True);assert r.returncode==0,r.stderr
print(json.dumps({'final_guard_head_check':True,'sealed_worker_access':True,'plan':str(g/'plan.json'),'plan_sha256':planinfo['plan_sha256']}))
