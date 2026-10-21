"""Proposed renewal hook tested only with temporary fake commands; no live reload."""
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / 'ops/letsencrypt/admin-renewal-hook.sh.example'


class CertificateHook(unittest.TestCase):
    def check(self, lineage, nginx_status):
        with tempfile.TemporaryDirectory(prefix='apex-admin-hook-test-') as folder:
            root = Path(folder)
            log = root / 'calls'
            nginx, systemctl = root / 'fake-nginx', root / 'fake-systemctl'
            nginx.write_text(f'#!/bin/sh\nprintf "nginx-test\\n" >> "{log}"\nexit {nginx_status}\n')
            systemctl.write_text(f'#!/bin/sh\nprintf "systemctl:$*\\n" >> "{log}"\n')
            for command in (nginx, systemctl):
                command.chmod(0o700)
            script = root / 'hook.sh'
            script.write_text(HOOK.read_text().replace('/usr/sbin/nginx', str(nginx)).replace('/usr/bin/systemctl', str(systemctl)))
            env = {'PATH': '/usr/bin:/bin'}
            if lineage is not None:
                env['RENEWED_LINEAGE'] = lineage
            result = subprocess.run(['/bin/sh', str(script)], env=env, capture_output=True)
            return result.returncode, log.read_text().splitlines() if log.exists() else []

    def test_other_or_missing_lineage_never_calls_services(self):
        for lineage in (None, '/etc/letsencrypt/live/api.apexpos.cloud', '/tmp/unapproved'):
            with self.subTest(lineage=lineage):
                self.assertEqual(self.check(lineage, 0), (0, []))

    def test_validation_failure_prevents_reload(self):
        self.assertEqual(self.check('/etc/letsencrypt/live/admin.apexpos.cloud', 1), (1, ['nginx-test']))

    def test_only_successful_admin_validation_allows_graceful_reload(self):
        self.assertEqual(self.check('/etc/letsencrypt/live/admin.apexpos.cloud', 0),
                         (0, ['nginx-test', 'systemctl:reload nginx']))
