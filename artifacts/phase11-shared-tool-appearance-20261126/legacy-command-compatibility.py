"""Compare immutable v1 request hashes against the actual prior committed model."""
import ast,json,os,subprocess
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy.engine import make_url
assert os.environ['APP_ENV']=='test'
url=make_url(os.environ['DATABASE_URL']);assert url.host=='127.0.0.1' and url.port==1 and url.database=='phase11_unreachable'
from app.business_settings.preferences import SavePreferences
from app.sales.commands import fingerprint
source=subprocess.check_output(['git','show','d704b4c:backend/app/business_settings/preferences.py'],text=True)
classes=[node for node in ast.parse(source).body if isinstance(node,ast.ClassDef) and node.name in {'Values','SavePreferences'}]
assert len(classes)==2
namespace={'BaseModel':BaseModel,'ConfigDict':ConfigDict,'Field':Field,'Literal':Literal,'UUID':UUID}
exec(compile(ast.Module(body=classes,type_ignores=[]),'frozen-d704b4c-v1-model','exec'),namespace)
checks=[]
for scope in ('company','branch','device'):
 for prefs in ({},{'selector_view':'cards'},{'selector_view':None}):
  values={'company_id':UUID(int=1),'request_id':UUID(int=2),'scope':scope,'version':7,'preferences':prefs,'branch_id':UUID(int=3) if scope!='company' else None,'device_id':UUID(int=4) if scope=='device' else None}
  old,new=namespace['SavePreferences'](**values),SavePreferences(**values)
  assert old.model_dump()==new.model_dump() and fingerprint(old)==fingerprint(new)
  checks.append({'scope':scope,'preferences':prefs,'unchanged_hash':fingerprint(new)})
print(json.dumps({'frozen_commit':'d704b4c','legacy_fingerprint_cases':checks,'database_connected':False},indent=2))
