"""Validate protected recovery config syntax and preserved public evidence pins only.

GPG lists metadata only in a disposable copy of the public keybox. No source GPG invocation, credential output, provider call, upload, decrypt or restore.
"""
import sys,json,hashlib,shutil,subprocess,tempfile,time
from pathlib import Path
repo=Path(__file__).resolve().parents[2];sys.path.insert(0,str(repo/'ops/phase10'))
import backup_proposal as backup
import backup_safety as safety
import backup_drive as drive
report={'read_only':True,'provider_contacted':False}
try:
 config=backup.load_config(Path('/etc/apexretail/backup.json'))
 report['source_config_valid']=True
 report['configured_public_recipient_fingerprint']=config['recipient']
 report['recipient_is_historical_missing_key']=config['recipient']=='4447A285D945ECA6A1F93F4A041047039797F95F'
 home=Path(config['gnupg_home']);report['public_keyring_present']=(home/'pubring.kbx').is_file()
 private=home/'private-keys-v1.d';report['source_private_key_directory_nonempty']=private.is_dir() and any(private.iterdir())
 with tempfile.TemporaryDirectory(prefix='apex-phase11-public-custody-review-') as temp:
  # Copy only public keybox bytes; GPG writes only in this new /tmp context.
  shutil.copy2(home/'pubring.kbx',Path(temp)/'pubring.kbx')
  r=subprocess.run(['/usr/bin/gpg','--no-options','--homedir',temp,'--batch','--no-autostart','--with-colons','--list-keys',config['recipient']],capture_output=True,text=True,timeout=15)
  assert r.returncode==0
  rows=[line.split(':') for line in r.stdout.splitlines()]
  primary=next(row for row in rows if row[0]=='pub');fingerprint=next(row[9] for row in rows if row[0]=='fpr')
  assert fingerprint==config['recipient'] and primary[1] not in ['r','e','d']
  assert not primary[6] or int(primary[6])>time.time()
  assert 'E' in primary[11]
  report['copied_public_keybox_recipient_currently_valid_for_encryption']=True
except Exception as exc:report['source_config_valid']=False;report['source_error_type']=type(exc).__name__
try:
 p=Path('/etc/apexretail/backup-offserver.json');data=safety.read_private_json(p)
 if data.get('provider')=='google-drive':drive.config(p);report['destination_kind']='dedicated-google-drive'
 else:safety.remote_config(p);report['destination_kind']='pinned-sftp'
 report['destination_config_and_protected_credential_syntax_valid']=True
except Exception as exc:report['destination_config_and_protected_credential_syntax_valid']=False;report['destination_error_type']=type(exc).__name__
base=Path('/root/apexretail-pos');pinfile=base/'artifacts/owner-recovery-two-path-closure-20261105/PRESERVED-EVIDENCE-PINS.json';pins=json.loads(pinfile.read_text());report['preserved_evidence_pins']=[]
for name,expected in pins.items():
 path=(base/name).resolve();assert path.is_relative_to(base) and path.is_file()
 if isinstance(expected,dict):expected=expected['sha256']
 assert isinstance(expected,str) and len(expected)==64
 report['preserved_evidence_pins'].append({'path':name,'sha256_matches':hashlib.sha256(path.read_bytes()).hexdigest()==expected})
source=base/'artifacts/current-production-recovery-20261023/source-20261023T090647Z'
manifest=json.loads((source/'encrypted-package/snapshot-manifest.json').read_text())
result=json.loads((source/'SOURCE-RESULT.json').read_text())
report['historical_configured_recipient_capture']={'manifest_sha256':hashlib.sha256((source/'encrypted-package/snapshot-manifest.json').read_bytes()).hexdigest(),'same_configured_recipient':manifest['recipient']==config['recipient'],'shared_snapshot_claim':manifest['snapshot_shared'],'restore_verified':manifest['restore_verified'],'dump_ciphertext_hash_matches':hashlib.sha256((source/'encrypted-package/apexretail_pos.dump.gpg').read_bytes()).hexdigest()==manifest['ciphertext_sha256'],'baseline_ciphertext_hash_matches':hashlib.sha256((source/'encrypted-package/snapshot-baseline.json.gpg').read_bytes()).hexdigest()==manifest['baseline_ciphertext_sha256'],'source_pipeline_exit_codes':{k:v for k,v in result['exit_results'].items() if isinstance(v,int)},'current_release_restore_proof':False}
print(json.dumps(report,indent=2))
