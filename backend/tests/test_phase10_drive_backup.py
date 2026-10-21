"""Disposable OAuth fixtures and real ephemeral GPG; no Drive/production calls."""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops/phase10'))
import backup_drive as drive
import backup_proposal as backup
import backup_safety as safety
import backup_schedule as schedule


class DriveBackup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='apex-drive-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.credentials = self.root / 'rclone.conf'
        self.cfgfile = self.root / 'drive.json'
        self.cfg = {'provider': 'google-drive', 'owner_email': drive.OWNER,
                    'folder_name': drive.FOLDER, 'root_folder_id': 'TEST_FOLDER_123456',
                    'remote': 'apexretail-backups', 'rclone_config': str(self.credentials)}
        self.write(self.cfgfile, self.cfg)
        self.credential()

    def write(self, file, data):
        file.write_text(json.dumps(data) if isinstance(data, dict) else data)
        file.chmod(0o600)

    def credential(self, **overrides):
        values = {'type': 'drive', 'scope': 'drive.file', 'root_folder_id': self.cfg['root_folder_id'],
                  'client_id': 'TEST_ONLY.apps.googleusercontent.com', 'client_secret': 'FAKE_NOT_A_SECRET',
                  'token': json.dumps({'access_token': 'FAKE_ACCESS', 'refresh_token': 'FAKE_REFRESH',
                                       'token_type': 'Bearer'})}
        values.update(overrides)
        self.write(self.credentials, '[apexretail-backups]\n' + '\n'.join(f'{k} = {v}' for k, v in values.items()))

    def package(self):
        folder = self.root / 'package'
        folder.mkdir(mode=0o700)
        archive = folder / safety.ARCHIVE
        archive.write_bytes(b'SYNTHETIC ENCRYPTED PACKET FIXTURE')
        archive.chmod(0o600)
        self.write(folder / 'manifest.json', {'database': backup.DATABASE, 'encrypted': True,
                   'ciphertext_sha256': backup.digest_file(archive),
                   'recipient': 'A' * 40,
                   'created_at': (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()})
        return folder

    def test_narrow_config_and_refresh_binding(self):
        first = drive.config(self.cfgfile)['oauth_binding_sha256']
        self.credential(token=json.dumps({'access_token': 'ROTATED_FAKE', 'refresh_token': 'FAKE_REFRESH', 'token_type': 'Bearer'}))
        self.assertEqual(first, drive.config(self.cfgfile)['oauth_binding_sha256'])
        self.credential(token=json.dumps({'access_token': 'FAKE', 'refresh_token': 'DIFFERENT_FAKE', 'token_type': 'Bearer'}))
        self.assertNotEqual(first, drive.config(self.cfgfile)['oauth_binding_sha256'])

    def test_config_rejects_broad_scope_or_wrong_destination(self):
        for changes in ({'scope': 'drive'}, {'scope': 'drive.file,drive'}, {'root_folder_id': 'OTHER_FOLDER'},
                        {'type': 'alias'}, {'skip_gdocs': 'true'}):
            self.credential(**changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                drive.config(self.cfgfile)
        self.credential()
        self.credentials.chmod(0o644)
        with self.assertRaises(RuntimeError):
            drive.config(self.cfgfile)

    def test_transfer_has_no_shell_token_environment_or_delete(self):
        cfg = drive.config(self.cfgfile)
        with patch.object(drive.Path, 'lstat', return_value=SimpleNamespace(st_mode=0o100755, st_uid=0)), \
             patch.object(drive.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            drive.transfer(cfg, '/private/archive.gpg', 'apexretail-backups:unique/archive.gpg')
        args, kwargs = run.call_args
        self.assertEqual(args[0][:2], ['/usr/bin/rclone', 'copyto'])
        self.assertIn('--immutable', args[0])
        self.assertNotIn('FAKE_ACCESS', ' '.join(args[0]))
        self.assertEqual(set(kwargs['env']), {'PATH', 'LANG', 'HOME'})
        self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
        self.assertNotIn('shell', kwargs)

    def fake_transfer(self, corrupt=False, fail=False):
        stored = {}
        def transfer(cfg, source, target):
            if fail:
                raise RuntimeError('simulated transfer failure')
            if str(source).startswith('apexretail-backups:'):
                Path(target).write_bytes(b'CORRUPTED' if corrupt else stored[str(source)])
                Path(target).chmod(0o600)
            else:
                self.assertNotIn(str(target), stored)
                stored[str(target)] = Path(source).read_bytes()
        return transfer

    @contextmanager
    def packets(self, valid=True):
        with patch.object(backup, 'load_config', return_value={'recipient': 'A' * 40, 'gnupg_home': str(self.root)}), \
             patch.object(backup, 'verify_public_keyring'), \
             patch.object(drive.subprocess, 'run', return_value=SimpleNamespace(returncode=0,
                stdout=b':pubkey enc packet:\n:encrypted data packet:' if valid else b'PLAINTEXT')):
            yield

    def test_publish_readback_receipt_and_retention_evidence(self):
        folder = self.package()
        with self.packets(), patch.object(drive, 'transfer', side_effect=self.fake_transfer()):
            receipt = drive.publish(folder, self.cfgfile)
        self.assertEqual(receipt['provider'], 'google-drive')
        self.write(folder / 'restore.json', {'kind': 'isolated-restore-v1', 'database': backup.DATABASE,
                   'archive_sha256': receipt['archive_sha256'], 'verified_at': datetime.now(timezone.utc).isoformat(),
                   'passed': True, 'baseline_verified': True, 'target_database': 'apexretail_backup_test_drive'})
        safety.verified_package(folder, datetime.now(timezone.utc))
        plan = safety.retention_plan(self.root, 30)
        self.assertEqual(plan['deleted'], [])
        with self.assertRaises(ValueError):
            drive.publish(folder, self.cfgfile)

    def test_failure_corruption_and_plaintext_never_issue_receipt(self):
        folder = self.package()
        for kwargs in ({'fail': True}, {'corrupt': True}):
            with self.packets(), patch.object(drive, 'transfer', side_effect=self.fake_transfer(**kwargs)), self.assertRaises(RuntimeError):
                drive.publish(folder, self.cfgfile)
            self.assertFalse((folder / 'offserver.json').exists())
        with self.packets(valid=False), \
             patch.object(drive, 'transfer') as transfer, self.assertRaises(ValueError):
            drive.publish(folder, self.cfgfile)
        transfer.assert_not_called()

    def test_scheduler_requires_real_drive_recovery_bound_to_authorization(self):
        folder = self.package()
        with self.packets(), patch.object(drive, 'transfer', side_effect=self.fake_transfer()):
            receipt = drive.publish(folder, self.cfgfile)
        self.write(folder / 'restore.json', {'kind': 'isolated-restore-v1', 'database': backup.DATABASE,
                   'archive_sha256': receipt['archive_sha256'], 'verified_at': datetime.now(timezone.utc).isoformat(),
                   'passed': True, 'baseline_verified': True, 'target_database': 'apexretail_backup_test_drive'})
        approval = self.root / 'activation.json'
        self.write(approval, {'approved_for_schedule': True, 'key_custody_verified': True,
                   'offserver_storage_approved': True, 'recipient': 'A' * 40,
                   'remote_config_sha256': backup.digest_file(self.cfgfile),
                   'verified_package': str(folder), 'verified_archive_sha256': receipt['archive_sha256'],
                   'expires_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
        with patch.object(schedule, 'REMOTE', self.cfgfile), patch.object(schedule, 'APPROVAL', approval), \
             patch.object(backup, 'load_config', return_value={'recipient': 'A' * 40, 'gnupg_home': str(self.root)}), \
             patch.object(backup, 'verify_public_keyring'):
            schedule.preflight()
            self.credential(token=json.dumps({'access_token': 'FAKE', 'refresh_token': 'CHANGED_FAKE', 'token_type': 'Bearer'}))
            with self.assertRaises(RuntimeError):
                schedule.preflight()

    def test_real_disposable_gpg_roundtrip_and_wrong_key_refusal(self):
        home, public = self.root / 'test-key', self.root / 'public-only'
        home.mkdir(mode=0o700); public.mkdir(mode=0o700)
        command = ['/usr/bin/gpg', '--homedir', str(home), '--batch', '--no-tty']
        try:
            subprocess.run(command + ['--pinentry-mode', 'loopback', '--passphrase', '', '--quick-generate-key',
                'DISPOSABLE BACKUP UNIT TEST ONLY', 'rsa2048', 'encrypt', '1d'], capture_output=True, check=True)
            listing = subprocess.run(command + ['--with-colons', '--list-keys'], capture_output=True, text=True, check=True).stdout
            recipient = next(x.split(':')[9] for x in listing.splitlines() if x.startswith('fpr:'))
            exported = subprocess.run(command + ['--export', recipient], capture_output=True, check=True).stdout
            pubcmd = ['/usr/bin/gpg', '--homedir', str(public), '--batch', '--no-tty']
            subprocess.run(pubcmd + ['--import'], input=exported, capture_output=True, check=True)
            subprocess.run(pubcmd + ['--import-ownertrust'], input=(recipient + ':6:\n').encode(), capture_output=True, check=True)
            backup.verify_public_keyring(public, recipient)
            encrypted = self.root / 'synthetic.gpg'
            content = b'SYNTHETIC NON-PRODUCTION RESTORE FIXTURE'
            subprocess.run(backup.encrypt_command(public, recipient, encrypted), input=content, capture_output=True, check=True)
            no_key = subprocess.run(pubcmd + ['--decrypt', str(encrypted)], capture_output=True)
            self.assertNotEqual(no_key.returncode, 0)
            self.assertEqual(no_key.stdout, b'')
            restored = subprocess.run(command + ['--decrypt', str(encrypted)], capture_output=True, check=True)
            self.assertEqual(restored.stdout, content)
            packet = subprocess.run(['/usr/bin/gpg', '--batch', '--no-options', '--list-only', '--list-packets', str(encrypted)],
                                    capture_output=True, env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'GNUPGHOME': str(public)})
            self.assertEqual(packet.returncode, 0, packet.stderr.decode())
            self.assertIn(b':pubkey enc packet:', packet.stdout)
            self.assertIn(b':encrypted data packet:', packet.stdout)
            damaged = self.root / 'corrupted.gpg'
            data = bytearray(encrypted.read_bytes()); data[-25] ^= 1
            damaged.write_bytes(data)
            self.assertNotEqual(subprocess.run(command + ['--decrypt', str(damaged)], capture_output=True).returncode, 0)
            folder = self.package()
            (folder / safety.ARCHIVE).write_bytes(encrypted.read_bytes())
            manifest = json.loads((folder / 'manifest.json').read_text())
            manifest.update(recipient=recipient, ciphertext_sha256=backup.digest_file(folder / safety.ARCHIVE))
            self.write(folder / 'manifest.json', manifest)
            with patch.object(backup, 'load_config', return_value={'recipient': recipient, 'gnupg_home': str(public)}), \
                 patch.object(drive, 'transfer', side_effect=self.fake_transfer()):
                self.assertEqual(drive.publish(folder, self.cfgfile)['provider'], 'google-drive')
        finally:
            for directory in (home, public):
                subprocess.run(['/usr/bin/gpgconf', '--homedir', str(directory), '--kill', 'gpg-agent'], capture_output=True)


if __name__ == '__main__':
    unittest.main()
