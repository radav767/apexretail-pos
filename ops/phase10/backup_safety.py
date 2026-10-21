"""UNINSTALLED off-server publishing and non-destructive retention planning.

Only ciphertext is transferred; credentials are read by SSH, never by this tool.
No scheduler changes, key generation, remote deletion or local pruning exist.
"""
import argparse
import ipaddress
import json
import os
import re
import socket
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from backup_proposal import DATABASE, digest_file, private

ARCHIVE = 'apexretail_pos.dump.gpg'
KNOWN_FILES = {ARCHIVE, 'manifest.json', 'SHA256SUMS', 'dump-error.log',
               'encryption-error.log', 'offserver.json', 'restore.json'}


def read_private_json(path):
    secure_ancestors(path)
    private(path.parent, True)
    private(path)
    return json.loads(path.read_text())


def secure_ancestors(path):
    for parent in path.absolute().parents:
        info = parent.lstat()
        if parent == Path('/tmp') and info.st_uid == 0 and info.st_mode & 0o1000:
            continue  # root sticky /tmp cannot replace our owned test directory
        if parent.is_symlink() or info.st_uid not in (0, os.geteuid()) or info.st_mode & 0o022:
            raise ValueError('Untrusted writable path ancestor')


def instant(value):
    value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        raise ValueError('Timezone-aware evidence required')
    return value.astimezone(timezone.utc)


def package(folder):
    secure_ancestors(folder)
    private(folder, True)
    if any(p.name not in KNOWN_FILES or p.is_symlink() for p in folder.iterdir()):
        raise ValueError('Unexpected or linked package contents')
    for child in folder.iterdir():
        private(child)
    archive = folder / ARCHIVE
    private(archive)
    manifest = read_private_json(folder / 'manifest.json')
    if (manifest.get('database') != DATABASE or manifest.get('encrypted') is not True
            or not re.fullmatch('[a-f0-9]{64}', str(manifest.get('ciphertext_sha256', '')))
            or digest_file(archive) != manifest['ciphertext_sha256']):
        raise ValueError('Encrypted package integrity check failed')
    return archive, manifest


def remote_config(path):
    data = read_private_json(path)
    expected = {'host', 'port', 'user', 'remote_root', 'identity_file',
                'known_hosts_file', 'host_key_fingerprint'}
    if set(data) != expected:
        raise ValueError('Unexpected remote configuration')
    if (not isinstance(data['host'], str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9.-]{0,252}', data['host'])
            or not isinstance(data['user'], str) or data['user'] == 'root' or not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', data['user'])
            or type(data['port']) is not int or not 1 <= data['port'] <= 65535
            or not isinstance(data['remote_root'], str) or not re.fullmatch('/[A-Za-z0-9/_-]+', data['remote_root'])
            or data['remote_root'].startswith('//') or not data['remote_root'].strip('/')
            or '..' in Path(data['remote_root']).parts
            or not re.fullmatch('SHA256:[A-Za-z0-9+/]{43}', str(data['host_key_fingerprint']))):
        raise ValueError('Approved off-server destination and pinned host key required')
    for key in ('identity_file', 'known_hosts_file'):
        file = Path(data[key])
        if not file.is_absolute():
            raise ValueError('Absolute protected SSH paths required')
        secure_ancestors(file)
        private(file.parent, True)
        private(file)
    # A dedicated one-entry known_hosts file, not an ambient trust database.
    host = data['host'] if data['port'] == 22 else f"[{data['host']}]:{data['port']}"
    entries = Path(data['known_hosts_file']).read_text().splitlines()
    if len(entries) != 1 or len(entries[0].split()) != 3 or entries[0].split()[0] != host:
        raise ValueError('Dedicated exact-host known_hosts entry required')
    result = subprocess.run(['/usr/bin/ssh-keygen', '-lf', data['known_hosts_file'], '-E', 'sha256'],
                            capture_output=True, text=True, check=True, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
    fields = result.stdout.split()
    if len(fields) < 2 or fields[1] != data['host_key_fingerprint']:
        raise ValueError('Pinned SSH host identity mismatch')
    return data


def sftp_command(config):
    return ['/usr/bin/sftp', '-F', '/dev/null', '-b', '-', '-P', str(config['port']),
            '-i', config['identity_file'], '-oBatchMode=yes', '-oStrictHostKeyChecking=yes',
            '-oUserKnownHostsFile=' + config['known_hosts_file'], '-oGlobalKnownHostsFile=/dev/null',
            '-oIdentitiesOnly=yes', '-oIdentityAgent=none', '-oForwardAgent=no',
            '-oPasswordAuthentication=no', '-oKbdInteractiveAuthentication=no',
            '-oConnectTimeout=15', '-oServerAliveInterval=15', '-oServerAliveCountMax=3',
            '-oControlMaster=no', '-oControlPath=none', '-oClearAllForwardings=yes',
            '-oLogLevel=ERROR', config['user'] + '@' + config['host']]


def quote(value):
    value = str(value)
    if any(c in value for c in '\n\r\x00'):
        raise ValueError('Invalid transfer path')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def publish(folder, config_path):
    archive, manifest = package(folder)
    if (folder / 'offserver.json').exists():
        raise ValueError('Verified transfer evidence already exists; refusing overwrite')
    config = remote_config(config_path)
    # Refuse loopback/private targets and the known production VPS itself. DNS
    # is not the trust anchor: SSH still requires the independently pinned key.
    addresses = {row[4][0] for row in socket.getaddrinfo(config['host'], config['port'], type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global or ip == '187.77.179.100' for ip in addresses):
        raise ValueError('A separate approved off-server endpoint is required')
    object_id = manifest['ciphertext_sha256'] + '-' + uuid4().hex
    remote = config['remote_root'].rstrip('/') + '/' + object_id
    metadata = json.dumps({'database': DATABASE, 'archive': ARCHIVE,
                           'ciphertext_sha256': manifest['ciphertext_sha256'],
                           'bytes': archive.stat().st_size}, sort_keys=True).encode()
    # A unique destination for every attempt avoids overwriting remote history.
    # No remote shell, delete, retention or credential-bearing URL is used.
    with tempfile.TemporaryDirectory(prefix='apex-backup-readback-', dir=folder.parent) as temp:
        temp = Path(temp)
        meta = temp / 'manifest.json'
        with meta.open('xb') as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(metadata)
        returned, returned_meta = temp / 'readback.gpg', temp / 'readback.json'
        commands = [f'mkdir {quote(remote)}', f'chmod 700 {quote(remote)}',
                    f'put {quote(archive)} {quote(remote + "/archive.part")}',
                    f'chmod 600 {quote(remote + "/archive.part")}',
                    f'put {quote(meta)} {quote(remote + "/manifest.part")}',
                    f'chmod 600 {quote(remote + "/manifest.part")}',
                    f'rename {quote(remote + "/archive.part")} {quote(remote + "/" + ARCHIVE)}',
                    f'rename {quote(remote + "/manifest.part")} {quote(remote + "/manifest.json")}',
                    f'get {quote(remote + "/" + ARCHIVE)} {quote(returned)}',
                    f'get {quote(remote + "/manifest.json")} {quote(returned_meta)}']
        result = subprocess.run(sftp_command(config), input='\n'.join(commands) + '\n',
                                capture_output=True, text=True, timeout=3600,
                                env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
        if result.returncode or not returned.exists() or not returned_meta.exists():
            raise RuntimeError('Off-server transfer/readback failed; no success evidence issued')
        if digest_file(returned) != manifest['ciphertext_sha256'] or returned_meta.read_bytes() != metadata:
            raise RuntimeError('Off-server readback integrity mismatch; no success evidence issued')
    receipt = {'kind': 'offserver-readback-v1', 'database': DATABASE,
               'archive_sha256': manifest['ciphertext_sha256'], 'object_id': object_id,
               'host': config['host'], 'host_key_fingerprint': config['host_key_fingerprint'],
               'config_sha256': digest_file(config_path), 'verified_at': datetime.now(timezone.utc).isoformat()}
    with (folder / 'offserver.json').open('x') as file:
        os.fchmod(file.fileno(), 0o600)
        json.dump(receipt, file, indent=2)
    return receipt


def verified_package(folder, now):
    _, data = package(folder)
    created = instant(data['created_at'])
    if created > now:
        raise ValueError('Future backup timestamp')
    remote = read_private_json(folder / 'offserver.json')
    restore = read_private_json(folder / 'restore.json')
    for receipt, kind in ((remote, 'offserver-readback-v1'), (restore, 'isolated-restore-v1')):
        if (receipt.get('kind') != kind or receipt.get('database') != DATABASE
                or receipt.get('archive_sha256') != data['ciphertext_sha256']
                or not created <= instant(receipt['verified_at']) <= now):
            raise ValueError('Missing or mismatched verification evidence')
    if (not re.fullmatch('[a-f0-9]{64}', str(remote.get('config_sha256', '')))
            or not re.fullmatch('SHA256:[A-Za-z0-9+/]{43}', str(remote.get('host_key_fingerprint', '')))
            or not re.fullmatch(data['ciphertext_sha256'] + '-[a-f0-9]{32}', str(remote.get('object_id', '')))
            or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9.-]{0,252}', str(remote.get('host', '')))):
        raise ValueError('Complete pinned-host readback evidence required')
    if (restore.get('passed') is not True or restore.get('baseline_verified') is not True
            or not re.fullmatch('apexretail_(?:backup|phase10)_[a-z0-9_]+', str(restore.get('target_database')))):
        raise ValueError('Successful isolated full restore required')
    return created, data, remote


def retention_plan(root, keep_days, keep_last=2, now=None):
    """Read-only eligibility plan; never moves or deletes anything."""
    private(root, True)
    if type(keep_days) is not int or not 1 <= keep_days <= 36500 or type(keep_last) is not int or keep_last < 2:
        raise ValueError('Explicit retention policy and at least two recent backups required')
    now = now or datetime.now(timezone.utc)
    verified, skipped = [], []
    for folder in sorted(root.iterdir()):
        try:
            created, _, _ = verified_package(folder, now)
            verified.append((created, folder.name))
        except (ValueError, RuntimeError, OSError, KeyError, TypeError):
            skipped.append(folder.name)
    verified.sort(reverse=True)
    retained = {name for _, name in verified[:keep_last]}
    eligible = [name for created, name in verified if name not in retained and created < now - timedelta(days=keep_days)]
    return {'mode': 'plan-only-preserve-all', 'eligible_after_separate_approval': eligible,
            'protected_recent': sorted(retained), 'unverified_or_unknown_preserved': skipped,
            'deleted': [], 'remote_deletion_supported': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    upload = sub.add_parser('publish-approved')
    upload.add_argument('folder', type=Path)
    upload.add_argument('--config', type=Path, required=True)
    plan = sub.add_parser('retention-plan')
    plan.add_argument('root', type=Path)
    plan.add_argument('--keep-days', type=int, required=True)
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise RuntimeError('Authorized root operation required')
        os.umask(0o077)
        if args.action == 'publish-approved':
            publish(args.folder, args.config)
            print('Ciphertext upload and full off-server readback verified.')
        else:
            print(json.dumps(retention_plan(args.root, args.keep_days), indent=2))
    except Exception:
        # Do not echo remote/client/config details or child output into logs.
        raise SystemExit('BLOCKED: backup verification failed; no pruning or activation performed')
