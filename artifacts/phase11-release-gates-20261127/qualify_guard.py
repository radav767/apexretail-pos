"""Single-use new populated qualification DB and sealed CPython3.11 payload."""
import os,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[2];py='/tmp/apex-phase11-release-qualified-311/bin/python';out=Path('/tmp/apex-phase11-independent-release-5lrb0b7l/qualification-logs');out.mkdir(mode=0o700)
env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1','APP_ENV':'test','JWT_SECRET':'synthetic-independent-release-secret-not-production-20261127','DATABASE_URL':'postgresql+asyncpg://postgres@/apex_phase11_release_rich_qualification?host=/tmp/apex-phase11-release-pg-ysjagwtm&port=55443'}
steps=[('baseline',[py,'-m','alembic','upgrade','p10a_platform_management'],repo/'backend'),('seed',[py,str(Path(__file__).with_name('rich_fixture.py')),'seed','--database','apex_phase11_release_rich_qualification'],repo),('payload',[py,str(Path(__file__).with_name('prepare_guard_rehearsal.py'))],repo),('interruption-resume',[py,str(Path(__file__).with_name('exercise_guard.py'))],repo),('controls',[py,str(Path(__file__).with_name('rich_fixture.py')),'controls','--database','apex_phase11_release_rich_qualification'],repo)]
for name,args,cwd in steps:
 with (out/(name+'.log')).open('x') as f:r=subprocess.run(args,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
 assert r.returncode==0,name
 print(name+': passed',flush=True)
