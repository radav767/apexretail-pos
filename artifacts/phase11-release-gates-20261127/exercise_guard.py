"""Synthetic interrupted migration and forward-resume driver; never production."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
root=Path('/tmp/apex-phase11-independent-release-5lrb0b7l');guard=Path((root/'latest-guard.txt').read_text());repo=Path(__file__).resolve().parents[2]
plan=json.loads((guard/'plan.json').read_text());env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1'}
assert plan['database']=='apex_phase11_release_rich_qualification' and plan['port']==55443
for name,extra,expected in [('interrupted',['--interrupt-after','5'],75),('resumed',[],0)]:
 out=guard/name;out.mkdir(mode=0o700)
 args=['/tmp/apex-phase11-release-qualified-311/bin/python',str(repo/'ops/phase11/release_guard.py'),'--plan',str(guard/'plan.json'),'--plan-sha256',hashlib.sha256((guard/'plan.json').read_bytes()).hexdigest(),'--clearance',str(guard/'clearance.json'),'--output',str(out),'--rehearse',*extra]
 with (guard/(name+'.log')).open('x') as log:result=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT)
 assert result.returncode==expected,(name,result.returncode)
 print(name+': expected exit '+str(expected),flush=True)
