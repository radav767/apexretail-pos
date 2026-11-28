"""Send only public pinned Python package names/versions to the public OSV API."""
import json,re,urllib.request
from pathlib import Path
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[2]/'backend';packages={}
def read(p):
 for raw in p.read_text().splitlines():
  line=raw.strip()
  if line.startswith('-r '):read(p.parent/line[3:].strip())
  elif line and not line.startswith('#'):
   match=re.fullmatch(r'([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^ ;]+)',line)
   if not match:raise ValueError('Unpinned requirement')
   packages[match[1].lower().replace('_','-')]=match[2]
read(root/'requirements-documents.lock')
queries=[{'package':{'name':n,'ecosystem':'PyPI'},'version':v} for n,v in sorted(packages.items())]
req=urllib.request.Request('https://api.osv.dev/v1/querybatch',data=json.dumps({'queries':queries}).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=45) as response:results=json.load(response)
assert len(results['results'])==len(queries)
report={'queried_utc':datetime.now(timezone.utc).isoformat(),'source':'https://api.osv.dev/v1/querybatch','scope':'Pinned backend runtime and document profile; no test-only tooling/OS coverage','packages':[],'advisories':{}}
for q,result in zip(queries,results['results']):
 ids=[v['id'] for v in result.get('vulns',[])];report['packages'].append({'name':q['package']['name'],'version':q['version'],'advisory_ids':ids})
 for id in ids:
  if id in report['advisories']:continue
  assert re.fullmatch('[A-Za-z0-9_-]+',id)
  with urllib.request.urlopen('https://api.osv.dev/v1/vulns/'+id,timeout=30) as response:report['advisories'][id]=json.load(response)
print(json.dumps(report,indent=2))
