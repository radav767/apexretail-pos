"""Synthetic transport fixtures only. Never contact a real backup server."""
import base64
import hashlib
import json
import shlex
import struct
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

OPS = Path(__file__).resolve().parents[2] / 'ops/phase10'
sys.path.insert(0, str(OPS))
import backup_proposal as backup
import backup_safety as safety
import backup_schedule as schedule

UTC = timezone.utc


def write(path, value):
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    path.chmod(0o600)


class BackupStorage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='apex-backup-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 10, 21, tzinfo=UTC)

    def make_package(self, name='sample', age=90, verified=True):
        folder = self.root / name
        folder.mkdir(mode=0o700)
        archive = b'SYNTHETIC CIPHERTEXT FIXTURE ONLY ' + name.encode()
        digest = hashlib.sha256(archive).hexdigest()
        created = self.now - timedelta(days=age)
        write(folder / safety.ARCHIVE, archive)
        write(folder / 'manifest.json', {'database': 'apexretail_pos', 'encrypted': True,
              'ciphertext_sha256': digest, 'created_at': created.isoformat()})
        if verified:
            common = {'database': 'apexretail_pos', 'archive_sha256': digest,
                      'verified_at': (created + timedelta(minutes=2)).isoformat()}
            write(folder / 'offserver.json', {**common, 'kind': 'offserver-readback-v1',
                  'config_sha256': 'b' * 64, 'host_key_fingerprint': 'SHA256:' + 'A' * 43,
                  'object_id': digest + '-' + '0' * 32, 'host': 'backup.example.invalid'})
            write(folder / 'restore.json', {**common, 'kind': 'isolated-restore-v1',
                  'passed': True, 'baseline_verified': True, 'target_database': 'apexretail_backup_test_123'})
        return folder

    def config(self):
        # Format-valid public test host key; no private key exists for this fixture.
        blob = struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32) + b'\x01' * 32
        fingerprint = 'SHA256:' + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip('=')
        known = self.root / 'known-hosts'
        write(known, b'backup.example.invalid ssh-ed25519 ' + base64.b64encode(blob) + b'\n')
        identity = self.root / 'identity'
        write(identity, b'SYNTHETIC FIXTURE: NOT A PRIVATE KEY; NEVER USED FOR REAL SSH')
        cfg = {'host': 'backup.example.invalid', 'port': 22, 'user': 'backup_upload',
               'remote_root': '/incoming/apexretail', 'identity_file': str(identity),
               'known_hosts_file': str(known), 'host_key_fingerprint': fingerprint}
        file = self.root / 'remote.json'
        write(file, cfg)
        return file, cfg

    def test_config_rejects_placeholder_and_unprotected_identity(self):
        file, cfg = self.config()
        self.assertEqual(safety.remote_config(file)['host'], cfg['host'])
        Path(cfg['identity_file']).chmod(0o644)
        with self.assertRaises(RuntimeError):
            safety.remote_config(file)
        Path(cfg['identity_file']).chmod(0o600)
        for change in ({'host': None}, {'user': 'root'}, {'remote_root': '/'}, {'remote_root': '/../escape'},
                       {'host': '-oBadOption'}, {'host_key_fingerprint': 'SHA256:' + 'A' * 43}):
            write(file, {**cfg, **change})
            with self.subTest(change=change), self.assertRaises((ValueError, RuntimeError)):
                safety.remote_config(file)

    def test_strict_transport_and_successful_full_readback_contract(self):
        folder = self.make_package(verified=False)
        file, cfg = self.config()
        real_run = subprocess.run
        stored, calls = {}, []

        def fake(command, **kwargs):
            if command[0] != '/usr/bin/sftp':
                return real_run(command, **kwargs)
            calls.append(command)
            for line in kwargs['input'].splitlines():
                parts = shlex.split(line)
                action = parts[0]
                if action == 'put':
                    self.assertNotIn(parts[2], stored)
                    stored[parts[2]] = Path(parts[1]).read_bytes()
                elif action == 'rename':
                    self.assertNotIn(parts[2], stored)
                    stored[parts[2]] = stored.pop(parts[1])
                elif action == 'get':
                    Path(parts[2]).write_bytes(stored[parts[1]])
                else:
                    self.assertIn(action, ('mkdir', 'chmod'))
            return SimpleNamespace(returncode=0)

        with patch.object(safety.socket, 'getaddrinfo', return_value=[(0, 0, 0, '', ('8.8.8.8', 22))]), \
             patch.object(safety.subprocess, 'run', side_effect=fake):
            receipt = safety.publish(folder, file)
        self.assertEqual(receipt['archive_sha256'], backup.digest_file(folder / safety.ARCHIVE))
        self.assertTrue((folder / 'offserver.json').exists())
        command = calls[0]
        for option in ('-oStrictHostKeyChecking=yes', '-oBatchMode=yes', '-oIdentityAgent=none',
                       '-oGlobalKnownHostsFile=/dev/null', '-oPasswordAuthentication=no'):
            self.assertIn(option, command)
        self.assertEqual(command[-1], cfg['user'] + '@' + cfg['host'])

    def test_remote_failure_or_wrong_readback_never_creates_success_receipt(self):
        folder = self.make_package(verified=False)
        file, _ = self.config()
        for code in (1, 0):
            def fake(command, **kwargs):
                for line in kwargs['input'].splitlines():
                    parts = shlex.split(line)
                    if parts[0] == 'get':
                        Path(parts[2]).write_bytes(b'WRONG READBACK FIXTURE')
                return SimpleNamespace(returncode=code)
            with patch.object(safety, 'remote_config', return_value=json.loads(file.read_text())), \
                 patch.object(safety.socket, 'getaddrinfo', return_value=[(0, 0, 0, '', ('8.8.8.8', 22))]), \
                 patch.object(safety.subprocess, 'run', side_effect=fake):
                with self.assertRaises(RuntimeError):
                    safety.publish(folder, file)
            self.assertFalse((folder / 'offserver.json').exists())
        self.assertTrue((folder / safety.ARCHIVE).exists())

    def test_local_private_and_production_vps_destinations_refused(self):
        folder = self.make_package(verified=False)
        file, cfg = self.config()
        for address in ('127.0.0.1', '10.0.0.2', '::1', '187.77.179.100'):
            with self.subTest(address=address), patch.object(safety, 'remote_config', return_value=cfg), \
                 patch.object(safety.socket, 'getaddrinfo', return_value=[(0, 0, 0, '', (address, 22))]), \
                 patch.object(safety.subprocess, 'run', side_effect=AssertionError('No transfer permitted')):
                with self.assertRaises(ValueError):
                    safety.publish(folder, file)

    def test_retention_is_non_destructive_and_keeps_two_verified_recent_backups(self):
        for index, age in enumerate((100, 90, 80, 70)):
            self.make_package('backup' + str(index), age)
        self.make_package('unverified', 200, verified=False)
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = safety.retention_plan(self.root, 30, now=self.now)
        self.assertEqual(set(result['eligible_after_separate_approval']), {'backup0', 'backup1'})
        self.assertEqual(result['protected_recent'], ['backup2', 'backup3'])
        self.assertIn('unverified', result['unverified_or_unknown_preserved'])
        self.assertEqual(result['deleted'], [])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_retention_skips_corrupt_foreign_symlink_unknown_and_mismatched_evidence(self):
        for name in ('corrupt', 'foreign', 'unknown', 'mismatch', 'failed', 'wrong_target', 'future'):
            folder = self.make_package(name)
            if name == 'corrupt':
                write(folder / safety.ARCHIVE, b'TAMPERED')
            elif name == 'foreign':
                data = json.loads((folder / 'manifest.json').read_text());data['database'] = 'other'
                write(folder / 'manifest.json', data)
            elif name == 'unknown':
                write(folder / 'unknown.sql', b'PRESERVE UNKNOWN DATA')
            else:
                receipt = folder / 'restore.json'
                data = json.loads(receipt.read_text())
                data.update({'mismatch': {'archive_sha256': '0' * 64}, 'failed': {'passed': False},
                             'wrong_target': {'target_database': 'apexretail_pos'},
                             'future': {'verified_at': (self.now + timedelta(days=1)).isoformat()}}[name])
                write(receipt, data)
        (self.root / 'linked').symlink_to(self.root / 'corrupt', target_is_directory=True)
        result = safety.retention_plan(self.root, 1, now=self.now)
        self.assertEqual(result['eligible_after_separate_approval'], [])
        self.assertEqual(len(result['unverified_or_unknown_preserved']), 8)

    def test_scheduler_refuses_private_key_material(self):
        with patch.object(backup.subprocess, 'run', return_value=SimpleNamespace(stdout='sec:u:TEST_ONLY')):
            with self.assertRaisesRegex(RuntimeError, 'public-key-only'):
                backup.verify_public_keyring('/unused', 'A' * 40)

    def test_scheduler_refuses_unusable_or_mismatched_recipients(self):
        for validity, capability, fingerprint in (('r', 'E', 'A' * 40), ('e', 'E', 'A' * 40),
                                                   ('u', 'S', 'A' * 40), ('u', 'E', 'B' * 40)):
            fields = ['pub', validity, '', '', '', '', '', '', '', '', '', capability]
            listing = ':'.join(fields) + '\nfpr:::::::::' + fingerprint + ':\n'
            with self.subTest(validity=validity, capability=capability), \
                 patch.object(backup.subprocess, 'run', side_effect=[SimpleNamespace(stdout=''), SimpleNamespace(stdout=listing)]):
                with self.assertRaises(RuntimeError):
                    backup.verify_public_keyring('/unused', 'A' * 40)

    def test_streaming_hash_and_retention_policy_guards(self):
        file = self.root / 'fixture';write(file, b'test' * 1024 * 1024)
        self.assertEqual(backup.digest_file(file), hashlib.sha256(file.read_bytes()).hexdigest())
        for days in (0, -1, True):
            with self.assertRaises(ValueError):
                safety.retention_plan(self.root, days)
        with self.assertRaises(ValueError):
            safety.retention_plan(self.root, 30, keep_last=1)

    def test_schedule_requires_bound_real_recovery_evidence_and_owner_approval(self):
        file, cfg = self.config()
        proof = self.make_package('verified-proof')
        data = json.loads((proof / 'manifest.json').read_text());data['recipient'] = 'A' * 40
        write(proof / 'manifest.json', data)
        receipt = json.loads((proof / 'offserver.json').read_text())
        receipt.update(config_sha256=backup.digest_file(file), host=cfg['host'], host_key_fingerprint=cfg['host_key_fingerprint'])
        write(proof / 'offserver.json', receipt)
        home = self.root / 'gpg';home.mkdir(mode=0o700)
        local = self.root / 'backup.json';write(local, {'recipient': 'A' * 40, 'gnupg_home': str(home)})
        approval_file = self.root / 'activation.json'
        good = {'approved_for_schedule': True, 'key_custody_verified': True, 'offserver_storage_approved': True,
                'recipient': 'A' * 40, 'remote_config_sha256': backup.digest_file(file),
                'verified_package': str(proof), 'verified_archive_sha256': data['ciphertext_sha256'],
                'expires_at': (datetime.now(UTC) + timedelta(days=1)).isoformat()}
        with patch.object(backup, 'CONFIG', local), patch.object(schedule, 'REMOTE', file), \
             patch.object(schedule, 'APPROVAL', approval_file), patch.object(backup, 'verify_public_keyring'):
            write(approval_file, good);schedule.preflight()
            for changes in ({'approved_for_schedule': False}, {'key_custody_verified': False},
                            {'offserver_storage_approved': False}, {'recipient': 'B' * 40},
                            {'remote_config_sha256': '0' * 64}, {'verified_archive_sha256': '0' * 64},
                            {'expires_at': (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}):
                write(approval_file, {**good, **changes})
                with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                    schedule.preflight()
            write(approval_file, good)
            receipt['config_sha256'] = '0' * 64;write(proof / 'offserver.json', receipt)
            with self.assertRaises(RuntimeError):
                schedule.preflight()

    def test_unapproved_schedule_stops_before_any_database_dump(self):
        with patch.object(schedule.os, 'geteuid', return_value=0), patch.object(backup, 'DEST', self.root), \
             patch.object(backup, 'private'), patch.object(schedule, 'preflight', side_effect=RuntimeError('not approved')), \
             patch.object(backup, 'run') as dump:
            with self.assertRaises(RuntimeError):
                schedule.run()
            dump.assert_not_called()


if __name__ == '__main__':
    unittest.main()
