"""Check staging package, original signer and byte-exact embedded web build."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

SOURCE=Path(__file__).resolve().parents[1]
APK=SOURCE/'pos-web/android/app/build/outputs/apk/acceptance/app-acceptance.apk'
DIST=SOURCE/'pos-web/dist'
EXPECTED_CERT='bb0d2ca7de6baa73009a4694fd1de1946548dc432992ba6443943c54306deb74'
TOOLS='/opt/android-sdk/build-tools/35.0.0/'

def main():
    signing=subprocess.run([TOOLS+'apksigner','verify','--verbose','--print-certs',str(APK)],capture_output=True,text=True,check=True)
    cert=re.search(r'certificate SHA-256 digest: ([0-9a-f]+)',signing.stdout).group(1)
    if cert!=EXPECTED_CERT:raise RuntimeError('Signing certificate changed')
    metadata=subprocess.check_output([TOOLS+'aapt','dump','badging',str(APK)],text=True)
    if "name='cloud.apexpos.pos.staging' versionCode='6' versionName='1.4.0-phase7f-acceptance'" not in metadata:
        raise RuntimeError('Unexpected acceptance APK identity')
    files=[]
    with zipfile.ZipFile(APK) as archive:
        for path in sorted(DIST.rglob('*')):
            if not path.is_file():continue
            relative=path.relative_to(DIST).as_posix();content=path.read_bytes()
            if archive.read('assets/public/'+relative)!=content:raise RuntimeError('Embedded build differs: '+relative)
            if path.suffix in {'.js','.html'}:
                for forbidden in (b'https://api.apexpos.cloud',b'https://backoffice.apexpos.cloud',b'-----BEGIN PRIVATE KEY-----'):
                    if forbidden in content:raise RuntimeError('Unsafe staging asset: '+relative)
            files.append({'path':relative,'sha256':hashlib.sha256(content).hexdigest()})
        scripts=b''.join(path.read_bytes() for path in DIST.rglob('*.js'))
        if b'https://localhost:18770/api' not in scripts or b'phase7f-staging-only' not in scripts:
            raise RuntimeError('Missing staging API/public entitlement key')
    result={'apk':str(APK),'size':APK.stat().st_size,'sha256':hashlib.sha256(APK.read_bytes()).hexdigest(),
        'application_id':'cloud.apexpos.pos.staging','version_code':6,'version_name':'1.4.0-phase7f-acceptance',
        'certificate_sha256':cert,'embedded_assets':files,'production_update':False,
        'physical_install_test':'PENDING','signing_warnings':signing.stderr.splitlines()}
    output=SOURCE/'phase7f-evidence/apk-verification.json';output.write_text(json.dumps(result,indent=2))
    print(json.dumps({key:value for key,value in result.items() if key not in {'embedded_assets','signing_warnings'}}))

if __name__=='__main__':main()
