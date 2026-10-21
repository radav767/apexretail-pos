"""Build UNINSTALLED root-owned bundle in /tmp; never writes /opt or live config."""
import grp,hashlib,io,json,os,subprocess,tarfile,tempfile
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
COMMIT='932557e3abca1a2fa046b2d04d0d6f8c6d4bcc35'

def main():
    if os.geteuid()!=0:raise SystemExit('Authorized root staging required')
    root=Path(tempfile.mkdtemp(prefix='apexretail-phase10-owner-bundle-'))
    archive=subprocess.check_output(['git','archive',COMMIT,'backend'],cwd=REPO)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            name=Path(member.name)
            if name.is_absolute() or '..' in name.parts or name.parts[0]!='backend' or not(member.isfile() or member.isdir()):raise RuntimeError('Unsafe git payload')
            path=root/name
            if member.isdir():path.mkdir(parents=True,exist_ok=True)
            else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(tar.extractfile(member).read())
    (root/'tools').mkdir()
    (root/'tools/prepare_phase10_release.py').write_bytes(subprocess.check_output(['git','show','f52f2826283a183d3d020d0bca12bb80134f3025:backend/scripts/prepare_phase10_release.py'],cwd=REPO))
    (root/'owner_worker.py').write_bytes((REPO/'ops/phase10/owner_worker.py').read_bytes())
    files=sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file())
    manifest=''.join(hashlib.sha256((root/f).read_bytes()).hexdigest()+'  '+f+'\n' for f in files)
    (root/'PAYLOAD.sha256').write_text(manifest)
    pin=hashlib.sha256(manifest.encode()).hexdigest()
    source=(REPO/'ops/phase10/migration_runner.py.in').read_text()
    if source.count('@@PAYLOAD_SHA256@@')!=1:raise RuntimeError('Runner template pin mismatch')
    (root/'migration_runner.py').write_text(source.replace('@@PAYLOAD_SHA256@@',pin))
    gid=grp.getgrnam('postgres').gr_gid
    for p in [*root.rglob('*'),root]:
        os.chown(p,0,gid);p.chmod(0o550 if p.is_dir() else 0o440)
    (root/'migration_runner.py').chmod(0o500)
    result={'bundle':str(root),'runtime_commit':COMMIT,'manifest_sha256':pin,
        'runner_sha256':hashlib.sha256((root/'migration_runner.py').read_bytes()).hexdigest(),
        'installed':False,'production_changed':False}
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
