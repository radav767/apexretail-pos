"""Download vendor-pinned public standalone Python into a new disposable /tmp root."""
import hashlib,json,tarfile,urllib.request
from pathlib import Path
root=Path('/tmp/apex-phase11-python31118-20261128-attempt2');root.mkdir(mode=0o700,exist_ok=False)
name='cpython-3.11.18+20261124-x86_64-unknown-linux-gnu-install_only.tar.gz'
url='https://github.com/astral-sh/python-build-standalone/releases/download/20261124/'+name.replace('+','%2B')
# Publisher digest from the public GitHub release API, tag20261124.
declared='ef0764e884b5e123692281b91bf388f8ebfd0afb41d6a212bb4f2779e51abf0e'
assert len(declared)==64 and all(c in '0123456789abcdef' for c in declared)
archive=root/name
with urllib.request.urlopen(url,timeout=60) as r,archive.open('xb') as out:
 while chunk:=r.read(1024*1024):out.write(chunk)
actual=hashlib.sha256(archive.read_bytes()).hexdigest();assert actual==declared
with tarfile.open(archive) as tar:
 for member in tar.getmembers():
  target=(root/member.name).resolve();assert target.is_relative_to(root.resolve())
  assert member.isfile() or member.isdir() or member.issym() or member.islnk()
  if member.issym():assert (target.parent/member.linkname).resolve().is_relative_to(root.resolve())
  if member.islnk():assert (root/member.linkname).resolve().is_relative_to(root.resolve())
 tar.extractall(root)
(root/'provenance.json').write_text(json.dumps({'vendor':'astral-sh/python-build-standalone','release':'20261124','url':url,'sha256':actual,'vendor_checksum_matches':True,'scope':'Disposable qualification only; no host/production runtime switch or provenance-attestation claim'},indent=2))
print(json.dumps({'root':str(root),'sha256':actual,'python':'3.11.18','production_modified':False}))
