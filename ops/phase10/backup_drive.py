"""UNINSTALLED Google Drive ciphertext adapter. No OAuth prompting or deletion.

Uses a private, owner-authorized rclone configuration. Child output is never
forwarded: OAuth errors may contain credentials. Scheduling remains gated.
"""
import configparser
import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import backup_safety as safety
import backup_proposal as backup
from backup_proposal import DATABASE, digest_file, private

RCLONE = Path('/usr/bin/rclone')
OWNER = 'prophetdavie@gmail.com'
FOLDER = 'ApexRetail-POS-Secure-Backups'


def config(path):
    data = safety.read_private_json(path)
    if (set(data) != {'provider', 'owner_email', 'folder_name', 'root_folder_id',
                      'rclone_config', 'remote'}
            or data['provider'] != 'google-drive' or data['owner_email'] != OWNER
            or data['folder_name'] != FOLDER or data['remote'] != 'apexretail_drive'
            or not re.fullmatch('[A-Za-z0-9_-]{10,200}', str(data['root_folder_id']))):
        raise ValueError('Approved dedicated Google Drive destination required')
    credential = Path(data['rclone_config'])
    if not credential.is_absolute():
        raise ValueError('Absolute protected credential path required')
    safety.secure_ancestors(credential)
    private(credential.parent, True)
    private(credential)
    ini = configparser.ConfigParser(interpolation=None)
    ini.read_string(credential.read_text())
    if ini.defaults() or ini.sections() != [data['remote']]:
        raise ValueError('One dedicated remote required')
    remote = ini[data['remote']]
    if (set(remote) != {'type', 'scope', 'root_folder_id', 'client_id', 'client_secret', 'token'}
            or remote['type'] != 'drive' or remote['scope'] != 'drive.file'
            or remote['root_folder_id'] != data['root_folder_id']
            or not remote['client_id'].endswith('.apps.googleusercontent.com')
            or not remote['client_secret']):
        raise ValueError('Dedicated narrow-scope OAuth configuration required')
    token = json.loads(remote['token'])
    if (not token.get('access_token') or not token.get('refresh_token')
            or token.get('token_type', '').lower() != 'bearer'
            or token.get('scope', 'https://www.googleapis.com/auth/drive.file')
            not in ('drive.file', 'https://www.googleapis.com/auth/drive.file')):
        raise ValueError('Private renewable narrow-scope OAuth authorization required')
    # Access tokens rotate normally; recipient authorization must be reapproved
    # if the client, refresh credential or destination changes. No token is output.
    binding = json.dumps([remote['client_id'], token['refresh_token'], remote['scope'],
                          data['root_folder_id']], separators=(',', ':')).encode()
    return {**data, 'oauth_binding_sha256': hashlib.sha256(binding).hexdigest()}


def transfer(cfg, source, target):
    info = RCLONE.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError('Root-owned protected rclone installation required')
    command = [str(RCLONE), 'copyto', str(source), str(target),
               '--config', cfg['rclone_config'], '--drive-scope', 'drive.file',
               '--drive-root-folder-id', cfg['root_folder_id'], '--immutable',
               '--retries', '3', '--low-level-retries', '3', '--contimeout', '15s',
               '--timeout', '5m', '--log-level', 'ERROR']
    result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=3600, env={'PATH': '/usr/bin:/bin', 'LANG': 'C',
                                              'HOME': '/nonexistent'})
    if result.returncode:
        raise RuntimeError('Drive transfer failed; private package retained')


def publish(folder, config_path):
    archive, manifest = safety.package(folder)
    if (folder / 'offserver.json').exists():
        raise ValueError('Refusing to replace existing recovery evidence')
    cfg = config(config_path)
    config_hash = digest_file(config_path)
    encryption = backup.load_config(backup.CONFIG)
    if manifest.get('recipient') != encryption['recipient']:
        raise ValueError('Archive recipient differs from approved recovery key')
    backup.verify_public_keyring(encryption['gnupg_home'], encryption['recipient'])
    # Reject renamed plaintext or an unrecognized format before any network call.
    result = subprocess.run(['/usr/bin/gpg', '--homedir', str(encryption['gnupg_home']),
                             '--batch', '--no-options', '--list-only',
                             '--list-packets', str(archive)], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=60,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
    if result.returncode or b':pubkey enc packet:' not in result.stdout or b':encrypted data packet:' not in result.stdout:
        raise ValueError('Public-key encrypted GPG archive required before upload')
    object_id = manifest['ciphertext_sha256'] + '-' + uuid4().hex
    remote = cfg['remote'] + ':' + object_id
    metadata = json.dumps({'database': DATABASE, 'archive': safety.ARCHIVE,
                           'ciphertext_sha256': manifest['ciphertext_sha256'],
                           'bytes': archive.stat().st_size}, sort_keys=True).encode()
    with tempfile.TemporaryDirectory(prefix='apex-drive-readback-', dir=folder.parent) as tmp:
        tmp = Path(tmp)
        meta = tmp / 'manifest.json'
        with meta.open('xb') as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(metadata)
        returned, returned_meta = tmp / 'readback.gpg', tmp / 'readback.json'
        transfer(cfg, archive, remote + '/' + safety.ARCHIVE)
        transfer(cfg, meta, remote + '/manifest.json')  # completion marker last
        transfer(cfg, remote + '/' + safety.ARCHIVE, returned)
        transfer(cfg, remote + '/manifest.json', returned_meta)
        if digest_file(returned) != manifest['ciphertext_sha256'] or returned_meta.read_bytes() != metadata:
            raise RuntimeError('Drive readback mismatch; no success evidence issued')
    after = config(config_path)
    if digest_file(config_path) != config_hash or after['oauth_binding_sha256'] != cfg['oauth_binding_sha256']:
        raise RuntimeError('Drive authorization changed during upload; review required')
    receipt = {'kind': 'offserver-readback-v1', 'provider': 'google-drive', 'database': DATABASE,
               'archive_sha256': manifest['ciphertext_sha256'], 'object_id': object_id,
               'host': 'www.googleapis.com', 'root_folder_id': cfg['root_folder_id'],
               'oauth_binding_sha256': cfg['oauth_binding_sha256'],
               'config_sha256': config_hash, 'verified_at': datetime.now(timezone.utc).isoformat()}
    with (folder / 'offserver.json').open('x') as file:
        os.fchmod(file.fileno(), 0o600)
        json.dump(receipt, file, indent=2)
        file.flush()
        os.fsync(file.fileno())
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Approved one-off ciphertext upload; never activates scheduling')
    parser.add_argument('action', choices=['publish-approved'])
    parser.add_argument('folder', type=Path)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise RuntimeError('Authorized root operation required')
        os.umask(0o077)
        publish(args.folder, args.config)
        print('Encrypted Drive upload and full readback verified; real-key restore and scheduling approval still required.')
    except Exception:
        raise SystemExit('BLOCKED: Drive/configuration/integrity check failed; private archives retained; no activation or pruning')
