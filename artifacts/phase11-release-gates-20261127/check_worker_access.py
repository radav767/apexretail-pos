"""Read/import-only OS-worker accessibility check of the sealed synthetic payload."""
import json,subprocess
from pathlib import Path
r=Path('/tmp/apex-phase11-independent-release-5lrb0b7l');g=Path((r/'latest-guard.txt').read_text());plan=json.loads((g/'plan.json').read_text());assert plan['database']=='apex_phase11_release_rich_qualification'
command=['/usr/sbin/runuser','-u','postgres','--','/usr/bin/env','-i','PATH=/usr/local/bin:/usr/bin:/bin','HOME=/tmp','PYTHONDONTWRITEBYTECODE=1',plan['python'],'-c',"import sys,alembic,psycopg2,asyncpg,PIL;assert sys.version_info[:3]==(3,11,18);assert PIL.__version__=='13.0.0';print('postgres worker imports sealed Python3.11.18 and patched dependencies successfully')"]
result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);assert result.returncode==0,result.stderr
print(result.stdout,end='')
