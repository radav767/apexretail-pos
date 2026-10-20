"""Persist sanitized evidence and the acceptance APK. Never publishes a website."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

SOURCE=Path(__file__).resolve().parents[1]
RUNTIME=Path('/tmp/apexretail-phase7f-runtime')
OUT=Path('/root/apexretail-pos/artifacts/phase7f-acceptance-20261020')

def main():
    if OUT.exists():raise SystemExit('Acceptance package already exists; do not overwrite it')
    if str(SOURCE)!='/tmp/apexpos-phase7f':raise SystemExit('Unexpected source')
    if subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip():raise SystemExit('Uncommitted source changes')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
    result=json.loads((SOURCE/'phase7f-evidence/apk-verification.json').read_text())
    frontend=json.loads((SOURCE/'phase7f-evidence/frontend/frontend-test-results.json').read_text())
    browser=json.loads((SOURCE/'phase7f-evidence/browser/summary.json').read_text())
    if any(row['status']!='PASS' for row in frontend) or browser['failed']:
        raise SystemExit('Automated frontend acceptance gate failed')
    OUT.mkdir(mode=0o700)
    shutil.copytree(SOURCE/'phase7f-evidence',OUT/'evidence')
    shutil.copyfile(SOURCE/'STAGING-ACCEPTANCE.md',OUT/'STAGING-ACCEPTANCE.md')
    apk=OUT/'apexretail-phase7f-acceptance-build6.apk';shutil.copyfile(result['apk'],apk)
    if hashlib.sha256(apk.read_bytes()).hexdigest()!=result['sha256']:raise RuntimeError('APK copy differs')
    backup=json.loads((RUNTIME/'backup-verification.json').read_text())
    shutil.copyfile(backup['backup'],OUT/'synthetic-staging-backup.dump')
    with (OUT/'source.tar').open('wb') as archive:
        subprocess.run(['git','archive','--format=tar',commit],cwd=SOURCE,stdout=archive,check=True)
    for project in ['pos-web','backoffice']:
        shutil.copytree(SOURCE/project/'dist',OUT/'builds'/project)
    reports=SOURCE/'pos-web/android/app/build'
    shutil.copytree(reports/'reports',OUT/'android-reports')
    shutil.copytree(reports/'test-results',OUT/'android-test-results')
    files={str(path.relative_to(OUT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(OUT.rglob('*')) if path.is_file()}
    manifest={'source_commit':commit,'baseline_commit':'390065557b1940e35c528fb407c51b3a3018af31',
        'apk':apk.name,'apk_sha256':result['sha256'],'signer_sha256':result['certificate_sha256'],
        'application_id':result['application_id'],'version_code':6,'version_name':result['version_name'],
        'staging_only':True,'physical_acceptance':'PENDING','production_readiness':'PENDING','files':files}
    (OUT/'release-manifest.json').write_text(json.dumps(manifest,indent=2))
    (OUT/'SHA256SUMS').write_text(''.join(f'{sha}  {path}\n' for path,sha in files.items()))
    for path in OUT.rglob('*'):
        if path.is_file():path.chmod(0o600)
    print(json.dumps({'path':str(OUT),'commit':commit,'apk_sha256':result['sha256'],'files':len(files)}))

if __name__=='__main__':main()
