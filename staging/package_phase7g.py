"""Persist Phase 7G acceptance evidence; no web publishing or production access."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

SOURCE=Path(__file__).resolve().parents[1]
RUNTIME=Path('/tmp/apexretail-phase7f-runtime')
OUT=Path('/root/apexretail-pos/artifacts/phase7g-acceptance-20261020')

def main():
    if str(SOURCE)!='/tmp/apexpos-phase7f' or OUT.exists():raise SystemExit('Unexpected source or existing artifact directory')
    if subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip():raise SystemExit('Commit verified source first')
    evidence=SOURCE/'phase7g-evidence'
    frontend=json.loads((evidence/'frontend/frontend-test-results.json').read_text())
    browser=json.loads((evidence/'browser/results.json').read_text())
    api=json.loads((evidence/'shift-api-results.json').read_text())
    apk=json.loads((evidence/'apk-verification.json').read_text())
    if any(r['status']!='PASS' for r in frontend) or any(r['result']!='PASS' for r in browser['checks']+api):raise SystemExit('Acceptance gate failed')
    if apk['version_code']!=7 or apk['application_id']!='cloud.apexpos.pos.staging':raise SystemExit('Wrong APK')
    previous=Path('/root/apexretail-pos/artifacts/phase7f-acceptance-20261020/apexretail-phase7f-acceptance-build6.apk')
    if hashlib.sha256(previous.read_bytes()).hexdigest()!='0e437d4b7fe21949c6046a5e93888501526bbfb0ff07bc171069d41fd3e05e0a':raise SystemExit('Previous artifact changed')
    OUT.mkdir(mode=0o700)
    shutil.copytree(evidence,OUT/'evidence')
    destination=OUT/'apexretail-phase7g-acceptance-build7.apk';shutil.copyfile(apk['apk'],destination)
    if hashlib.sha256(destination.read_bytes()).hexdigest()!=apk['sha256']:raise SystemExit('APK copy mismatch')
    shutil.copyfile(SOURCE/'PHASE7G-ACCEPTANCE.md',OUT/'PHASE7G-ACCEPTANCE.md')
    backup=json.loads((RUNTIME/'backup-verification.json').read_text())
    if not backup['content_preserved']:raise SystemExit('Backup restore failed')
    shutil.copyfile(backup['backup'],OUT/'synthetic-staging-backup.dump')
    shutil.copyfile(SOURCE/'phase7f-evidence/staging-local-ca.pem',OUT/'staging-local-ca.pem')
    for project in ['pos-web','backoffice']:shutil.copytree(SOURCE/project/'dist',OUT/'builds'/project)
    shutil.copytree(SOURCE/'pos-web/android/app/build/reports',OUT/'android-reports')
    shutil.copytree(SOURCE/'pos-web/android/app/build/test-results',OUT/'android-test-results')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
    with (OUT/'source.tar').open('wb') as output:subprocess.run(['git','archive',commit],cwd=SOURCE,stdout=output,check=True)
    files={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob('*')) if p.is_file()}
    manifest={'source_commit':commit,'baseline_commit':'79053396d78a50f24950bd6065a81b772504b5cc','apk':destination.name,
        'apk_sha256':apk['sha256'],'application_id':apk['application_id'],'version_code':7,'version_name':apk['version_name'],
        'certificate_sha256':apk['certificate_sha256'],'physical_testing':'PENDING','production_readiness':'PENDING','files':files}
    (OUT/'release-manifest.json').write_text(json.dumps(manifest,indent=2))
    (OUT/'SHA256SUMS').write_text(''.join(f'{sha}  {path}\n' for path,sha in files.items()))
    for path in OUT.rglob('*'):
        if path.is_file():path.chmod(0o600)
    print(json.dumps({'artifacts':str(OUT),'source_commit':commit,'apk_sha256':apk['sha256'],'files':len(files)}))

if __name__=='__main__':main()
