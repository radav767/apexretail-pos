import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops/phase10'))
import backup_monitor as monitor


class BackupMonitor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='apex-monitor-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 10, 21, tzinfo=timezone.utc)

    def write(self, file, value):
        file.write_text(json.dumps(value)); file.chmod(0o600)

    def package(self, hours=1, restored=True):
        folder = self.root / ('fixture-' + str(hours)); folder.mkdir(mode=0o700)
        archive = folder / 'apexretail_pos.dump.gpg'; archive.write_bytes(b'SYNTHETIC CIPHERTEXT ONLY'); archive.chmod(0o600)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        date = (self.now - timedelta(hours=hours)).isoformat()
        self.write(folder / 'manifest.json', {'database': 'apexretail_pos', 'encrypted': True,
                   'ciphertext_sha256': digest, 'created_at': date})
        self.write(folder / 'offserver.json', {'kind': 'offserver-readback-v1', 'provider': 'google-drive',
                   'database': 'apexretail_pos', 'archive_sha256': digest, 'verified_at': date,
                   'config_sha256': 'a' * 64, 'object_id': digest + '-' + 'b' * 32,
                   'host': 'www.googleapis.com', 'root_folder_id': 'TEST_FOLDER_123456',
                   'oauth_binding_sha256': 'c' * 64})
        if restored:
            self.write(folder / 'restore.json', {'kind': 'isolated-restore-v1', 'database': 'apexretail_pos',
                       'archive_sha256': digest, 'verified_at': date, 'passed': True,
                       'baseline_verified': True, 'target_database': 'apexretail_backup_test_monitor'})
        return folder

    def test_missing_success_is_critical(self):
        self.assertEqual(monitor.status(self.root, self.now)['status'], 'critical')

    def test_fresh_readback_and_full_restore_are_healthy(self):
        self.package(); result = monitor.status(self.root, self.now)
        self.assertEqual(result['status'], 'healthy'); self.assertFalse(result['monthly_recovery_due'])

    def test_daily_readback_is_not_mistaken_for_recovery(self):
        self.package(restored=False); result = monitor.status(self.root, self.now)
        self.assertEqual(result['status'], 'warning'); self.assertTrue(result['monthly_recovery_due'])

    def test_warning_critical_and_monthly_thresholds(self):
        self.package(27); self.assertEqual(monitor.status(self.root, self.now)['status'], 'warning')
        self.assertEqual(monitor.status(self.root, self.now + timedelta(days=2))['status'], 'critical')
        self.assertTrue(monitor.status(self.root, self.now + timedelta(days=32))['monthly_recovery_due'])

    def test_corrupt_and_future_evidence_cannot_claim_success(self):
        folder = self.package(); (folder / 'apexretail_pos.dump.gpg').write_bytes(b'CORRUPT')
        self.package(-1)
        result = monitor.status(self.root, self.now)
        self.assertEqual(result['status'], 'critical'); self.assertEqual(result['invalid_or_unverified_packages'], 2)
        self.assertEqual(result['deleted'], 0); self.assertEqual(result['network_requests'], 0)
