"""Read-only frontend validation + new local manifest; NEVER publishes assets."""
import argparse
import hashlib
import json
import re
from pathlib import Path

API = 'https://api.apexpos.cloud/api'


def inspect(root, platform=False, public_keyring=None):
    root = Path(root)
    files = sorted(p for p in root.rglob('*') if p.is_file())
    if not files or any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('Complete non-linked frontend build required')
    index = (root / 'index.html').read_text()
    for url in re.findall(r'(?:src|href)="(/[^"]+)"', index):
        if url.startswith('//') or '..' in Path(url).parts or not (root / url.lstrip('/')).is_file():
            raise ValueError('Root-hosted index references an unavailable asset')
    scripts = '\n'.join(p.read_text() for p in files if p.suffix == '.js')
    if API not in scripts or any(x in scripts for x in (
            'https://localhost:18770/api', 'phase7f-staging-only')):
        raise ValueError('Production API/keyring configuration required')
    if platform and not all(x in scripts for x in (
            'admin.apexpos.cloud', '/platform/login', '/platform/mfa', 'apex_platform_session_v1')):
        raise ValueError('Existing separate MFA-protected platform entry missing')
    if public_keyring is not None:
        keyring = json.loads(Path(public_keyring).read_text())
        if keyring.get('version') != 1 or not keyring.get('keys'):
            raise ValueError('Public verification keyring required')
        for key in keyring['keys']:
            pem = key['public_key_pem']
            body = [line for line in pem.splitlines() if line and not line.startswith('-----')]
            if ('PRIVATE KEY' in pem or 'BEGIN PUBLIC KEY' not in pem or not body
                    or key['kid'] not in scripts or not all(line in scripts for line in body)):
                raise ValueError('Build does not preserve the supplied public verification keys')
    hashes = {}
    for path in files:
        if path.suffix in ('.env', '.key', '.pem', '.dump', '.sql', '.apk') or path.name.startswith('.env'):
            raise ValueError('Unexpected credential/database/package file in frontend build')
        content = path.read_bytes()
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s*[A-Za-z0-9+/\r\n]{64}', content):
            raise ValueError('Private key material in frontend build')
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(content).hexdigest()
    return {'api': API, 'root_hosted_assets_valid': True, 'platform_entry': platform,
            'public_keyring_verified': public_keyring is not None, 'files': hashes}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pos', type=Path, required=True)
    parser.add_argument('--backoffice', type=Path, required=True)
    parser.add_argument('--public-keyring', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.source_commit):
        raise ValueError('Exact source commit required')
    report = {'source_commit': args.source_commit, 'published': False,
              'pos': inspect(args.pos, public_keyring=args.public_keyring),
              'backoffice': inspect(args.backoffice, platform=True)}
    with args.output.open('x') as file:
        json.dump(report, file, indent=2)
    print('PASS: root assets, production API, existing public keys and separate Platform entry; not deployed')


if __name__ == '__main__':
    main()
