"""UNINSTALLED approval-gated encrypted backup + off-server readback coordinator.

Never creates an approval, provisions secrets, enables timers or prunes backups.
"""
import fcntl
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import backup_proposal as backup
import backup_safety as safety

REMOTE = Path('/etc/apexretail/backup-offserver.json')
APPROVAL = Path('/etc/apexretail/backup-activation.json')


def preflight():
    config = backup.load_config(backup.CONFIG)
    remote = safety.remote_config(REMOTE)
    approval = safety.read_private_json(APPROVAL)
    now = datetime.now(timezone.utc)
    if (approval.get('approved_for_schedule') is not True
            or approval.get('key_custody_verified') is not True
            or approval.get('offserver_storage_approved') is not True
            or approval.get('recipient') != config['recipient']
            or approval.get('remote_config_sha256') != backup.digest_file(REMOTE)
            or not now < safety.instant(approval['expires_at']) <= now + timedelta(days=365)):
        raise RuntimeError('Explicit verified owner approval required')
    proof = Path(approval['verified_package'])
    if not proof.is_absolute():
        raise RuntimeError('Absolute protected recovery evidence required')
    _, manifest, receipt = safety.verified_package(proof, now)
    if (manifest.get('recipient') != config['recipient']
            or manifest['ciphertext_sha256'] != approval.get('verified_archive_sha256')
            or receipt['config_sha256'] != backup.digest_file(REMOTE)
            or receipt['host'] != remote['host']
            or receipt['host_key_fingerprint'] != remote['host_key_fingerprint']):
        raise RuntimeError('Actual matching-recipient off-server restore proof required')
    backup.verify_public_keyring(config['gnupg_home'], config['recipient'])


def run():
    if os.geteuid() != 0:
        raise RuntimeError('Authorized root execution required')
    os.umask(0o077)
    backup.private(backup.DEST, True)
    lock_path = backup.DEST / '.backup.lock'
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        backup.private(lock_path)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Custody, configuration and acceptance gates precede a production dump.
        preflight()
        folder = backup.run(announce=False)
        safety.publish(folder, REMOTE)
    print('Encrypted backup and off-server full readback verified; no pruning performed.')


if __name__ == '__main__':
    if sys.argv[1:] != ['--run-approved']:
        raise SystemExit('Requires --run-approved after verified owner activation approval')
    try:
        run()
    except Exception:
        raise SystemExit('BACKUP FAILED: approval/integrity/transfer check failed; private archives retained')
