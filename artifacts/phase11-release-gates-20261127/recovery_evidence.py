"""Read-only bounded recovery evidence review. No key loading/provider operations."""
import hashlib,json,stat
from pathlib import Path
ROOT=Path('/root/apexretail-pos/artifacts')
folders=[ROOT/'owner-offhost-restore-20261105',ROOT/'owner-recovery-two-path-closure-20261105',Path('/etc/apexretail/platform-commissioning-owner'),ROOT/'current-production-recovery-20261023']
allowed={'result','status','classification','state','restore_started','restore_exit_status','restore_verified','key_custody_verified','independent_review_approved','production_actions_authorized','passed','baseline_verified','commissioning_checks_passed','rollback_checks_passed','source_revision','resume_authorized','secret_key_found','public_key_found'}
report={'read_only':True,'evidence':[],'search_scope':[str(p) for p in folders]}
def summaries(value,prefix=''):
 result={}
 if isinstance(value,dict):
  for k,v in value.items():
   path=prefix+'.'+k if prefix else k
   if k in allowed and isinstance(v,(bool,int,type(None))):result[path]=v
   elif k in allowed and isinstance(v,str) and len(v)<180 and all(c.isupper() or c.isdigit() or c in '_-: ' for c in v):result[path]=v
   elif k=='source_revision' and isinstance(v,str) and v.startswith('p10a_'):result[path]=v
   elif isinstance(v,dict):result.update(summaries(v,path))
 return result
for folder in folders:
 for p in sorted(folder.glob('**/*.json')):
  if len(p.relative_to(folder).parts)>4:continue
  info=p.lstat()
  if not stat.S_ISREG(info.st_mode) or p.is_symlink() or info.st_size>1024*1024:continue
  data=p.read_bytes()
  try:value=json.loads(data)
  except ValueError:continue
  report['evidence'].append({'path':str(p),'sha256':hashlib.sha256(data).hexdigest(),'summary':summaries(value),'template_only':'.template.' in p.name})
packages=[]
for folder in [Path('/root/apexretail-pos/backups'),Path('/root/backups')]:
 # Metadata scan only; never open dumps, business exports, environment files or keys.
 count=0
 for p in folder.glob('*/*/*'):
  count+=1
  if count>20000:raise RuntimeError('Inventory resource bound exceeded')
  if p.name in ['offserver.json','restore.json','apexretail_pos.dump.gpg']:packages.append(str(p))
report['bounded_package_paths']=sorted(packages)
report['scheduled_backup_directory_empty']=not any(Path('/root/apexretail-pos/backups/scheduled-production').iterdir())
report['activation_file_present']=Path('/etc/apexretail/backup-activation.json').is_file()
report['config_presence']={p:Path(p).is_file() for p in ['/etc/apexretail/backup.json','/etc/apexretail/backup-offserver.json']}
print(json.dumps(report,indent=2))
