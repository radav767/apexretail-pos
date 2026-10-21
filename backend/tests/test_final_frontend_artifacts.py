"""Synthetic artifact fixtures; no builds, secrets, network or production access."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[2] / 'ops/phase10/verify_frontend_artifacts.py'
spec = importlib.util.spec_from_file_location('frontend_artifacts', path)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


class FrontendArtifacts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='apex-assets-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'assets').mkdir()
        (self.root / 'index.html').write_text('<script src="/assets/index.js"></script>')
        (self.root / 'assets/index.js').write_text(module.API + ' admin.apexpos.cloud /platform/login /platform/mfa apex_platform_session_v1')

    def test_root_build_and_platform_entry(self):
        result = module.inspect(self.root, platform=True)
        self.assertEqual(len(result['files']), 2)
        self.assertTrue(result['root_hosted_assets_valid'])

    def test_nested_base_missing_asset_and_staging_configuration_rejected(self):
        (self.root / 'index.html').write_text('<script src="/backoffice/assets/index.js"></script>')
        with self.assertRaises(ValueError): module.inspect(self.root)
        (self.root / 'index.html').write_text('<script src="/assets/index.js"></script>')
        (self.root / 'assets/index.js').write_text(module.API + ' https://localhost:18770/api')
        with self.assertRaises(ValueError): module.inspect(self.root)

    def test_linked_and_private_artifacts_rejected(self):
        (self.root / 'unexpected').symlink_to(self.root / 'assets/index.js')
        with self.assertRaises(ValueError): module.inspect(self.root)
        (self.root / 'unexpected').unlink()
        (self.root / '.env.production').write_text('SYNTHETIC=not_a_secret')
        with self.assertRaises(ValueError): module.inspect(self.root)

    def test_public_keyring_must_match_embedded_public_material(self):
        keyring = self.root.parent / (self.root.name + '-public.json')
        self.addCleanup(lambda: keyring.unlink(missing_ok=True))
        keyring.write_text(json.dumps({'version': 1, 'keys': [{'kid': 'test-public',
            'public_key_pem': '-----BEGIN PUBLIC KEY-----\nSYNTHETIC_PUBLIC\n-----END PUBLIC KEY-----'}]}))
        with self.assertRaises(ValueError): module.inspect(self.root, public_keyring=keyring)
        with (self.root / 'assets/index.js').open('a') as file:
            file.write(' test-public SYNTHETIC_PUBLIC')
        self.assertTrue(module.inspect(self.root, public_keyring=keyring)['public_keyring_verified'])
