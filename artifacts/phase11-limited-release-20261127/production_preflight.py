"""Read-only production configuration/schema identity; never prints secrets/business rows."""
from pathlib import Path
import os,json,shlex,re,hashlib
from urllib.parse import urlsplit
unit=Path('/etc/systemd/system/apexpos.service');files=[unit,*sorted(Path(str(unit)+'.d').glob('*.conf'))]
values={};envfiles=[];environment={};seen_keys=set()
for path in files:
 if not path.exists():continue
 section=''
 for raw in path.read_text().splitlines():
  line=raw.strip()
  if line.startswith('['):section=line
  if section!='[Service]' or '=' not in line or line.startswith('#'):continue
  name,value=line.split('=',1)
  if name=='EnvironmentFile':
   if not value:envfiles=[]
   else:envfiles.extend(shlex.split(value))
  elif name=='Environment':
   for assignment in shlex.split(value):
    if '=' in assignment:key,item=assignment.split('=',1);environment[key]=item;seen_keys.add(key)
  elif name in ['WorkingDirectory','User','Group','ExecStart']:values[name]=value
for file in envfiles:
 path=Path(file.lstrip('-'))
 if not path.is_file():continue
 for line in path.read_text().splitlines():
  line=line.strip()
  if not line or line.startswith('#') or '=' not in line:continue
  key,value=line.removeprefix('export ').split('=',1);key=key.strip();value=value.strip()
  if value[:1] in ['"',"'"] and value[-1:]==value[:1]:value=value[1:-1]
  environment[key]=value;seen_keys.add(key)
# The established unit keeps cwd at the original backend and imports runtime
# through --app-dir. Dotenv is read by that runtime without exporting os.environ.
dotenv=Path(values.get('WorkingDirectory','/tmp/not-present'))/'.env'
if dotenv.is_file():
 from dotenv import dotenv_values
 for key,value in dotenv_values(dotenv).items():
  if value is not None:environment.setdefault(key,value)
processes=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  args=(proc/'cmdline').read_bytes().split(b'\0');cwd=str((proc/'cwd').resolve())
  if not any(b'uvicorn' in arg for arg in args) or cwd!=values.get('WorkingDirectory'):continue
  current=dict(part.decode().split('=',1) for part in (proc/'environ').read_bytes().split(b'\0') if b'=' in part)
  environment.update(current);seen_keys.update(current);processes.append({'pid':int(proc.name),'uid':proc.stat().st_uid,'gid':proc.stat().st_gid,'cwd':cwd,'executable':str((proc/'exe').resolve())})
 except (OSError,UnicodeDecodeError):continue
safe_modes={name:environment.get(name,'<unset>') if environment.get(name,'') in ['','production','development','test','disabled','sink'] else '<unexpected value redacted>' for name in ['APP_ENV','SPLIT_CHECKOUT_MODE','QUOTATION_PRICING_MODE','DOCUMENT_DELIVERY_MODE','BUSINESS_EMAIL_MODE']}
report={'read_only':True,'unit_files':[str(path) for path in files if path.exists()],'working_directory':values.get('WorkingDirectory'),'configured_user':values.get('User','root (unit default)'),'configured_group':values.get('Group','unit default'),'environment_files':[{'path':item.lstrip('-'),'exists':Path(item.lstrip('-')).is_file()} for item in envfiles],'processes':processes,'safe_modes':safe_modes,'sensitive_config_present':{name:bool(environment.get(name)) for name in ['DATABASE_URL','JWT_SECRET','ENTITLEMENT_SIGNING_KEY_FILE','ENTITLEMENT_SIGNING_KEY_CREDENTIAL','ENTITLEMENT_PRIVATE_KEY','ENTITLEMENT_PUBLIC_KEY','ENTITLEMENT_PUBLIC_KEYRING_FILE','BUSINESS_EMAIL_KEY','DOCUMENT_DELIVERY_KEY']}}
for name in ['BACKOFFICE_ORIGIN','CORS_ORIGINS']:
 value=environment.get(name)
 if value:
  try:
   host=urlsplit(value);report[name]={'scheme':host.scheme,'hostname':host.hostname,'has_userinfo':bool(host.username),'has_query_or_fragment':bool(host.query or host.fragment)}
  except ValueError:report[name]='unparseable; value withheld'
arguments=shlex.split(values.get('ExecStart',''));runtime_source=arguments[arguments.index('--app-dir')+1] if '--app-dir' in arguments else values.get('WorkingDirectory','/tmp/not-present');report['runtime_source']=runtime_source;report['dotenv_present']=dotenv.is_file();report['jwt_secret_length']=len(environment.get('JWT_SECRET',''));report['jwt_placeholder_like']=any(marker in environment.get('JWT_SECRET','').lower() for marker in ['change-me','changeme','placeholder','development','synthetic'])
working=Path(runtime_source)
if working.is_dir():
 app_files=sorted((working/'app').rglob('*.py'));report['runtime_python_files']=len(app_files);report['runtime_application_manifest_sha256']=hashlib.sha256(''.join(str(p.relative_to(working))+':'+hashlib.sha256(p.read_bytes()).hexdigest()+'\n' for p in app_files).encode()).hexdigest()
 for name in ['requirements-runtime.lock','requirements.txt']:
  path=working/name
  if path.is_file():report[name+'_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
report['nginx_sites']=[]
for path in sorted(Path('/etc/nginx/sites-enabled').iterdir()):
 if not path.is_file():continue
 text=path.read_text();report['nginx_sites'].append({'path':str(path),'resolved_path':str(path.resolve()),'server_names':re.findall(r'^\s*server_name\s+([^;]+);',text,re.M),'roots':re.findall(r'^\s*root\s+([^;]+);',text,re.M),'holding_503':bool(re.search(r'return\s+503',text))})
# Validate only in memory, with no inherited dotenv or error input disclosure.
try:
 import sys
 sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
 from app.core.config import Settings
 supplied={name:environment[name.upper()] for name in Settings.model_fields if name.upper() in environment}
 candidate=Settings(_env_file=None,**supplied)
 report['candidate_settings_valid']=True
 report['candidate_disabled_modes']={name:getattr(candidate,name) for name in ['split_checkout_mode','quotation_pricing_mode','business_email_mode','document_delivery_mode']}
except Exception as exc:
 report['candidate_settings_valid']=False
 report['candidate_settings_error_type']=type(exc).__name__
 report['candidate_settings_errors']='withheld; validator inputs may contain secrets'
try:
 from cryptography.hazmat.primitives import serialization
 private=environment.get('ENTITLEMENT_PRIVATE_KEY')
 if environment.get('ENTITLEMENT_SIGNING_KEY_FILE'):private=Path(environment['ENTITLEMENT_SIGNING_KEY_FILE']).read_text()
 public=environment.get('ENTITLEMENT_PUBLIC_KEY')
 key=serialization.load_pem_private_key(private.replace('\\n','\n').encode(),password=None)
 pub=serialization.load_pem_public_key(public.replace('\\n','\n').encode())
 encode=lambda k:k.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
 report['entitlement_inline_pair_matches']=encode(key.public_key())==encode(pub)
 ring_path=Path(environment['ENTITLEMENT_PUBLIC_KEYRING_FILE']);ring_bytes=ring_path.read_bytes();ring=json.loads(ring_bytes)
 entries=ring.get('keys',[])
 report['entitlement_public_ring_sha256']=hashlib.sha256(ring_bytes).hexdigest()
 report['entitlement_ring_contains_signing_public_key']=any(encode(serialization.load_pem_public_key(entry['public_key_pem'].replace('\\n','\n').encode()))==encode(key.public_key()) for entry in entries)
except Exception as exc:
 report['entitlement_pair_verification_error_type']=type(exc).__name__

try:
 from unittest.mock import patch
 from app.auth.entitlement_keys import load_signing_key,load_public_keyring
 from datetime import datetime,timezone
 with patch.dict(os.environ,environment,clear=True):
  effective_key=serialization.load_pem_private_key(load_signing_key(candidate).encode(),password=None)
  effective_ring=load_public_keyring(candidate)
  active=effective_ring.keys[candidate.entitlement_active_key_id]
  active_public=serialization.load_pem_public_key(active.public_key_pem.encode())
  report['effective_signer_matches_active_ring_key']=encode(effective_key.public_key())==encode(active_public)
  report['effective_signer_source']='systemd credential' if candidate.entitlement_signing_key_credential else 'protected file' if candidate.entitlement_signing_key_file else 'deprecated inline'
  report['active_public_key_deadline_valid']=active.accept_until is None or active.accept_until>datetime.now(timezone.utc)
except Exception as exc:
 report['effective_signer_verification_error_type']=type(exc).__name__

report['schema']={'inspected':False}
try:
 import psycopg2
 from sqlalchemy.engine import make_url
 url=make_url(environment.get('DATABASE_URL',''))
 if url.database!='apexretail_pos':raise ValueError('Unexpected database identity; refusing schema query')
 connection=psycopg2.connect(dbname=url.database,user=url.username,password=url.password,host=url.host or url.query.get('host','/var/run/postgresql'),port=url.port or url.query.get('port',5432),connect_timeout=5,application_name='phase11_limited_readonly_preflight',options='-c default_transaction_read_only=on -c statement_timeout=10000 -c lock_timeout=2000')
 connection.set_session(readonly=True,isolation_level='REPEATABLE READ')
 with connection.cursor() as cursor:
  cursor.execute('SHOW transaction_read_only');assert cursor.fetchone()[0]=='on'
  cursor.execute('SELECT current_database(),current_user,version()');database,user,version=cursor.fetchone()
  cursor.execute('SELECT version_num FROM alembic_version');revisions=[row[0] for row in cursor.fetchall()]
  cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'");tables=cursor.fetchone()[0]
  cursor.execute("SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT t.tgisinternal");triggers=cursor.fetchone()[0]
  report['schema']={'inspected':True,'transaction_read_only':True,'database':database,'role':user,'version':version.split(',')[0],'revisions':revisions,'tables':tables,'user_triggers':triggers}
 connection.rollback();connection.close()
except Exception as exc:report['schema']={'inspected':False,'error_type':type(exc).__name__,'details':'withheld; no secret/error DSN output'}
print(json.dumps(report,indent=2))
